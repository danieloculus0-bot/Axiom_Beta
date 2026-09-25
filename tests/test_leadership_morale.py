from __future__ import annotations


def test_leadership_and_automation(tmp_path,monkeypatch):
    monkeypatch.setenv("SUPERFORGE_DATA_DIR",str(tmp_path/"data"))

    from superforge.app import create_app
    from superforge.db import db
    from superforge.event_bus import publish
    from superforge.modules.automation import create_automation_rule
    from superforge.modules.reward_rules import create_reward_rule
    from superforge.modules.leadership import (
        award_points,
        complete_training,
        create_reward_account,
        create_training_requirement,
        record_morale_pulse,
        reward_balance,
    )

    app=create_app({"TESTING":True})
    client=app.test_client()
    assert client.get("/leadership").status_code==200
    assert client.get("/automation").status_code==200

    pulse_id=record_morale_pulse({
        "period_start":"2026-09-01",
        "period_end":"2026-09-24",
        "department":"Fabrication",
        "scheduled_headcount":20,
        "present_headcount":16,
        "overtime_hours":160,
        "over_50_hours_count":6,
        "exhausted_pto_count":4,
        "pto_absence_count":3,
        "sick_absence_clusters":4,
        "turnover_count":2,
        "staffing_shortage_count":4,
        "quality_risk_signal":70,
    },actor="tester")

    with db() as con:
        pulse=con.execute("SELECT * FROM morale_pulses WHERE id=?",(pulse_id,)).fetchone()
        assert pulse["risk_score"]>=60
        action=con.execute(
            "SELECT id FROM workflow_actions WHERE workflow_key='morale-response' AND entity_id=?",
            (str(pulse_id),),
        ).fetchone()
        assert action is not None

    account_id=create_reward_account("CARD-100",display_name="Participant",department="Fabrication",vendor_ref="VENDOR-100",actor="tester")
    award_points(account_id,25,category="quality",reason="First-pass recognition",approved_by="tester")
    assert reward_balance(account_id)==25

    training_id=create_training_requirement({
        "training_key":"ISO-AWARENESS",
        "title":"ISO 9001 Awareness",
        "department":"Fabrication",
        "recurrence_days":365,
        "reward_points":10,
    },actor="tester")
    complete_training(training_id,account_id,completed_by="Participant",verified_by="tester",evidence_ref="training-matrix")
    assert reward_balance(account_id)==35

    create_reward_rule({
        "name":"Automatic FPY recognition",
        "event_type":"quality.excellence",
        "source_module":"quality",
        "account_payload_key":"reward_account_id",
        "payload_key":"fpy",
        "operator":"gte",
        "payload_value":"99",
        "category":"quality",
        "points":"5",
        "requires_approval":"0",
        "period_limit_points":"50",
    },actor="tester")
    publish(
        "quality.excellence",source_module="quality",entity_type="job",entity_id="42",
        actor="tester",payload={"reward_account_id":account_id,"fpy":99.5},
    )
    assert reward_balance(account_id)==40

    create_reward_rule({
        "name":"Capped recognition",
        "event_type":"quality.capped",
        "source_module":"quality",
        "account_payload_key":"reward_account_id",
        "category":"quality",
        "points":"5",
        "requires_approval":"0",
        "period_limit_points":"1",
    },actor="tester")
    capped_event=publish(
        "quality.capped",source_module="quality",entity_type="job",entity_id="42",
        actor="tester",payload={"reward_account_id":account_id},
    )
    assert reward_balance(account_id)==40
    with db() as con:
        held=con.execute(
            "SELECT status FROM reward_nominations WHERE source_event_id=?",
            (capped_event.event_id,),
        ).fetchone()
        assert held["status"]=="held_limit"

    rule_id=create_automation_rule({
        "name":"Escalate serious test signal",
        "event_type":"test.signal",
        "source_module":"test",
        "payload_key":"severity",
        "operator":"gte",
        "payload_value":"3",
        "workflow_key":"test-escalation",
        "step_key":"leadership-review",
        "target_module":"leadership",
        "assigned_to":"Operations",
        "due_days":"2",
        "enabled":"1",
        "priority":"10",
    },actor="tester")

    event=publish("test.signal",source_module="test",entity_type="job",entity_id="42",actor="tester",payload={"severity":4})
    with db() as con:
        action=con.execute(
            "SELECT * FROM workflow_actions WHERE workflow_key='test-escalation' AND event_id=?",
            (event.event_id,),
        ).fetchone()
        assert action is not None
        run=con.execute(
            "SELECT * FROM automation_rule_runs WHERE rule_id=? AND source_event_id=?",
            (rule_id,event.event_id),
        ).fetchone()
        assert run is not None
        assert run["workflow_action_id"]==action["id"]


def test_morale_risk_is_bounded():
    from superforge.modules.leadership import calculate_morale_risk

    assert calculate_morale_risk({})==0.0
    score=calculate_morale_risk({
        "scheduled_headcount":10,
        "present_headcount":0,
        "overtime_hours":10000,
        "turnover_count":100,
        "staffing_shortage_count":100,
        "quality_risk_signal":500,
    })
    assert 0.0<=score<=100.0
