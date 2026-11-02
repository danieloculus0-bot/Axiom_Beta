"""Synthetic read-only SQL event delivery diagnostics regression.

No production records, employee identifiers, drawings, suppliers, or live services.
"""
from __future__ import annotations

from superforge import event_bus
from superforge.db import db


def _by_type(report, name):
    return next(item for item in report["event_types"] if item["event_type"] == name)


def test_delivery_diagnostics_detects_missing_domain_consumers_and_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    client = create_app({"TESTING": True}).test_client()
    calls = {"stable": 0, "flaky": 0}

    def stable(event):
        calls["stable"] += 1
        event_bus.create_action(
            event, workflow_key="synthetic-health", step_key="planning-review",
            target_module="planning",
        )

    def flaky(event):
        calls["flaky"] += 1
        if calls["flaky"] == 1:
            raise RuntimeError("synthetic interrupted consumer")
        event_bus.create_action(
            event, workflow_key="synthetic-health", step_key="quality-review",
            target_module="quality",
        )

    event_bus.subscribe("test.health.known", stable)
    event_bus.subscribe("test.health.flaky", flaky)
    with db() as con:
        job_id = con.execute(
            "INSERT INTO jobs(job_number,status) VALUES('SYN-HEALTH-0001','open')"
        ).lastrowid
        known = event_bus.stage_event(
            con, "test.health.known", source_module="integrations",
            entity_type="job", entity_id=str(job_id), payload={"revision": "SYN-A"},
        )
        broken = event_bus.stage_event(
            con, "test.health.flaky", source_module="integrations",
            entity_type="job", entity_id=str(job_id), payload={"revision": "SYN-A"},
        )
        unhandled = event_bus.stage_event(
            con, "test.health.no-domain", source_module="integrations",
            entity_type="job", entity_id=str(job_id), payload={"revision": "SYN-A"},
        )
        waiting = event_bus.stage_event(
            con, "test.health.no-domain", source_module="integrations",
            entity_type="job", entity_id=str(job_id), payload={"revision": "SYN-B"},
        )
    assert event_bus.deliver_staged(known.event_id)["failed"] == 0
    assert event_bus.deliver_staged(broken.event_id)["failed"] == 1
    event_bus.deliver_staged(unhandled.event_id)
    with db() as con:
        # Simulate a delivered event whose durable typed-consumer receipt is missing.
        con.execute(
            "DELETE FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (known.event_id, event_bus._handler_key(stable)),
        )

    response = client.get("/integrations/sync-health")
    assert response.status_code == 200
    report = response.get_json()
    assert report["schema"] == "axiom.sql-delivery-diagnostics.v1"
    assert report["source"] == "local_axiom_sql"
    assert report["status"] == "attention_required"
    assert _by_type(report, "test.health.known")["delivered_missing_current_receipts"] == 1
    assert _by_type(report, "test.health.flaky")["partial_failure"] == 1
    assert _by_type(report, "test.health.flaky")["failed_receipts"] == 1
    unknown = _by_type(report, "test.health.no-domain")
    assert unknown["typed_subscribers"] == 0
    assert unknown["without_typed_subscriber_events"] == 2
    assert unknown["pending_delivery"] >= 1
    assert report["totals"]["delivered_missing_current_receipts"] >= 1
    assert report["totals"]["without_typed_subscriber_events"] >= 2
    assert "SYN-HEALTH-0001" not in response.get_data(as_text=True)
    assert "SYN-A" not in response.get_data(as_text=True)

    # Restart retries a partial failure without duplicating the existing action.
    create_app({"TESTING": True})
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (broken.event_id,)
        ).fetchone()[0] == "delivered"
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE event_id=? AND workflow_key='synthetic-health'""",
            (broken.event_id,),
        ).fetchone()[0] == 1
    assert calls["flaky"] == 2
    after = event_bus.delivery_diagnostics()
    assert _by_type(after, "test.health.flaky")["partial_failure"] == 0
    assert _by_type(after, "test.health.flaky")["failed_receipts"] == 0
    # A missing receipt on an already delivered event is still flagged for review.
    assert _by_type(after, "test.health.known")["delivered_missing_current_receipts"] == 1


def test_thousand_synthetic_sql_events_recover_after_subscriber_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    create_app({"TESTING": True})
    event_type = "test.health.bulk-late-subscriber"
    with db() as con:
        for i in range(1000):
            job_id = con.execute(
                "INSERT INTO jobs(job_number,status) VALUES(?,'open')",
                (f"SYN-HEALTH-BULK-{i:04d}",),
            ).lastrowid
            event_bus.stage_event(
                con, event_type, source_module="integrations",
                entity_type="job", entity_id=str(job_id),
                payload={"job_id": job_id, "revision": "SYN-A"},
            )

    before = _by_type(event_bus.delivery_diagnostics(), event_type)
    assert before["total"] == 1000
    assert before["pending_delivery"] == 1000
    assert before["without_typed_subscriber_events"] == 1000

    def planning(event):
        event_bus.create_action(
            event, workflow_key="synthetic-health-bulk",
            step_key="review-job", target_module="planning",
        )

    event_bus.subscribe(event_type, planning)
    create_app({"TESTING": True})  # simulated restart; reuse the same SQL and event bus
    after = _by_type(event_bus.delivery_diagnostics(), event_type)
    assert after["delivered"] == 1000
    assert after["pending_delivery"] == 0
    assert after["without_typed_subscriber_events"] == 0
    assert after["delivered_missing_current_receipts"] == 0
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-health-bulk'"
        ).fetchone()[0] == 1000
        assert con.execute(
            """SELECT COUNT(*) FROM event_delivery_receipts
               WHERE event_type=? AND status='delivered' AND handler_key=?""",
            (event_type, event_bus._handler_key(planning)),
        ).fetchone()[0] == 1000
    create_app({"TESTING": True})  # repeat startup is idempotent
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='synthetic-health-bulk'"
        ).fetchone()[0] == 1000
