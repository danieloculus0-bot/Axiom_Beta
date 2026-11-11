"""Synthetic SQL producer to read-only operation evidence consumer regression."""
from __future__ import annotations

import csv
import json

from superforge import event_bus
from superforge.db import db
from superforge.integrations.service import IntegrationService


def _feed(path, operation="SYN-OP-10"):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Job", "PartId", "Op", "Status"])
        writer.writeheader()
        writer.writerow({
            "Job": "SYN-FRESH-WO-001", "PartId": _feed.part_id,
            "Op": operation, "Status": "open",
        })


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app

    client = create_app({"TESTING": True}).test_client()
    path = tmp_path / "fictional_freshness.csv"
    with db() as con:
        part_id = int(con.execute(
            "INSERT INTO parts(part_number,revision) VALUES('SYN-FRESH-PART-001','A')"
        ).lastrowid)
        job_id = int(con.execute(
            """INSERT INTO jobs(job_number,part_id,status,current_operation)
               VALUES('SYN-FRESH-WO-001',?,'seed','SYN-OP-10')""", (part_id,),
        ).lastrowid)
        plan_id = int(con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,required_date,status)
               VALUES(?,?,'SYN-FRESH-WO-001','SYN-FRESH-PART-001','A','2099-01-01','DRAFT')""",
            (job_id, part_id),
        ).lastrowid)
        operation_id = int(con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,10,'SYN-WC','SYN-OP-10','2099-01-01','Fictional review')""",
            (plan_id,),
        ).lastrowid)
        cid = int(con.execute(
            """INSERT INTO erp_connections(name,erp_type,adapter_type,direction,config_json)
               VALUES('SYN-FRESH-FEED','generic','flatfile','in',?)""",
            (json.dumps({"path": str(path), "external_id_field": "Job"}),),
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
                (cid, external, internal, transform),
            )
    _feed.part_id = str(part_id)
    _feed(path)
    return client, path, cid, job_id, part_id, plan_id, operation_id


def _event_id(con, job_id):
    return con.execute(
        """SELECT event_id FROM event_ledger
           WHERE event_type='job.changed' AND entity_type='job' AND entity_id=?
           ORDER BY id DESC LIMIT 1""", (str(job_id),),
    ).fetchone()["event_id"]


def _get(client, job_id, event_id):
    response = client.get(f"/api/v1/jobs/{job_id}/operation-evidence/{event_id}")
    return response.status_code, response.get_json()


def test_producer_consumer_freshness_revision_ambiguity_and_supersession(tmp_path, monkeypatch):
    client, path, cid, job_id, part_id, plan_id, op_id = _setup(tmp_path, monkeypatch)
    service = IntegrationService()
    first = service.pull(cid, "job", actor="synthetic-freshness")
    assert (first["applied"], first["errors"]) == (1, 0), first
    with db() as con:
        original_event = _event_id(con, job_id)
        original = con.execute(
            "SELECT payload_json,status FROM event_ledger WHERE event_id=?",
            (original_event,),
        ).fetchone()
        assert original["status"] == "delivered"
        assert json.loads(original["payload_json"])["identity"]["operation_id"] == op_id
        counts_before = tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                              for table in ("event_ledger", "workflow_actions",
                                            "module_suggestions", "event_delivery_receipts"))
    status_code, result = _get(client, job_id, original_event)
    assert status_code == 200 and result["ok"] is True, result
    assert result["status"] == "current_review_candidate", result
    assert (result["job_id"], result["part_id"], result["method_plan_id"],
            result["operation_id"], result["part_revision"]) == (
                job_id, part_id, plan_id, op_id, "A")
    assert result["human_review_required"] is True
    assert result["schema"] == "axiom.operation-evidence.v1"
    assert result["planning_action_id"] and result["methods_suggestion_id"]
    with db() as con:
        counts_after = tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                             for table in ("event_ledger", "workflow_actions",
                                           "module_suggestions", "event_delivery_receipts"))
        assert counts_after == counts_before  # HTTP consumer does not write

        con.execute("UPDATE ezm_method_plans SET status='REVIEW' WHERE id=?", (plan_id,))
    _, result = _get(client, job_id, original_event)
    assert result["status"] == "stale_identity"
    assert "method_plan_status" in result["changed_fields"]
    assert result["operation_id"] is None
    with db() as con:
        con.execute("UPDATE ezm_method_plans SET status='DRAFT' WHERE id=?", (plan_id,))
        con.execute("UPDATE parts SET revision='B' WHERE id=?", (part_id,))
    _, result = _get(client, job_id, original_event)
    assert result["status"] == "stale_identity"
    assert "part_revision" in result["changed_fields"]
    with db() as con:
        con.execute("UPDATE parts SET revision='A' WHERE id=?", (part_id,))
        duplicate_plan = int(con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,required_date,status)
               VALUES(?,?,'SYN-FRESH-WO-001','SYN-FRESH-PART-001','A','2099-01-01','DRAFT')""",
            (job_id, part_id),
        ).lastrowid)
    _, result = _get(client, job_id, original_event)
    assert result["status"] == "stale_identity"
    assert "method_match_status" in result["changed_fields"]
    with db() as con:
        con.execute("DELETE FROM ezm_method_plans WHERE id=?", (duplicate_plan,))
        duplicate_op = int(con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,20,'SYN-WC','SYN-OP-10','2099-01-01','Fictional duplicate')""",
            (plan_id,),
        ).lastrowid)
    _, result = _get(client, job_id, original_event)
    assert result["status"] == "stale_identity"
    assert result["operation_id"] is None
    with db() as con:
        con.execute("DELETE FROM ezm_operations WHERE id=?", (duplicate_op,))
        new_op = int(con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,20,'SYN-WC','SYN-OP-20','2099-01-01','Fictional review')""",
            (plan_id,),
        ).lastrowid)
    assert _get(client, job_id, original_event)[1]["status"] == "current_review_candidate"
    _feed(path, operation="SYN-OP-20")
    changed = service.pull(cid, "job", actor="synthetic-freshness")
    assert (changed["read"], changed["applied"], changed["skipped"], changed["errors"]) == (1, 1, 0, 0), changed
    with db() as con:
        newer_event = _event_id(con, job_id)
        assert newer_event != original_event
    assert _get(client, job_id, original_event)[1]["status"] == "superseded_event"
    _, current = _get(client, job_id, newer_event)
    assert current["status"] == "current_review_candidate"
    assert current["operation_id"] == new_op
    repeat = service.pull(cid, "job", actor="synthetic-freshness")
    assert (repeat["applied"], repeat["skipped"], repeat["errors"]) == (0, 1, 0), repeat
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed'"
        ).fetchone()[0] == 2


def test_partial_delivery_missing_receipt_restart_and_scope_guards(tmp_path, monkeypatch):
    client, path, cid, job_id, part_id, plan_id, op_id = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(event_bus, "_HANDLERS",
                        {kind: list(handlers) for kind, handlers in event_bus._HANDLERS.items()})
    attempts = {"count": 0}

    def flaky(event):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("fictional subscriber interruption")

    event_bus.subscribe("job.changed", flaky)
    first = IntegrationService().pull(cid, "job", actor="synthetic-restart")
    assert (first["applied"], first["errors"]) == (1, 0), first
    with db() as con:
        event_id = _event_id(con, job_id)
        action_id = con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (event_id,),
        ).fetchone()[0]
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event_id,)
        ).fetchone()[0] == "partial_failure"
    assert _get(client, job_id, event_id)[1]["status"] == "event_not_delivered"

    from superforge.app import create_app
    client = create_app({"TESTING": True}).test_client()  # restart replay
    assert attempts["count"] == 2
    _, recovered = _get(client, job_id, event_id)
    assert recovered["status"] == "current_review_candidate"
    assert recovered["planning_action_id"] == action_id
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (event_id,),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND status='failed'",
            (event_id,),
        ).fetchone()[0] == 0
        con.execute(
            "DELETE FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event_id, event_bus._handler_key(event_bus._job_changed)),
        )
    _, missing = _get(client, job_id, event_id)
    assert missing["status"] == "consumer_evidence_incomplete"
    assert missing["operation_id"] is None
    event_bus.deliver_staged(event_id)  # replays only missing receipt, idempotently
    assert _get(client, job_id, event_id)[1]["status"] == "current_review_candidate"
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (event_id,),
        ).fetchone()[0] == 1
    assert _get(client, job_id + 1, event_id)[1]["status"] == "event_scope_mismatch"
    status, missing_event = _get(client, job_id, "evt_fictional_missing")
    assert status == 404 and missing_event["status"] == "event_not_found"
    status, invalid = _get(client, job_id, "x" * 161)
    assert status == 200 and invalid["status"] == "invalid_event_id"


def test_ewi_operator_page_shows_current_stale_and_missing_sql_evidence(tmp_path, monkeypatch):
    """The EWI page reads the existing SQL producer and freshness consumer."""
    client, path, cid, job_id, part_id, plan_id, op_id = _setup(tmp_path, monkeypatch)
    url = f"/ewi/jobs/{job_id}"
    missing = client.get(url)
    assert missing.status_code == 200
    assert "no_sql_job_change_event" in missing.get_data(as_text=True)
    assert "No canonical SQL job-change event" in missing.get_data(as_text=True)

    first = IntegrationService().pull(cid, "job", actor="synthetic-ewi-review")
    assert (first["applied"], first["errors"]) == (1, 0), first
    with db() as con:
        event_id = _event_id(con, job_id)
        counts_before = tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                              for table in ("event_ledger", "workflow_actions",
                                            "module_suggestions", "event_delivery_receipts"))
    current = client.get(url).get_data(as_text=True)
    assert "current_review_candidate" in current
    assert f"Operation candidate #{op_id}" in current
    assert f"Source event: <code>{event_id}</code>" in current
    assert "not a released instruction or an EWI step match" in current
    with db() as con:
        counts_after = tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                             for table in ("event_ledger", "workflow_actions",
                                           "module_suggestions", "event_delivery_receipts"))
        assert counts_after == counts_before  # page view is read-only
        con.execute("UPDATE parts SET revision='B' WHERE id=?", (part_id,))
    stale = client.get(url).get_data(as_text=True)
    assert "stale_identity" in stale
    assert "part_revision" in stale
    assert "Operation candidate #" not in stale
    with db() as con:
        con.execute("UPDATE parts SET revision='A' WHERE id=?", (part_id,))
    repeat = IntegrationService().pull(cid, "job", actor="synthetic-ewi-review")
    assert (repeat["applied"], repeat["skipped"], repeat["errors"]) == (0, 1, 0)
    assert "current_review_candidate" in client.get(url).get_data(as_text=True)


def test_ewi_review_rejects_partial_delivery_and_missing_receipt_then_recovers(tmp_path, monkeypatch):
    client, path, cid, job_id, part_id, plan_id, op_id = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(event_bus, "_HANDLERS",
                        {kind: list(handlers) for kind, handlers in event_bus._HANDLERS.items()})
    attempts = {"count": 0}

    def interrupted(event):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("fictional delivery interruption")

    event_bus.subscribe("job.changed", interrupted)
    first = IntegrationService().pull(cid, "job", actor="synthetic-ewi-replay")
    assert (first["applied"], first["errors"]) == (1, 0), first
    with db() as con:
        event_id = _event_id(con, job_id)
        action_id = con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (event_id,),
        ).fetchone()[0]
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?",
                           (event_id,)).fetchone()[0] == "partial_failure"
    pending = client.get(f"/ewi/jobs/{job_id}").get_data(as_text=True)
    assert "event_not_delivered" in pending
    assert "Operation candidate #" not in pending

    from superforge.app import create_app
    client = create_app({"TESTING": True}).test_client()
    assert attempts["count"] == 2
    recovered = client.get(f"/ewi/jobs/{job_id}").get_data(as_text=True)
    assert "current_review_candidate" in recovered
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
                           (event_id,)).fetchone()[0] == 1
        con.execute("DELETE FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
                    (event_id, event_bus._handler_key(event_bus._job_changed)))
    incomplete = client.get(f"/ewi/jobs/{job_id}").get_data(as_text=True)
    assert "consumer_evidence_incomplete" in incomplete
    assert "Operation candidate #" not in incomplete
    event_bus.deliver_staged(event_id)
    restored = client.get(f"/ewi/jobs/{job_id}").get_data(as_text=True)
    assert "current_review_candidate" in restored
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
                           (event_id,)).fetchone()[0] == 1
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?",
                           (event_id,)).fetchone()[0] == "delivered"
        assert con.execute("SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND status='failed'",
                           (event_id,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND status='delivered'",
                           (event_id,)).fetchone()[0] >= 2
    assert action_id
