"""Read-only, job-scoped evidence passport for the local Axiom workbench.

Only direct job_id links are treated as job evidence. Part-level records are
shown separately and NEVER imply that a job has completed an inspection,
approved an estimate, or released a drawing.
"""
from __future__ import annotations

from html import escape

from flask import Blueprint, abort

from ..db import db
from ..ui import page

passport_blueprint = Blueprint("job_passport", __name__)


def _esc(value):
    return escape("" if value is None else str(value), quote=True)


def _rows(con, sql, params):
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def get_job_passport(job_id: int) -> dict | None:
    """Return persisted evidence only; no writes and no inferred approvals."""
    with db() as con:
        job = con.execute(
            """SELECT j.*, p.part_number, p.revision AS part_revision,
                      c.name AS customer_name
               FROM jobs j
               LEFT JOIN parts p ON p.id=j.part_id
               LEFT JOIN customers c ON c.id=j.customer_id
               WHERE j.id=?""", (job_id,)
        ).fetchone()
        if job is None:
            return None
        info = dict(job)
        linked = {
            "purchase_orders": _rows(
                con, """SELECT id,po_number,status,required_date,expected_date
                        FROM purchase_orders WHERE job_id=? ORDER BY id""", (job_id,)
            ),
            "quality": _rows(
                con, """SELECT id,record_number,record_type,status,severity,due_date
                        FROM quality_records WHERE job_id=? ORDER BY id""", (job_id,)
            ),
            "inspections": _rows(
                con, """SELECT f.id,f.fai_number,f.status,f.characteristic_count,
                               f.pass_count,f.fail_count,f.drawing_revision,
                               l.vault_version_id,l.release_package_number,l.pdf_sha256
                        FROM fai_runs f LEFT JOIN fai_source_links l ON l.fai_run_id=f.id
                        WHERE f.job_id=? ORDER BY f.id""", (job_id,)
            ),
            "methods": _rows(
                con, """SELECT id,job_number,part_number,revision,status
                        FROM ezm_method_plans WHERE job_id=?
                        ORDER BY id""", (job_id,)
            ),
            "documents": _rows(
                con, """SELECT id,document_number,title,revision,status,sha256
                        FROM documents WHERE job_id=? ORDER BY id""", (job_id,)
            ),
            "requisitions": _rows(con, """SELECT r.id,r.status,r.quantity,r.unit,i.item_number
                    FROM procurement_requisitions r JOIN inventory_items i ON i.id=r.item_id
                    WHERE r.job_id=? ORDER BY r.id""",(job_id,)),
            "reservations": _rows(con, """SELECT r.quantity,i.item_number
                    FROM inventory_reservations r JOIN inventory_items i ON i.id=r.item_id
                    WHERE r.job_id=? ORDER BY i.item_number""",(job_id,)),
            "inventory_movements": _rows(
                con, """SELECT t.id,i.item_number,t.txn_type,t.quantity,t.reference
                        FROM inventory_transactions t
                        JOIN inventory_items i ON i.id=t.item_id
                        WHERE t.job_id=? ORDER BY t.id""", (job_id,)
            ),
        }
        # Part-linked estimates and drawings are REFERENCES, not job releases.
        part_references = {"quotes": [], "documents": [], "inspections": []}
        if info["part_id"] is not None:
            p = info["part_id"]
            part_references["quotes"] = _rows(
                con, """SELECT q.id,q.quote_number,q.status,q.estimated_value,
                               e.source_version_id,e.drawing_sha256
                        FROM quote_intakes q
                        LEFT JOIN ezstimate_quote_evidence e ON e.quote_intake_id=q.id
                        WHERE q.part_id=? ORDER BY q.id""", (p,)
            )
            part_references["documents"] = _rows(
                con, """SELECT id,document_number,title,revision,status,sha256
                        FROM documents
                        WHERE part_id=? AND (job_id IS NULL OR job_id!=?)
                        ORDER BY id""", (p, job_id)
            )
            part_references["inspections"] = _rows(
                con, """SELECT id,fai_number,status,characteristic_count,
                               drawing_revision
                        FROM fai_runs
                        WHERE part_id=? AND (job_id IS NULL OR job_id!=?)
                        ORDER BY id""", (p, job_id)
            )
        return {"job": info, "linked": linked, "part_references": part_references}


def _table(items, fields, *, empty):
    if not items:
        return "<p class='sub'>" + _esc(empty) + "</p>"
    head = "".join("<th>" + _esc(label) + "</th>" for _, label in fields)
    body = "".join(
        "<tr>" + "".join("<td>" + _esc(record.get(key)) + "</td>" for key, _ in fields) + "</tr>"
        for record in items
    )
    return "<table><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table>"


@passport_blueprint.get("/jobs/<int:job_id>/passport")
def job_passport_page(job_id: int):
    data = get_job_passport(job_id)
    if data is None:
        abort(404)
    j = data["job"]
    linked = data["linked"]
    refs = data["part_references"]
    body = (
        "<section class='page-head'><div class='grow'>"
        "<p class='eyebrow'>Job-scoped source evidence / read only</p>"
        "<h1>Job Passport: " + _esc(j["job_number"]) + "</h1>"
        "<p class='sub'>Only explicitly job-linked records are treated as evidence for this job. "
        "Part-level references below are NOT job assignments, approvals, or completed operations.</p>"
        "</div><a class='button secondary' href='/jobs'>Back to Jobs</a></section>"
    )
    body += (
        "<div class='grid'>"
        "<div class='card'><span class='label'>Part / revision</span>"
        "<strong class='big'>" + _esc(j["part_number"] or "Not linked") + "</strong><div class='sub'>"
        + _esc(j["part_revision"] or "Revision unassigned") + "</div></div>"
        "<div class='card'><span class='label'>Job status</span>"
        "<strong class='big'>" + _esc(j["status"]) + "</strong><div class='sub'>"
        + _esc(j["current_operation"] or "Operation not recorded") + "</div></div>"
        "<div class='card'><span class='label'>Order / due</span><strong class='big'>"
        + _esc(j["quantity"] if j["quantity"] is not None else "Unknown")
        + "</strong><div class='sub'>Due: " + _esc(j["due_date"] or "Not recorded") + "</div></div>"
        "<div class='card'><span class='label'>Quality records</span><strong class='big'>"
        + str(len(linked["quality"])) + "</strong><div class='sub'>Directly linked only</div></div>"
        "</div>"
    )
    sections = [
        ("Drawing / document custody", linked["documents"],
         [("document_number", "Document"), ("revision", "Revision"),
          ("status", "Lifecycle"), ("sha256", "SHA-256")]),
        ("Inspection / FAI evidence", linked["inspections"],
         [("fai_number", "FAI"), ("drawing_revision", "Drawing rev"),
          ("status", "Status"), ("characteristic_count", "Characteristics"),
          ("pass_count", "Measured passes"), ("fail_count", "Measured failures"),
          ("vault_version_id", "Verified vault version"),
          ("pdf_sha256", "PDF checksum")]),
        ("Methods / routing", linked["methods"],
         [("id", "Plan ID"), ("revision", "Revision"), ("status", "Status")]),
        ("Purchasing", linked["purchase_orders"],
         [("po_number", "PO"), ("status", "Status"),
          ("required_date", "Required"), ("expected_date", "Expected")]),
        ("Quality / corrective action", linked["quality"],
         [("record_number", "Record"), ("record_type", "Type"),
          ("status", "Status"), ("severity", "Severity"), ("due_date", "Due")]),
        ("Purchasing requisitions",linked["requisitions"],
         [("id","PR ID"),("item_number","Stock item"),("quantity","Qty"),
          ("unit","Unit"),("status","Status")]),
        ("Reserved stock",linked["reservations"],
         [("item_number","Stock item"),("quantity","Reserved Qty")]),
        ("Material movements", linked["inventory_movements"],
         [("item_number", "Item"), ("txn_type", "Movement"),
          ("quantity", "Quantity"), ("reference", "Reference")]),
    ]
    for title, rows, fields in sections:
        body += ("<section class='panel'><h2>" + _esc(title) + "</h2>"
                 + _table(rows, fields, empty="No records directly linked to this job.")
                 + "</section>")
    body += (
        "<section class='panel'><h2>Part-level references (not job evidence)</h2>"
        "<p class='sub'>Matching the same part does not establish a purchase commitment, "
        "inspection completion, or drawing revision release for this specific job.</p>"
    )
    for title, rows, fields in [
        ("Estimating proposals", refs["quotes"],
         [("quote_number", "Estimate"), ("status", "Status"),
          ("estimated_value", "Draft value"), ("source_version_id", "Source version")]),
        ("Part documents", refs["documents"],
         [("document_number", "Document"), ("revision", "Revision"), ("status", "Lifecycle")]),
        ("Other inspections", refs["inspections"],
         [("fai_number", "FAI"), ("drawing_revision", "Revision"), ("status", "Status")]),
    ]:
        body += "<h3>" + _esc(title) + "</h3>" + _table(rows, fields, empty="No part-level references.")
    body += "</section>"
    body += (
        "<p class='sub'>Evidence limitations: a saved label is not authenticated authorship; "
        "a checksum displayed here is not revalidated against file bytes on page load; "
        "missing records mean no link found, not proof that work was not performed.</p>"
    )
    return page("Job Passport", body, module_key="job_tracker")
