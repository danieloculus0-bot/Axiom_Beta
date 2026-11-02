"""Transactional SQL synchronization and event-recovery regression tests.

All inputs are fictional. This suite exercises 1,000 distinct change notifications,
an identical 1,000-record repeat, and replay after interrupted dispatch.
"""
from __future__ import annotations

import csv
import json

from superforge.db import db
from superforge.event_bus import (
    create_action, deliver_staged, recover_undelivered, stage_event, subscribe,
)


def test_one_thousand_imported_jobs_notify_modules_once(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    from superforge.integrations.service import IntegrationService

    create_app({"TESTING": True})
    feed = tmp_path / "synthetic_jobs.csv"
    records = [{"Job": f"SYN-SYNC-{i:04d}", "Status": "open"} for i in range(1000)]

    def write_feed():
        with feed.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Job", "Status"])
            writer.writeheader()
            writer.writerows(records)

    write_feed()
    with db() as con:
        connection_id = int(con.execute(
            """INSERT INTO erp_connections(name,erp_type,adapter_type,direction,config_json)
               VALUES(?,?,?,?,?)""",
            ("Synthetic sync feed", "generic", "flatfile", "in",
             json.dumps({"path": str(feed), "external_id_field": "Job"})),
        ).lastrowid)
        con.execute(
            """INSERT INTO erp_mappings(connection_id,entity_type,external_field,internal_field,transform,direction,required)
               VALUES(?,?,?,?,?,'in',1)""",
            (connection_id, "job", "Job", "job_number", "strip"),
        )
        con.execute(
            """INSERT INTO erp_mappings(connection_id,entity_type,external_field,internal_field,transform,direction,required)
               VALUES(?,?,?,?,?,'in',0)""",
            (connection_id, "job", "Status", "status", "lower"),
        )

    service = IntegrationService()
    first = service.pull(connection_id, "job", actor="synthetic-test")
    assert first["status"] == "completed", first
    assert (first["read"], first["applied"], first["skipped"], first["errors"]) == (1000, 1000, 0, 0)

    with db() as con:
        count = lambda sql: con.execute(sql).fetchone()[0]
        assert count("SELECT COUNT(*) FROM jobs WHERE job_number LIKE 'SYN-SYNC-%'") == 1000
        assert count("SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed' AND source_module='integrations'") == 1000
        assert count("""SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed'
                         AND source_module='integrations' AND status!='delivered'""") == 0
        assert count("""SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='job-change'
                         AND source_module='integrations'""") == 1000
        assert count("""SELECT COUNT(*) FROM module_suggestions WHERE source_module='integrations'
                         AND target_module='ez_methods' AND suggestion_key='job-method-readiness'""") == 1000

    # Repeat the same 1,000 records. No new change notifications or workflow actions.
    repeat = service.pull(connection_id, "job", actor="synthetic-test")
    assert (repeat["read"], repeat["applied"], repeat["skipped"], repeat["errors"]) == (1000, 0, 1000, 0), repeat
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed' AND source_module='integrations'"
        ).fetchone()[0] == 1000
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='job-change' AND source_module='integrations'"
        ).fetchone()[0] == 1000

    # Exactly one altered source row must activate exactly one new set of subscribers.
    records[407]["Status"] = "closed"
    write_feed()
    changed = service.pull(connection_id, "job", actor="synthetic-test")
    assert (changed["read"], changed["applied"], changed["skipped"], changed["errors"]) == (1000, 1, 999, 0), changed
    with db() as con:
        assert con.execute(
            "SELECT status FROM jobs WHERE job_number='SYN-SYNC-0407'"
        ).fetchone()["status"] == "closed"
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='job-change' AND source_module='integrations'"
        ).fetchone()[0] == 1001
        assert con.execute(
            """SELECT COUNT(*) FROM module_suggestions WHERE source_module='integrations'
               AND target_module='ez_methods' AND suggestion_key='job-method-readiness'"""
        ).fetchone()[0] == 1001


def test_committed_unpublished_job_event_survives_restart_and_replay_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    create_app({"TESTING": True})

    with db() as con:
        job_id = int(con.execute(
            "INSERT INTO jobs(job_number,status) VALUES('SYN-RECOVERY-1','open')"
        ).lastrowid)
        event = stage_event(
            con, "job.changed", source_module="integrations", entity_type="job",
            entity_id=str(job_id), actor="synthetic-test", payload={"job_id": job_id},
        )
    with db() as con:
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?", (event.event_id,)).fetchone()[0] == "pending_delivery"
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE event_id=?", (event.event_id,)).fetchone()[0] == 0

    # Reinitialization simulates restart after SQL commit but before dispatch.
    create_app({"TESTING": True})
    with db() as con:
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?", (event.event_id,)).fetchone()[0] == "delivered"
        original = con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
            (event.event_id,),
        ).fetchone()[0]
        assert con.execute(
            "SELECT COUNT(*) FROM module_suggestions WHERE source_event_id=? AND target_module='ez_methods'",
            (event.event_id,),
        ).fetchone()[0] == 1

    receipt = deliver_staged(event.event_id)
    assert receipt["failed"] == 0 and receipt["delivered"] == 0 and receipt["skipped"] >= 2
    duplicate = create_action(
        event, workflow_key="job-change", step_key="check-po-material-quality",
        target_module="planning",
    )
    assert duplicate == original
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='job-change'",
                           (event.event_id,)).fetchone()[0] == 1


def test_failed_handler_retries_without_replaying_successful_sibling(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    create_app({"TESTING": True})
    calls = {"transient": 0, "healthy": 0}

    def transient(event):
        calls["transient"] += 1
        if calls["transient"] == 1:
            raise RuntimeError("synthetic transient failure")

    def healthy(event):
        calls["healthy"] += 1

    subscribe("test.sync.transient.recovery", transient)
    subscribe("test.sync.transient.recovery", healthy)
    with db() as con:
        event = stage_event(
            con, "test.sync.transient.recovery", source_module="synthetic-test",
            entity_type="job", entity_id="42", payload={"scenario": "replay"},
        )
    first = deliver_staged(event.event_id)
    assert first["failed"] == 1 and first["delivered"] == 1
    recovered = recover_undelivered(limit=100)
    assert recovered["failed"] == 0 and recovered["delivered"] >= 1
    assert calls == {"transient": 2, "healthy": 1}
    with db() as con:
        statuses = [row["status"] for row in con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=?", (event.event_id,)
        )]
        assert statuses == ["delivered", "delivered"]
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event.event_id,)
        ).fetchone()[0] == "delivered"
