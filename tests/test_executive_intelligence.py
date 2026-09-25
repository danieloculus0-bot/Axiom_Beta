from __future__ import annotations


def test_decision_protocol_routes_signal_through_org_and_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom-exec"))

    from superforge.app import create_app
    from superforge.db import db
    from superforge.event_bus import publish
    from superforge.modules.executive import (
        accept_executive_suggestion,
        assign_person_to_role,
        capture_executive_outcome,
        pareto_queue,
        upsert_person,
    )

    app = create_app({"TESTING": True})
    client = app.test_client()
    assert client.get("/executive").status_code == 200

    upsert_person(
        "quality.lead",
        "Quality Lead",
        email="quality.lead@example.com",
        actor="admin",
    )
    assign_person_to_role(
        "quality.lead",
        "quality_manager",
        primary=True,
        actor="admin",
    )

    event = publish(
        "quality.created",
        source_module="quality",
        entity_type="quality_record",
        entity_id="NCR-9001",
        actor="quality-engineer",
        reason="Critical customer escape",
        payload={
            "severity": "critical",
            "impact_score": 1.0,
            "urgency_score": 0.95,
            "confidence": 0.90,
            "job_id": 10,
            "quantity_affected": 5,
        },
    )

    with db() as con:
        suggestion = con.execute(
            """SELECT * FROM module_suggestions
               WHERE source_event_id=? AND suggestion_key LIKE 'exec:%'
               ORDER BY id DESC LIMIT 1""",
            (event.event_id,),
        ).fetchone()
        assert suggestion is not None
        suggestion_id = int(suggestion["id"])

    pareto = pareto_queue()
    assert pareto["open_count"] >= 1
    assert pareto["pareto_count"] >= 1
    assert pareto["pareto_impact_share"] >= 0.80
    assert any(int(row["id"]) == suggestion_id for row in pareto["signals"])

    action_id = accept_executive_suggestion(suggestion_id, actor="general-manager")
    with db() as con:
        action = con.execute("SELECT * FROM workflow_actions WHERE id=?", (action_id,)).fetchone()
        suggestion = con.execute("SELECT * FROM module_suggestions WHERE id=?", (suggestion_id,)).fetchone()
        assert action is not None
        assert action["assigned_to"] == "quality.lead@example.com"
        assert action["status"] == "open"
        assert suggestion["status"] == "accepted"
        assert int(suggestion["accepted_action_id"]) == action_id

    observation_id = capture_executive_outcome(
        suggestion_id,
        outcome="Containment completed and repeat escape prevented",
        human_rating=4.5,
        actor="general-manager",
    )
    with db() as con:
        observation = con.execute(
            "SELECT * FROM learning_observations WHERE id=?",
            (observation_id,),
        ).fetchone()
        assert observation is not None
        assert observation["signal_key"].startswith("executive:")
        assert observation["outcome"] == "Containment completed and repeat escape prevented"
        assert float(observation["human_rating"]) == 4.5


def test_org_defaults_and_protocols_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom-org"))

    from superforge.app import create_app
    from superforge.db import db

    create_app({"TESTING": True})
    with db() as con:
        roles = {
            row["role_key"]
            for row in con.execute("SELECT role_key FROM org_roles WHERE active=1")
        }
        protocols = {
            row["event_type"]
            for row in con.execute("SELECT event_type FROM decision_protocols WHERE active=1")
        }

    assert {"general_manager", "operations_manager", "quality_manager", "purchasing_manager", "payroll_manager"} <= roles
    assert {"quality.created", "po.late", "inventory.shortage", "pm.failed", "morale.pulse.recorded"} <= protocols
