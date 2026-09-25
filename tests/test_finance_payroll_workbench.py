from __future__ import annotations

import csv
import io

import pytest


def test_payroll_posts_balanced_ledger_and_payment(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))

    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.finance import (
        approve_pay_run,
        create_employee,
        create_pay_run,
        mark_pay_run_paid,
        payroll_run_snapshot,
        trial_balance,
        upsert_pay_item,
    )

    app = create_app({"TESTING": True})
    assert app.test_client().get("/payroll").status_code == 200
    assert app.test_client().get("/accounting").status_code == 200
    assert app.test_client().get("/sheets").status_code == 200

    create_employee(
        "EMP-001",
        "Hourly Tester",
        department="Fabrication",
        pay_type="hourly",
        hourly_rate="25.00",
        overtime_multiplier="1.5",
        actor="hr",
    )
    run_id = create_pay_run(
        "2026-09-14",
        "2026-09-20",
        "2026-09-25",
        pay_group="WEEKLY",
        run_key="PAY-TEST-001",
        actor="hr",
    )
    upsert_pay_item(
        run_id,
        "EMP-001",
        regular_hours="40",
        overtime_hours="5",
        bonus="100",
        tax_withheld="200",
        other_deductions="50",
        payment_method="direct deposit",
        actor="payroll",
    )

    snap = payroll_run_snapshot(run_id)
    assert snap["totals"] == {
        "gross": 1287.5,
        "tax": 200.0,
        "deductions": 50.0,
        "net": 1037.5,
    }

    approval_journal = approve_pay_run(run_id, actor="payroll-approver")
    with db() as con:
        lines = con.execute(
            "SELECT debit,credit FROM finance_journal_lines WHERE journal_id=?",
            (approval_journal,),
        ).fetchall()
        assert round(sum(float(x["debit"]) for x in lines), 2) == 1287.50
        assert round(sum(float(x["credit"]) for x in lines), 2) == 1287.50

    payment_journal = mark_pay_run_paid(
        run_id,
        payment_reference="ACH-2026-09-25-001",
        payment_method="direct deposit",
        actor="payroll",
    )
    assert payment_journal != approval_journal

    with db() as con:
        run = con.execute("SELECT * FROM payroll_runs WHERE id=?", (run_id,)).fetchone()
        assert run["status"] == "paid"
        assert run["payment_reference"] == "ACH-2026-09-25-001"
        item = con.execute("SELECT * FROM payroll_items WHERE run_id=?", (run_id,)).fetchone()
        assert item["status"] == "paid"
        assert item["payment_reference"] == "ACH-2026-09-25-001"

    balances = {row["code"]: row for row in trial_balance()}
    assert balances["6100"]["balance"] == 1287.5
    assert balances["2120"]["balance"] == 0.0
    assert balances["1000"]["balance"] == -1037.5


def test_salary_pay_and_unbalanced_journal_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom2"))

    from superforge.app import create_app
    from superforge.modules.finance import (
        create_employee,
        create_pay_run,
        payroll_run_snapshot,
        post_journal_entry,
        upsert_pay_item,
    )

    create_app({"TESTING": True})
    create_employee(
        "EMP-SAL",
        "Salary Tester",
        pay_type="salary",
        annual_salary="52000",
        pay_periods_per_year=52,
        actor="hr",
    )
    run_id = create_pay_run(
        "2026-09-14",
        "2026-09-20",
        "2026-09-25",
        run_key="PAY-SAL-001",
        actor="hr",
    )
    upsert_pay_item(run_id, "EMP-SAL", tax_withheld="150", other_deductions="25", actor="payroll")
    snap = payroll_run_snapshot(run_id)
    assert snap["items"][0]["regular_pay"] == 1000.0
    assert snap["items"][0]["net_pay"] == 825.0

    with pytest.raises(ValueError, match="not balanced"):
        post_journal_entry(
            "2026-09-25",
            "Bad entry",
            [
                {"account_code": "1000", "debit": 100},
                {"account_code": "4000", "credit": 99},
            ],
            actor="tester",
        )


def test_sheet_workbench_formula_import_export_and_payroll_post(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom3"))

    from superforge.app import create_app
    from superforge.modules.finance import (
        create_employee,
        create_pay_run,
        evaluate_formula,
        export_sheet_csv,
        export_sheet_xlsx,
        import_sheet_bytes,
        post_payroll_sheet,
        save_sheet_rows,
        sheet_snapshot,
        template_sheet,
    )

    create_app({"TESTING": True})
    create_employee("EMP-002", "Sheet Tester", pay_type="hourly", hourly_rate="20", actor="hr")
    run_id = create_pay_run(
        "2026-09-21",
        "2026-09-27",
        "2026-10-02",
        run_key="PAY-SHEET-001",
        actor="hr",
    )

    assert evaluate_formula("=Regular_Hours*Hourly_Rate", {"Regular Hours": 40, "Hourly Rate": 20}) == 800.0
    with pytest.raises(ValueError):
        evaluate_formula("=__import__('os').system(1)", {})

    sheet_id = template_sheet("payroll", name="Weekly Payroll", actor="payroll")
    save_sheet_rows(
        sheet_id,
        [{
            "Employee Ref": "EMP-002",
            "Regular Hours": "40",
            "OT Hours": "2",
            "Bonus": "25",
            "Tax Withheld": "125",
            "Other Deductions": "20",
            "Gross Preview": "",
            "Net Preview": "",
        }],
        actor="payroll",
    )
    assert post_payroll_sheet(sheet_id, run_id, actor="payroll") == 1
    snap = sheet_snapshot(sheet_id, evaluate=False)
    assert snap["status"] == "posted"
    assert snap["posted_entity_type"] == "payroll_run"

    csv_text = export_sheet_csv(sheet_id)
    assert "EMP-002" in csv_text
    assert export_sheet_xlsx(sheet_id).startswith(b"PK")

    import_id = template_sheet("blank", name="Imported", actor="tester")
    source = b"Part,Qty,Rate\nP-100,4,12.50\n"
    import_sheet_bytes(import_id, "parts.csv", source, actor="tester")
    imported = sheet_snapshot(import_id, evaluate=False)
    assert imported["columns"] == ["Part", "Qty", "Rate"]
    assert imported["rows"][0]["Part"] == "P-100"


def test_finance_routes_and_context_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom4"))

    from superforge.app import create_app

    client = create_app({"TESTING": True}).test_client()
    for route in ["/payroll", "/accounting", "/sheets"]:
        assert client.get(route).status_code == 200

    menu = client.get("/api/context-menu?entity_type=clocking_error&entity_id=1&current_module=clocking").get_json()
    labels = {x["label"] for x in menu["items"]}
    assert "Payroll" in labels
    assert "Sheet Workbench" in labels
