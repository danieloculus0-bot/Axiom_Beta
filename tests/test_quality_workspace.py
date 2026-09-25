from __future__ import annotations

def test_quality_case_workspace_and_car(tmp_path,monkeypatch):
    monkeypatch.setenv("SUPERFORGE_DATA_DIR",str(tmp_path/"quality-data"))
    from superforge.app import create_app
    from superforge.audit import verify_journal
    from superforge.db import db

    app=create_app({"TESTING":True})
    client=app.test_client()

    created=client.post("/quality/new",data={
        "record_type":"NCR",
        "record_number":"NCR-QW-001",
        "severity":"high",
        "quantity_affected":"3",
        "quantity_shipped":"3000",
        "description":"Hole pattern out of tolerance",
        "containment":"Quarantine affected work",
        "owner":"Quality",
        "actor":"qe",
    },follow_redirects=False)
    assert created.status_code in {302,303}

    with db() as con:
        q=con.execute("SELECT id FROM quality_records WHERE record_number='NCR-QW-001'").fetchone()
        assert q is not None
        record_id=int(q["id"])

    view=client.get(f"/quality/{record_id}")
    assert view.status_code==200
    assert b"Quality Forge" in view.data
    assert b"Immediate Containment" in view.data
    assert b"Corrective Action" in view.data
    assert b"Case Audit Trail" in view.data

    car=client.post(f"/quality/{record_id}",data={
        "action":"create_car",
        "car_number":"CAR-QW-001",
        "problem_statement":"Recurring hole pattern failure",
        "car_owner":"Quality",
        "root_cause_due":"2026-09-30",
        "action_due":"2026-10-10",
        "actor":"qe",
    },follow_redirects=True)
    assert car.status_code==200
    assert b"CAR-QW-001" in car.data
    assert b"Why 1" in car.data

    with db() as con:
        row=con.execute("SELECT id FROM corrective_actions WHERE car_number='CAR-QW-001'").fetchone()
        assert row is not None
        car_id=int(row["id"])

    saved=client.post(f"/quality/{record_id}",data={
        "action":"save_five_why",
        "car_id":str(car_id),
        "why1":"Feature was formed incorrectly",
        "why2":"Tooling setup was wrong",
        "why3":"Setup verification was skipped",
        "why4":"Routing did not require the check",
        "why5":"Planning template lacked the control",
        "car_root_cause":"Routing lacked a mandatory setup verification gate",
        "car_corrective_action":"Add setup verification to the routing",
        "car_preventive_action":"Apply the gate to similar routed operations",
        "actor":"qe",
    },follow_redirects=True)
    assert saved.status_code==200
    assert b"Routing lacked a mandatory setup verification gate" in saved.data

    closed=client.post(f"/quality/{record_id}",data={
        "action":"update_record",
        "severity":"high",
        "status":"closed",
        "owner":"Quality",
        "description":"Hole pattern out of tolerance",
        "containment":"Quarantine affected work",
        "disposition":"Rework",
        "root_cause":"Routing lacked setup verification",
        "corrective_action":"Add setup verification",
        "preventive_action":"Template control added",
        "effectiveness":"Verify next three jobs",
        "actor":"qe",
        "change_reason":"Corrective action complete",
    },follow_redirects=True)
    assert closed.status_code==200

    with db() as con:
        effectiveness=con.execute("SELECT COUNT(*) n FROM workflow_actions WHERE workflow_key='quality-effectiveness' AND entity_id=?",(str(record_id),)).fetchone()["n"]
        assert effectiveness>=1

    assert verify_journal()["ok"] is True
