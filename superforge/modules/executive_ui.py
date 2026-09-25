from __future__ import annotations

import html

from flask import Blueprint, redirect, request

from ..db import db
from ..ui import page
from .executive import (
    accept_executive_suggestion,
    assign_person_to_role,
    capture_executive_outcome,
    create_decision_protocol,
    organization_snapshot,
    upsert_person,
)

executive_blueprint = Blueprint("executive_module", __name__)


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _pct(value) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


@executive_blueprint.get("/executive")
def executive_dashboard():
    snap = organization_snapshot()
    pareto = snap["pareto"]

    signal_rows = "".join(
        f"<tr class='sf-context' data-entity-type='module_suggestion' data-entity-id='{row['id']}' data-entity-label='{_e(row['title'])}'>"
        f"<td>{float(row['weighted_impact_score']):.1f}</td>"
        f"<td>{_e(row['priority'])}</td><td>{_e(row['title'])}</td>"
        f"<td>{_e(row['rationale'])}</td><td>{_e(row['recommended_action'])}</td>"
        f"<td>{_e(row.get('target_role_key'))}</td>"
        f"<td><form method='post' action='/executive/suggestion/{row['id']}/accept' style='display:inline'>"
        f"<input type='hidden' name='actor' value='local'><button>Accept + Route</button></form></td></tr>"
        for row in pareto["signals"]
    ) or "<tr><td colspan='7' class='empty'>No executive signals currently require attention.</td></tr>"

    role_rows = "".join(
        f"<tr><td>{_e(r['role_key'])}</td><td>{_e(r['title'])}</td><td>{_e(r['unit_name'])}</td>"
        f"<td>{_e(r['parent_role_key'])}</td><td>{_e(r['authority_level'])}</td>"
        f"<td>{_e(r['display_name'])}</td><td>{_e(r['email'])}</td></tr>"
        for r in snap["roles"]
    ) or "<tr><td colspan='7' class='empty'>No organization roles.</td></tr>"

    unit_rows = "".join(
        f"<tr><td>{_e(u['unit_key'])}</td><td>{_e(u['name'])}</td><td>{_e(u['parent_unit_key'])}</td></tr>"
        for u in snap["units"]
    ) or "<tr><td colspan='3' class='empty'>No organization units.</td></tr>"

    protocol_rows = "".join(
        f"<tr><td>{_e(p['name'])}</td><td><code>{_e(p['event_type'])}</code></td><td>{_e(p['source_module'])}</td>"
        f"<td>{_e(p['target_role_key'])}</td><td>{_e(p['target_module'])}</td><td>{_e(p['priority'])}</td>"
        f"<td>{_e(p['default_impact'])}</td><td>{_e(p['default_urgency'])}</td><td>{_e(p['escalation_hours'])}h</td></tr>"
        for p in snap["protocols"]
    ) or "<tr><td colspan='9' class='empty'>No decision protocols.</td></tr>"

    with db() as con:
        people = [dict(r) for r in con.execute(
            "SELECT * FROM org_people WHERE active=1 ORDER BY display_name,person_key"
        )]
        roles = [dict(r) for r in con.execute(
            "SELECT role_key,title FROM org_roles WHERE active=1 ORDER BY authority_level DESC,title"
        )]
        recent = [dict(r) for r in con.execute(
            """SELECT s.id,s.title,s.status,s.accepted_action_id,s.reviewed_by,s.reviewed_at,
                      a.assigned_to,a.status action_status
               FROM module_suggestions s
               LEFT JOIN workflow_actions a ON a.id=s.accepted_action_id
               WHERE s.suggestion_key LIKE 'exec:%'
               ORDER BY s.id DESC LIMIT 50"""
        )]

    person_options = "".join(
        f"<option value='{_e(p['person_key'])}'>{_e(p['display_name'])} - {_e(p['person_key'])}</option>"
        for p in people
    )
    role_options = "".join(
        f"<option value='{_e(r['role_key'])}'>{_e(r['title'])} - {_e(r['role_key'])}</option>"
        for r in roles
    )
    recent_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{_e(r['title'])}</td><td>{_e(r['status'])}</td>"
        f"<td>{_e(r['accepted_action_id'])}</td><td>{_e(r['assigned_to'])}</td><td>{_e(r['action_status'])}</td>"
        f"<td><form method='post' action='/executive/suggestion/{r['id']}/outcome' class='statline'>"
        f"<input name='outcome' placeholder='Outcome / result' required style='min-width:220px'>"
        f"<input type='number' name='human_rating' step='.1' min='0' max='5' placeholder='0-5' style='width:80px'>"
        f"<input type='hidden' name='actor' value='local'><button class='secondary'>Teach Axiom</button></form></td></tr>"
        for r in recent
    ) or "<tr><td colspan='7' class='empty'>No executive recommendation history.</td></tr>"

    body = f"""<section class='page-head'><div class='grow'>
<p class='eyebrow'>Executive Intelligence</p><h1>Find what matters, route what matters</h1>
<p class='sub'>Axiom watches the same event spine used by production, quality, purchasing, payroll and finance. Decision protocols add organizational context: who owns the decision, how urgent it is, and what controlled action is expected. Recommendations remain human-governed and become ordinary auditable workflow actions only when accepted.</p>
</div></section>

<div class='grid'>
<div class='card'><strong class='big'>{pareto['open_count']}</strong><span class='label'>Open Executive Signals</span></div>
<div class='card'><strong class='big'>{pareto['pareto_count']}</strong><span class='label'>Signals In Current Pareto Cut</span></div>
<div class='card'><strong class='big'>{_pct(pareto['pareto_impact_share'])}</strong><span class='label'>Weighted Impact Explained</span></div>
<div class='card'><strong class='big'>{_pct(pareto['pareto_signal_share'])}</strong><span class='label'>Share Of Open Signals</span></div>
</div>

<div class='panel' style='margin-top:14px'><h2>80/20 Executive Queue</h2>
<p class='sub'>This is the smallest ranked set of current executive signals whose combined weighted score reaches at least 80% of open executive impact. It is not a fixed “show 20% of rows” gimmick.</p>
<table><tr><th>Score</th><th>Priority</th><th>Signal</th><th>Why It Matters</th><th>Recommended Action</th><th>Owner Role</th><th>Route</th></tr>{signal_rows}</table></div>

<div class='grid'>
<details class='panel'><summary><b>Add / update org person</b></summary>
<form method='post' action='/executive/person' class='form-grid' style='margin-top:12px'>
<label>Person Key<input name='person_key' required placeholder='jane.smith'></label>
<label>Name<input name='display_name' required></label>
<label>Email<input type='email' name='email'></label><label>Actor<input name='actor' value='local'></label>
<div><button>Save Person</button></div></form></details>

<details class='panel'><summary><b>Assign person to role</b></summary>
<form method='post' action='/executive/assignment' class='form-grid' style='margin-top:12px'>
<label>Person<select name='person_key' required>{person_options}</select></label>
<label>Role<select name='role_key' required>{role_options}</select></label>
<label><input type='checkbox' name='primary' value='1' checked> Primary role holder</label>
<label>Actor<input name='actor' value='local'></label><div><button>Assign</button></div></form></details>
</div>

<details class='panel'><summary><b>Add decision protocol</b></summary>
<form method='post' action='/executive/protocol' class='form-grid' style='margin-top:12px'>
<label>Name<input name='name' required></label><label>Event Type<input name='event_type' required placeholder='customer.complaint'></label>
<label>Source Module<input name='source_module' placeholder='optional exact module'></label>
<label>Target Module<input name='target_module' value='leadership'></label>
<label>Owner Role Key<select name='target_role_key'><option value=''>Unassigned role</option>{role_options}</select></label>
<label>Signal Type<input name='signal_type' value='operational'></label>
<label>Priority<select name='priority'><option>low</option><option selected>normal</option><option>high</option><option>critical</option></select></label>
<label>Escalation Hours<input type='number' min='0' name='escalation_hours' value='24'></label>
<label>Default Impact 0-1<input type='number' step='.05' min='0' max='1' name='default_impact' value='.5'></label>
<label>Default Urgency 0-1<input type='number' step='.05' min='0' max='1' name='default_urgency' value='.5'></label>
<label>Confidence Floor 0-1<input type='number' step='.05' min='0' max='1' name='confidence_floor' value='.5'></label>
<label class='wide'>Signal Title Template<input name='title_template' value='Executive review required'></label>
<label class='wide'>Why It Matters<textarea name='rationale_template'>The event crossed a configured decision protocol.</textarea></label>
<label class='wide'>Recommended Action<textarea name='action_template'>Review the event and assign a controlled response.</textarea></label>
<label class='wide'>Notes<textarea name='notes'></textarea></label><label>Actor<input name='actor' value='local'></label>
<div><button>Create Protocol</button></div></form></details>

<div class='panel'><h2>Organization Roles & Reporting Structure</h2>
<table><tr><th>Role Key</th><th>Role</th><th>Unit</th><th>Reports To</th><th>Authority</th><th>Primary Person</th><th>Email</th></tr>{role_rows}</table></div>
<details class='panel'><summary><b>Organization Units</b></summary>
<table><tr><th>Unit Key</th><th>Unit</th><th>Parent</th></tr>{unit_rows}</table></details>
<details class='panel'><summary><b>Decision Protocols</b></summary>
<table><tr><th>Protocol</th><th>Event</th><th>Source</th><th>Owner Role</th><th>Target</th><th>Priority</th><th>Impact</th><th>Urgency</th><th>Escalate</th></tr>{protocol_rows}</table></details>
<div class='panel'><h2>Recommendation Outcomes / Learning</h2>
<p class='sub'>Record whether accepted recommendations actually helped. These outcome labels feed the existing supervised BEAN observation store rather than silently rewriting operating rules.</p>
<table><tr><th>ID</th><th>Recommendation</th><th>Suggestion Status</th><th>Action</th><th>Assigned To</th><th>Action Status</th><th>Outcome</th></tr>{recent_rows}</table></div>"""
    return page("Executive Intelligence", body, module_key="executive")


@executive_blueprint.post("/executive/person")
def executive_person_post():
    upsert_person(
        request.form.get("person_key", ""),
        request.form.get("display_name", ""),
        email=request.form.get("email") or "",
        actor=request.form.get("actor") or "local",
    )
    return redirect("/executive")


@executive_blueprint.post("/executive/assignment")
def executive_assignment_post():
    assign_person_to_role(
        request.form.get("person_key", ""),
        request.form.get("role_key", ""),
        primary=bool(request.form.get("primary")),
        actor=request.form.get("actor") or "local",
    )
    return redirect("/executive")


@executive_blueprint.post("/executive/protocol")
def executive_protocol_post():
    create_decision_protocol(dict(request.form), actor=request.form.get("actor") or "local")
    return redirect("/executive")


@executive_blueprint.post("/executive/suggestion/<int:suggestion_id>/accept")
def executive_accept_post(suggestion_id: int):
    accept_executive_suggestion(suggestion_id, actor=request.form.get("actor") or "local")
    return redirect("/executive")


@executive_blueprint.post("/executive/suggestion/<int:suggestion_id>/outcome")
def executive_outcome_post(suggestion_id: int):
    rating = request.form.get("human_rating")
    capture_executive_outcome(
        suggestion_id,
        outcome=request.form.get("outcome") or "",
        human_rating=None if rating in (None, "") else float(rating),
        actor=request.form.get("actor") or "local",
    )
    return redirect("/executive")
