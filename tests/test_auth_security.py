"""Negative security tests always enforce production authentication rules."""
import json
import re

from werkzeug.security import generate_password_hash

from superforge.app import create_app
from superforge.db import db


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom-auth-db"))
    monkeypatch.setenv("AXIOM_USERS_JSON", json.dumps({
        "alice": {"password_hash": generate_password_hash("test-editor-secret"), "role": "editor"},
        "viewonly": {"password_hash": generate_password_hash("test-view-secret"), "role": "viewer"},
    }))
    return create_app({"TESTING": True, "ENFORCE_SECURITY_IN_TESTS": True})


def _sign_in(client, user, password):
    page = client.get("/login")
    assert page.status_code == 200
    csrf = re.search(r'name="_csrf" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    signed = client.post("/login", data={"username": user, "password": password, "_csrf": csrf})
    assert signed.status_code == 302
    with client.session_transaction() as auth_session:
        return auth_session["_csrf"]


def test_anonymous_request_cannot_mutate_jobs_or_see_dashboard(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    client = app.test_client()
    assert client.post("/jobs", data={"job_number": "FORGED"}).status_code == 401
    assert client.get("/").status_code == 302
    with db() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs WHERE job_number='FORGED'").fetchone()[0] == 0


def test_csrf_and_role_enforced_even_with_authenticated_cookie(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    viewer = app.test_client()
    csrf = _sign_in(viewer, "viewonly", "test-view-secret")
    assert viewer.post("/jobs", data={"job_number": "FORGED", "_csrf": csrf}).status_code == 403

    editor = app.test_client()
    csrf = _sign_in(editor, "alice", "test-editor-secret")
    assert editor.post("/jobs", data={"job_number": "FORGED"}).status_code == 403
    assert editor.post("/payroll/run", data={"_csrf": csrf}).status_code == 403
    assert editor.post("/quality/new", data={"actor": "bob", "_csrf": csrf}).status_code == 403
    with db() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs WHERE job_number='FORGED'").fetchone()[0] == 0


def test_verified_actor_replaces_untrusted_local_form_placeholder(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    client = app.test_client()
    csrf = _sign_in(client, "alice", "test-editor-secret")
    response = client.post("/quality/new", data={
        "_csrf": csrf, "actor": "local",
        "record_type": "NCR", "record_number": "AUTH-QA-01",
        "description": "Credential boundary regression", "severity": "low",
    })
    assert response.status_code in (302, 303)
    from superforge.audit import tail_entries
    quality_events = [event for event in tail_entries(limit=100)
                      if event.get("module") == "quality" and event.get("entity_id")]
    assert quality_events and any(event.get("actor") == "alice" for event in quality_events)
