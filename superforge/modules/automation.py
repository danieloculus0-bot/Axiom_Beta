from __future__ import annotations

import html
import json
from datetime import date, timedelta

from flask import Blueprint, redirect, request

from ..audit import record_event
from ..db import db
from ..event_bus import DomainEvent, create_action, subscribe
from ..ui import page

automation_blueprint = Blueprint("automation_module", __name__)
_REGISTERED = False


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _coerce(value):
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return text


def _matches(rule: dict, event: DomainEvent) -> bool:
    if rule.get("source_module") and rule["source_module"] != event.source_module:
        return False
    key = (rule.get("payload_key") or "").strip()
    if not key:
        return True
    actual = event.payload.get(key)
    op = (rule.get("operator") or "eq").lower()
    expected = _coerce(rule.get("payload_value"))
    left = _coerce(actual)
    if op == "truthy":
        return bool(actual)
    if op == "contains":
        return str(expected).lower() in str(actual or "").lower()
    if op in {"gt", "gte", "lt", "lte"}:
        try:
            l = float(left)
            r = float(expected)
        except (TypeError, ValueError):
            return False
        return {"gt": l > r, "gte": l >= r, "lt": l < r, "lte": l <= r}[op]
    if op == "ne":
        return left != expected
    return left == expected


def _automation_handler(event: DomainEvent) -> None:
    with db() as con:
        rules = [dict(r) for r in con.execute(
            """SELECT * FROM automation_rules
               WHERE enabled=1 AND (event_type=? OR event_type='*')
               ORDER BY priority DESC,id""",
            (event.event_type,),
        )]
    for rule in rules:
        if not _matches(rule, event):
            continue
        with db() as con:
            prior = con.execute(
                "SELECT id FROM automation_rule_runs WHERE rule_id=? AND source_event_id=?",
                (rule["id"], event.event_id),
            ).fetchone()
        if prior:
            continue
        due_date = ""
        if int(rule.get("due_days") or 0) > 0:
            due_date = str(date.today() + timedelta(days=int(rule["due_days"])))
        action_id = create_action(
            event,
            workflow_key=rule["workflow_key"],
            step_key=rule["step_key"],
            target_module=rule["target_module"],
            assigned_to=rule.get("assigned_to") or "",
            due_date=due_date,
            input_data={
                "automation_rule_id": rule["id"],
                "rule_name": rule["name"],
                "source_payload": event.payload,
            },
        )
        with db() as con:
            con.execute(
                """INSERT OR IGNORE INTO automation_rule_runs(
                     rule_id,source_event_id,workflow_action_id,status,detail_json
                   ) VALUES(?,?,?,'executed',?)""",
                (
                    rule["id"],
                    event.event_id,
                    action_id,
                    json.dumps(
                        {
                            "event_type": event.event_type,
                            "entity_type": event.entity_type,
                            "entity_id": event.entity_id,
                        },
                        sort_keys=True,
                    ),
                ),
            )
        record_event(
            event_type="AUTOMATION_RULE",
            action="EXECUTED",
            module="automation",
            source_module=event.source_module,
            target_module=rule["target_module"],
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor=event.actor,
            reason=rule["name"],
            data={"rule_id": rule["id"], "workflow_action_id": action_id},
            parent_event_id=event.event_id,
            correlation_id=event.correlation_id,
        )


def register_automation_logic() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe("*", _automation_handler)
    _REGISTERED = True


def create_automation_rule(data: dict, *, actor: str = "local") -> int:
    with db() as con:
        cur = con.execute(
            """INSERT INTO automation_rules(
                name,event_type,source_module,payload_key,operator,payload_value,
                workflow_key,step_key,target_module,assigned_to,due_days,enabled,priority,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (data.get("name") or "").strip(),
                (data.get("event_type") or "").strip(),
                (data.get("source_module") or "").strip(),
                (data.get("payload_key") or "").strip(),
                (data.get("operator") or "eq").strip(),
                (data.get("payload_value") or "").strip(),
                (data.get("workflow_key") or "").strip(),
                (data.get("step_key") or "").strip(),
                (data.get("target_module") or "").strip(),
                (data.get("assigned_to") or "").strip(),
                int(data.get("due_days") or 0),
                1 if str(data.get("enabled", "1")).lower() not in {"0", "false", "off"} else 0,
                int(data.get("priority") or 0),
                (data.get("notes") or "").strip(),
            ),
        )
        rid = int(cur.lastrowid)
    record_event(
        event_type="AUTOMATION_RULE",
        action="CREATE",
        module="automation",
        entity_type="automation_rule",
        entity_id=rid,
        actor=actor,
        data={"name": data.get("name"), "event_type": data.get("event_type")},
    )
    return rid


@automation_blueprint.route("/automation", methods=["GET", "POST"])
def automation_dashboard():
    if request.method == "POST":
        create_automation_rule(dict(request.form), actor=request.form.get("actor") or "local")
        return redirect("/automation")
    with db() as con:
        rules = [dict(r) for r in con.execute(
            "SELECT * FROM automation_rules ORDER BY enabled DESC,priority DESC,id"
        )]
        runs = [dict(r) for r in con.execute(
            """SELECT r.id,r.source_event_id,r.workflow_action_id,r.status,r.executed_at,
                      a.name rule_name,a.target_module
               FROM automation_rule_runs r
               JOIN automation_rules a ON a.id=r.rule_id
               ORDER BY r.id DESC LIMIT 80"""
        )]
    rule_rows = "".join(
        f"<tr class='sf-context' data-entity-type='automation_rule' data-entity-id='{r['id']}' data-entity-label='{_e(r['name'])}'>"
        f"<td>{r['id']}</td><td><b>{_e(r['name'])}</b></td><td>{_e(r['event_type'])}</td>"
        f"<td>{_e(r['source_module'])}</td><td>{_e(r['payload_key'])} {_e(r['operator'])} {_e(r['payload_value'])}</td>"
        f"<td>{_e(r['workflow_key'])} / {_e(r['step_key'])}</td><td>{_e(r['target_module'])}</td>"
        f"<td>{_e(r['assigned_to'])}</td><td>{_e(r['due_days'])}</td><td>{_e(r['enabled'])}</td></tr>"
        for r in rules
    ) or "<tr><td colspan='10' class='empty'>No configurable rules yet. Core routing remains active.</td></tr>"
    run_rows = "".join(
        f"<tr><td>{x['id']}</td><td>{_e(x['rule_name'])}</td><td>{_e(x['source_event_id'])}</td>"
        f"<td>{_e(x['workflow_action_id'])}</td><td>{_e(x['target_module'])}</td><td>{_e(x['status'])}</td>"
        f"<td>{_e(x['executed_at'])}</td></tr>"
        for x in runs
    ) or "<tr><td colspan='7' class='empty'>No automation executions yet.</td></tr>"
    body = f"""<section class='page-head'><div class='grow'><p class='eyebrow'>Deterministic automation</p>
<h1>Automation Rules</h1><p class='sub'>Turn domain events into assigned, due-dated workflow actions. Every execution keeps the source event, generated action and audit receipt.</p></div></section>
<details class='panel'><summary><b>Add automation rule</b></summary>
<form method='post' class='form-grid' style='margin-top:12px'>
<label>Name<input name='name' required></label><label>Event Type<input name='event_type' required placeholder='training.completed'></label>
<label>Source Module<input name='source_module' placeholder='optional'></label><label>Payload Key<input name='payload_key' placeholder='optional'></label>
<label>Operator<select name='operator'><option>eq</option><option>ne</option><option>gt</option><option>gte</option><option>lt</option><option>lte</option><option>contains</option><option>truthy</option></select></label>
<label>Payload Value<input name='payload_value'></label><label>Workflow Key<input name='workflow_key' required></label>
<label>Step Key<input name='step_key' required></label><label>Target Module<input name='target_module' required></label>
<label>Assigned To<input name='assigned_to'></label><label>Due Days<input type='number' name='due_days' value='0' min='0'></label>
<label>Priority<input type='number' name='priority' value='0'></label><label>Enabled<select name='enabled'><option value='1'>Yes</option><option value='0'>No</option></select></label>
<label>Actor<input name='actor' value='local'></label><label class='wide'>Notes<textarea name='notes'></textarea></label>
<div><button>Create Rule</button></div></form></details>
<div class='panel'><h2>Rules</h2><table><tr><th>ID</th><th>Name</th><th>Event</th><th>Source</th><th>Condition</th><th>Workflow</th><th>Target</th><th>Owner</th><th>Due Days</th><th>Enabled</th></tr>{rule_rows}</table></div>
<div class='panel'><h2>Execution Receipts</h2><table><tr><th>ID</th><th>Rule</th><th>Source Event</th><th>Action</th><th>Target</th><th>Status</th><th>Executed</th></tr>{run_rows}</table></div>"""
    return page("Automation Rules", body, module_key="automation")
