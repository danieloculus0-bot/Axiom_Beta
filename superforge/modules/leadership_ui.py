from __future__ import annotations

import html

from flask import Blueprint, redirect, request

from ..db import db
from ..ui import page
from .reward_rules import approve_nomination, create_reward_rule, reject_nomination
from .leadership import (
    _f,
    award_points,
    complete_workflow_action,
    create_reward_account,
    create_training_requirement,
    leadership_snapshot,
    record_morale_pulse,
    redeem_points,
)

leadership_blueprint=Blueprint("leadership_module",__name__)


def _e(value)->str:
    return html.escape("" if value is None else str(value))


def _table(rows,columns)->str:
    if not rows:
        return "<div class='empty'>No records yet.</div>"
    out=["<table><tr>"]
    out.extend(f"<th>{_e(label)}</th>" for _,label in columns)
    out.append("</tr>")
    for row in rows:
        d=dict(row)
        out.append("<tr>")
        out.extend(f"<td>{_e(d.get(key))}</td>" for key,_ in columns)
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


@leadership_blueprint.get("/leadership")
def leadership_dashboard():
    snap=leadership_snapshot()
    with db() as con:
        pulses=[dict(r) for r in con.execute(
            "SELECT * FROM morale_pulses ORDER BY period_end DESC,id DESC LIMIT 30"
        )]
        rewards=[dict(r) for r in con.execute(
            """SELECT e.id,a.account_key,a.display_name,a.department,e.event_type,e.category,
                      e.points,e.reason,e.approved_by,e.vendor_reference,e.created_at
               FROM reward_events e
               JOIN reward_accounts a ON a.id=e.account_id
               ORDER BY e.id DESC LIMIT 40"""
        )]
        accounts=[dict(r) for r in con.execute(
            """SELECT a.*,COALESCE(SUM(e.points),0) balance
               FROM reward_accounts a
               LEFT JOIN reward_events e ON e.account_id=a.id
               GROUP BY a.id ORDER BY a.department,a.display_name,a.account_key"""
        )]
        training=[dict(r) for r in con.execute(
            "SELECT * FROM training_requirements WHERE active=1 ORDER BY department,title"
        )]
        reward_rules=[dict(r) for r in con.execute(
            "SELECT * FROM reward_rules WHERE active=1 ORDER BY event_type,name"
        )]
        nominations=[dict(r) for r in con.execute(
            """SELECT n.*,r.name rule_name,a.account_key,a.display_name
               FROM reward_nominations n JOIN reward_rules r ON r.id=n.rule_id
               JOIN reward_accounts a ON a.id=n.account_id
               ORDER BY CASE n.status WHEN 'pending' THEN 0 WHEN 'held_limit' THEN 1 ELSE 2 END,n.id DESC LIMIT 60"""
        )]
        actions=[dict(r) for r in con.execute(
            """SELECT id,workflow_key,step_key,source_module,target_module,entity_type,entity_id,
                      assigned_to,status,due_date,created_at
               FROM workflow_actions WHERE status='open'
               ORDER BY CASE WHEN due_date!='' AND due_date<date('now') THEN 0 ELSE 1 END,due_date,id DESC
               LIMIT 80"""
        )]

    latest=snap["latest_morale"]
    risk="n/a" if not latest else latest["risk_score"]
    action_rows="".join(
        f"<tr><td>{a['id']}</td><td>{_e(a['workflow_key'])}</td><td>{_e(a['step_key'])}</td>"
        f"<td>{_e(a['source_module'])}</td><td>{_e(a['target_module'])}</td><td>{_e(a['assigned_to'])}</td>"
        f"<td>{_e(a['due_date'])}</td><td><form method='post' action='/leadership/action/{a['id']}/complete'>"
        f"<input name='actor' value='local' style='display:none'><button class='secondary'>Complete</button></form></td></tr>"
        for a in actions
    ) or "<tr><td colspan='8' class='empty'>No open workflow actions.</td></tr>"

    body=f"""<section class='page-head'><div class='grow'>
<p class='eyebrow'>Leadership / Company Pulse</p><h1>Run the company, not just the database</h1>
<p class='sub'>Cross-functional accountability, aggregate morale and workforce health, recognition, training incentives and the actions created by quality, purchasing, methods, maintenance and ERP events. Morale reporting is aggregate by department and period. Reward accounts remain a separate positive recognition ledger.</p>
</div></section>
<div class='grid'>
<div class='card'><strong class='big'>{_e(risk)}</strong><span class='label'>Latest Morale Risk / 100</span></div>
<div class='card'><strong class='big'>{snap['open_actions']}</strong><span class='label'>Open Actions</span></div>
<div class='card'><strong class='big'>{snap['overdue_actions']}</strong><span class='label'>Overdue Actions</span></div>
<div class='card'><strong class='big'>{snap['unassigned_actions']}</strong><span class='label'>Unassigned Actions</span></div>
<div class='card'><strong class='big'>{snap['open_quality']}</strong><span class='label'>Open Quality</span></div>
<div class='card'><strong class='big'>{snap['late_pos']}</strong><span class='label'>Late / At-Risk POs</span></div>
<div class='card'><strong class='big'>{snap['blocked_methods']}</strong><span class='label'>Methods Resource Blocks</span></div>
<div class='card'><strong class='big'>{_e(snap['reward_points_30d'])}</strong><span class='label'>Recognition Points / 30d</span></div>
</div>

<details class='panel' style='margin-top:14px'><summary><b>Record aggregate morale / workforce pulse</b></summary>
<form method='post' action='/leadership/morale' class='form-grid' style='margin-top:12px'>
<label>Period Start<input type='date' name='period_start' required></label><label>Period End<input type='date' name='period_end' required></label>
<label>Department<input name='department' value='ALL'></label><label>Source<input name='source' value='manual'></label>
<label>Scheduled Headcount<input type='number' name='scheduled_headcount' min='0'></label><label>Present Headcount<input type='number' name='present_headcount' min='0'></label>
<label>Overtime Hours<input type='number' step='.1' name='overtime_hours' min='0'></label><label>Employees Over 50 Hours<input type='number' name='over_50_hours_count' min='0'></label>
<label>Exhausted PTO Count<input type='number' name='exhausted_pto_count' min='0'></label><label>PTO Absence Count<input type='number' name='pto_absence_count' min='0'></label>
<label>Sick-Absence Clusters<input type='number' name='sick_absence_clusters' min='0'></label><label>Turnover Count<input type='number' name='turnover_count' min='0'></label>
<label>Staffing Shortage Count<input type='number' name='staffing_shortage_count' min='0'></label><label>Quality Risk Signal (0-100)<input type='number' step='.1' name='quality_risk_signal' min='0' max='100'></label>
<label class='wide'>Notes<textarea name='notes'></textarea></label><label>Actor<input name='actor' value='local'></label><div><button>Record Pulse</button></div>
</form></details>

<div class='grid'>
<details class='panel'><summary><b>Create reward / vending account</b></summary>
<form method='post' action='/leadership/reward-account' class='form-grid' style='margin-top:12px'>
<label>Account Key<input name='account_key' required placeholder='Card/account reference'></label><label>Display Name<input name='display_name'></label>
<label>Department<input name='department'></label><label>Vendor Ref<input name='vendor_ref' placeholder='Canteen/vendor account'></label>
<label>Actor<input name='actor' value='local'></label><div><button>Create Account</button></div></form></details>

<details class='panel'><summary><b>Award recognition points</b></summary>
<form method='post' action='/leadership/reward-credit' class='form-grid' style='margin-top:12px'>
<label>Account ID<input type='number' name='account_id' required></label><label>Points<input type='number' step='.01' name='points' required></label>
<label>Category<select name='category'><option>throughput</option><option>accuracy</option><option>quality</option><option>compliance</option><option>training</option><option>kaizen</option><option>safety</option><option>recognition</option></select></label>
<label>Approved By<input name='approved_by' value='local'></label><label class='wide'>Reason<textarea name='reason' required></textarea></label><div><button>Award</button></div>
</form></details>

<details class='panel'><summary><b>Redeem points</b></summary>
<form method='post' action='/leadership/redeem' class='form-grid' style='margin-top:12px'>
<label>Account ID<input type='number' name='account_id' required></label><label>Points<input type='number' step='.01' name='points' required></label>
<label>Vendor Reference<input name='vendor_reference'></label><label>Actor<input name='actor' value='local'></label>
<label class='wide'>Reason<input name='reason' value='Reward redemption'></label><div><button>Redeem</button></div></form></details>

<details class='panel'><summary><b>Add training requirement</b></summary>
<form method='post' action='/leadership/training-requirement' class='form-grid' style='margin-top:12px'>
<label>Training Key<input name='training_key' required></label><label>Title<input name='title' required></label>
<label>Department<input name='department'></label><label>Role<input name='role'></label>
<label>Recurrence Days<input type='number' name='recurrence_days' min='0'></label><label>Reward Points<input type='number' step='.01' name='reward_points' min='0'></label>
<label class='wide'>Notes<textarea name='notes'></textarea></label><label>Actor<input name='actor' value='local'></label><div><button>Add Training</button></div></form></details>

<details class='panel'><summary><b>Add recognition rule</b></summary>
<form method='post' action='/leadership/reward-rule' class='form-grid' style='margin-top:12px'>
<label>Name<input name='name' required></label><label>Event Type<input name='event_type' required placeholder='quality.excellence'></label>
<label>Source Module<input name='source_module'></label><label>Account Payload Key<input name='account_payload_key' value='reward_account_id'></label>
<label>Payload Key<input name='payload_key' placeholder='fpy'></label><label>Operator<select name='operator'><option>eq</option><option>ne</option><option>gt</option><option>gte</option><option>lt</option><option>lte</option><option>contains</option><option>truthy</option></select></label>
<label>Payload Value<input name='payload_value'></label><label>Category<input name='category' value='recognition'></label>
<label>Points<input type='number' step='.01' name='points' required min='0.01'></label><label>30-Day Limit<input type='number' step='.01' name='period_limit_points' value='0' min='0'></label>
<label>Approval<select name='requires_approval'><option value='1'>Review first</option><option value='0'>Auto-credit</option></select></label>
<label>Actor<input name='actor' value='local'></label><label class='wide'>Notes<textarea name='notes'></textarea></label><div><button>Add Recognition Rule</button></div>
</form></details>
</div>

<div class='panel'><h2>Leadership Action Queue</h2>
<table><tr><th>ID</th><th>Workflow</th><th>Step</th><th>Source</th><th>Target</th><th>Owner</th><th>Due</th><th>Close</th></tr>{action_rows}</table></div>
<div class='panel'><h2>Morale / Workforce Pulse History</h2>{_table(pulses,[('period_end','Period'),('department','Department'),('scheduled_headcount','Scheduled'),('present_headcount','Present'),('overtime_hours','OT Hours'),('over_50_hours_count','50+ Hrs'),('turnover_count','Turnover'),('staffing_shortage_count','Shortage'),('risk_score','Risk')])}</div>
<div class='panel'><h2>Recognition Accounts</h2>{_table(accounts,[('id','ID'),('account_key','Account'),('display_name','Name'),('department','Department'),('vendor_ref','Vendor Ref'),('balance','Balance'),('status','Status')])}</div>
<div class='panel'><h2>Recent Recognition / Redemption Ledger</h2>{_table(rewards,[('created_at','Time'),('account_key','Account'),('display_name','Name'),('category','Category'),('points','Points'),('reason','Reason'),('approved_by','Approved By'),('vendor_reference','Vendor Ref')])}</div>
<div class='panel'><h2>Training Requirements</h2>{_table(training,[('id','ID'),('training_key','Key'),('title','Training'),('department','Department'),('role','Role'),('recurrence_days','Recurrence Days'),('reward_points','Reward Points')])}</div>
<div class='panel'><h2>Recognition Rules</h2>{_table(reward_rules,[('id','ID'),('name','Rule'),('event_type','Event'),('payload_key','Signal'),('operator','Op'),('payload_value','Threshold'),('category','Category'),('points','Points'),('requires_approval','Review'),('period_limit_points','30-Day Limit')])}</div>
<div class='panel'><h2>Recognition Nominations / Rule Results</h2>
<table><tr><th>ID</th><th>Rule</th><th>Account</th><th>Points</th><th>Category</th><th>Status</th><th>Review</th></tr>
{''.join(f"<tr><td>{n['id']}</td><td>{_e(n['rule_name'])}</td><td>{_e(n['account_key'])}</td><td>{_e(n['points'])}</td><td>{_e(n['category'])}</td><td>{_e(n['status'])}</td><td>"+((f"<form method='post' action='/leadership/reward-nomination/{n['id']}/approve' style='display:inline'><input name='actor' value='local' style='display:none'><button>Approve</button></form> <form method='post' action='/leadership/reward-nomination/{n['id']}/reject' style='display:inline'><input name='actor' value='local' style='display:none'><button class='secondary'>Reject</button></form>") if n['status'] in ('pending','held_limit') else _e(n.get('reviewed_by')))+"</td></tr>" for n in nominations) or "<tr><td colspan='7' class='empty'>No rule results yet.</td></tr>"}
</table></div>"""
    return page("Leadership / Company Pulse",body,module_key="leadership")


@leadership_blueprint.post("/leadership/morale")
def morale_post():
    record_morale_pulse(dict(request.form),actor=request.form.get("actor") or "local")
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/reward-account")
def reward_account_post():
    create_reward_account(
        request.form.get("account_key",""),
        display_name=request.form.get("display_name",""),
        department=request.form.get("department",""),
        vendor_ref=request.form.get("vendor_ref",""),
        actor=request.form.get("actor") or "local",
    )
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/reward-credit")
def reward_credit_post():
    award_points(
        int(request.form.get("account_id")),_f(request.form.get("points")),
        category=request.form.get("category") or "recognition",
        reason=request.form.get("reason") or "Recognition",
        approved_by=request.form.get("approved_by") or "local",
    )
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/redeem")
def reward_redeem_post():
    redeem_points(
        int(request.form.get("account_id")),_f(request.form.get("points")),
        vendor_reference=request.form.get("vendor_reference") or "",
        reason=request.form.get("reason") or "Reward redemption",
        actor=request.form.get("actor") or "local",
    )
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/training-requirement")
def training_requirement_post():
    create_training_requirement(dict(request.form),actor=request.form.get("actor") or "local")
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/action/<int:action_id>/complete")
def workflow_action_complete_post(action_id: int):
    complete_workflow_action(
        action_id,actor=request.form.get("actor") or "local",output=request.form.get("output") or ""
    )
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/reward-rule")
def reward_rule_post():
    create_reward_rule(dict(request.form),actor=request.form.get("actor") or "local")
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/reward-nomination/<int:nomination_id>/approve")
def reward_nomination_approve_post(nomination_id: int):
    approve_nomination(nomination_id,actor=request.form.get("actor") or "local")
    return redirect("/leadership")


@leadership_blueprint.post("/leadership/reward-nomination/<int:nomination_id>/reject")
def reward_nomination_reject_post(nomination_id: int):
    reject_nomination(nomination_id,actor=request.form.get("actor") or "local")
    return redirect("/leadership")
