from __future__ import annotations

import ipaddress
from datetime import date, datetime
from html import escape

from flask import abort, jsonify, redirect, render_template_string, request

import forgeqc_app
from audit_journal import record_event, register_request_audit, tail_entries, verify_journal
from forgeqc_app import Customer, Department, ReasonCode, WorkOrder, as_int, db, get_or_create, page
from quality_forms import NonconformanceRecord, next_form_number
from quality_workflow import after_quality_save, ppm_metrics, workflow_counts
from runtime_paths import audit_journal_path, data_root


REPORTER_CSS = """
body{margin:0;background:#07111b;color:#eaf3fb;font:16px Segoe UI,Arial,sans-serif}
.wrap{max-width:760px;margin:auto;padding:20px}.brand{font-size:28px;font-weight:800;margin:8px 0 18px}
.card{background:#101d29;border:1px solid #27445e;border-radius:14px;padding:18px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;color:#bad0e3;font-size:13px}
input,select,textarea{box-sizing:border-box;width:100%;margin-top:5px;background:#07111b;color:#fff;border:1px solid #355b7a;border-radius:9px;padding:12px;font:inherit}
textarea{min-height:120px}.wide{grid-column:1/-1}button{background:#2f79b5;color:white;border:0;border-radius:10px;padding:13px 18px;font-weight:700;font-size:16px;cursor:pointer}
.notice{background:#10283a;border-left:4px solid #4a9bd3;padding:12px;border-radius:8px;margin-bottom:14px}
small{color:#8fb0c9}@media(max-width:640px){.grid{grid-template-columns:1fr}.wide{grid-column:auto}.wrap{padding:12px}}
"""


def h(value):
    return escape(str(value or ""), quote=True)


def _is_loopback(address):
    try:
        return ipaddress.ip_address(address or "127.0.0.1").is_loopback
    except ValueError:
        return False


def _options(model, selected=""):
    result = "<option value=''></option>"
    for row in model.query.filter_by(active=True).order_by(model.name):
        mark = " selected" if str(row.name) == str(selected) else ""
        result += f"<option{mark}>{h(row.name)}</option>"
    return result


def _report_form(message=""):
    return render_template_string(
        """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>ForgeQC NCR Reporter</title><style>{{css}}</style></head><body><div class='wrap'><div class='brand'>ForgeQC NCR Reporter</div>{{message|safe}}<div class='card'><form method='post' class='grid'>
        <label>Reported By<input name='reported_by' required placeholder='Name or initials'></label>
        <label>Work Order<input name='work_order_number' placeholder='Scan or enter WO'></label>
        <label>Department<select name='department'>{{departments|safe}}</select></label>
        <label>Reason / Defect Type<select name='reason'>{{reasons|safe}}</select></label>
        <label>Part Number<input name='part_number'></label>
        <label>Revision<input name='revision'></label>
        <label>Quantity Affected<input name='quantity_affected' type='number' min='0' value='1'></label>
        <label>Source / Location<input name='source_location' placeholder='Weld cell, final inspection, shipping...'></label>
        <label class='wide'>Condition Found / Nonconformance<textarea name='defect_description' required></textarea></label>
        <label class='wide'>Immediate Containment Taken<textarea name='containment_action' placeholder='What was stopped, segregated, identified, or checked?'></textarea></label>
        <label class='wide'>Additional Notes<textarea name='notes'></textarea></label>
        <div class='wide'><button>Submit NCR</button><br><small>Submission creates the controlled ForgeQC NCR and its Quality Expedite workflow immediately.</small></div>
        </form></div></div></body></html>""",
        css=REPORTER_CSS,
        message=message,
        departments=_options(Department),
        reasons=_options(ReasonCode),
    )


def install_ui():
    if "href='/report/ncr'" not in forgeqc_app.BASE:
        forgeqc_app.BASE = forgeqc_app.BASE.replace(
            "<a href='/'>Dashboard</a>",
            "<a href='/'>Dashboard</a><a href='/report/ncr'>NCR Reporter</a><a href='/erp-import'>ERP Imports</a><a href='/audit-journal'>Audit Journal</a>",
        )
    if "forgeqc-live-status" not in forgeqc_app.BASE:
        forgeqc_app.CSS += """
        .live-status{position:fixed;right:18px;top:14px;z-index:10005;background:#102436;border:1px solid #315776;border-radius:999px;padding:6px 10px;color:#cfe5f5;font-size:12px}
        """
        widget = """
        <div id='forgeqc-live-status' class='live-status'>Live quality: connecting...</div>
        <script>
        (function(){
          async function refreshLive(){
            try{
              const r=await fetch('/api/live/quality-summary',{cache:'no-store'});
              if(!r.ok) return;
              const j=await r.json();
              document.getElementById('forgeqc-live-status').textContent='Live quality: '+j.open_ncr+' NCR | '+j.overdue_actions+' overdue | journal #'+j.journal_sequence;
            }catch(e){}
          }
          refreshLive(); setInterval(refreshLive,5000);
        })();
        </script>
        """
        forgeqc_app.BASE = forgeqc_app.BASE.replace("</body>", widget + "</body>")


def register(app):
    register_request_audit(app)

    @app.before_request
    def _forgeqc_remote_surface_guard():
        if _is_loopback(request.remote_addr):
            return None
        allowed = (
            request.path == "/health"
            or request.path == "/report/ncr"
            or request.path.startswith("/report/ncr/")
        )
        if not allowed:
            abort(403)

    @app.route("/health")
    def health():
        verification = verify_journal()
        return jsonify({
            "status": "ok" if verification.get("ok") else "audit-warning",
            "app": "ForgeQC",
            "data_root": str(data_root()),
            "audit_ok": verification.get("ok"),
            "audit_entries": verification.get("entries", 0),
        })

    @app.route("/report/ncr", methods=["GET", "POST"])
    def web_ncr_reporter():
        if request.method == "GET":
            return _report_form()

        reporter = str(request.form.get("reported_by") or "").strip()
        wo_number = str(request.form.get("work_order_number") or "").strip()
        work_order = WorkOrder.query.filter_by(work_order_number=wo_number).first() if wo_number else None
        department = get_or_create(Department, request.form.get("department"))
        reason = get_or_create(ReasonCode, request.form.get("reason"))
        part_number = str(request.form.get("part_number") or "").strip() or (work_order.part_number if work_order else "")
        customer_id = work_order.customer_id if work_order else None
        notes = str(request.form.get("notes") or "").strip()
        source_location = str(request.form.get("source_location") or "").strip()
        combined_notes = "\n".join(x for x in [f"Web reporter: {reporter}", f"Source/location: {source_location}" if source_location else "", notes] if x)

        row = NonconformanceRecord(
            record_number=next_form_number(NonconformanceRecord, "record_number", "NCR"),
            record_type="NCR",
            date_opened=date.today(),
            customer_id=customer_id,
            department_id=department.id if department else None,
            reason_code_id=reason.id if reason else None,
            work_order_id=work_order.id if work_order else None,
            part_number=part_number,
            revision=str(request.form.get("revision") or "").strip(),
            quantity_affected=as_int(request.form.get("quantity_affected"), 0),
            defect_description=str(request.form.get("defect_description") or "").strip(),
            containment_action=str(request.form.get("containment_action") or "").strip(),
            disposition="Review Needed",
            disposition_owner="Quality",
            status="Open",
            notes=combined_notes,
        )
        db.session.add(row)
        db.session.flush()
        workflow = after_quality_save("NCR", row, "Submitted from web NCR reporter")
        workflow.workflow_status = "ASSIGNMENT REQUIRED"
        workflow.next_action = "Quality review, verify containment, assign disposition owner, and determine CAR need."
        record_event(
            "NCR_REPORT",
            "Created",
            entity_type="NCR",
            entity_id=row.record_number,
            actor=reporter,
            detail="Submitted through web NCR reporter",
            data={
                "id": row.id,
                "work_order": wo_number,
                "part_number": row.part_number,
                "quantity_affected": row.quantity_affected,
                "department": department.name if department else "",
                "reason": reason.name if reason else "",
            },
        )
        db.session.commit()
        message = f"<div class='notice'><b>{h(row.record_number)} submitted.</b><br>Quality has the controlled record and action workflow now.</div>"
        return _report_form(message)

    @app.route("/api/live/quality-summary")
    def live_quality_summary():
        open_ncr = NonconformanceRecord.query.filter(NonconformanceRecord.status != "Closed").count()
        counts = workflow_counts()
        ppm = ppm_metrics(30)
        journal = verify_journal()
        recent = [
            {
                "record_number": row.record_number,
                "date_opened": row.date_opened.isoformat() if row.date_opened else None,
                "part_number": row.part_number,
                "quantity_affected": row.quantity_affected,
                "status": row.status,
            }
            for row in NonconformanceRecord.query.order_by(NonconformanceRecord.id.desc()).limit(10)
        ]
        return jsonify({
            "server_time": datetime.utcnow().isoformat() + "Z",
            "open_ncr": open_ncr,
            "open_quality_actions": counts["open"],
            "overdue_actions": counts["overdue"],
            "unassigned_actions": counts["unassigned"],
            "ncr_ppm": ppm["ncr_ppm"],
            "rma_ppm": ppm["rma_ppm"],
            "ppm_denominator_source": ppm.get("denominator_source"),
            "ppm_units": ppm.get("units"),
            "journal_sequence": journal.get("entries", 0),
            "recent_ncr": recent,
        })

    @app.route("/audit-journal")
    def audit_journal_page():
        verification = verify_journal()
        rows = "".join(
            f"<tr><td>{h(item.get('sequence'))}</td><td>{h(item.get('timestamp_utc'))}</td><td>{h(item.get('event_type'))}</td><td>{h(item.get('action'))}</td><td>{h(item.get('entity_type'))} {h(item.get('entity_id'))}</td><td>{h(item.get('actor'))}</td><td>{h(item.get('detail'))}</td></tr>"
            for item in reversed(tail_entries(200))
        )
        state = "VALID" if verification.get("ok") else f"FAILED: {h(verification.get('error'))}"
        body = f"""
        <div class='notice'><b>Journal verification: {state}</b><br>Path: {h(audit_journal_path())}<br>Entries: {verification.get('entries', 0)}. The journal is hash-chained and stored outside the application install directory on Windows. Uninstall does not remove it.</div>
        <section><table><tr><th>#</th><th>UTC</th><th>Event</th><th>Action</th><th>Entity</th><th>Actor</th><th>Detail</th></tr>{rows}</table></section>
        """
        return page("Audit Journal", body)
