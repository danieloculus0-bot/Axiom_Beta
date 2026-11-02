"""Crash-safe SQL startup recovery beyond the former 10,000-event ceiling.

All jobs, operations and revisions are completely fictional.
"""
from __future__ import annotations

import pytest

from superforge import event_bus
from superforge.db import db
from superforge.sql_recovery import CURSOR_KEY


def test_recovery_cursor_survives_ten_thousand_event_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app

    create_app({"TESTING": True})
    event_type = "test.sql.startup.cursor.bulk"
    total = 10005
    first_id = last_id = None
    with db() as con:
        for i in range(total):
            job_id = int(con.execute(
                "INSERT INTO jobs(job_number,status,current_operation) VALUES(?,'open','SYN-10')",
                (f"SYN-CURSOR-{i:05d}",),
            ).lastrowid)
            event = event_bus.stage_event(
                con, event_type, source_module="integrations",
                entity_type="job", entity_id=str(job_id),
                payload={"job_id": job_id, "revision": "SYN-A", "operation": "SYN-10"},
            )
            if i == 0:
                first_id = event.event_id
            if i == total - 1:
                last_id = event.event_id

    attempts = {"first": 0}

    def planning(event):
        if event.event_id in (first_id, last_id):
            event_bus.create_action(
                event, workflow_key="synthetic-cursor-recovery",
                step_key="review-operation", target_module="planning",
            )
        if event.event_id == first_id and attempts["first"] == 0:
            attempts["first"] += 1
            raise RuntimeError("synthetic first delivery interruption")

    event_bus.subscribe(event_type, planning)
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM jobs WHERE job_number LIKE 'SYN-CURSOR-%'"
        ).fetchone()[0] == total
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type=? AND status='pending_delivery'",
            (event_type,),
        ).fetchone()[0] == total
        tenth_id = con.execute(
            "SELECT id FROM event_ledger WHERE event_type=? ORDER BY id LIMIT 1 OFFSET 9999",
            (event_type,),
        ).fetchone()[0]

    create_app({"TESTING": True})  # first bounded startup: exactly 10,000 attempts
    with db() as con:
        counts = {row["status"]: row["n"] for row in con.execute(
            "SELECT status,COUNT(*) AS n FROM event_ledger WHERE event_type=? GROUP BY status",
            (event_type,),
        )}
        assert counts == {"delivered": 9999, "partial_failure": 1, "pending_delivery": 5}
        assert int(con.execute(
            "SELECT value FROM system_meta WHERE key=?", (CURSOR_KEY,),
        ).fetchone()[0]) == tenth_id
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_type=? AND handler_key=? AND status='delivered'",
            (event_type, event_bus._handler_key(planning)),
        ).fetchone()[0] == 9999
        first_action = con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='synthetic-cursor-recovery'",
            (first_id,),
        ).fetchone()[0]
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-cursor-recovery'"
        ).fetchone()[0] == 1

    create_app({"TESTING": True})  # resume five later events, then retry old failure
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type=? AND status='delivered'",
            (event_type,),
        ).fetchone()[0] == total
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_type=? AND handler_key=? AND status='delivered'",
            (event_type, event_bus._handler_key(planning)),
        ).fetchone()[0] == total
        assert con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='synthetic-cursor-recovery'",
            (first_id,),
        ).fetchone()[0] == first_action
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-cursor-recovery'"
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND workflow_key='synthetic-cursor-recovery'",
            (last_id,),
        ).fetchone()[0] == 1

    create_app({"TESTING": True})  # repeat restart cannot duplicate either action
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-cursor-recovery'"
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type=? AND status!='delivered'",
            (event_type,),
        ).fetchone()[0] == 0


def test_crash_mid_page_does_not_checkpoint_unprocessed_events(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app

    create_app({"TESTING": True})
    event_type = "test.sql.startup.cursor.crash"
    with db() as con:
        ids = []
        for i in range(2):
            job_id = int(con.execute(
                "INSERT INTO jobs(job_number,status) VALUES(?,'open')",
                (f"SYN-CRASH-{i:04d}",),
            ).lastrowid)
            ids.append(event_bus.stage_event(
                con, event_type, source_module="integrations",
                entity_type="job", entity_id=str(job_id),
                payload={"revision": "SYN-A", "operation": "SYN-10"},
            ).event_id)

    attempts = {"first": 0}

    def planning(event):
        event_bus.create_action(
            event, workflow_key="synthetic-crash-recovery",
            step_key="review-operation", target_module="planning",
        )
        if event.event_id == ids[0] and attempts["first"] == 0:
            attempts["first"] += 1
            raise SystemExit("synthetic process interruption")

    event_bus.subscribe(event_type, planning)
    with pytest.raises(SystemExit, match="synthetic process interruption"):
        create_app({"TESTING": True})

    with db() as con:
        assert con.execute(
            "SELECT value FROM system_meta WHERE key=?", (CURSOR_KEY,),
        ).fetchone() is None
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (ids[0],),
        ).fetchone()[0] == "pending_delivery"
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-crash-recovery'"
        ).fetchone()[0] == 1

    create_app({"TESTING": True})
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type=? AND status='delivered'",
            (event_type,),
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_type=? AND handler_key=? AND status='delivered'",
            (event_type, event_bus._handler_key(planning)),
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-crash-recovery'"
        ).fetchone()[0] == 2
