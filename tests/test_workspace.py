from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from superforge.workspace import SERVICES, probe_service, runtime_snapshot
from workspace_launcher import load_config, plan_modules


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return self.body


def test_nonconflicting_ports_and_loopback_services():
    ports = [5060, *(entry["port"] for entry in SERVICES)]
    assert len(set(ports)) == len(ports)
    assert next(entry for entry in SERVICES if entry["id"] == "forgevault")["port"] == 8766
    assert next(entry for entry in SERVICES if entry["id"] == "ezstimate")["port"] == 8765


def test_service_is_verified_only_if_expected_product_responds():
    service = next(item for item in SERVICES if item["id"] == "ezstimate")
    observed = []

    def open_ok(req, timeout):
        observed.append((req.full_url, timeout))
        return FakeResponse('{"product":"EZstimate","scope":"experimental alpha"}')

    result = probe_service(service, opener=open_ok)
    assert observed == [("http://127.0.0.1:8765/api/status", 0.4)]
    assert result["status"] == "verified_local"
    assert result["url"] == "http://127.0.0.1:8765/"


def test_wrong_service_on_port_is_not_claimed_as_online():
    service = next(item for item in SERVICES if item["id"] == "ezstimate")
    result = probe_service(service, opener=lambda *_a, **_k: FakeResponse("A different web service"))
    assert result["status"] == "reachable_unverified"
    assert result["url"] is None


def test_offline_service_and_snapshot():
    def fail(*_args, **_kwargs):
        raise URLError("refused")

    assert probe_service(SERVICES[0], opener=fail)["status"] == "offline"
    snapshot = runtime_snapshot(opener=fail)
    assert snapshot["core"]["status"] == "running"
    assert all(item["status"] == "offline" for item in snapshot["services"])


def test_config_requires_explicit_enabled_modules(tmp_path):
    configured = tmp_path / "modules"
    configured.mkdir()
    payload = {
        "modules": [
            {"id": "one", "directory": "modules", "command": ["{python}", "-m", "test"],
             "enabled": False, "port": 8765},
        ]
    }
    path = tmp_path / "launch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_config(path)[0]["id"] == "one"
    assert plan_modules(path) == []
    assert plan_modules(path, all_installed=True)[0]["port"] == 8765


def test_launcher_rejects_conflicting_assigned_ports(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    payload = {
        "modules": [
            {"id": "one", "directory": "one", "command": ["python"], "enabled": True, "port": 8765},
            {"id": "two", "directory": "two", "command": ["python"], "enabled": True, "port": 8765},
        ]
    }
    path = tmp_path / "launch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Port conflict"):
        plan_modules(path)


def test_launcher_rejects_bad_commands_and_duplicate_ids(tmp_path):
    path = tmp_path / "launch.json"
    path.write_text(json.dumps({"modules": [
        {"id": "x", "directory": ".", "command": ["python"]},
        {"id": "x", "directory": ".", "command": ["python"]},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="distinct"):
        load_config(path)
    path.write_text(json.dumps({"modules": [
        {"id": "other", "directory": ".", "command": "python"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="command"):
        load_config(path)


def test_workspace_is_mounted_in_axiom_app(monkeypatch):
    from superforge import workspace
    from superforge.app import create_app

    monkeypatch.setattr(workspace, "runtime_snapshot", lambda **_kw: {
        "mode": "local_workstation",
        "core": {"id": "axiom", "status": "running", "url": "/"},
        "services": [{"id": s["id"], "name": s["name"],
                      "description": s["description"], "repository": s["repo"],
                      "status": "offline", "url": None} for s in SERVICES],
    })
    client = create_app({"TESTING": True}).test_client()
    ui = client.get("/workspace")
    assert ui.status_code == 200
    assert b"Engineering suite" in ui.data
    assert b"EZstimate" in ui.data
    api = client.get("/api/workspace/status")
    assert api.status_code == 200
    assert api.get_json()["core"]["status"] == "running"
    assert api.headers["Cache-Control"] == "no-store"
