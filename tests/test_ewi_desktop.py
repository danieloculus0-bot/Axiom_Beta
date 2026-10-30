"""Synthetic-only EWI tests. Never depend on real workplace ERP data."""
from __future__ import annotations

import hashlib
import json

import pytest


def build_job(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "appdata"))
    docroot = tmp_path / "released"
    docroot.mkdir()
    monkeypatch.setenv("AXIOM_EWI_DOCUMENT_ROOT", str(docroot))
    monkeypatch.delenv("AXIOM_JB2_CLIENT_ID", raising=False)
    monkeypatch.delenv("AXIOM_JB2_CLIENT_SECRET", raising=False)
    from superforge.app import create_app
    from superforge.db import db
    app = create_app({"TESTING": True})
    pdf = docroot / "approved.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% synthetic document test fixture\n%%EOF\n")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    with db() as con:
        part = con.execute("INSERT INTO parts(part_number,revision) VALUES (?,?)",
                           ("SYN-100", "C")).lastrowid
        job = con.execute(
            "INSERT INTO jobs(job_number,part_id,status) VALUES (?,?,?)",
            ("SYN-WO-100", part, "open")
        ).lastrowid
        con.execute("""INSERT INTO documents
            (document_number,title,revision,document_type,status,part_id,job_id,storage_reference,sha256)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            ("SYN-DWG-100", "Synthetic test drawing", "C", "drawing", "released",
             part, job, "approved.pdf", digest))
    return app, job, pdf


def routes():
    return [{"step": "10", "operation": "CUT", "work_center": "WC-1",
             "instruction": "Cut synthetic sample", "part_number": "SYN-100",
             "external_id": "SYN-ROUTE-1"}]


def test_complete_ewi_flow_is_local_pending_sync(tmp_path, monkeypatch):
    app, job, pdf = build_job(tmp_path, monkeypatch)
    from superforge.modules.ewi import packet, save_remote_routes, clock_start, clock_stop
    from superforge.db import db

    client = app.test_client()
    assert client.get("/ewi").status_code == 200
    assert "SYN-WO-100" in client.get("/ewi").get_data(as_text=True)
    assert packet(job)["ready"] is False
    assert "No JobBOSS" in packet(job)["issues"][0]
    assert save_remote_routes(job, routes()) == 1
    assert packet(job)["ready"] is True
    html = client.get(f"/ewi/jobs/{job}").get_data(as_text=True)
    assert "Cut synthetic sample" in html
    assert "Ready for local clocking" in html
    assert client.get(f"/ewi/jobs/{job}/drawing").data == pdf.read_bytes()
    session = clock_start(job, "10", "TECH-01", "synthetic_test")
    with pytest.raises(ValueError, match="already has"):
        clock_start(job, "10", "TECH-01", "synthetic_test")
    clock_stop(session, "TECH-01", "synthetic_test")
    with pytest.raises(ValueError, match="No matching"):
        clock_stop(session, "TECH-01", "synthetic_test")
    with db() as con:
        rows = con.execute(
            "SELECT event_kind,state,payload_json FROM ewi_outbox ORDER BY created_at,event_kind"
        ).fetchall()
    assert {r["event_kind"] for r in rows} == {"START", "STOP"}
    assert all(r["state"] == "PENDING" for r in rows)
    assert all(json.loads(r["payload_json"])["session_id"] == session for r in rows)


def test_document_tamper_blocks_clock_and_pdf(tmp_path, monkeypatch):
    app, job, pdf = build_job(tmp_path, monkeypatch)
    from superforge.modules.ewi import packet, save_remote_routes, clock_start
    save_remote_routes(job, routes())
    pdf.write_bytes(b"%PDF-1.4\nTampered\n%%EOF")
    assert "checksum mismatch" in " ".join(packet(job)["issues"])
    assert app.test_client().get(f"/ewi/jobs/{job}/drawing").status_code == 409
    with pytest.raises(ValueError, match="blocked"):
        clock_start(job, "10", "TECH-01", "tester")


def test_part_only_release_is_not_job_release(tmp_path, monkeypatch):
    app, job, _ = build_job(tmp_path, monkeypatch)
    from superforge.db import db
    from superforge.modules.ewi import packet, save_remote_routes
    save_remote_routes(job, routes())
    with db() as con:
        con.execute("UPDATE documents SET job_id=NULL WHERE job_id=?", (job,))
    assert packet(job)["ready"] is False
    assert "job-linked" in " ".join(packet(job)["issues"])


def test_route_conflict_does_not_replace_previous_snapshot(tmp_path, monkeypatch):
    app, job, _ = build_job(tmp_path, monkeypatch)
    from superforge.modules.ewi import packet, save_remote_routes
    save_remote_routes(job, routes())
    with pytest.raises(ValueError, match="part number"):
        save_remote_routes(job, [dict(routes()[0], part_number="OTHER-PART")])
    assert packet(job)["ready"] is True
    with pytest.raises(ValueError, match="duplicated"):
        save_remote_routes(job, routes() + routes())
    assert len(packet(job)["routes"]) == 1


def test_sync_disabled_without_credentials(tmp_path, monkeypatch):
    app, job, _ = build_job(tmp_path, monkeypatch)
    response = app.test_client().post(f"/ewi/jobs/{job}/sync", follow_redirects=True)
    assert response.status_code == 200
    assert "not configured" in response.get_data(as_text=True).lower()


def test_api_reader_filters_job_and_never_sends_erp_write(monkeypatch):
    monkeypatch.setenv("AXIOM_JB2_CLIENT_ID", "SYNTHETIC-ID")
    monkeypatch.setenv("AXIOM_JB2_CLIENT_SECRET", "SYNTHETIC-SECRET")
    from superforge.integrations.jobboss2_reader import JobBoss2Reader

    calls = []
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def read(self, *_args):
            return json.dumps(self.payload).encode()

    def transport(request, timeout):
        calls.append((request.get_method(), request.full_url))
        if request.get_method() == "POST":
            return FakeResponse({"access_token": "synthetic-token"})
        return FakeResponse({"data": [
            {"jobNumber": "OTHER", "stepNumber": 1},
            {"jobNumber": "SYN-WO-100", "stepNumber": 10,
             "partNumber": "SYN-100", "description": "Cut"},
        ]})

    result = JobBoss2Reader(transport=transport).routes("SYN-WO-100")
    assert len(result) == 1
    assert result[0]["instruction"] == "Cut"
    assert [x[0] for x in calls] == ["POST", "GET"]
