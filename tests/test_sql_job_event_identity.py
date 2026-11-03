"""Canonical job/part/revision snapshots across Axiom's existing SQL event bus.

All names, records, operations and revisions are fictional.
"""
from __future__ import annotations

import csv
import json

from superforge.db import db
from superforge import event_bus


def _feed(path, records):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Job", "PartId", "Op", "Status"])
        writer.writeheader()
        writer.writerows(records)


def _connection(con, path):
    connection_id = int(con.execute(
        """INSERT INTO erp_connections(name,erp_type,adapter_type,direction,config_json)
           VALUES('SYN-ID-IMPORT','generic','flatfile','in',?)""",
        (json.dumps({"path": str(path), "external_id_field": "Job"}),),
    ).lastrowid)
    for external, internal, transform, required in (
        ("Job", "job_number", "strip", 1),
        ("PartId", "part_id", "int", 0),
        ("Op", "current_operation", "strip", 0),
        ("Status", "status", "lower", 0),
    ):
        con.execute(
            """INSERT INTO erp_mappings
               (connection_id,entity_type,external_field,internal_field,transform,direction,required)
               VALUES(?,'job',?,?,?,'in',?)""",
            (connection_id, external, internal, transform, required),
        )
    return connection_id


def test_thousand_fictional_jobs_carry_sql_identity_to_planning(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    from superforge.integrations.service import IntegrationService

    client = create_app({"TESTING": True}).test_client()
    path = tmp_path / "fictional_jobs.csv"
    with db() as con:
        part_ids = [
            int(con.execute(
                "INSERT INTO parts(part_number,revision,description) VALUES(?,'A','Fictional component')",
                (f"SYN-ID-PART-{i:04d}",),
            ).lastrowid)
            for i in range(1000)
        ]
        connection_id = _connection(con, path)
    records = [
        {"Job": f"SYN-ID-WO-{i:04d}", "PartId": str(part_ids[i]),
         "Op": "SYN-OP-10", "Status": "open"}
        for i in range(1000)
    ]
    _feed(path, records)
    service = IntegrationService()
    first = service.pull(connection_id, "job", actor="synthetic-identity-test")
    assert (first["read"], first["applied"], first["skipped"], first["errors"]) == (1000, 1000, 0, 0), first

    with db() as con:
        rows = con.execute(
            """SELECT e.event_id,e.entity_id,e.payload_json,e.status,
                      j.job_number,j.part_id,j.current_operation,
                      p.part_number,p.revision,
                      a.id AS action_id,a.input_json
               FROM event_ledger e
               JOIN jobs j ON CAST(e.entity_id AS INTEGER)=j.id
               JOIN parts p ON p.id=j.part_id
               JOIN workflow_actions a ON a.event_id=e.event_id
                 AND a.workflow_key='job-change' AND a.target_module='planning'
               WHERE e.event_type='job.changed' AND e.source_module='integrations'
               ORDER BY e.id"""
        ).fetchall()
        assert len(rows) == 1000
        assert len({r["event_id"] for r in rows}) == 1000
        assert con.execute(
            """SELECT COUNT(*) FROM event_delivery_receipts
               WHERE event_type='job.changed' AND status='delivered'"""
        ).fetchone()[0] >= 1000
        assert con.execute(
            """SELECT COUNT(*) FROM module_suggestions
               WHERE source_module='integrations' AND target_module='ez_methods'
                 AND suggestion_key='job-method-readiness'"""
        ).fetchone()[0] == 1000
        for row in rows:
            assert row["status"] == "delivered"
            payload = json.loads(row["payload_json"])
            identity = payload["identity"]
            assert identity["schema"] == "axiom.job-identity.v1"
            assert identity["source"] == "local_axiom_sql"
            assert identity["job_id"] == int(row["entity_id"])
            assert identity["job_number"] == row["job_number"]
            assert identity["part_id"] == row["part_id"]
            assert identity["part_number"] == row["part_number"]
            assert identity["part_revision"] == row["revision"] == "A"
            assert identity["part_link_status"] == "linked_record_revision_unverified"
            assert identity["operation_label"] == row["current_operation"] == "SYN-OP-10"
            assert identity["operation_id"] is None
            assert identity["operation_status"] == "unverified_label"
            assert identity["human_review_required"] is True
            assert json.loads(row["input_json"])["identity"] == identity

    repeat = service.pull(connection_id, "job", actor="synthetic-identity-test")
    assert (repeat["read"], repeat["applied"], repeat["skipped"], repeat["errors"]) == (1000, 0, 1000, 0), repeat
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed' AND source_module='integrations'"
        ).fetchone()[0] == 1000
        original = json.loads(rows[407]["payload_json"])["identity"]
        con.execute("UPDATE parts SET revision='B' WHERE id=?", (part_ids[407],))

    # A part revision edit alone does not fake a job event. The next real job
    # change snapshots the new revision, leaving the original event immutable.
    records[407]["Op"] = "SYN-OP-20"
    _feed(path, records)
    changed = service.pull(connection_id, "job", actor="synthetic-identity-test")
    assert (changed["read"], changed["applied"], changed["skipped"], changed["errors"]) == (1000, 1, 999, 0), changed
    with db() as con:
        history = con.execute(
            """SELECT e.payload_json,e.status FROM event_ledger e
               JOIN jobs j ON CAST(e.entity_id AS INTEGER)=j.id
               WHERE j.job_number='SYN-ID-WO-0407' AND e.event_type='job.changed'
               ORDER BY e.id"""
        ).fetchall()
        assert len(history) == 2
        assert json.loads(history[0]["payload_json"])["identity"] == original
        updated = json.loads(history[1]["payload_json"])["identity"]
        assert updated["part_revision"] == "B"
        assert updated["operation_label"] == "SYN-OP-20"
        assert all(r["status"] == "delivered" for r in history)
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE workflow_key='job-change' AND source_module='integrations'"""
        ).fetchone()[0] == 1001
    # Existing read-only consumer contract sees the same canonical SQL identity.
    context = client.get(f"/api/v1/jobs/{updated['job_id']}/manufacturing-context").get_json()
    assert context["job"]["part_id"] == updated["part_id"]
    assert context["job"]["part_revision"] == "B"
    assert context["job"]["current_operation"] == "SYN-OP-20"
    assert context["method_status"] == "no_method_plan"
    assert context["cam"]["machine_program_ready"] is False


def test_unlinked_job_identity_replays_after_partial_handler_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    from superforge.integrations.service import IntegrationService

    create_app({"TESTING": True})
    # Isolate the additional test subscriber from other test modules.
    monkeypatch.setattr(event_bus, "_HANDLERS",
                        {kind: list(handlers) for kind, handlers in event_bus._HANDLERS.items()})
    calls = {"flaky": 0}

    def flaky(event):
        calls["flaky"] += 1
        if calls["flaky"] == 1:
            raise RuntimeError("synthetic receipt/recovery interruption")

    event_bus.subscribe("job.changed", flaky)
    path = tmp_path / "unlinked.csv"
    _feed(path, [{"Job": "SYN-UNLINKED-WO", "PartId": "", "Op": "", "Status": "open"}])
    with db() as con:
        connection_id = _connection(con, path)
    first = IntegrationService().pull(connection_id, "job", actor="synthetic-recovery-test")
    assert (first["read"], first["applied"], first["errors"]) == (1, 1, 0), first
    with db() as con:
        row = con.execute(
            "SELECT event_id,payload_json,status FROM event_ledger WHERE event_type='job.changed'"
        ).fetchone()
        assert row["status"] == "partial_failure"
        identity = json.loads(row["payload_json"])["identity"]
        assert identity["part_id"] is None
        assert identity["part_number"] is None
        assert identity["part_revision"] is None
        assert identity["part_link_status"] == "not_linked"
        assert identity["operation_label"] is None
        assert identity["operation_id"] is None
        assert identity["operation_status"] == "not_recorded"
        assert identity["human_review_required"] is True
        action_id = con.execute(
            """SELECT id FROM workflow_actions
               WHERE event_id=? AND workflow_key='job-change'""",
            (row["event_id"],),
        ).fetchone()[0]

    create_app({"TESTING": True})  # simulated restart retries failed consumer
    assert calls["flaky"] == 2
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (row["event_id"],)
        ).fetchone()[0] == "delivered"
        assert con.execute(
            """SELECT status FROM event_delivery_receipts
               WHERE event_id=? AND handler_key=?""",
            (row["event_id"], event_bus._handler_key(flaky)),
        ).fetchone()[0] == "delivered"
        assert con.execute(
            """SELECT id FROM workflow_actions
               WHERE event_id=? AND workflow_key='job-change'""",
            (row["event_id"],),
        ).fetchone()[0] == action_id
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (row["event_id"],),
        ).fetchone()[0] == 1
        assert json.loads(con.execute(
            "SELECT payload_json FROM event_ledger WHERE event_id=?", (row["event_id"],)
        ).fetchone()[0])["identity"] == identity
