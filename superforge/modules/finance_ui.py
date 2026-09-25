from __future__ import annotations

import html
import io
import json

from flask import Blueprint, Response, redirect, request, send_file

from ..db import db
from ..ui import page
from .finance import (
    approve_pay_run,
    apply_approved_iso_hungry_earnings,
    create_account,
    create_employee,
    create_pay_run,
    export_sheet_csv,
    export_sheet_xlsx,
    import_sheet_bytes,
    mark_pay_run_paid,
    payroll_run_snapshot,
    post_journal_sheet,
    post_payroll_sheet,
    save_sheet_rows,
    seed_finance_defaults,
    sheet_snapshot,
    template_sheet,
    trial_balance,
    upsert_pay_item,
)

finance_blueprint = Blueprint("finance_module", __name__)


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _money(value) -> str:
    try:
        return "$" + f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


@finance_blueprint.get("/payroll")
def payroll_dashboard():
    seed_finance_defaults()
    with db() as con:
        employees = [dict(r) for r in con.execute(
            "SELECT * FROM payroll_employees ORDER BY status,display_name,employee_ref"
        )]
        runs = [dict(r) for r in con.execute(
            "SELECT * FROM payroll_runs ORDER BY id DESC LIMIT 60"
        )]
        bonuses = [dict(r) for r in con.execute(
            """SELECT e.id,pr.employee_ref,e.amount,e.status,e.earning_code,e.reason,e.created_at
               FROM iso_hungry_earnings e
               JOIN iso_hungry_pay_profiles pr ON pr.id=e.profile_id
               WHERE e.status IN ('pending','approved','held_limit')
               ORDER BY e.id DESC LIMIT 40"""
        )]

    employee_rows = "".join(
        f"<tr class='sf-context' data-entity-type='payroll_employee' data-entity-id='{r['id']}' data-entity-label='{_e(r['display_name'])}'>"
        f"<td>{_e(r['employee_ref'])}</td><td>{_e(r['display_name'])}</td><td>{_e(r['department'])}</td>"
        f"<td>{_e(r['pay_type'])}</td><td>{_money(r['hourly_rate'])}</td><td>{_money(r['annual_salary'])}</td><td>{_e(r['status'])}</td></tr>"
        for r in employees
    ) or "<tr><td colspan='7' class='empty'>No payroll employees.</td></tr>"

    run_rows = "".join(
        f"<tr class='sf-context' data-entity-type='payroll_run' data-entity-id='{r['id']}' data-entity-label='{_e(r['run_key'])}'>"
        f"<td><a href='/payroll/run/{r['id']}'>{_e(r['run_key'])}</a></td><td>{_e(r['period_start'])} - {_e(r['period_end'])}</td>"
        f"<td>{_e(r['check_date'])}</td><td>{_e(r['pay_group'])}</td><td><span class='badge accent'>{_e(r['status'])}</span></td>"
        f"<td>{_money(r['gross_total'])}</td><td>{_money(r['net_total'])}</td></tr>"
        for r in runs
    ) or "<tr><td colspan='7' class='empty'>No pay runs.</td></tr>"

    bonus_rows = "".join(
        f"<tr><td>{_e(r['employee_ref'])}</td><td>{_e(r['earning_code'])}</td><td>{_money(r['amount'])}</td><td>{_e(r['status'])}</td><td>{_e(r['reason'])}</td></tr>"
        for r in bonuses
    ) or "<tr><td colspan='5' class='empty'>No open ISO-Hungry earnings.</td></tr>"

    body = f"""<section class='page-head'><div class='grow'>
<p class='eyebrow'>HR / Payroll</p><h1>Payroll</h1>
<p class='sub'>Regular checks, hourly/salary pay, overtime, bonuses, withholdings, deductions, approvals, payment receipts and automatic accounting entries. Tax amounts are explicit inputs/imports until a jurisdiction-specific tax adapter is configured.</p>
</div><a class='button secondary' href='/sheets'>Open Sheet Workbench</a></section>

<div class='grid'>
<details class='panel'><summary><b>Add / update employee</b></summary>
<form method='post' action='/payroll/employee' class='form-grid' style='margin-top:12px'>
<label>Employee Ref<input name='employee_ref' required></label><label>Name<input name='display_name' required></label>
<label>Department<input name='department'></label><label>Pay Type<select name='pay_type'><option value='hourly'>Hourly</option><option value='salary'>Salary</option></select></label>
<label>Hourly Rate<input type='number' step='.01' name='hourly_rate' value='0'></label><label>Annual Salary<input type='number' step='.01' name='annual_salary' value='0'></label>
<label>Pay Periods / Year<input type='number' name='pay_periods_per_year' value='52'></label><label>OT Multiplier<input type='number' step='.01' name='overtime_multiplier' value='1.5'></label>
<label>Payment Method<select name='default_payment_method'><option>check</option><option>direct deposit</option><option>other</option></select></label>
<label>Actor<input name='actor' value='local'></label><div><button>Save Employee</button></div></form></details>

<details class='panel'><summary><b>Create pay run</b></summary>
<form method='post' action='/payroll/run' class='form-grid' style='margin-top:12px'>
<label>Period Start<input type='date' name='period_start' required></label><label>Period End<input type='date' name='period_end' required></label>
<label>Check Date<input type='date' name='check_date' required></label><label>Pay Group<input name='pay_group' value='WEEKLY'></label>
<label>Run Key<input name='run_key' placeholder='Optional'></label><label>Actor<input name='actor' value='local'></label>
<div><button>Create Pay Run</button></div></form></details>
</div>

<div class='panel'><h2>Employees</h2><table><tr><th>Employee</th><th>Name</th><th>Department</th><th>Type</th><th>Hourly</th><th>Salary</th><th>Status</th></tr>{employee_rows}</table></div>
<div class='panel'><h2>Pay Runs</h2><table><tr><th>Run</th><th>Period</th><th>Check Date</th><th>Group</th><th>Status</th><th>Gross</th><th>Net</th></tr>{run_rows}</table></div>
<div class='panel'><h2>ISO-Hungry Earnings Available to Payroll</h2>
<p class='sub'>Recognition cash remains approval-controlled and separate from ordinary payroll. It can be reviewed here without silently changing a paycheck.</p>
<table><tr><th>Employee</th><th>Code</th><th>Amount</th><th>Status</th><th>Reason</th></tr>{bonus_rows}</table></div>"""
    return page("Payroll", body, module_key="payroll")


@finance_blueprint.post("/payroll/employee")
def payroll_employee_post():
    create_employee(
        request.form.get("employee_ref", ""),
        request.form.get("display_name", ""),
        department=request.form.get("department", ""),
        pay_type=request.form.get("pay_type", "hourly"),
        hourly_rate=request.form.get("hourly_rate") or 0,
        annual_salary=request.form.get("annual_salary") or 0,
        pay_periods_per_year=int(request.form.get("pay_periods_per_year") or 52),
        overtime_multiplier=request.form.get("overtime_multiplier") or 1.5,
        default_payment_method=request.form.get("default_payment_method") or "check",
        actor=request.form.get("actor") or "local",
    )
    return redirect("/payroll")


@finance_blueprint.post("/payroll/run")
def payroll_run_post():
    run_id = create_pay_run(
        request.form.get("period_start", ""),
        request.form.get("period_end", ""),
        request.form.get("check_date", ""),
        pay_group=request.form.get("pay_group") or "WEEKLY",
        run_key=request.form.get("run_key") or "",
        actor=request.form.get("actor") or "local",
    )
    return redirect(f"/payroll/run/{run_id}")


@finance_blueprint.get("/payroll/run/<int:run_id>")
def payroll_run_detail(run_id: int):
    snap = payroll_run_snapshot(run_id)
    run, items, totals = snap["run"], snap["items"], snap["totals"]
    with db() as con:
        employees = [dict(r) for r in con.execute(
            "SELECT employee_ref,display_name FROM payroll_employees WHERE status='active' ORDER BY display_name"
        )]
    options = "".join(f"<option value='{_e(r['employee_ref'])}'>{_e(r['display_name'])} - {_e(r['employee_ref'])}</option>" for r in employees)
    rows = "".join(
        f"<tr><td>{_e(x['employee_ref'])}</td><td>{_e(x['display_name'])}</td><td>{x['regular_hours']}</td><td>{x['overtime_hours']}</td>"
        f"<td>{_money(x['bonus'])}</td><td>{_money(x['gross_pay'])}</td><td>{_money(x['tax_withheld'])}</td>"
        f"<td>{_money(x['other_deductions'])}</td><td>{_money(x['net_pay'])}</td><td>{_e(x['payment_method'])}</td></tr>"
        for x in items
    ) or "<tr><td colspan='10' class='empty'>No payroll items.</td></tr>"
    controls = ""
    import_notice = ""
    imported_count = request.args.get("recognition_imported")
    skipped_count = request.args.get("recognition_skipped")
    if imported_count is not None:
        import_notice = (
            f"<div class='notice'>Recognition import: <b>{_e(imported_count)}</b> imported, "
            f"<b>{_e(skipped_count or 0)}</b> skipped. Pending or held recognition is never pulled into payroll.</div>"
        )
    if run["status"] == "draft":
        controls = f"""<details class='panel'><summary><b>Add / update paycheck</b></summary>
<form method='post' action='/payroll/run/{run_id}/item' class='form-grid' style='margin-top:12px'>
<label>Employee<select name='employee_ref' required>{options}</select></label>
<label>Regular Hours<input type='number' step='.01' name='regular_hours' value='0'></label>
<label>OT Hours<input type='number' step='.01' name='overtime_hours' value='0'></label>
<label>Bonus<input type='number' step='.01' name='bonus' value='0'></label>
<label>Tax Withheld<input type='number' step='.01' name='tax_withheld' value='0'></label>
<label>Other Deductions<input type='number' step='.01' name='other_deductions' value='0'></label>
<label>Payment Method<select name='payment_method'><option>check</option><option>direct deposit</option><option>other</option></select></label>
<label>Actor<input name='actor' value='local'></label><label class='wide'>Notes<textarea name='notes'></textarea></label><div><button>Save Paycheck</button></div>
</form></details>
<div class='toolbar'>
<form method='post' action='/payroll/run/{run_id}/import-recognition'><input type='hidden' name='actor' value='local'><button class='secondary'>Import Approved ISO-Hungry Earnings</button></form>
<form method='post' action='/payroll/run/{run_id}/approve'><input type='hidden' name='actor' value='local'><button>Approve & Post to Ledger</button></form>
</div>"""
    elif run["status"] == "approved":
        controls = f"""<form method='post' action='/payroll/run/{run_id}/paid' class='panel form-grid'>
<label>Payment Reference<input name='payment_reference' required placeholder='ACH batch / check run / bank ref'></label>
<label>Method<select name='payment_method'><option>mixed</option><option>checks</option><option>direct deposit</option></select></label>
<label>Actor<input name='actor' value='local'></label><div><br><button>Mark Paid & Clear Cash</button></div></form>"""

    body = f"""<section class='page-head'><div class='grow'><p class='eyebrow'>Payroll Run</p><h1>{_e(run['run_key'])}</h1>
<p class='sub'>{_e(run['period_start'])} through {_e(run['period_end'])} · check date {_e(run['check_date'])} · <b>{_e(run['status'])}</b></p></div>
<a class='button secondary' href='/payroll'>Back to Payroll</a></section>
<div class='grid'>
<div class='card'><strong class='big'>{_money(totals['gross'])}</strong><span class='label'>Gross</span></div>
<div class='card'><strong class='big'>{_money(totals['tax'])}</strong><span class='label'>Tax Withheld</span></div>
<div class='card'><strong class='big'>{_money(totals['deductions'])}</strong><span class='label'>Other Deductions</span></div>
<div class='card'><strong class='big'>{_money(totals['net'])}</strong><span class='label'>Net Pay</span></div>
</div>{import_notice}{controls}
<div class='panel' style='margin-top:14px'><h2>Paychecks</h2><table><tr><th>Employee</th><th>Name</th><th>Reg Hrs</th><th>OT Hrs</th><th>Bonus</th><th>Gross</th><th>Tax</th><th>Deductions</th><th>Net</th><th>Method</th></tr>{rows}</table></div>"""
    return page(f"Payroll {run['run_key']}", body, module_key="payroll", context_type="payroll_run", context_id=str(run_id))


@finance_blueprint.post("/payroll/run/<int:run_id>/item")
def payroll_item_post(run_id: int):
    upsert_pay_item(
        run_id,
        request.form.get("employee_ref", ""),
        regular_hours=request.form.get("regular_hours") or 0,
        overtime_hours=request.form.get("overtime_hours") or 0,
        bonus=request.form.get("bonus") or 0,
        tax_withheld=request.form.get("tax_withheld") or 0,
        other_deductions=request.form.get("other_deductions") or 0,
        payment_method=request.form.get("payment_method") or "",
        notes=request.form.get("notes") or "",
        actor=request.form.get("actor") or "local",
    )
    return redirect(f"/payroll/run/{run_id}")


@finance_blueprint.post("/payroll/run/<int:run_id>/import-recognition")
def payroll_import_recognition_post(run_id: int):
    result = apply_approved_iso_hungry_earnings(
        run_id,
        actor=request.form.get("actor") or "local",
    )
    return redirect(
        f"/payroll/run/{run_id}?recognition_imported={len(result['imported'])}"
        f"&recognition_skipped={len(result['skipped'])}"
    )


@finance_blueprint.post("/payroll/run/<int:run_id>/approve")
def payroll_approve_post(run_id: int):
    approve_pay_run(run_id, actor=request.form.get("actor") or "local")
    return redirect(f"/payroll/run/{run_id}")


@finance_blueprint.post("/payroll/run/<int:run_id>/paid")
def payroll_paid_post(run_id: int):
    mark_pay_run_paid(
        run_id,
        payment_reference=request.form.get("payment_reference") or "",
        actor=request.form.get("actor") or "local",
        payment_method=request.form.get("payment_method") or "mixed",
    )
    return redirect(f"/payroll/run/{run_id}")


@finance_blueprint.get("/accounting")
def accounting_dashboard():
    seed_finance_defaults()
    tb = trial_balance()
    with db() as con:
        journals = [dict(r) for r in con.execute("SELECT * FROM finance_journals ORDER BY id DESC LIMIT 80")]
        accounts = [dict(r) for r in con.execute("SELECT * FROM finance_accounts WHERE active=1 ORDER BY code")]
    tb_rows = "".join(
        f"<tr><td>{_e(x['code'])}</td><td>{_e(x['name'])}</td><td>{_e(x['account_type'])}</td>"
        f"<td>{_money(x['debit'])}</td><td>{_money(x['credit'])}</td><td>{_money(x['balance'])}</td></tr>"
        for x in tb
    )
    jr_rows = "".join(
        f"<tr class='sf-context' data-entity-type='finance_journal' data-entity-id='{r['id']}' data-entity-label='{_e(r['journal_number'])}'>"
        f"<td>{_e(r['journal_number'])}</td><td>{_e(r['entry_date'])}</td><td>{_e(r['memo'])}</td><td>{_e(r['reference'])}</td>"
        f"<td>{_e(r['source_module'])}</td><td>{_e(r['posted_by'])}</td></tr>" for r in journals
    ) or "<tr><td colspan='6' class='empty'>No journal entries.</td></tr>"
    acct_rows = "".join(f"<tr><td>{_e(a['code'])}</td><td>{_e(a['name'])}</td><td>{_e(a['account_type'])}</td></tr>" for a in accounts)
    body = f"""<section class='page-head'><div class='grow'><p class='eyebrow'>Finance</p><h1>Accounting Ledger</h1>
<p class='sub'>No-frills double-entry bookkeeping. Every posted journal must balance. Payroll posts here automatically. CSV/XLSX staging happens in the Sheet Workbench instead of bypassing the ledger.</p></div>
<a class='button secondary' href='/sheets'>Open Sheet Workbench</a></section>
<div class='grid'>
<details class='panel'><summary><b>Add chart account</b></summary><form method='post' action='/accounting/account' class='form-grid' style='margin-top:12px'>
<label>Code<input name='code' required></label><label>Name<input name='name' required></label>
<label>Type<select name='account_type'><option>asset</option><option>liability</option><option>equity</option><option>revenue</option><option>expense</option></select></label>
<label>Actor<input name='actor' value='local'></label><div><button>Add Account</button></div></form></details>
<div class='panel'><h2>QuickBooks without the circus</h2><p class='sub'>Use a Journal template in Sheets for manual journal entries. Payroll, future AP/AR and imported transactions all land in this same balanced ledger.</p></div>
</div>
<div class='panel'><h2>Trial Balance</h2><table><tr><th>Code</th><th>Account</th><th>Type</th><th>Debits</th><th>Credits</th><th>Balance</th></tr>{tb_rows}</table></div>
<div class='panel'><h2>Recent Journal Entries</h2><table><tr><th>Journal</th><th>Date</th><th>Memo</th><th>Reference</th><th>Source</th><th>Posted By</th></tr>{jr_rows}</table></div>
<details class='panel'><summary><b>Chart of Accounts</b></summary><table><tr><th>Code</th><th>Name</th><th>Type</th></tr>{acct_rows}</table></details>"""
    return page("Accounting Ledger", body, module_key="accounting")


@finance_blueprint.post("/accounting/account")
def accounting_account_post():
    create_account(
        request.form.get("code", ""),
        request.form.get("name", ""),
        request.form.get("account_type", ""),
        actor=request.form.get("actor") or "local",
    )
    return redirect("/accounting")


@finance_blueprint.route("/sheets", methods=["GET", "POST"])
def sheets_dashboard():
    if request.method == "POST":
        sheet_id = template_sheet(
            request.form.get("template_type") or "blank",
            name=request.form.get("name") or "",
            actor=request.form.get("actor") or "local",
        )
        return redirect(f"/sheets/{sheet_id}")
    with db() as con:
        sheets = [dict(r) for r in con.execute("SELECT * FROM sheet_books ORDER BY id DESC LIMIT 100")]
    rows = "".join(
        f"<tr class='sf-context' data-entity-type='sheet_book' data-entity-id='{r['id']}' data-entity-label='{_e(r['name'])}'>"
        f"<td><a href='/sheets/{r['id']}'>{_e(r['name'])}</a></td><td>{_e(r['template_type'])}</td><td>{_e(r['status'])}</td>"
        f"<td>{_e(r['posted_entity_type'])}</td><td>{_e(r['posted_entity_id'])}</td><td>{_e(r['updated_at'])}</td></tr>" for r in sheets
    ) or "<tr><td colspan='6' class='empty'>No sheets yet.</td></tr>"
    body = f"""<section class='page-head'><div class='grow'><p class='eyebrow'>Utility / Data Workbench</p><h1>Sheet Workbench</h1>
<p class='sub'>Bambu Studio to Excel: enough grid, formulas, CSV/XLSX import/export and posting actions to get real work done without trying to become a full spreadsheet suite.</p></div></section>
<details class='panel'><summary><b>New sheet</b></summary><form method='post' class='form-grid' style='margin-top:12px'>
<label>Name<input name='name'></label><label>Template<select name='template_type'><option value='blank'>Blank</option><option value='payroll'>Payroll Input</option><option value='journal'>Journal Entry</option></select></label>
<label>Actor<input name='actor' value='local'></label><div><button>Create Sheet</button></div></form></details>
<div class='panel'><table><tr><th>Name</th><th>Template</th><th>Status</th><th>Posted Type</th><th>Posted ID</th><th>Updated</th></tr>{rows}</table></div>"""
    return page("Sheet Workbench", body, module_key="sheets")


@finance_blueprint.get("/sheets/<int:sheet_id>")
def sheet_detail(sheet_id: int):
    snap = sheet_snapshot(sheet_id, evaluate=True)
    columns, rows = snap["columns"], snap["rows"]
    if not rows:
        rows = [{c: "" for c in columns} for _ in range(8)]
    head = "".join(f"<th contenteditable='true'>{_e(c)}</th>" for c in columns)
    body_rows = "".join(
        "<tr>" + "".join(f"<td contenteditable='true'>{_e(row.get(c,''))}</td>" for c in columns) + "</tr>"
        for row in rows
    )
    formula_rows = snap.get("evaluated_rows") or []
    has_formulas = any(
        isinstance(row.get(col), str) and row.get(col, "").strip().startswith("=")
        for row in snap["rows"] for col in columns
    )
    preview_rows = "".join(
        "<tr>" + "".join(
            f"<td>{_e(row.get(col + ' (value)', row.get(col, '')))}</td>"
            for col in columns
        ) + "</tr>"
        for row in formula_rows
    )
    formula_preview = (
        "<details class='panel'><summary><b>Calculated Preview</b></summary>"
        "<p class='sub'>Server-evaluated formula results. Posting to Payroll or Accounting uses these resolved values.</p>"
        "<table><tr>" + "".join(f"<th>{_e(col)}</th>" for col in columns) + "</tr>" + preview_rows + "</table></details>"
        if has_formulas else ""
    )
    post_controls = ""
    if snap["template_type"] == "payroll":
        with db() as con:
            runs = [dict(r) for r in con.execute("SELECT id,run_key FROM payroll_runs WHERE status='draft' ORDER BY id DESC")]
        options = "".join(f"<option value='{r['id']}'>{_e(r['run_key'])}</option>" for r in runs)
        post_controls = f"""<form method='post' action='/sheets/{sheet_id}/post-payroll' style='display:flex;gap:8px;align-items:end'>
<label>Draft Pay Run<select name='run_id' required>{options}</select></label><input type='hidden' name='actor' value='local'><button>Post Rows to Payroll</button></form>"""
    elif snap["template_type"] == "journal":
        post_controls = f"""<form method='post' action='/sheets/{sheet_id}/post-journal' style='display:flex;gap:8px;align-items:end'>
<label>Memo<input name='memo' value='Sheet journal'></label><input type='hidden' name='actor' value='local'><button>Post Balanced Journal</button></form>"""

    body = f"""<section class='page-head'><div class='grow'><p class='eyebrow'>Sheet Workbench</p><h1>{_e(snap['name'])}</h1>
<p class='sub'>Click any cell and type. Formulas begin with <code>=</code> and support row-column names plus + - * /, SUM, MIN, MAX, ABS and ROUND. Example: <code>=Regular_Hours*25</code>.</p></div>
<a class='button secondary' href='/sheets'>All Sheets</a></section>
<div class='panel'><div class='toolbar'><button type='button' id='add-row'>Add Row</button>
<button type='button' class='secondary' id='save-grid'>Save Grid</button>
<a class='button secondary' href='/sheets/{sheet_id}/export.csv'>CSV</a><a class='button secondary' href='/sheets/{sheet_id}/export.xlsx'>XLSX</a></div>
<div style='overflow:auto'><table id='sheet-grid'><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div></div>
{formula_preview}
<form id='sheet-save' method='post' action='/sheets/{sheet_id}/save'><input type='hidden' name='grid_json' id='grid-json'><input type='hidden' name='actor' value='local'></form>
<div class='grid'>
<form class='panel' method='post' action='/sheets/{sheet_id}/import' enctype='multipart/form-data'><h2>Import</h2>
<input type='file' name='file' accept='.csv,.xlsx,.xlsm' required><div style='margin-top:10px'><button>Replace Grid From File</button></div></form>
<div class='panel'><h2>Post</h2>{post_controls or "<p class='sub'>Blank sheets are scratch work and do not post until converted into a supported workflow.</p>"}</div></div>
<script>
const grid=document.getElementById('sheet-grid');
document.getElementById('add-row').onclick=()=>{{const tr=document.createElement('tr');for(let i=0;i<grid.tHead.rows[0].cells.length;i++){{const td=document.createElement('td');td.contentEditable='true';tr.appendChild(td)}}grid.tBodies[0].appendChild(tr)}};
document.getElementById('save-grid').onclick=()=>{{const cols=[...grid.tHead.rows[0].cells].map(x=>x.innerText.trim());const rows=[...grid.tBodies[0].rows].map(tr=>Object.fromEntries([...tr.cells].map((td,i)=>[cols[i],td.innerText])));document.getElementById('grid-json').value=JSON.stringify({{columns:cols,rows}});document.getElementById('sheet-save').submit()}};
</script>"""
    return page(snap["name"], body, module_key="sheets", context_type="sheet_book", context_id=str(sheet_id))


@finance_blueprint.post("/sheets/<int:sheet_id>/save")
def sheet_save(sheet_id: int):
    payload = json.loads(request.form.get("grid_json") or "{}")
    columns = [str(x).strip() for x in payload.get("columns", []) if str(x).strip()]
    rows = payload.get("rows") or []
    if columns:
        with db() as con:
            con.execute("UPDATE sheet_books SET columns_json=? WHERE id=?", (json.dumps(columns), sheet_id))
    save_sheet_rows(sheet_id, rows, actor=request.form.get("actor") or "local")
    return redirect(f"/sheets/{sheet_id}")


@finance_blueprint.post("/sheets/<int:sheet_id>/import")
def sheet_import(sheet_id: int):
    upload = request.files.get("file")
    if upload is None:
        return redirect(f"/sheets/{sheet_id}")
    import_sheet_bytes(sheet_id, upload.filename or "import.csv", upload.read(), actor="local")
    return redirect(f"/sheets/{sheet_id}")


@finance_blueprint.get("/sheets/<int:sheet_id>/export.csv")
def sheet_export_csv(sheet_id: int):
    return Response(
        export_sheet_csv(sheet_id),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=sheet_{sheet_id}.csv"},
    )


@finance_blueprint.get("/sheets/<int:sheet_id>/export.xlsx")
def sheet_export_xlsx(sheet_id: int):
    return send_file(
        io.BytesIO(export_sheet_xlsx(sheet_id)),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"sheet_{sheet_id}.xlsx",
    )


@finance_blueprint.post("/sheets/<int:sheet_id>/post-payroll")
def sheet_post_payroll(sheet_id: int):
    run_id = int(request.form.get("run_id") or 0)
    post_payroll_sheet(sheet_id, run_id, actor=request.form.get("actor") or "local")
    return redirect(f"/payroll/run/{run_id}")


@finance_blueprint.post("/sheets/<int:sheet_id>/post-journal")
def sheet_post_journal(sheet_id: int):
    post_journal_sheet(sheet_id, actor=request.form.get("actor") or "local", memo=request.form.get("memo") or "Sheet journal")
    return redirect("/accounting")
