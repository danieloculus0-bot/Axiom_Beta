"""Axiom EWI: controlled drawing + JobBOSS² routing + local clocking.

All ERP reads are opt-in; clocking never silently posts time to the ERP.
A PDF is usable only when its explicitly job-linked released record, revision,
local allowlisted path and SHA-256 all agree. No part-only release inference.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from flask import Blueprint, abort, flash, redirect, request, send_file, url_for

from ..access_control import verified_actor
from ..audit import record_event
from ..db import db
from ..ui import page
from ..integrations.jobboss2_reader import JobBoss2Reader, JobBossError, configured

ewi_blueprint = Blueprint("ewi", __name__)
_EMPLOYEE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


def init_ewi() -> None:
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS ewi_routes (
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            step TEXT NOT NULL,
            operation TEXT NOT NULL DEFAULT '',
            work_center TEXT NOT NULL DEFAULT '',
            instruction TEXT NOT NULL DEFAULT '',
            external_id TEXT NOT NULL DEFAULT '',
            part_number TEXT NOT NULL DEFAULT '',
            pulled_at TEXT NOT NULL,
            PRIMARY KEY(job_id,step)
        );
        CREATE TABLE IF NOT EXISTS ewi_clock_sessions (
            id TEXT PRIMARY KEY,
            employee_ref TEXT NOT NULL,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            step TEXT NOT NULL,
            started_utc TEXT NOT NULL,
            ended_utc TEXT,
            actor TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'LOCAL',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ix_ewi_one_active_employee
          ON ewi_clock_sessions(employee_ref) WHERE ended_utc IS NULL;
        CREATE TABLE IF NOT EXISTS ewi_outbox (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES ewi_clock_sessions(id),
            event_kind TEXT NOT NULL CHECK(event_kind IN ('START','STOP')),
            payload_json TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','SENT','ERROR')),
            remote_receipt TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _released_pdf(job: dict) -> tuple[Path | None, dict | None, str]:
    """Never select a released part reference as a job release."""
    with db() as con:
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM documents WHERE job_id=? AND lower(status)='released'",
            (job["id"],),
        )]
    if len(rows) != 1:
        return None, None, "Exactly one released, job-linked drawing is required"
    doc = rows[0]
    part_rev = str(job.get("part_revision") or "").strip().casefold()
    doc_rev = str(doc.get("revision") or "").strip().casefold()
    if not part_rev or part_rev != doc_rev:
        return None, doc, "Job part revision and drawing revision do not match"
    root_env = os.environ.get("AXIOM_EWI_DOCUMENT_ROOT")
    if not root_env:
        return None, doc, "Controlled drawing root is not configured"
    if not doc.get("storage_reference") or not doc.get("sha256"):
        return None, doc, "Released drawing lacks file reference or checksum"
    root = Path(root_env).resolve()
    path = Path(doc["storage_reference"])
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None, doc, "Drawing is outside the approved document root"
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return None, doc, "Controlled PDF is unavailable"
    digest = hashlib.sha256()
    with path.open("rb") as source:
        if source.read(5) != b"%PDF-":
            return None, doc, "Document is not a PDF"
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != str(doc["sha256"]).lower():
        return None, doc, "Drawing checksum mismatch; review required"
    return path, doc, ""


def packet(job_id: int) -> dict | None:
    with db() as con:
        row = con.execute("""
            SELECT j.id,j.job_number,j.status,j.quantity,j.current_operation,
                   p.part_number,p.revision AS part_revision
            FROM jobs j LEFT JOIN parts p ON p.id=j.part_id WHERE j.id=?
        """, (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        routes = [dict(r) for r in con.execute(
            "SELECT * FROM ewi_routes WHERE job_id=? ORDER BY CAST(step AS INTEGER),step",
            (job_id,),
        )]
        sessions = [dict(r) for r in con.execute("""
            SELECT * FROM ewi_clock_sessions WHERE job_id=?
            ORDER BY started_utc DESC LIMIT 30
        """, (job_id,))]
    path, drawing, issue = _released_pdf(job)
    errors = [issue] if issue else []
    if not routes:
        errors.append("No JobBOSS² routed operations have been synchronized")
    if routes and any(r["part_number"] and r["part_number"] != (job.get("part_number") or "") for r in routes):
        errors.append("ERP routing part number conflicts with job part")
    if (job.get("status") or "").lower() in {"closed", "cancelled", "canceled", "hold", "on_hold"}:
        errors.append("Job status does not permit starting work")
    return {"job": job, "drawing": drawing, "pdf_path": path, "routes": routes,
            "sessions": sessions, "issues": errors, "ready": not errors}


def save_remote_routes(job_id: int, routes: list[dict]) -> int:
    """Atomically replace one job's routing snapshot; never overwrite ERP."""
    if not routes:
        raise ValueError("ERP returned no matching routings; previous snapshot retained")
    if len(routes) > 500:
        raise ValueError("Unexpected ERP routing count")
    seen = set()
    with db() as con:
        job = con.execute("""
            SELECT p.part_number FROM jobs j LEFT JOIN parts p ON p.id=j.part_id WHERE j.id=?
        """, (job_id,)).fetchone()
        if job is None:
            raise ValueError("Job not found")
        expected = job["part_number"] or ""
        for route in routes:
            step = str(route.get("step") or "").strip()
            if not step or len(step) > 20 or step in seen:
                raise ValueError("ERP routing step missing or duplicated")
            seen.add(step)
            if route.get("part_number") and route["part_number"] != expected:
                raise ValueError("ERP routing part number does not match Axiom job")
        con.execute("DELETE FROM ewi_routes WHERE job_id=?", (job_id,))
        stamp = _now()
        for r in routes:
            con.execute("""
                INSERT INTO ewi_routes(job_id,step,operation,work_center,instruction,external_id,part_number,pulled_at)
                VALUES(?,?,?,?,?,?,?,?)
            """, (job_id, str(r["step"]).strip(), str(r.get("operation") or "")[:120],
                  str(r.get("work_center") or "")[:120], str(r.get("instruction") or "")[:3000],
                  str(r.get("external_id") or "")[:100], str(r.get("part_number") or "")[:120], stamp))
    record_event(event_type="EWI_ROUTING", action="SYNC", module="ewi",
                 entity_type="job", entity_id=job_id, actor="jobboss2_reader",
                 data={"operation_count": len(routes)})
    return len(routes)


def clock_start(job_id: int, step: str, employee_ref: str, actor: str) -> str:
    employee_ref = employee_ref.strip().upper()
    if not _EMPLOYEE.fullmatch(employee_ref):
        raise ValueError("Employee code must be 1 to 32 letters, numbers, dots, underscores or hyphens")
    current = packet(job_id)
    if current is None:
        raise ValueError("Job not found")
    if not current["ready"]:
        raise ValueError("EWI is blocked: " + "; ".join(current["issues"]))
    if step not in {str(r["step"]) for r in current["routes"]}:
        raise ValueError("Operation does not belong to this job")
    session_id = uuid.uuid4().hex
    stamp = _now()
    import json
    with db() as con:
        try:
            con.execute("""INSERT INTO ewi_clock_sessions
                (id,employee_ref,job_id,step,started_utc,actor) VALUES (?,?,?,?,?,?)""",
                (session_id, employee_ref, job_id, step, stamp, actor))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Employee already has an active local clocking session") from exc
        con.execute("""INSERT INTO ewi_outbox(event_id,session_id,event_kind,payload_json)
            VALUES(?,?,'START',?)""", (uuid.uuid4().hex, session_id, json.dumps({
                "session_id": session_id, "employee_ref": employee_ref, "job_id": job_id,
                "step": step, "timestamp_utc": stamp,
            }, sort_keys=True)))
    record_event(event_type="EWI_CLOCK", action="START_LOCAL", module="ewi",
                 entity_type="job", entity_id=job_id, actor=actor,
                 data={"session_id": session_id, "step": step})
    return session_id


def clock_stop(session_id: str, employee_ref: str, actor: str) -> None:
    import json
    employee_ref = employee_ref.strip().upper()
    stamp = _now()
    with db() as con:
        row = con.execute("""SELECT * FROM ewi_clock_sessions WHERE id=? AND employee_ref=? 
            AND ended_utc IS NULL""", (session_id, employee_ref)).fetchone()
        if row is None:
            raise ValueError("No matching active session for this employee code")
        con.execute("UPDATE ewi_clock_sessions SET ended_utc=? WHERE id=?", (stamp, session_id))
        con.execute("""INSERT INTO ewi_outbox(event_id,session_id,event_kind,payload_json)
            VALUES(?,?,'STOP',?)""", (uuid.uuid4().hex, session_id, json.dumps({
                "session_id": session_id, "employee_ref": employee_ref,
                "job_id": row["job_id"], "step": row["step"], "timestamp_utc": stamp,
            }, sort_keys=True)))
    record_event(event_type="EWI_CLOCK", action="STOP_LOCAL", module="ewi",
                 entity_type="job", entity_id=row["job_id"], actor=actor,
                 data={"session_id": session_id, "step": row["step"]})


@ewi_blueprint.get("/ewi")
def index():
    query = request.args.get("q", "").strip()[:80]
    with db() as con:
        rows = con.execute(
            "SELECT id,job_number,status,current_operation FROM jobs WHERE job_number LIKE ? ORDER BY id DESC LIMIT 100",
            ("%" + query + "%",),
        ).fetchall()
    body = (
        "<section class='page-head'><div><p class='eyebrow'>Axiom / operator station</p>"
        "<h1>Electronic Work Instructions</h1>"
        "<p class='sub'>Two controlled sources: ECI routing data and released, job-linked drawings. "
        "Clocking is local and pending ERP reconciliation, not a JobBOSS time ticket.</p></div></section>"
        "<section class='panel'><form method='get'><label>Find job number"
        "<input name='q' placeholder='Search jobs' value='" + _e(query) +
        "'></label><button>Find job</button></form></section><section class='panel'>"
        "<h2>Jobs</h2><table><tr><th>Job</th><th>Status</th><th>Current operation</th></tr>"
    )
    for row in rows:
        body += ("<tr><td><a href='/ewi/jobs/" + str(row["id"]) + "'><b>" +
                 _e(row["job_number"]) + "</b></a></td><td>" + _e(row["status"]) +
                 "</td><td>" + _e(row["current_operation"]) + "</td></tr>")
    body += "</table></section>"
    return page("Electronic Work Instructions", body, module_key="ewi")


@ewi_blueprint.get("/ewi/jobs/<int:job_id>")
def job_view(job_id: int):
    data = packet(job_id)
    if data is None:
        abort(404)
    job = data["job"]
    alerts = "".join("<p><strong>" + _e(s) + "</strong></p>" for s in data["issues"])
    banner = ("<span class='badge good'>Ready for local clocking</span>"
              if data["ready"] else "<span class='badge danger'>REVIEW REQUIRED</span>")
    notice = "".join("<p>" + _e(message) + "</p>" for message, category in __import__("flask").get_flashed_messages(with_categories=True))
    body = ("<section class='page-head'><div class='grow'><p class='eyebrow'>EWI / JobBOSS² routing + controlled drawing</p>"
            "<h1>Job " + _e(job["job_number"]) + "</h1><p class='sub'>Part: " +
            _e(job["part_number"]) + " | Job part revision: " + _e(job["part_revision"]) +
            " | Status: " + _e(job["status"]) + "</p>" + banner +
            "</div><a class='button secondary' href='/ewi'>All jobs</a></section>")
    if notice:
        body += "<section class='panel'>" + notice + "</section>"
    if alerts:
        body += "<section class='panel'><h2>Release / sync checks</h2>" + alerts + "</section>"
    body += "<section class='panel'><h2>JobBOSS² routed operations</h2>"
    body += ("<p class='sub'>API read: " + ("Configured" if configured() else "Not configured") +
             ". Sync reads routing data only. No production ERP updates.</p>"
             "<form method='post' action='/ewi/jobs/" + str(job_id) + "/sync'>"
             "<button class='secondary'>Refresh ERP routing</button></form>")
    for r in data["routes"]:
        body += ("<div class='card' style='margin:12px 0'><h3>Step " + _e(r["step"]) +
                 " | " + _e(r["operation"]) + "</h3><p class='sub'>Work center: " +
                 _e(r["work_center"]) + " | Source: JobBOSS² API | Pulled: " +
                 _e(r["pulled_at"]) + "</p><p>" + _e(r["instruction"]) + "</p>")
        if data["ready"]:
            body += ("<form class='toolbar' method='post' action='/ewi/jobs/" + str(job_id) +
                     "/clock'><input type='hidden' name='action' value='start'>"
                     "<input type='hidden' name='step' value='" + _e(r["step"]) + "'>"
                     "<label>Employee code<input name='employee_ref' required maxlength='32'></label>"
                     "<button>Clock into step " + _e(r["step"]) + "</button></form>")
        body += "</div>"
    body += "</section><section class='panel'><h2>Controlled drawing</h2>"
    if data["pdf_path"]:
        body += ("<p>Verified released job drawing: " + _e(data["drawing"]["document_number"]) +
                 " / Rev " + _e(data["drawing"]["revision"]) +
                 "</p><iframe title='Controlled drawing' style='width:100%;height:650px;border:1px solid var(--line)'"
                 " src='/ewi/jobs/" + str(job_id) + "/drawing'></iframe>")
    else:
        body += "<p class='sub'>No verified job-specific PDF available for display.</p>"
    body += "</section><section class='panel'><h2>Local clocking history</h2>"
    body += "<p class='sub'>Pending-sync records are not payroll approval or confirmed ERP time tickets. Employee codes entered here are not authenticated identities.</p>"
    for s in data["sessions"]:
        state = "Active" if s["ended_utc"] is None else "Stopped"
        body += ("<div class='card' style='margin:8px 0'><b>" + _e(s["employee_ref"]) +
                 "</b> | Step " + _e(s["step"]) + " | " + state +
                 " | Started UTC: " + _e(s["started_utc"]) +
                 (" | Ended UTC: " + _e(s["ended_utc"]) if s["ended_utc"] else "") )
        if s["ended_utc"] is None:
            body += ("<form class='toolbar' method='post' action='/ewi/jobs/" + str(job_id) +
                     "/clock'><input type='hidden' name='action' value='stop'>"
                     "<input type='hidden' name='session_id' value='" + _e(s["id"]) +
                     "'><label>Employee code<input name='employee_ref' required maxlength='32'></label>"
                     "<button class='secondary'>Stop clock</button></form>")
        body += "</div>"
    body += "</section>"
    return page("EWI " + str(job["job_number"]), body, module_key="ewi",
                context_type="job", context_id=str(job_id))


@ewi_blueprint.get("/ewi/jobs/<int:job_id>/drawing")
def drawing_pdf(job_id: int):
    data = packet(job_id)
    if data is None:
        abort(404)
    if not data["pdf_path"]:
        abort(409)
    response = send_file(data["pdf_path"], mimetype="application/pdf",
                         as_attachment=False, conditional=False)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@ewi_blueprint.post("/ewi/jobs/<int:job_id>/sync")
def sync(job_id: int):
    data = packet(job_id)
    if data is None:
        abort(404)
    try:
        count = save_remote_routes(job_id, JobBoss2Reader().routes(data["job"]["job_number"]))
        flash(str(count) + " ERP operations synchronized; drawing release remains independently controlled.")
    except (JobBossError, ValueError) as exc:
        flash(str(exc))
    return redirect(url_for("ewi.job_view", job_id=job_id), code=303)


@ewi_blueprint.post("/ewi/jobs/<int:job_id>/clock")
def clock(job_id: int):
    if packet(job_id) is None:
        abort(404)
    actor = verified_actor("local_operator")
    try:
        action = request.form.get("action")
        if action == "start":
            clock_start(job_id, request.form.get("step", ""), request.form.get("employee_ref", ""), actor)
            flash("Local clock started; JobBOSS synchronization is pending.")
        elif action == "stop":
            session_id = request.form.get("session_id", "")
            with db() as con:
                row = con.execute("SELECT job_id FROM ewi_clock_sessions WHERE id=?", (session_id,)).fetchone()
            if row is None or row["job_id"] != job_id:
                raise ValueError("Clock session is not linked to this job")
            clock_stop(session_id, request.form.get("employee_ref", ""), actor)
            flash("Local clock stopped; JobBOSS synchronization is pending.")
        else:
            raise ValueError("Unknown clocking action")
    except ValueError as exc:
        flash(str(exc))
    return redirect(url_for("ewi.job_view", job_id=job_id), code=303)
