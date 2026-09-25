from __future__ import annotations


def test_iso_hungry_report_to_pay_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERFORGE_DATA_DIR", str(tmp_path / "data"))

    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.iso_hungry import (
        approve_earning,
        approve_pay_batch,
        create_cash_policy,
        create_pay_batch,
        export_pay_batch_csv,
        mark_pay_batch_paid,
        record_reported_event,
        reporting_snapshot,
        upsert_pay_profile,
    )
    from superforge.modules.leadership import create_reward_account
    from superforge.modules.reward_rules import create_reward_rule

    create_app({"TESTING": True})

    account_id = create_reward_account(
        "EMP-CARD-001",
        display_name="Test Employee",
        department="Fabrication",
        actor="tester",
    )
    profile_id = upsert_pay_profile(
        account_id,
        employee_ref="EMP-001",
        payroll_ref="PAYROLL-001",
        pay_group="WEEKLY",
        actor="tester",
    )
    assert profile_id > 0

    create_reward_rule(
        {
            "name": "Reported throughput recognition",
            "event_type": "report.throughput",
            "source_module": "reporting",
            "account_payload_key": "reward_account_id",
            "payload_key": "good_units",
            "operator": "gte",
            "payload_value": "100",
            "category": "throughput",
            "points": "10",
            "requires_approval": "0",
            "period_limit_points": "0",
        },
        actor="tester",
    )
    create_cash_policy(
        {
            "name": "Throughput cash recognition",
            "reward_category": "throughput",
            "source_module": "reporting",
            "earning_code": "ISOH_BONUS",
            "currency": "USD",
            "dollars_per_point": "0.50",
            "fixed_amount": "0",
            "max_event_amount": "25",
            "rolling_30d_limit": "100",
            "requires_approval": "1",
        },
        actor="tester",
    )

    report_event = record_reported_event(
        "report.throughput",
        reward_account_id=account_id,
        source_module="reporting",
        entity_type="production_report",
        entity_id="SHIFT-2026-09-24-A",
        actor="supervisor",
        reason="Verified shift production report",
        payload={"good_units": 120, "scrap_units": 1},
    )
    assert report_event.event_id.startswith("evt_")

    with db() as con:
        reward = con.execute(
            "SELECT * FROM reward_events WHERE account_id=? ORDER BY id DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        earning = con.execute(
            "SELECT * FROM iso_hungry_earnings WHERE reward_event_id=?",
            (reward["id"],),
        ).fetchone()
        assert reward["points"] == 10
        assert earning["status"] == "pending"
        assert earning["amount"] == 5.0
        earning_id = int(earning["id"])

    approve_earning(earning_id, actor="payroll-reviewer")
    with db() as con:
        assert con.execute(
            "SELECT status FROM iso_hungry_earnings WHERE id=?", (earning_id,)
        ).fetchone()["status"] == "approved"

    batch_id = create_pay_batch(
        "2026-09-01",
        "2026-09-30",
        pay_group="WEEKLY",
        batch_key="ISOH-TEST-2026-09",
        actor="payroll-reviewer",
    )
    approve_pay_batch(batch_id, actor="payroll-approver")
    csv_text = export_pay_batch_csv(batch_id, actor="payroll-export")
    assert "EMP-001" in csv_text
    assert "PAYROLL-001" in csv_text
    assert "ISOH_BONUS" in csv_text
    assert ",5.00," in csv_text

    mark_pay_batch_paid(
        batch_id,
        payment_reference="PAYROLL-RUN-2026-09-30",
        actor="payroll-confirmation",
    )
    with db() as con:
        batch = con.execute(
            "SELECT status,export_sha256,payment_reference FROM iso_hungry_pay_batches WHERE id=?",
            (batch_id,),
        ).fetchone()
        earning = con.execute(
            "SELECT status FROM iso_hungry_earnings WHERE id=?", (earning_id,)
        ).fetchone()
        assert batch["status"] == "paid"
        assert batch["export_sha256"]
        assert batch["payment_reference"] == "PAYROLL-RUN-2026-09-30"
        assert earning["status"] == "paid"

    snap = reporting_snapshot()
    assert snap["paid_batches"] == 1
    assert snap["paid_amount"] == 5.0


def test_iso_hungry_missing_profile_becomes_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERFORGE_DATA_DIR", str(tmp_path / "data2"))

    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.iso_hungry import create_cash_policy, record_reported_event
    from superforge.modules.leadership import create_reward_account
    from superforge.modules.reward_rules import create_reward_rule

    create_app({"TESTING": True})
    account_id = create_reward_account("EMP-CARD-002", actor="tester")

    create_reward_rule(
        {
            "name": "Quality cash exception test",
            "event_type": "report.quality_win",
            "source_module": "reporting",
            "account_payload_key": "reward_account_id",
            "payload_key": "verified",
            "operator": "truthy",
            "category": "quality",
            "points": "4",
            "requires_approval": "0",
        },
        actor="tester",
    )
    create_cash_policy(
        {
            "name": "Quality cash test policy",
            "reward_category": "quality",
            "source_module": "reporting",
            "dollars_per_point": "1",
            "requires_approval": "1",
        },
        actor="tester",
    )

    record_reported_event(
        "report.quality_win",
        reward_account_id=account_id,
        source_module="reporting",
        entity_type="inspection",
        entity_id="I-100",
        actor="supervisor",
        payload={"verified": True},
    )
    with db() as con:
        exc = con.execute(
            "SELECT * FROM iso_hungry_exceptions WHERE reward_account_id=? AND status='open'",
            (account_id,),
        ).fetchone()
        assert exc is not None
        assert exc["reason_code"] == "missing_pay_profile"
