from __future__ import annotations

import json
from datetime import date, timedelta

from ..audit import record_event
from ..db import db
from ..event_bus import publish


def _f(value, default=0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return float(default)


def _i(value, default=0) -> int:
    try:
        return int(float(value if value not in (None, "") else default))
    except (TypeError, ValueError):
        return int(default)


def calculate_morale_risk(data: dict) -> float:
    """Aggregate workforce-health heuristic. It never scores an individual."""
    scheduled=max(_i(data.get("scheduled_headcount")), _i(data.get("present_headcount")), 1)
    present=max(_i(data.get("present_headcount")),0)
    attendance_gap=(max(scheduled-present,0)/scheduled) if _i(data.get("scheduled_headcount"))>0 else 0.0
    overtime=_f(data.get("overtime_hours"))/max(scheduled*40.0,1.0)
    over50=_i(data.get("over_50_hours_count"))/scheduled
    exhausted=_i(data.get("exhausted_pto_count"))/scheduled
    sick=_i(data.get("sick_absence_clusters"))/scheduled
    turnover=_i(data.get("turnover_count"))/scheduled
    shortage=_i(data.get("staffing_shortage_count"))/scheduled
    quality=max(0.0,min(_f(data.get("quality_risk_signal")),100.0))/100.0
    weighted=(
        min(attendance_gap/0.10,1.0)*0.25
        + min(overtime/0.15,1.0)*0.15
        + min(over50/0.10,1.0)*0.10
        + min(exhausted/0.15,1.0)*0.10
        + min(sick/0.10,1.0)*0.10
        + min(turnover/0.08,1.0)*0.15
        + min(shortage/0.10,1.0)*0.10
        + quality*0.05
    )
    return round(max(0.0,min(weighted*100.0,100.0)),1)


def record_morale_pulse(data: dict, *, actor: str="local") -> int:
    payload={
        "period_start":data.get("period_start") or str(date.today()),
        "period_end":data.get("period_end") or str(date.today()),
        "department":(data.get("department") or "ALL").strip(),
        "scheduled_headcount":_i(data.get("scheduled_headcount")),
        "present_headcount":_i(data.get("present_headcount")),
        "overtime_hours":_f(data.get("overtime_hours")),
        "over_50_hours_count":_i(data.get("over_50_hours_count")),
        "exhausted_pto_count":_i(data.get("exhausted_pto_count")),
        "pto_absence_count":_i(data.get("pto_absence_count")),
        "sick_absence_clusters":_i(data.get("sick_absence_clusters")),
        "turnover_count":_i(data.get("turnover_count")),
        "staffing_shortage_count":_i(data.get("staffing_shortage_count")),
        "quality_risk_signal":_f(data.get("quality_risk_signal")),
        "source":data.get("source") or "manual",
        "notes":data.get("notes") or "",
    }
    payload["risk_score"]=calculate_morale_risk(payload)
    with db() as con:
        cur=con.execute(
            """INSERT INTO morale_pulses(
              period_start,period_end,department,scheduled_headcount,present_headcount,overtime_hours,
              over_50_hours_count,exhausted_pto_count,pto_absence_count,sick_absence_clusters,
              turnover_count,staffing_shortage_count,quality_risk_signal,risk_score,source,notes,created_by
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                payload["period_start"],payload["period_end"],payload["department"],payload["scheduled_headcount"],
                payload["present_headcount"],payload["overtime_hours"],payload["over_50_hours_count"],
                payload["exhausted_pto_count"],payload["pto_absence_count"],payload["sick_absence_clusters"],
                payload["turnover_count"],payload["staffing_shortage_count"],payload["quality_risk_signal"],
                payload["risk_score"],payload["source"],payload["notes"],actor,
            ),
        )
        pulse_id=int(cur.lastrowid)
    publish(
        "morale.pulse.recorded",source_module="leadership",entity_type="morale_pulse",entity_id=str(pulse_id),
        actor=actor,reason="Aggregate morale/company pulse recorded",payload=payload,
    )
    return pulse_id


def create_reward_account(account_key: str, *, display_name: str="", department: str="", vendor_ref: str="", actor: str="local") -> int:
    key=(account_key or "").strip()
    if not key:
        raise ValueError("account_key is required")
    with db() as con:
        con.execute(
            """INSERT INTO reward_accounts(account_key,display_name,department,vendor_ref)
               VALUES(?,?,?,?)
               ON CONFLICT(account_key) DO UPDATE SET
                 display_name=excluded.display_name,department=excluded.department,
                 vendor_ref=excluded.vendor_ref,updated_at=CURRENT_TIMESTAMP""",
            (key,display_name.strip(),department.strip(),vendor_ref.strip()),
        )
        row=con.execute("SELECT id FROM reward_accounts WHERE account_key=?",(key,)).fetchone()
        account_id=int(row["id"])
    record_event(
        event_type="REWARD_ACCOUNT",action="UPSERT",module="leadership",
        entity_type="reward_account",entity_id=account_id,actor=actor,
        data={"account_key":key,"department":department},
    )
    return account_id


def reward_balance(account_id: int) -> float:
    with db() as con:
        row=con.execute("SELECT COALESCE(SUM(points),0) balance FROM reward_events WHERE account_id=?",(account_id,)).fetchone()
    return float(row["balance"] or 0)


def award_points(account_id: int, points: float, *, category: str, reason: str, source_module: str="leadership", source_event_id: str="", approved_by: str="local") -> int:
    value=_f(points)
    if value<=0:
        raise ValueError("award points must be positive")
    with db() as con:
        account=con.execute("SELECT id FROM reward_accounts WHERE id=? AND status='active'",(account_id,)).fetchone()
        if not account:
            raise ValueError("active reward account not found")
        cur=con.execute(
            """INSERT INTO reward_events(account_id,event_type,category,points,source_module,source_event_id,reason,approved_by)
               VALUES(?,'credit',?,?,?,?,?,?)""",
            (account_id,category,value,source_module,source_event_id,reason,approved_by),
        )
        reward_event_id=int(cur.lastrowid)
    publish(
        "recognition.awarded",source_module="leadership",entity_type="reward_event",entity_id=str(reward_event_id),
        actor=approved_by,reason=reason,payload={"account_id":account_id,"points":value,"category":category},
    )
    return reward_event_id


def redeem_points(account_id: int, points: float, *, vendor_reference: str="", reason: str="Reward redemption", actor: str="local") -> int:
    value=_f(points)
    if value<=0:
        raise ValueError("redemption points must be positive")
    if reward_balance(account_id)<value:
        raise ValueError("insufficient reward balance")
    with db() as con:
        cur=con.execute(
            """INSERT INTO reward_events(account_id,event_type,category,points,source_module,reason,approved_by,vendor_reference)
               VALUES(?,'redemption','redemption',?,'leadership',?,?,?)""",
            (account_id,-value,reason,actor,vendor_reference),
        )
        reward_event_id=int(cur.lastrowid)
    publish(
        "reward.redeemed",source_module="leadership",entity_type="reward_event",entity_id=str(reward_event_id),
        actor=actor,reason=reason,payload={"account_id":account_id,"points":value,"vendor_reference":vendor_reference},
    )
    return reward_event_id


def create_training_requirement(data: dict, *, actor: str="local") -> int:
    key=(data.get("training_key") or "").strip()
    title=(data.get("title") or "").strip()
    if not key or not title:
        raise ValueError("training_key and title are required")
    with db() as con:
        cur=con.execute(
            """INSERT INTO training_requirements(training_key,title,department,role,recurrence_days,reward_points,active,notes)
               VALUES(?,?,?,?,?,?,1,?)""",
            (
                key,title,(data.get("department") or "").strip(),(data.get("role") or "").strip(),
                _i(data.get("recurrence_days")),_f(data.get("reward_points")),data.get("notes") or "",
            ),
        )
        rid=int(cur.lastrowid)
    record_event(
        event_type="TRAINING_REQUIREMENT",action="CREATE",module="leadership",
        entity_type="training_requirement",entity_id=rid,actor=actor,
    )
    return rid


def complete_training(requirement_id: int, account_id: int|None, *, completed_by: str, verified_by: str, evidence_ref: str="") -> int:
    with db() as con:
        req=con.execute("SELECT * FROM training_requirements WHERE id=? AND active=1",(requirement_id,)).fetchone()
        if not req:
            raise ValueError("active training requirement not found")
        expires_on=""
        if int(req["recurrence_days"] or 0)>0:
            expires_on=str(date.today()+timedelta(days=int(req["recurrence_days"])))
        cur=con.execute(
            """INSERT INTO training_completions(
                 requirement_id,reward_account_id,completed_by,verified_by,completed_on,expires_on,evidence_ref
               ) VALUES(?,?,?,?,?,?,?)""",
            (requirement_id,account_id,completed_by,verified_by,str(date.today()),expires_on,evidence_ref),
        )
        completion_id=int(cur.lastrowid)
        points=float(req["reward_points"] or 0)
        title=req["title"]
    evt=publish(
        "training.completed",source_module="leadership",entity_type="training_completion",entity_id=str(completion_id),
        actor=verified_by,reason=f"Training completed: {title}",
        payload={"requirement_id":requirement_id,"account_id":account_id,"reward_points":points,"title":title},
    )
    if account_id and points>0:
        award_points(
            account_id,points,category="training",reason=f"Training completed: {title}",
            source_module="leadership",source_event_id=evt.event_id,approved_by=verified_by,
        )
    return completion_id


def complete_workflow_action(action_id: int, *, actor: str="local", output: str="") -> None:
    with db() as con:
        row=con.execute("SELECT * FROM workflow_actions WHERE id=?",(action_id,)).fetchone()
        if not row:
            raise ValueError("workflow action not found")
        con.execute(
            "UPDATE workflow_actions SET status='completed',output_json=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps({"note":output},sort_keys=True),action_id),
        )
    record_event(
        event_type="WORKFLOW_ACTION",action="COMPLETED",module="leadership",
        source_module=row["source_module"] or "",target_module=row["target_module"] or "",
        entity_type=row["entity_type"] or "workflow_action",entity_id=row["entity_id"] or str(action_id),
        actor=actor,reason=row["workflow_key"] or "workflow action",
        data={"action_id":action_id,"output":output},event_id=row["event_id"] or "",
    )


def leadership_snapshot() -> dict:
    with db() as con:
        latest=con.execute("SELECT * FROM morale_pulses ORDER BY period_end DESC,id DESC LIMIT 1").fetchone()
        return {
            "latest_morale":dict(latest) if latest else None,
            "open_actions":con.execute("SELECT COUNT(*) n FROM workflow_actions WHERE status='open'").fetchone()["n"],
            "overdue_actions":con.execute("SELECT COUNT(*) n FROM workflow_actions WHERE status='open' AND due_date!='' AND due_date<date('now')").fetchone()["n"],
            "unassigned_actions":con.execute("SELECT COUNT(*) n FROM workflow_actions WHERE status='open' AND COALESCE(assigned_to,'')=''").fetchone()["n"],
            "open_quality":con.execute("SELECT COUNT(*) n FROM quality_records WHERE status NOT IN ('closed','complete')").fetchone()["n"],
            "late_pos":con.execute("SELECT COUNT(*) n FROM purchase_orders WHERE status NOT IN ('closed','received') AND COALESCE(expected_date,required_date)<date('now')").fetchone()["n"],
            "blocked_methods":con.execute("SELECT COUNT(*) n FROM ezm_dependencies WHERE availability IN ('UNKNOWN','BLOCKED')").fetchone()["n"],
            "reward_points_30d":con.execute("SELECT COALESCE(SUM(points),0) n FROM reward_events WHERE points>0 AND created_at>=datetime('now','-30 days')").fetchone()["n"],
        }
