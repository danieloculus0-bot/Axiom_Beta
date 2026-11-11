"""Synthetic Quality KPI replay regression over the existing Axiom SQLite ledger.

No real drawings, people, employers, jobs, suppliers or external systems.
"""
from __future__ import annotations

from superforge import event_bus
from superforge.db import db


def test_quality_ppm_deduplicates_when_receipt_fails_and_event_replays(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app

    create_app({"TESTING": True})
    with db() as con:
        quality_id = int(con.execute(
            """INSERT INTO quality_records(record_type,record_number,description)
               VALUES('NCR','SYN-Q-RECEIPT-001','Fictional dimensional review')"""
        ).lastrowid)
        event = event_bus.stage_event(
            con, "quality.created", source_module="quality",
            entity_type="quality_record", entity_id=str(quality_id),
            actor="synthetic-test", reason="Fictional quality event",
            payload={"quantity_affected": 2, "quantity_shipped": 100},
        )
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event.event_id,)
        ).fetchone()["status"] == "pending_delivery"
        assert con.execute(
            "SELECT COUNT(*) FROM kpi_snapshots WHERE source_event_id=?", (event.event_id,)
        ).fetchone()[0] == 0

    original = event_bus._record_delivery
    interrupted = {"once": True}

    def fail_quality_receipt_once(evt, handler, status, error_text=""):
        if (evt.event_id == event.event_id and handler is event_bus._quality_created
                and status == "delivered" and interrupted["once"]):
            interrupted["once"] = False
            return False
        return original(evt, handler, status, error_text)

    monkeypatch.setattr(event_bus, "_record_delivery", fail_quality_receipt_once)
    first = event_bus.deliver_staged(event.event_id)
    assert first["failed"] == 1, first
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event.event_id,)
        ).fetchone()["status"] == "partial_failure"
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event.event_id, event_bus._handler_key(event_bus._quality_created)),
        ).fetchone()[0] == 0
        ppm = con.execute(
            """SELECT id,value,unit FROM kpi_snapshots WHERE source_event_id=?
               AND metric_name='PPM' AND metric_scope='quality' AND scope_id=?""",
            (event.event_id, str(quality_id)),
        ).fetchall()
        assert len(ppm) == 1
        assert (ppm[0]["value"], ppm[0]["unit"]) == (20000.0, "ppm")
        original_ppm_id = ppm[0]["id"]
        actions = con.execute(
            """SELECT id,workflow_key,step_key FROM workflow_actions
               WHERE event_id=? AND workflow_key IN ('quality-response','quality-to-job')
               ORDER BY id""", (event.event_id,),
        ).fetchall()
        assert [(a["workflow_key"], a["step_key"]) for a in actions] == [
            ("quality-response", "containment"),
            ("quality-to-job", "review-job-risk"),
        ]
        original_action_ids = [a["id"] for a in actions]

    monkeypatch.setattr(event_bus, "_record_delivery", original)
    create_app({"TESTING": True})  # restart replays the committed, partially delivered event
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event.event_id,)
        ).fetchone()["status"] == "delivered"
        assert con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event.event_id, event_bus._handler_key(event_bus._quality_created)),
        ).fetchone()["status"] == "delivered"
        ppm_ids = [r["id"] for r in con.execute(
            "SELECT id FROM kpi_snapshots WHERE source_event_id=? AND metric_name='PPM'",
            (event.event_id,),
        )]
        assert ppm_ids == [original_ppm_id], ppm_ids
        replay_action_ids = [r["id"] for r in con.execute(
            """SELECT id FROM workflow_actions WHERE event_id=?
               AND workflow_key IN ('quality-response','quality-to-job') ORDER BY id""",
            (event.event_id,),
        )]
        assert replay_action_ids == original_action_ids

    # Another committed quality event may legitimately add a separate snapshot.
    with db() as con:
        second = event_bus.stage_event(
            con, "quality.created", source_module="quality",
            entity_type="quality_record", entity_id=str(quality_id),
            actor="synthetic-test", reason="Distinct fictional quality event",
            payload={"quantity_affected": 3, "quantity_shipped": 100},
        )
    assert event_bus.deliver_staged(second.event_id)["failed"] == 0
    assert event_bus.deliver_staged(event.event_id)["delivered"] == 0
    with db() as con:
        rows = con.execute(
            """SELECT source_event_id,value FROM kpi_snapshots
               WHERE metric_name='PPM' AND metric_scope='quality' AND scope_id=?
               ORDER BY id""", (str(quality_id),),
        ).fetchall()
        assert [(r["source_event_id"], r["value"]) for r in rows] == [
            (event.event_id, 20000.0), (second.event_id, 30000.0),
        ]
