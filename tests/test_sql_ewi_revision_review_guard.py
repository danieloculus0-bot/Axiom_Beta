"""Synthetic SQL-to-EWI revision-review bridge; no real drawings or ERP data."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace

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
    restored = client.get(url).get_json()
    assert restored["status"] == "cross_source_candidate_review_required", restored
    assert restored["method_operation_id"] == operation_id
    assert restored["human_review_required"] is True
    assert restored["released_route_approved"] is False


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
    assert client.get(url).get_json()["status"] == "cross_source_candidate_review_required"
