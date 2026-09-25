from __future__ import annotations

import csv
import html
import io
import json
from flask import Blueprint, Response, request

from ..audit import record_event
from ..db import db
from ..ui import page

reporting_blueprint = Blueprint("reporting", __name__, url_prefix="/reports")

REPORTS = {
    "quality": {
        "title": "Quality Records",
        "description": "NCR, RMA, CAR/CAPA-linked quality records with ownership, quantity and due-date context.",
        "sql": """SELECT record_number,record_type,status,severity,quantity_affected,quantity_shipped,owner,due_date,created_at,updated_at
                  FROM quality_records ORDER BY id DESC""",
    },
    "purchasing": {
        "title": "Purchasing / PO Risk",
        "description": "Open purchasing commitments with supplier, job, required and expected dates.",
        "sql": """SELECT p.po_number,s.name supplier,j.job_number,p.status,p.order_date,p.required_date,p.expected_date,p.total_value,p.updated_at
                  FROM purchase_orders p
                  LEFT JOIN suppliers s ON s.id=p.supplier_id
                  LEFT JOIN jobs j ON j.id=p.job_id
                  ORDER BY p.id DESC""",
    },
    "actions": {
        "title": "Workflow Actions",
        "description": "Cross-module assigned work, due dates, source modules and completion status.",
        "sql": """SELECT id,workflow_key,step_key,source_module,target_module,entity_type,entity_id,assigned_to,status,due_date,created_at,completed_at
                  FROM workflow_actions ORDER BY id DESC""",
    },
    "kpi": {
        "title": "KPI History",
        "description": "Auditable KPI snapshots including PPM and future operating metrics.",
        "sql": """SELECT metric_date,metric_name,metric_scope,scope_id,value,unit,target,status,source_event_id,created_at
                  FROM kpi_snapshots ORDER BY id DESC""",
    },
    "intelligence": {
        "title": "Intelligence Proposals",
        "description": "BEAN observations converted into governed improvement proposals with review status and execution permission.",
        "sql": """SELECT proposal_id,title,target_module,risk_level,status,execution_permission,reviewed_by,review_notes,created_at,updated_at
                  FROM learning_proposals ORDER BY id DESC""",
    },
    "executive": {
        "title": "Executive Recommendations",
        "description": "Decision-protocol recommendations, organizational ownership, priority and acceptance state.",
        "sql": """SELECT id,source_event_id,source_module,target_module,title,rationale,recommended_action,
                         priority,status,entity_type,entity_id,accepted_action_id,reviewed_by,created_at,reviewed_at
                  FROM module_suggestions
                  WHERE suggestion_key LIKE 'exec:%'
                  ORDER BY id DESC""",
    },
    "payroll-runs": {
        "title": "Payroll Runs",
        "description": "Pay-period status, gross/net totals, approval, payment references and ledger linkage.",
        "sql": """SELECT run_key,period_start,period_end,check_date,pay_group,status,gross_total,tax_total,
                         deduction_total,net_total,journal_id,payment_journal_id,payment_reference,
                         created_by,approved_by,paid_by,created_at,approved_at,paid_at
                  FROM payroll_runs ORDER BY id DESC""",
    },
    "payroll-items": {
        "title": "Payroll Detail",
        "description": "Employee-level regular/overtime hours, gross pay, explicit withholdings, deductions and net pay.",
        "sql": """SELECT r.run_key,e.employee_ref,e.display_name,e.department,i.regular_hours,i.overtime_hours,
                         i.regular_pay,i.overtime_pay,i.bonus,i.gross_pay,i.tax_withheld,i.other_deductions,
                         i.net_pay,i.payment_method,i.payment_reference,i.status
                  FROM payroll_items i
                  JOIN payroll_runs r ON r.id=i.run_id
                  JOIN payroll_employees e ON e.id=i.employee_id
                  ORDER BY r.id DESC,e.display_name""",
    },
    "accounting-journals": {
        "title": "Accounting Journals",
        "description": "Posted balanced journal headers with source-module and source-entity traceability.",
        "sql": """SELECT journal_number,entry_date,memo,reference,source_module,source_entity_type,
                         source_entity_id,status,posted_by,posted_at,created_at
                  FROM finance_journals ORDER BY id DESC""",
    },
    "accounting-lines": {
        "title": "Accounting Journal Lines",
        "description": "Double-entry debit/credit detail by account with employee and job references where applicable.",
        "sql": """SELECT j.journal_number,j.entry_date,a.code account_code,a.name account_name,
                         l.description,l.debit,l.credit,l.employee_ref,l.job_ref,j.source_module,j.reference
                  FROM finance_journal_lines l
                  JOIN finance_journals j ON j.id=l.journal_id
                  JOIN finance_accounts a ON a.id=l.account_id
                  WHERE j.status='posted'
                  ORDER BY j.id DESC,l.line_no""",
    },
    "events": {
        "title": "Domain Event Ledger",
        "description": "Cross-module event receipts with correlation IDs for end-to-end traceability.",
        "sql": """SELECT event_id,parent_event_id,correlation_id,event_type,source_module,target_module,entity_type,entity_id,actor,status,created_at
                  FROM event_ledger ORDER BY id DESC""",
    },
}

def _rows(report_key: str) -> list[dict]:
    spec = REPORTS.get(report_key)
    if not spec:
        raise KeyError(report_key)
    with db() as con:
        return [dict(r) for r in con.execute(spec["sql"]).fetchall()]

def executive_snapshot() -> dict:
    with db() as con:
        row = con.execute("""SELECT
            (SELECT COUNT(*) FROM jobs WHERE status!='closed') open_jobs,
            (SELECT COUNT(*) FROM purchase_orders WHERE status NOT IN ('closed','received')) open_pos,
            (SELECT COUNT(*) FROM quality_records WHERE status!='closed') open_quality,
            (SELECT COUNT(*) FROM corrective_actions WHERE status!='closed') open_cars,
            (SELECT COUNT(*) FROM workflow_actions WHERE status='open') open_actions,
            (SELECT COUNT(*) FROM workflow_actions WHERE status='open' AND due_date!='' AND due_date<date('now')) overdue_actions,
            (SELECT COUNT(*) FROM inventory_items WHERE (on_hand-allocated)<=reorder_point) inventory_watch,
            (SELECT COUNT(*) FROM learning_proposals WHERE status NOT IN ('rejected','validated','rolled_back')) intelligence_proposals,
            (SELECT COUNT(*) FROM module_suggestions WHERE status='open' AND suggestion_key LIKE 'exec:%') executive_signals,
            (SELECT COUNT(*) FROM payroll_runs WHERE status='draft') draft_payroll,
            (SELECT COUNT(*) FROM finance_journals WHERE status='posted') posted_journals
        """).fetchone()
        morale = con.execute("SELECT risk_score FROM morale_pulses ORDER BY period_end DESC,id DESC LIMIT 1").fetchone()
    snap=dict(row)
    snap["company_pulse_risk"] = None if morale is None else morale["risk_score"]
    return snap

def _table_preview(rows: list[dict], limit: int = 12) -> str:
    if not rows:
        return "<div class='empty'>No rows yet.</div>"
    fields=list(rows[0].keys())
    head="".join(f"<th>{html.escape(f.replace('_',' ').title())}</th>" for f in fields)
    body=[]
    for row in rows[:limit]:
        body.append(
            "<tr>"+"".join(
                f"<td>{html.escape('' if row.get(f) is None else str(row.get(f)))}</td>"
                for f in fields
            )+"</tr>"
        )
    return f"<div style='overflow:auto'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"

@reporting_blueprint.get("")
def reporting_home():
    snap=executive_snapshot()
    cards=[
        ("Open Jobs",snap["open_jobs"]),
        ("Open POs",snap["open_pos"]),
        ("Open Quality",snap["open_quality"]),
        ("Open CARs",snap["open_cars"]),
        ("Open Actions",snap["open_actions"]),
        ("Overdue Actions",snap["overdue_actions"]),
        ("Inventory Watch",snap["inventory_watch"]),
        ("Intelligence Proposals",snap["intelligence_proposals"]),
        ("Executive Signals",snap["executive_signals"]),
        ("Draft Payroll",snap["draft_payroll"]),
        ("Posted Journals",snap["posted_journals"]),
    ]
    body="<section class='page-head'><div class='grow'><p class='eyebrow'>Reporting & Output</p><h1>Reporting Center</h1><p class='sub'>One output layer over Axiom's shared operational database. Reports keep the same entity IDs, event receipts and correlation trail used by Quality, Purchasing, Payroll, Accounting, Executive Intelligence, Leadership, Automation and BEAN.</p></div></section>"
    body+="<div class='grid'>"+"".join(f"<div class='card'><strong class='big'>{v}</strong><span class='label'>{k}</span></div>" for k,v in cards)+"</div>"
    body+="<div class='panel' style='margin-top:14px'><h2>Company Pulse</h2><div class='statline'><span>Current aggregate risk: <b>{}</b></span></div></div>".format("n/a" if snap["company_pulse_risk"] is None else snap["company_pulse_risk"])
    for key,spec in REPORTS.items():
        rows=_rows(key)
        body+=f"<div class='panel'><div class='toolbar'><div style='flex:1'><h2 style='margin-bottom:4px'>{spec['title']}</h2><div class='hint'>{spec['description']}</div></div><a class='button secondary' href='/reports/export/{key}?format=csv'>CSV</a><a class='button secondary' href='/reports/export/{key}?format=json'>JSON</a></div>{_table_preview(rows)}</div>"
    return page("Reporting Center",body,module_key="reports")

@reporting_blueprint.get("/export/<report_key>")
def export_report(report_key: str):
    if report_key not in REPORTS:
        return Response("Unknown report",status=404,mimetype="text/plain")
    fmt=(request.args.get("format") or "csv").lower()
    rows=_rows(report_key)
    record_event(
        event_type="REPORT_EXPORT",
        action="GENERATE",
        module="reporting",
        entity_type="report",
        entity_id=report_key,
        actor="local",
        data={"format":fmt,"row_count":len(rows)},
    )
    if fmt=="json":
        payload={"report":report_key,"title":REPORTS[report_key]["title"],"rows":rows}
        return Response(json.dumps(payload,indent=2,default=str),mimetype="application/json",
                        headers={"Content-Disposition":f"attachment; filename=axiom_{report_key}.json"})
    if fmt!="csv":
        return Response("Supported formats: csv, json",status=400,mimetype="text/plain")
    output=io.StringIO()
    if rows:
        writer=csv.DictWriter(output,fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return Response(output.getvalue(),mimetype="text/csv",
                    headers={"Content-Disposition":f"attachment; filename=axiom_{report_key}.csv"})
