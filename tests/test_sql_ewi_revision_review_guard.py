"""Synthetic SQL-to-EWI revision-review bridge; no real drawings or ERP data."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace

import pytest

from superforge.db import db
from superforge.event_bus import create_action, publish
from superforge.integrations.service import IntegrationService


def _fictional_aligned_job(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    from superforge.modules.ewi import save_remote_routes

    client = create_app({"TESTING": True}).test_client()
    csv_path = tmp_path / "synthetic_jobs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Job", "PartId", "Op", "Status"])
        writer.writeheader()
        # The part ID is inserted below; write the row after seeding SQL.

    with db() as con:
        part_id = int(con.execute(
            "INSERT INTO parts(part_number,revision) VALUES('SYN-REV-PART-001','A')"
        ).lastrowid)
        job_id = int(con.execute(
            """INSERT INTO jobs(job_number,part_id,status,current_operation)
               VALUES('SYN-REV-WO-001',?,'seed','SYN-OP-10')""",
            (part_id,),
        ).lastrowid)
        plan_id = int(con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,required_date,status)
               VALUES(?,?,'SYN-REV-WO-001','SYN-REV-PART-001','A','2099-01-01','DRAFT')""",
            (job_id, part_id),
        ).lastrowid)
        operation_id = int(con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,10,'SYN-CELL','SYN-OP-10','2099-01-01','Fictional step')""",
            (plan_id,),
        ).lastrowid)
        connection_id = int(con.execute(
            """INSERT INTO erp_connections(name,erp_type,adapter_type,direction,config_json)
               VALUES('SYN-REV-FEED','generic','flatfile','in',?)""",
            (json.dumps({"path": str(csv_path), "external_id_field": "Job"}),),
        ).lastrowid)
        for external, internal, transform in (
            ("Job", "job_number", "strip"),
            ("PartId", "part_id", "int"),
            ("Op", "current_operation", "strip"),
            ("Status", "status", "lower"),
        ):
            con.execute(
                """INSERT INTO erp_mappings
                   (connection_id,entity_type,external_field,internal_field,transform,direction)
                   VALUES(?,'job',?,?,?,'in')""",
                (connection_id, external, internal, transform),
            )

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Job", "PartId", "Op", "Status"])
        writer.writeheader()
        writer.writerow({"Job": "SYN-REV-WO-001", "PartId": part_id,
                         "Op": "SYN-OP-10", "Status": "open"})
    imported = IntegrationService().pull(connection_id, "job", actor="synthetic-bridge")
    assert (imported["applied"], imported["errors"]) == (1, 0), imported

    root = tmp_path / "fictional-controlled-pdfs"
    root.mkdir()
    monkeypatch.setenv("AXIOM_EWI_DOCUMENT_ROOT", str(root))
    pdf = root / "fictional.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% Entirely fictional revision guard fixture\n%%EOF\n")
    with db() as con:
        con.execute(
            """INSERT INTO documents
               (document_number,title,revision,document_type,status,part_id,job_id,storage_reference,sha256)
               VALUES('SYN-REV-DWG-001','Fictional drawing','A','drawing','released',?,?,?,?)""",
            (part_id, job_id, "fictional.pdf", hashlib.sha256(pdf.read_bytes()).hexdigest()),
        )
    assert save_remote_routes(job_id, [{
        "step": "10", "operation": "SYN-OP-10", "part_number": "SYN-REV-PART-001",
        "external_id": "SYN-ROUTE-10",
    }]) == 1
    with db() as con:
        event_id = con.execute(
            """SELECT event_id FROM event_ledger
               WHERE event_type='job.changed' AND entity_type='job' AND entity_id=?
               ORDER BY id DESC LIMIT 1""", (str(job_id),),
        ).fetchone()["event_id"]
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event_id,),
        ).fetchone()["status"] == "delivered"
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE event_id=? AND workflow_key='job-change'""", (event_id,),
        ).fetchone()[0] == 1
        assert con.execute(
            """SELECT COUNT(*) FROM event_delivery_receipts
               WHERE event_id=? AND status='delivered'""", (event_id,),
        ).fetchone()[0] >= 2
    return client, job_id, part_id, operation_id, event_id


def _revision_action(job_id, part_id, *, suffix="101"):
    """Simulate PR #106's existing verified-action contract, not its FAI parser."""
    event = publish(
        "fai.imported", source_module="ezfair", entity_type="fai",
        entity_id=suffix, actor="synthetic-bridge",
        payload={"inspection_status": "review_required"},
    )
    action = create_action(
        replace(event, entity_type="job", entity_id=str(job_id)),
        workflow_key="controlled-drawing-ewi-review",
        step_key="review-job-packet-fai-" + suffix,
        target_module="ewi",
        input_data={
            "contract_version": 1, "job_id": job_id, "part_id": part_id,
            "source_event_id": event.event_id, "fai_run_id": int(suffix),
            "previous_revision": "A", "new_revision": "B",
            "provenance": "EZ_FAIR_IMPORTED_CONTROLLED_DRAWING",
            "review_state": "REVIEW_REQUIRED",
        },
    )
    return event, action


def _counts():
    with db() as con:
        return tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("event_ledger", "event_delivery_receipts",
                                   "workflow_actions", "module_suggestions"))


def test_open_fai_revision_review_suppresses_ewi_alignment_until_review(tmp_path, monkeypatch):
    from superforge.app import create_app
    client, job_id, part_id, operation_id, event_id = _fictional_aligned_job(tmp_path, monkeypatch)
    url = f"/api/v1/jobs/{job_id}/ewi-operation-alignment/{event_id}"

    before = client.get(url).get_json()
    assert before["status"] == "cross_source_candidate_review_required", before
    assert before["method_operation_id"] == operation_id
    event, action_id = _revision_action(job_id, part_id)
    with db() as con:
        row = con.execute(
            """SELECT a.status,a.entity_type,a.entity_id,e.event_type,e.source_module
               FROM workflow_actions a JOIN event_ledger e ON e.event_id=a.event_id
               WHERE a.id=?""", (action_id,),
        ).fetchone()
        assert tuple(row) == ("open", "job", str(job_id), "fai.imported", "ezfair")

    counts = _counts()
    blocked = client.get(url).get_json()
    assert blocked["status"] == "controlled_revision_review_pending", blocked
    assert blocked["revision_review_action_id"] == action_id
    assert blocked["revision_review_source_event_id"] == event.event_id
    assert blocked["method_operation_id"] is None
    assert blocked["ewi_step"] is None and blocked["drawing_document_id"] is None
    html = client.get(f"/ewi/jobs/{job_id}").get_data(as_text=True)
    assert "controlled_revision_review_pending" in html
    assert "Local EWI step 10 and checksum-verified drawing" not in html
    assert _counts() == counts  # HTTP reads do not enqueue or acknowledge work.

    client = create_app({"TESTING": True}).test_client()  # restart
    assert client.get(url).get_json()["status"] == "controlled_revision_review_pending"
    replay_id = create_action(
        replace(event, entity_type="job", entity_id=str(job_id)),
        workflow_key="controlled-drawing-ewi-review",
        step_key="review-job-packet-fai-101",
        target_module="ewi",
        input_data={"synthetic_replay": True},
    )
    assert replay_id == action_id
    with db() as con:
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE workflow_key='controlled-drawing-ewi-review'
                 AND entity_type='job' AND entity_id=?""", (str(job_id),),
        ).fetchone()[0] == 1
        con.execute(
            "UPDATE workflow_actions SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (action_id,),
        )
    # Watchdog regression: a completed task is NOT verified revision/route
    # reconciliation. The source drawing and EWI route are still revision A.
    unresolved = client.get(url).get_json()
    assert unresolved["status"] == "controlled_revision_reconciliation_unverified", unresolved
    assert unresolved["revision_review_action_id"] == action_id
    assert unresolved["revision_review_action_status"] == "completed"
    assert unresolved["revision_review_source_event_id"] == event.event_id
    assert unresolved["method_operation_id"] is None
    assert unresolved["ewi_step"] is None
    assert unresolved["drawing_document_id"] is None
    assert unresolved["human_review_required"] is True
    assert unresolved["released_route_approved"] is False
    assert "controlled_revision_reconciliation_unverified" in client.get(
        f"/ewi/jobs/{job_id}"
    ).get_data(as_text=True)
    assert _counts() == counts


def test_wrong_job_and_orphaned_review_actions_fail_closed_by_scope(tmp_path, monkeypatch):
    client, job_id, part_id, operation_id, event_id = _fictional_aligned_job(tmp_path, monkeypatch)
    url = f"/api/v1/jobs/{job_id}/ewi-operation-alignment/{event_id}"
    with db() as con:
        other_job = int(con.execute(
            "INSERT INTO jobs(job_number,status) VALUES('SYN-OTHER-JOB','open')"
        ).lastrowid)
    _revision_action(other_job, part_id, suffix="202")
    assert client.get(url).get_json()["status"] == "cross_source_candidate_review_required"

    # An orphaned action is still an unresolved review, never an implicit approval.
    with db() as con:
        orphan_id = int(con.execute(
            """INSERT INTO workflow_actions
               (event_id,workflow_key,step_key,source_module,target_module,
                entity_type,entity_id,status,input_json)
               VALUES('evt_missing_fictional','controlled-drawing-ewi-review',
                      'review-job-packet-fai-303','ezfair','ewi','job',?,'open','{}')""",
            (str(job_id),),
        ).lastrowid)
    blocked = client.get(url).get_json()
    assert blocked["status"] == "controlled_revision_review_pending"
    assert blocked["revision_review_action_id"] == orphan_id
    assert blocked["revision_review_source_event_id"] is None
    assert blocked["method_operation_id"] is None
    with db() as con:
        con.execute("UPDATE workflow_actions SET status='completed' WHERE id=?", (orphan_id,))
    orphaned = client.get(url).get_json()
    assert orphaned["status"] == "controlled_revision_reconciliation_unverified"
    assert orphaned["revision_review_action_id"] == orphan_id
    assert orphaned["revision_review_source_event_id"] is None
    assert orphaned["method_operation_id"] is None

def test_unverified_completion_claim_and_cancelled_review_cannot_restore_alignment(tmp_path, monkeypatch):
    """Human task status and self-reported output cannot prove route provenance."""
    from superforge.app import create_app

    client, job_id, part_id, operation_id, event_id = _fictional_aligned_job(tmp_path, monkeypatch)
    url = f"/api/v1/jobs/{job_id}/ewi-operation-alignment/{event_id}"
    event, action_id = _revision_action(job_id, part_id, suffix="401")
    with db() as con:
        con.execute(
            "UPDATE workflow_actions SET status='completed',completed_at=CURRENT_TIMESTAMP,"
            "output_json=? WHERE id=?",
            (json.dumps({"reconciled": True, "route_revision": "B",
                         "approved_by": "fictional-reviewer"}), action_id),
        )
    counts = _counts()
    response = client.get(url).get_json()
    assert response["status"] == "controlled_revision_reconciliation_unverified", response
    assert response["revision_review_action_id"] == action_id
    assert response["revision_review_source_event_id"] == event.event_id
    assert response["method_operation_id"] is None
    assert response["ewi_step"] is None

    # An additional open review takes precedence over the completed one.
    _, newer_action_id = _revision_action(job_id, part_id, suffix="402")
    pending = client.get(url).get_json()
    assert pending["status"] == "controlled_revision_review_pending", pending
    assert pending["revision_review_action_id"] == newer_action_id

    # Cancelling the newer task does not prove reconciliation either.
    after_second_review = _counts()
    with db() as con:
        con.execute("UPDATE workflow_actions SET status='cancelled' WHERE id=?",
                    (newer_action_id,))
    client = create_app({"TESTING": True}).test_client()  # process restart
    unresolved = client.get(url).get_json()
    assert unresolved["status"] == "controlled_revision_reconciliation_unverified", unresolved
    assert unresolved["method_operation_id"] is None
    assert unresolved["released_route_approved"] is False
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-drawing-ewi-review' "
            "AND entity_type='job' AND entity_id=?", (str(job_id),)
        ).fetchone()[0] == 2
    assert _counts() == after_second_review


def test_route_revision_capture_blocks_stale_and_legacy_snapshots(tmp_path, monkeypatch):
    """SQL/Methods and EWI must agree on the local revision captured at route pull."""
    from superforge.app import create_app
    from superforge.modules.ewi import save_remote_routes

    client, job_id, part_id, operation_id, event_id = _fictional_aligned_job(
        tmp_path, monkeypatch
    )
    url = f"/api/v1/jobs/{job_id}/ewi-operation-alignment/{event_id}"
    first = client.get(url).get_json()
    assert first["status"] == "cross_source_candidate_review_required", first
    assert first["route_local_part_revision_at_pull"] == "A"
    assert first["remote_erp_revision_verified"] is False

    with db() as con:
        row = con.execute(
            "SELECT local_part_revision_at_pull,pulled_at FROM ewi_routes WHERE job_id=?",
            (job_id,),
        ).fetchone()
        assert row["local_part_revision_at_pull"] == "A" and row["pulled_at"]
        con.execute(
            "UPDATE ewi_routes SET local_part_revision_at_pull='B' WHERE job_id=?",
            (job_id,),
        )
    counts = _counts()
    stale = client.get(url).get_json()
    assert stale["status"] == "ewi_route_revision_stale", stale
    assert stale["ewi_step"] is None and stale["method_operation_id"] is None
    assert "ewi_route_revision_stale" in client.get(
        f"/ewi/jobs/{job_id}"
    ).get_data(as_text=True)
    assert _counts() == counts

    with db() as con:
        con.execute(
            "UPDATE ewi_routes SET local_part_revision_at_pull='' WHERE job_id=?",
            (job_id,),
        )
    unverified = client.get(url).get_json()
    assert unverified["status"] == "ewi_route_revision_unverified", unverified
    assert unverified["ewi_step"] is None
    assert _counts() == counts

    routes = [{
        "step": "10", "operation": "SYN-OP-10",
        "part_number": "SYN-REV-PART-001", "external_id": "SYN-ROUTE-10",
    }]
    assert save_remote_routes(job_id, routes) == 1
    client = create_app({"TESTING": True}).test_client()
    restored = client.get(url).get_json()
    assert restored["status"] == "cross_source_candidate_review_required", restored
    assert restored["route_local_part_revision_at_pull"] == "A"
    assert restored["method_operation_id"] == operation_id
    assert _counts() == counts
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (event_id,),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND status='delivered'",
            (event_id,),
        ).fetchone()[0] >= 2

    # Invalid route refresh must not destroy the prior atomic snapshot.
    with pytest.raises(ValueError, match="duplicated"):
        save_remote_routes(job_id, routes + [dict(routes[0])])
    assert client.get(url).get_json()["status"] == "cross_source_candidate_review_required"


def test_legacy_ewi_route_schema_migrates_without_claiming_revision(tmp_path, monkeypatch):
    """An old route row must survive migration but remain unverified."""
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.db import init_db
    from superforge.app import create_app

    init_db()
    with db() as con:
        con.execute("""CREATE TABLE ewi_routes (
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            step TEXT NOT NULL, operation TEXT NOT NULL DEFAULT '',
            work_center TEXT NOT NULL DEFAULT '', instruction TEXT NOT NULL DEFAULT '',
            external_id TEXT NOT NULL DEFAULT '', part_number TEXT NOT NULL DEFAULT '',
            pulled_at TEXT NOT NULL, PRIMARY KEY(job_id,step))""")
        part_id = int(con.execute(
            "INSERT INTO parts(part_number,revision) VALUES('SYN-LEGACY-PART','A')"
        ).lastrowid)
        job_id = int(con.execute(
            "INSERT INTO jobs(job_number,part_id) VALUES('SYN-LEGACY-JOB',?)",
            (part_id,),
        ).lastrowid)
        con.execute(
            """INSERT INTO ewi_routes(job_id,step,operation,part_number,pulled_at)
               VALUES(?,'10','SYN-LEGACY-OP','SYN-LEGACY-PART','2099-01-01T00:00:00Z')""",
            (job_id,),
        )
    create_app({"TESTING": True})
    with db() as con:
        row = con.execute(
            "SELECT local_part_revision_at_pull FROM ewi_routes WHERE job_id=?",
            (job_id,),
        ).fetchone()
        assert row is not None and row["local_part_revision_at_pull"] == ""
        assert con.execute(
            "SELECT COUNT(*) FROM ewi_routes WHERE job_id=?", (job_id,)
        ).fetchone()[0] == 1


def test_sql_revision_review_blocks_clocking_even_after_action_completed(tmp_path, monkeypatch):
    """SQL EZ FAIR review must block real clock-in, not just the advisory panel."""
    client, job_id, part_id, _, job_event_id = _fictional_aligned_job(tmp_path, monkeypatch)
    from superforge.modules.ewi import packet, clock_start, clock_stop
    from superforge.app import create_app

    assert packet(job_id)["ready"] is True
    prior_session = clock_start(job_id, "10", "SYN-TECH-OLD", "synthetic-bridge")
    event, action_id = _revision_action(job_id, part_id, suffix="301")
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (job_event_id,)
        ).fetchone()[0] == "delivered"
        assert tuple(con.execute(
            "SELECT event_type,source_module FROM event_ledger WHERE event_id=?",
            (event.event_id,),
        ).fetchone()) == ("fai.imported", "ezfair")
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND status='delivered'",
            (job_event_id,),
        ).fetchone()[0] >= 2
        before = (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )
    counts = _counts()
    assert packet(job_id)["ready"] is False
    assert f"revision review action #{action_id}" in client.get(
        f"/ewi/jobs/{job_id}"
    ).get_data(as_text=True)
    with pytest.raises(ValueError, match="revision review action"):
        clock_start(job_id, "10", "SYN-TECH-NEW", "synthetic-bridge")
    with db() as con:
        assert before == (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )
        con.execute(
            "UPDATE workflow_actions SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (action_id,),
        )
    create_app({"TESTING": True})  # Restart must not turn task completion into route approval.
    assert packet(job_id)["ready"] is False
    with pytest.raises(ValueError, match="revision review action"):
        clock_start(job_id, "10", "SYN-TECH-NEW", "synthetic-bridge")
    with db() as con:
        assert before == (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )
    assert _counts() == counts
    clock_stop(prior_session, "SYN-TECH-OLD", "synthetic-bridge")
    with db() as con:
        assert con.execute(
            "SELECT ended_utc FROM ewi_clock_sessions WHERE id=?", (prior_session,)
        ).fetchone()[0] is not None


def test_revision_review_arriving_after_packet_read_blocks_transactional_clock_in(
    tmp_path, monkeypatch,
):
    """No time-of-check gap between the operator packet and durable session."""
    _, job_id, part_id, _, _ = _fictional_aligned_job(tmp_path, monkeypatch)
    from superforge.modules import ewi as ewi_module

    original_packet = ewi_module.packet

    def packet_then_review(job):
        snapshot = original_packet(job)
        assert snapshot["ready"] is True
        _revision_action(job, part_id, suffix="302")
        return snapshot

    monkeypatch.setattr(ewi_module, "packet", packet_then_review)
    with pytest.raises(ValueError, match="revision review action"):
        ewi_module.clock_start(job_id, "10", "SYN-TECH-RACE", "synthetic-bridge")
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-drawing-ewi-review'"
        ).fetchone()[0] == 1
