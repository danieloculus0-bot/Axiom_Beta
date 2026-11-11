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


def test_stale_or_unverified_route_revision_blocks_clock_in_not_clock_out(tmp_path, monkeypatch):
    """A new released fictional revision cannot silently reuse old local routing."""
    app, job, _ = build_job(tmp_path, monkeypatch)
    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.ewi import packet, save_remote_routes, clock_start, clock_stop

    assert save_remote_routes(job, routes()) == 1
    assert packet(job)["ready"] is True
    original_session = clock_start(job, "10", "TECH-OLD", "synthetic_test")

    revised_pdf = tmp_path / "released" / "fictional-revision-d.pdf"
    revised_pdf.write_bytes(b"%PDF-1.4\n% entirely fictional revision D\n%%EOF\n")
    revised_hash = hashlib.sha256(revised_pdf.read_bytes()).hexdigest()
    with db() as con:
        con.execute(
            "UPDATE parts SET revision='D' WHERE id=(SELECT part_id FROM jobs WHERE id=?)",
            (job,),
        )
        con.execute(
            """UPDATE documents SET revision='D',storage_reference=?,sha256=?
               WHERE job_id=?""",
            ("fictional-revision-d.pdf", revised_hash, job),
        )
        before = (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )
        assert con.execute(
            "SELECT local_part_revision_at_pull FROM ewi_routes WHERE job_id=?",
            (job,),
        ).fetchone()[0] == "C"

    # The replacement drawing is locally valid; the ROUTE is stale.
    stale = packet(job)
    assert stale["ready"] is False
    assert any("routing revision stale" in issue for issue in stale["issues"])
    assert app.test_client().get(f"/ewi/jobs/{job}").status_code == 200
    with pytest.raises(ValueError, match="EWI is blocked"):
        clock_start(job, "10", "TECH-NEW", "synthetic_test")
    with db() as con:
        assert before == (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )

    # Existing sessions must remain stoppable after a revision change.
    clock_stop(original_session, "TECH-OLD", "synthetic_test")
    with db() as con:
        assert con.execute(
            "SELECT ended_utc FROM ewi_clock_sessions WHERE id=?",
            (original_session,),
        ).fetchone()[0] is not None

    # A fresh local routing pull captures D; no remote revision approval is implied.
    assert save_remote_routes(job, routes()) == 1
    create_app({"TESTING": True})  # application restart preserves snapshot
    assert packet(job)["ready"] is True
    with db() as con:
        assert con.execute(
            "SELECT local_part_revision_at_pull FROM ewi_routes WHERE job_id=?",
            (job,),
        ).fetchone()[0] == "D"
        con.execute(
            "UPDATE ewi_routes SET local_part_revision_at_pull='' WHERE job_id=?",
            (job,),
        )
    legacy = packet(job)
    assert legacy["ready"] is False
    assert any("revision snapshot unverified" in issue for issue in legacy["issues"])
    with pytest.raises(ValueError, match="EWI is blocked"):
        clock_start(job, "10", "TECH-NEW", "synthetic_test")


def test_clock_in_rechecks_route_revision_in_its_sql_write_transaction(tmp_path, monkeypatch):
    """A route revision changed after packet validation cannot start clocking."""
    _, job, _ = build_job(tmp_path, monkeypatch)
    from superforge.db import db
    from superforge.modules import ewi as ewi_module

    assert ewi_module.save_remote_routes(job, routes()) == 1
    original_packet = ewi_module.packet

    def packet_then_route_changes(job_id):
        snapshot = original_packet(job_id)
        assert snapshot["ready"] is True
        # Simulate another writer changing the route after the packet read.
        with db() as con:
            con.execute(
                "UPDATE ewi_routes SET local_part_revision_at_pull='B' WHERE job_id=?",
                (job_id,),
            )
        return snapshot

    monkeypatch.setattr(ewi_module, "packet", packet_then_route_changes)
    with pytest.raises(ValueError, match="routing revision changed before clocking"):
        ewi_module.clock_start(job, "10", "TECH-RACE", "synthetic_test")
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0] == 0
