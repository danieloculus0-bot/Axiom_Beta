"""Regression: a successful consumer without a durable SQL receipt is not delivered.

All records are invented. This tests the existing SQL ledger, receipts and
workflow actions, not a live external ERP or BEAN service.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from superforge import event_bus
from superforge.db import db


def test_receipt_sql_write_failure_is_observable(monkeypatch):
    """A storage error must never masquerade as a successful receipt."""
    @contextmanager
    def broken_db():
        raise sqlite3.OperationalError("synthetic receipt storage unavailable")
        yield

    event = event_bus.DomainEvent(
        event_id="evt_synthetic_receipt", event_type="test.sync.receipt",
        source_module="synthetic", entity_type="job", entity_id="1",
        actor="synthetic", reason="test", payload={}, correlation_id="corr_synthetic",
    )
    monkeypatch.setattr(event_bus, "db", broken_db)
    assert event_bus._record_delivery(event, lambda event: None, "delivered") is False


def test_successful_job_consumer_without_receipt_replays_once_after_restart(tmp_path, monkeypatch):
    """SQL record and event survive a simulated receipt failure and app restart."""
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    create_app({"TESTING": True})

    calls = {"planning": 0}
    def planning(event):
        calls["planning"] += 1
        event_bus.create_action(
            event, workflow_key="synthetic-receipt-recovery",
            step_key="review-job", target_module="planning",
        )

    event_bus.subscribe("test.sync.receipt.recovery", planning)
    with db() as con:
        job_id = int(con.execute(
            "INSERT INTO jobs(job_number,status) VALUES('SYN-RECEIPT-001','open')"
        ).lastrowid)
        event = event_bus.stage_event(
            con, "test.sync.receipt.recovery", source_module="integrations",
            entity_type="job", entity_id=str(job_id),
            payload={"job_id": job_id, "revision": "SYN-A"},
        )
    with db() as con:
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?",
                           (event.event_id,)).fetchone()[0] == "pending_delivery"
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE event_id=?",
                           (event.event_id,)).fetchone()[0] == 0

    original = event_bus._record_delivery
    interrupted = {"once": True}
    def unavailable_once(evt, handler, status, error_text=""):
        if (evt.event_id == event.event_id and handler is planning
                and status == "delivered" and interrupted["once"]):
            interrupted["once"] = False
            return False
        return original(evt, handler, status, error_text)

    monkeypatch.setattr(event_bus, "_record_delivery", unavailable_once)
    first = event_bus.deliver_staged(event.event_id)
    assert first["failed"] == 1, first
    assert calls["planning"] == 1
    with db() as con:
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?",
                           (event.event_id,)).fetchone()[0] == "partial_failure"
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event.event_id, event_bus._handler_key(planning)),
        ).fetchone()[0] == 0
        action = con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='synthetic-receipt-recovery'",
            (event.event_id,),
        ).fetchone()
        assert action is not None
        original_action_id = action["id"]

    monkeypatch.setattr(event_bus, "_record_delivery", original)
    create_app({"TESTING": True})  # recovery of committed, partially delivered event
    with db() as con:
        assert con.execute("SELECT status FROM event_ledger WHERE event_id=?",
                           (event.event_id,)).fetchone()[0] == "delivered"
        assert con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event.event_id, event_bus._handler_key(planning)),
        ).fetchone()["status"] == "delivered"
        actions = con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? AND workflow_key='synthetic-receipt-recovery'",
            (event.event_id,),
        ).fetchall()
        assert [row["id"] for row in actions] == [original_action_id]
    assert calls["planning"] == 2  # at-least-once retry, no duplicate action

    again = event_bus.deliver_staged(event.event_id)
    assert again["failed"] == 0 and again["delivered"] == 0
    assert again["skipped"] >= 1
    assert calls["planning"] == 2
