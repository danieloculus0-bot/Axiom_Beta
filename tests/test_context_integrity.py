from __future__ import annotations


def test_context_identity_and_open_record_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom-context"))

    from superforge.app import create_app
    from superforge.audit import tail_entries
    from superforge.db import db
    from superforge.event_bus import publish
    from superforge.modules.finance import (
        create_employee,
        create_pay_run,
        post_journal_entry,
        template_sheet,
    )

    app = create_app({"TESTING": True})
    client = app.test_client()

    create_employee("CTX-EMP", "Context Employee", hourly_rate="20", actor="tester")
    run_id = create_pay_run(
        "2026-09-21", "2026-09-27", "2026-10-02",
        run_key="CTX-PAY", actor="tester",
    )
    journal_id = post_journal_entry(
        "2026-09-24", "Context journal",
        [
            {"account_code": "1000", "debit": 10},
            {"account_code": "3000", "credit": 10},
        ],
        actor="tester",
    )
    sheet_id = template_sheet("blank", name="Context Sheet", actor="tester")

    with db() as con:
        quote_id = int(con.execute(
            "INSERT INTO quote_intakes(quote_number,status) VALUES('CTX-Q-1','new')"
        ).lastrowid)
        ppap_id = int(con.execute(
            "INSERT INTO ppap_packages(ppap_number,level,status) VALUES('CTX-P-1',3,'draft')"
        ).lastrowid)

    event = publish(
        "context.test",
        source_module="test",
        entity_type="job",
        entity_id="1",
        actor="tester",
    )
    with db() as con:
        action_id = int(con.execute(
            """INSERT INTO workflow_actions(
                 event_id,workflow_key,step_key,source_module,target_module,entity_type,entity_id,status
               ) VALUES(?,?,?,?,?,?,?,'open')""",
            (event.event_id, "ctx", "review", "test", "planning", "job", "1"),
        ).lastrowid)

    for entity_type, entity_id in [
        ("payroll_run", run_id),
        ("finance_journal", journal_id),
        ("sheet_book", sheet_id),
        ("quote_intake", quote_id),
        ("ppap_package", ppap_id),
        ("workflow_action", action_id),
    ]:
        response = client.get(f"/context/{entity_type}/{entity_id}")
        assert response.status_code == 200, (entity_type, response.data[:200])

    assert b"data-entity-type='workflow_action'" in client.get("/planning").data
    assert b"data-entity-type='quote_intake'" in client.get("/quoting").data
    assert b"data-entity-type='ppap_package'" in client.get("/ppap").data

    audit_row = tail_entries(1)[0]
    assert client.get(f"/context/audit_event/{audit_row['sequence']}").status_code == 200
