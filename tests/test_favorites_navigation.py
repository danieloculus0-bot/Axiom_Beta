"""Actual Axiom favorites: clickable menu entries and persisted tool actions."""
from __future__ import annotations

import pytest


def test_favorites_saved_in_actual_axiom_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app

    app = create_app({"TESTING": True})
    client = app.test_client()
    assert client.get("/api/favorites").get_json() == {"ok": True, "items": []}

    found = client.get("/api/navigation?q=Quality").get_json()
    assert found["ok"]
    assert {"key": "quality", "label": "Quality Forge", "href": "/quality"} in found["items"]
    assert client.get("/api/navigation?q=not-a-registered-module").get_json()["items"] == []

    saved = client.post("/api/favorites", json={"module_key": "quality"})
    assert saved.status_code == 200
    assert saved.get_json() == {
        "ok": True, "saved": True, "created": True,
        "favorite": {"key": "quality", "label": "Quality Forge", "href": "/quality"},
    }
    twice = client.post("/api/favorites", json={"module_key": "quality"}).get_json()
    assert twice["saved"] and not twice["created"]

    menu = client.get("/").get_data(as_text=True)
    assert "Manage favorites" in menu
    assert "★ Quality Forge" in menu
    assert "href='/quality'" in menu
    assert client.get("/favorites").status_code == 200
    assert "data-remove-favorite='quality'" in client.get("/favorites").get_data(as_text=True)

    # Creating a fresh app instance reads the same on-disk state.
    other = create_app({"TESTING": True}).test_client()
    assert other.get("/api/favorites").get_json()["items"] == [
        {"key": "quality", "label": "Quality Forge", "href": "/quality"}
    ]
    assert other.get("/quality").status_code == 200
    removed = other.delete("/api/favorites/quality").get_json()
    assert removed == {"ok": True, "removed": True, "module_key": "quality"}
    assert client.get("/api/favorites").get_json()["items"] == []


def test_rejects_unregistered_or_non_json_navigation_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app

    client = create_app({"TESTING": True}).test_client()
    assert client.post("/api/favorites", data="quality").status_code == 415
    assert client.post("/api/favorites", json={"module_key": "/not-real"}).status_code == 400
    assert client.post("/api/favorites", json={"module_key": "https://malicious.example"}).status_code == 400
    assert client.delete("/api/favorites/no-such-key").status_code == 400
    assert client.get("/api/navigation?q=" + ("x" * 161)).status_code == 400
    assert client.get("/api/favorites").get_json()["items"] == []
