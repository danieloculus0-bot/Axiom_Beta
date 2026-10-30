"""HTTP boundary regression: identity, permissions, CSRF and audit attribution."""
from __future__ import annotations

import json
import re

import pytest
from werkzeug.security import generate_password_hash


def _setup_shared(monkeypatch, tmp_path):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom-shared"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "shared")
    users = {
        name: {
            "role": role,
            "password_hash": generate_password_hash("test-password", method="pbkdf2:sha256:100000"),
        }
        for name, role in (
            ("boss", "admin"),
            ("inspector", "quality"),
            ("worker", "operations"),
            ("bookkeeper", "finance"),
            ("guest", "viewer"),
        )
    }
    monkeypatch.setenv("AXIOM_USERS_JSON", json.dumps(users))
    from superforge.app import create_app
    return create_app({"TESTING": True})


def _csrf(html):
    token = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert token, "HTML POST form must contain CSRF token"
    return token.group(1)


def _login(client, name):
    page = client.get("/login")
    assert page.status_code == 200
    token = _csrf(page.get_data(as_text=True))
    response = client.post("/login", data={
        "username": name, "password": "test-password", "_csrf_token": token
    })
    assert response.status_code == 302
    return _csrf(client.get("/quality/new").get_data(as_text=True))


def test_local_beta_mode_has_no_extra_request_ip_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "local"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    app = create_app({"TESTING": True})
    client = app.test_client()
    assert client.get("/health", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}).status_code == 200
    # Beta only: no independent request-source restriction is applied.
    # This is a simulated socket address, not proof of network reachability.
    assert client.get("/health", environ_overrides={"REMOTE_ADDR": "192.0.2.50"}).status_code == 200

    # RESTORE WITH THE LOCAL REQUEST-IP GATE BEFORE INTENDED SHARED DEPLOYMENT:
    # assert client.post(
    #     "/jobs", data={"job_number": "SHOULD-NOT-EXIST"},
    #     environ_overrides={"REMOTE_ADDR": "192.0.2.50"}
    # ).status_code == 403
    # from superforge.db import db
    # with db() as con:
    #     assert con.execute(
    #         "SELECT COUNT(*) FROM jobs WHERE job_number='SHOULD-NOT-EXIST'"
    #     ).fetchone()[0] == 0


def test_shared_mode_rejects_missing_users(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "invalid"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "shared")
    monkeypatch.delenv("AXIOM_USERS_JSON", raising=False)
    from superforge.app import create_app
    with pytest.raises(ValueError, match="AXIOM_USERS_JSON"):
        create_app({"TESTING": True})


def test_shared_mode_rejects_unauthenticated_writes_and_bad_login(tmp_path, monkeypatch):
    app = _setup_shared(monkeypatch, tmp_path)
    client = app.test_client()
    assert client.get("/").status_code == 302
    assert client.post("/jobs", data={"job_number": "DENIED"}).status_code == 401
    login_page = client.get("/login")
    token = _csrf(login_page.get_data(as_text=True))
    assert client.post("/login", data={"username": "boss", "password": "test-password"}).status_code == 403
    assert client.post("/login", data={
        "username": "boss", "password": "not-right", "_csrf_token": token,
    }).status_code == 200
    assert client.get("/").status_code == 302


def test_shared_mode_denies_viewer_writes_and_payroll_reads(tmp_path, monkeypatch):
    app = _setup_shared(monkeypatch, tmp_path)
    client = app.test_client()
    csrf = _login(client, "guest")
    assert client.get("/").status_code == 200
    assert client.get("/payroll").status_code == 403
    assert client.get("/reports/export/payroll-runs?format=json").status_code == 403
    assert client.post("/quality/new", data={
        "_csrf_token": csrf, "record_number": "FORGED", "description": "never"
    }).status_code == 403
    assert client.post("/logout", data={"_csrf_token": csrf}).status_code == 302
    assert client.get("/").status_code == 302


def test_quality_write_needs_csrf_and_uses_verified_actor(tmp_path, monkeypatch):
    app = _setup_shared(monkeypatch, tmp_path)
    client = app.test_client()
    token = _login(client, "inspector")
    data = {
        "record_type": "NCR", "record_number": "NCR-SEC-1",
        "description": "synthetic quality fixture", "actor": "boss",
    }
    assert client.post("/quality/new", data=data).status_code == 403
    assert client.post("/quality/new", data={**data, "_csrf_token": "wrong"}).status_code == 403
    good = client.post("/quality/new", data={**data, "_csrf_token": token})
    assert good.status_code == 302
    assert client.post("/jobs", data={"job_number": "BAD", "_csrf_token": token}).status_code == 403
    from superforge.db import db
    from superforge.audit import tail_entries
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM quality_records WHERE record_number='NCR-SEC-1'").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE job_number='BAD'").fetchone()[0] == 0
    qevents = [x for x in tail_entries(100) if x["event_type"] == "QUALITY_MUTATION"]
    assert qevents and qevents[-1]["actor"] == "inspector"


def test_authenticated_json_mutation_requires_header_token(tmp_path, monkeypatch):
    app = _setup_shared(monkeypatch, tmp_path)
    client = app.test_client()
    token = _login(client, "boss")
    assert client.post("/api/favorites", json={"module_key": "quality"}).status_code == 403
    # The endpoint is reachable after CSRF and role checks, whether or not
    # the independently maintained favorite key is valid.
    response = client.post("/api/favorites", json={"module_key": "quality"},
                           headers={"X-CSRF-Token": token})
    assert response.status_code in {200, 400}


def test_shared_mode_is_https_only_outside_tests(tmp_path, monkeypatch):
    app = _setup_shared(monkeypatch, tmp_path)
    app.config["TESTING"] = False
    client = app.test_client()
    assert client.get("/login", base_url="http://localhost").status_code == 403
    assert client.get("/login", base_url="https://localhost").status_code == 200
