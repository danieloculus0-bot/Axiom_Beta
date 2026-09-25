from __future__ import annotations

from ..audit import record_event
from ..db import db
from ..event_bus import DomainEvent, subscribe
from .leadership import award_points

_REGISTERED=False


def _number_or_text(value):
    if value is None:
        return None
    if isinstance(value,(int,float,bool)):
        return value
    text=str(value).strip()
    try:
        return float(text)
    except ValueError:
        return text


def _matches(rule: dict,event: DomainEvent)->bool:
    if rule.get("source_module") and rule["source_module"]!=event.source_module:
        return False
    key=(rule.get("payload_key") or "").strip()
    if not key:
        return True
    actual=_number_or_text(event.payload.get(key))
    expected=_number_or_text(rule.get("payload_value"))
    op=(rule.get("operator") or "eq").lower()
    if op=="truthy":
        return bool(event.payload.get(key))
    if op=="contains":
        return str(expected).lower() in str(actual or "").lower()
    if op in {"gt","gte","lt","lte"}:
        try:
            left=float(actual); right=float(expected)
        except (TypeError,ValueError):
            return False
        return {"gt":left>right,"gte":left>=right,"lt":left<right,"lte":left<=right}[op]
    if op=="ne":
        return actual!=expected
    return actual==expected


def _handler(event: DomainEvent)->None:
    if event.event_type in {"recognition.awarded","reward.redeemed"}:
        return
    with db() as con:
        rules=[dict(r) for r in con.execute(
            "SELECT * FROM reward_rules WHERE active=1 AND event_type=? ORDER BY id",
            (event.event_type,),
        )]
    for rule in rules:
        if not _matches(rule,event):
            continue
        account_value=event.payload.get(rule.get("account_payload_key") or "reward_account_id")
        try:
            account_id=int(account_value)
        except (TypeError,ValueError):
            continue
        with db() as con:
            account=con.execute(
                "SELECT id FROM reward_accounts WHERE id=? AND status='active'",(account_id,)
            ).fetchone()
            prior=con.execute(
                "SELECT id FROM reward_nominations WHERE rule_id=? AND source_event_id=? AND account_id=?",
                (rule["id"],event.event_id,account_id),
            ).fetchone()
        if not account or prior:
            continue

        points=float(rule["points"] or 0)
        status="pending" if int(rule["requires_approval"] or 0) else "ready"
        cap=float(rule["period_limit_points"] or 0)
        if status=="ready" and cap>0:
            with db() as con:
                earned=con.execute(
                    """SELECT COALESCE(SUM(points),0) n FROM reward_events
                       WHERE account_id=? AND category=? AND points>0
                         AND created_at>=datetime('now','-30 days')""",
                    (account_id,rule["category"]),
                ).fetchone()["n"]
            if float(earned or 0)+points>cap:
                status="held_limit"

        reason=f"Recognition rule: {rule['name']}"
        with db() as con:
            cur=con.execute(
                """INSERT INTO reward_nominations(
                     rule_id,source_event_id,account_id,points,category,reason,status
                   ) VALUES(?,?,?,?,?,?,?)""",
                (rule["id"],event.event_id,account_id,points,rule["category"],reason,status),
            )
            nomination_id=int(cur.lastrowid)

        if status=="ready":
            reward_event_id=award_points(
                account_id,points,category=rule["category"],reason=reason,
                source_module=event.source_module,source_event_id=event.event_id,
                approved_by="AUTOMATION",
            )
            with db() as con:
                con.execute(
                    """UPDATE reward_nominations SET status='awarded',reviewed_by='AUTOMATION',
                       reward_event_id=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (reward_event_id,nomination_id),
                )


def register_reward_logic()->None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe("*",_handler)
    _REGISTERED=True


def create_reward_rule(data: dict, *, actor: str="local")->int:
    points=float(data.get("points") or 0)
    if points<=0:
        raise ValueError("points must be positive")
    requires=1 if str(data.get("requires_approval","1")).lower() not in {"0","false","no","off"} else 0
    with db() as con:
        cur=con.execute(
            """INSERT INTO reward_rules(
                 name,event_type,source_module,account_payload_key,payload_key,operator,payload_value,
                 category,points,requires_approval,period_limit_points,active,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (data.get("name") or "").strip(),(data.get("event_type") or "").strip(),
                (data.get("source_module") or "").strip(),
                (data.get("account_payload_key") or "reward_account_id").strip(),
                (data.get("payload_key") or "").strip(),(data.get("operator") or "eq").strip(),
                (data.get("payload_value") or "").strip(),(data.get("category") or "recognition").strip(),
                points,requires,float(data.get("period_limit_points") or 0),1,(data.get("notes") or "").strip(),
            ),
        )
        rid=int(cur.lastrowid)
    record_event(
        event_type="REWARD_RULE",action="CREATE",module="leadership",
        entity_type="reward_rule",entity_id=rid,actor=actor,
        data={"name":data.get("name"),"event_type":data.get("event_type"),"points":points},
    )
    return rid


def approve_nomination(nomination_id: int, *, actor: str="local")->int:
    with db() as con:
        row=con.execute("SELECT * FROM reward_nominations WHERE id=?",(nomination_id,)).fetchone()
        if not row:
            raise ValueError("nomination not found")
        if row["status"]=="awarded":
            return int(row["reward_event_id"])
    reward_event_id=award_points(
        int(row["account_id"]),float(row["points"]),category=row["category"],reason=row["reason"],
        source_module="leadership",source_event_id=row["source_event_id"],approved_by=actor,
    )
    with db() as con:
        con.execute(
            """UPDATE reward_nominations SET status='awarded',reviewed_by=?,reward_event_id=?,
               reviewed_at=CURRENT_TIMESTAMP WHERE id=?""",
            (actor,reward_event_id,nomination_id),
        )
    return reward_event_id


def reject_nomination(nomination_id: int, *, actor: str="local")->None:
    with db() as con:
        row=con.execute("SELECT status FROM reward_nominations WHERE id=?",(nomination_id,)).fetchone()
        if not row:
            raise ValueError("nomination not found")
        if row["status"]=="awarded":
            raise ValueError("awarded nomination cannot be rejected")
        con.execute(
            "UPDATE reward_nominations SET status='rejected',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (actor,nomination_id),
        )
    record_event(
        event_type="REWARD_NOMINATION",action="REJECT",module="leadership",
        entity_type="reward_nomination",entity_id=nomination_id,actor=actor,
    )
