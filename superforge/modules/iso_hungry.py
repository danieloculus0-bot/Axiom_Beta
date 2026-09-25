from __future__ import annotations

import csv
import hashlib
import io
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from ..audit import record_event
from ..db import db
from ..event_bus import DomainEvent, publish, subscribe

_REGISTERED = False
_CENTS = Decimal("0.01")
_ALLOWED_PROFILE_STATUS = {"active", "hold", "disabled"}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _money(value: Any) -> float:
    return float(_decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP))


def _flag(value: Any, default: bool = False) -> int:
    if value in (None, ""):
        return 1 if default else 0
    return 0 if str(value).strip().lower() in {"0", "false", "no", "off"} else 1


def record_reported_event(
    event_type: str,
    *,
    reward_account_id: int,
    source_module: str,
    entity_type: str,
    entity_id: str,
    actor: str,
    reason: str = "",
    payload: dict[str, Any] | None = None,
) -> DomainEvent:
    """Publish a report event that can feed normal recognition rules.

    This function does not create money. It records the report on the shared
    event and audit spine and injects only the reward-account reference needed
    by recognition rules.
    """
    data = dict(payload or {})
    data["reward_account_id"] = int(reward_account_id)
    return publish(
        event_type,
        source_module=source_module,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor=actor,
        reason=reason,
        payload=data,
    )


def upsert_pay_profile(
    reward_account_id: int,
    *,
    employee_ref: str,
    payroll_ref: str = "",
    pay_group: str = "",
    allow_cash_awards: bool = True,
    status: str = "active",
    notes: str = "",
    actor: str = "local",
) -> int:
    employee_ref = (employee_ref or "").strip()
    if not employee_ref:
        raise ValueError("employee_ref is required")
    status = (status or "active").strip().lower()
    if status not in _ALLOWED_PROFILE_STATUS:
        raise ValueError(f"invalid pay profile status: {status}")
    with db() as con:
        account = con.execute(
            "SELECT id FROM reward_accounts WHERE id=?", (int(reward_account_id),)
        ).fetchone()
        if not account:
            raise ValueError("reward account not found")
        con.execute(
            """INSERT INTO iso_hungry_pay_profiles(
                 reward_account_id,employee_ref,payroll_ref,pay_group,allow_cash_awards,status,notes
               ) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(reward_account_id) DO UPDATE SET
                 employee_ref=excluded.employee_ref,
                 payroll_ref=excluded.payroll_ref,
                 pay_group=excluded.pay_group,
                 allow_cash_awards=excluded.allow_cash_awards,
                 status=excluded.status,
                 notes=excluded.notes,
                 updated_at=CURRENT_TIMESTAMP""",
            (
                int(reward_account_id),
                employee_ref,
                (payroll_ref or "").strip(),
                (pay_group or "").strip(),
                1 if allow_cash_awards else 0,
                status,
                notes or "",
            ),
        )
        row = con.execute(
            "SELECT id FROM iso_hungry_pay_profiles WHERE reward_account_id=?",
            (int(reward_account_id),),
        ).fetchone()
        profile_id = int(row["id"])
    record_event(
        event_type="ISO_HUNGRY_PROFILE",
        action="UPSERT",
        module="iso_hungry",
        entity_type="pay_profile",
        entity_id=profile_id,
        actor=actor,
        data={
            "reward_account_id": int(reward_account_id),
            "employee_ref": employee_ref,
            "pay_group": pay_group,
            "status": status,
            "allow_cash_awards": bool(allow_cash_awards),
        },
    )
    reconcile_account(int(reward_account_id), actor=actor)
    return profile_id


def create_cash_policy(data: dict[str, Any], *, actor: str = "local") -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("policy name is required")
    dollars_per_point = _money(data.get("dollars_per_point"))
    fixed_amount = _money(data.get("fixed_amount"))
    if dollars_per_point <= 0 and fixed_amount <= 0:
        raise ValueError("policy requires dollars_per_point or fixed_amount")
    max_event_amount = _money(data.get("max_event_amount"))
    rolling_30d_limit = _money(data.get("rolling_30d_limit"))
    if max_event_amount < 0 or rolling_30d_limit < 0:
        raise ValueError("policy limits cannot be negative")
    with db() as con:
        cur = con.execute(
            """INSERT INTO iso_hungry_cash_policies(
                 name,reward_category,source_module,earning_code,currency,
                 dollars_per_point,fixed_amount,max_event_amount,rolling_30d_limit,
                 requires_approval,active,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                name,
                (data.get("reward_category") or "*").strip(),
                (data.get("source_module") or "").strip(),
                (data.get("earning_code") or "ISOH_BONUS").strip(),
                (data.get("currency") or "USD").strip().upper(),
                dollars_per_point,
                fixed_amount,
                max_event_amount,
                rolling_30d_limit,
                _flag(data.get("requires_approval"), default=True),
                _flag(data.get("active"), default=True),
                data.get("notes") or "",
            ),
        )
        policy_id = int(cur.lastrowid)
    record_event(
        event_type="ISO_HUNGRY_POLICY",
        action="CREATE",
        module="iso_hungry",
        entity_type="cash_policy",
        entity_id=policy_id,
        actor=actor,
        data={
            "name": name,
            "reward_category": data.get("reward_category") or "*",
            "earning_code": data.get("earning_code") or "ISOH_BONUS",
            "currency": (data.get("currency") or "USD").upper(),
            "dollars_per_point": dollars_per_point,
            "fixed_amount": fixed_amount,
            "max_event_amount": max_event_amount,
            "rolling_30d_limit": rolling_30d_limit,
            "requires_approval": bool(_flag(data.get("requires_approval"), default=True)),
        },
    )
    return policy_id


def _matching_policies(reward_event: dict[str, Any]) -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute(
            """SELECT * FROM iso_hungry_cash_policies
               WHERE active=1
                 AND (reward_category='*' OR reward_category='' OR reward_category=?)
                 AND (COALESCE(source_module,'')='' OR source_module=?)
               ORDER BY id""",
            (reward_event["category"], reward_event.get("source_module") or ""),
        ).fetchall()
    return [dict(row) for row in rows]


def _open_exception(
    reward_event_id: int,
    reward_account_id: int,
    reason_code: str,
    detail: str,
) -> None:
    with db() as con:
        con.execute(
            """INSERT INTO iso_hungry_exceptions(
                 reward_event_id,reward_account_id,reason_code,detail,status
               ) VALUES(?,?,?,?,'open')
               ON CONFLICT(reward_event_id,reason_code) DO UPDATE SET
                 detail=excluded.detail,status='open',resolved_by=NULL,resolved_at=NULL""",
            (reward_event_id, reward_account_id, reason_code, detail),
        )


def _resolve_exceptions(reward_event_id: int, actor: str) -> None:
    with db() as con:
        con.execute(
            """UPDATE iso_hungry_exceptions
               SET status='resolved',resolved_by=?,resolved_at=CURRENT_TIMESTAMP
               WHERE reward_event_id=? AND status='open'""",
            (actor, reward_event_id),
        )


def _rolling_total(profile_id: int, policy_id: int, exclude_earning_id: int | None = None) -> float:
    sql = """SELECT COALESCE(SUM(amount),0) total
             FROM iso_hungry_earnings
             WHERE profile_id=? AND policy_id=?
               AND status IN ('approved','batched','exported','paid')
               AND created_at>=datetime('now','-30 days')"""
    args: list[Any] = [profile_id, policy_id]
    if exclude_earning_id is not None:
        sql += " AND id<>?"
        args.append(exclude_earning_id)
    with db() as con:
        row = con.execute(sql, tuple(args)).fetchone()
    return _money(row["total"] if row else 0)


def _capture_reward_event(
    reward_event_id: int,
    *,
    actor: str = "AUTOMATION",
    parent_event_id: str = "",
    correlation_id: str = "",
) -> list[int]:
    with db() as con:
        row = con.execute(
            """SELECT e.*,a.account_key
               FROM reward_events e
               JOIN reward_accounts a ON a.id=e.account_id
               WHERE e.id=?""",
            (int(reward_event_id),),
        ).fetchone()
    if not row:
        return []
    reward_event = dict(row)
    if reward_event["event_type"] != "credit" or float(reward_event["points"] or 0) <= 0:
        return []

    policies = _matching_policies(reward_event)
    if not policies:
        return []

    with db() as con:
        profile_row = con.execute(
            "SELECT * FROM iso_hungry_pay_profiles WHERE reward_account_id=?",
            (int(reward_event["account_id"]),),
        ).fetchone()
    if not profile_row:
        _open_exception(
            int(reward_event["id"]),
            int(reward_event["account_id"]),
            "missing_pay_profile",
            "A payable recognition matched a cash policy but no ISO-Hungry pay profile exists.",
        )
        return []
    profile = dict(profile_row)
    if int(profile["allow_cash_awards"] or 0) != 1 or profile["status"] != "active":
        _open_exception(
            int(reward_event["id"]),
            int(reward_event["account_id"]),
            "pay_profile_hold",
            f"Pay profile is not eligible for cash awards. status={profile['status']}",
        )
        return []

    created: list[int] = []
    for policy in policies:
        amount = _money(
            _decimal(reward_event["points"]) * _decimal(policy["dollars_per_point"])
            + _decimal(policy["fixed_amount"])
        )
        max_event = _money(policy["max_event_amount"])
        if max_event > 0:
            amount = min(amount, max_event)
        if amount <= 0:
            continue

        requires_approval = int(policy["requires_approval"] or 0) == 1
        status = "pending" if requires_approval else "approved"
        approved_by = None if requires_approval else "AUTOMATION"
        approved_at_sql = None if requires_approval else "CURRENT_TIMESTAMP"

        limit = _money(policy["rolling_30d_limit"])
        if not requires_approval and limit > 0:
            current = _rolling_total(int(profile["id"]), int(policy["id"]))
            if _money(current + amount) > limit:
                status = "held_limit"
                approved_by = None
                approved_at_sql = None

        reason = f"{policy['name']}: {reward_event['reason']}"
        with db() as con:
            existing = con.execute(
                """SELECT id,status FROM iso_hungry_earnings
                   WHERE profile_id=? AND policy_id=? AND reward_event_id=?""",
                (int(profile["id"]), int(policy["id"]), int(reward_event["id"])),
            ).fetchone()
            if existing:
                created.append(int(existing["id"]))
                continue
            if approved_at_sql:
                cur = con.execute(
                    """INSERT INTO iso_hungry_earnings(
                         profile_id,policy_id,reward_event_id,source_event_id,points,amount,currency,
                         earning_code,category,reason,status,approved_by,approved_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?, ?,CURRENT_TIMESTAMP)""",
                    (
                        int(profile["id"]),
                        int(policy["id"]),
                        int(reward_event["id"]),
                        reward_event.get("source_event_id") or "",
                        float(reward_event["points"]),
                        amount,
                        policy["currency"],
                        policy["earning_code"],
                        reward_event["category"],
                        reason,
                        status,
                        approved_by,
                    ),
                )
            else:
                cur = con.execute(
                    """INSERT INTO iso_hungry_earnings(
                         profile_id,policy_id,reward_event_id,source_event_id,points,amount,currency,
                         earning_code,category,reason,status
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(profile["id"]),
                        int(policy["id"]),
                        int(reward_event["id"]),
                        reward_event.get("source_event_id") or "",
                        float(reward_event["points"]),
                        amount,
                        policy["currency"],
                        policy["earning_code"],
                        reward_event["category"],
                        reason,
                        status,
                    ),
                )
            earning_id = int(cur.lastrowid)
        created.append(earning_id)
        record_event(
            event_type="ISO_HUNGRY_EARNING",
            action="CAPTURED",
            module="iso_hungry",
            source_module=reward_event.get("source_module") or "leadership",
            target_module="iso_hungry",
            entity_type="payable_earning",
            entity_id=earning_id,
            actor=actor,
            reason=reason,
            data={
                "profile_id": int(profile["id"]),
                "reward_event_id": int(reward_event["id"]),
                "source_event_id": reward_event.get("source_event_id") or "",
                "policy_id": int(policy["id"]),
                "amount": amount,
                "currency": policy["currency"],
                "earning_code": policy["earning_code"],
                "status": status,
            },
            parent_event_id=parent_event_id,
            correlation_id=correlation_id,
        )
        publish(
            "iso_hungry.earning.recorded",
            source_module="iso_hungry",
            entity_type="payable_earning",
            entity_id=str(earning_id),
            actor=actor,
            reason=reason,
            payload={
                "profile_id": int(profile["id"]),
                "reward_event_id": int(reward_event["id"]),
                "amount": amount,
                "currency": policy["currency"],
                "status": status,
            },
            parent_event_id=parent_event_id,
            correlation_id=correlation_id,
        )

    if created:
        _resolve_exceptions(int(reward_event["id"]), actor)
    return created


def _recognition_handler(event: DomainEvent) -> None:
    try:
        reward_event_id = int(event.entity_id)
    except (TypeError, ValueError):
        return
    _capture_reward_event(
        reward_event_id,
        actor=event.actor or "AUTOMATION",
        parent_event_id=event.event_id,
        correlation_id=event.correlation_id,
    )


def register_iso_hungry_logic() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe("recognition.awarded", _recognition_handler)
    _REGISTERED = True


def reconcile_account(reward_account_id: int, *, actor: str = "local") -> list[int]:
    with db() as con:
        rows = con.execute(
            """SELECT DISTINCT reward_event_id
               FROM iso_hungry_exceptions
               WHERE reward_account_id=? AND status='open'
               ORDER BY reward_event_id""",
            (int(reward_account_id),),
        ).fetchall()
    created: list[int] = []
    for row in rows:
        created.extend(_capture_reward_event(int(row["reward_event_id"]), actor=actor))
    return created


def approve_earning(
    earning_id: int,
    *,
    actor: str = "local",
    override_limit: bool = False,
) -> int:
    with db() as con:
        row = con.execute(
            """SELECT e.*,p.rolling_30d_limit,pr.status profile_status,pr.allow_cash_awards
               FROM iso_hungry_earnings e
               JOIN iso_hungry_cash_policies p ON p.id=e.policy_id
               JOIN iso_hungry_pay_profiles pr ON pr.id=e.profile_id
               WHERE e.id=?""",
            (int(earning_id),),
        ).fetchone()
    if not row:
        raise ValueError("earning not found")
    if row["status"] in {"approved", "batched", "exported", "paid"}:
        return int(earning_id)
    if row["status"] == "rejected":
        raise ValueError("rejected earning cannot be approved")
    if row["profile_status"] != "active" or int(row["allow_cash_awards"] or 0) != 1:
        raise ValueError("pay profile is not active for cash awards")

    limit = _money(row["rolling_30d_limit"])
    if limit > 0 and not override_limit:
        total = _rolling_total(int(row["profile_id"]), int(row["policy_id"]), int(earning_id))
        if _money(total + float(row["amount"])) > limit:
            with db() as con:
                con.execute(
                    "UPDATE iso_hungry_earnings SET status='held_limit' WHERE id=?",
                    (int(earning_id),),
                )
            record_event(
                event_type="ISO_HUNGRY_EARNING",
                action="HELD_LIMIT",
                module="iso_hungry",
                entity_type="payable_earning",
                entity_id=int(earning_id),
                actor=actor,
                reason="Rolling 30-day policy limit exceeded",
                data={"rolling_30d_limit": limit, "current_total": total, "amount": row["amount"]},
            )
            raise ValueError("rolling 30-day policy limit exceeded; explicit override required")

    with db() as con:
        con.execute(
            """UPDATE iso_hungry_earnings
               SET status='approved',approved_by=?,approved_at=CURRENT_TIMESTAMP,
                   rejected_by=NULL,rejected_at=NULL
               WHERE id=?""",
            (actor, int(earning_id)),
        )
    record_event(
        event_type="ISO_HUNGRY_EARNING",
        action="APPROVE",
        module="iso_hungry",
        entity_type="payable_earning",
        entity_id=int(earning_id),
        actor=actor,
        data={"amount": row["amount"], "currency": row["currency"], "override_limit": bool(override_limit)},
    )
    publish(
        "iso_hungry.earning.approved",
        source_module="iso_hungry",
        entity_type="payable_earning",
        entity_id=str(earning_id),
        actor=actor,
        payload={"profile_id": int(row["profile_id"]), "amount": row["amount"], "currency": row["currency"]},
    )
    return int(earning_id)


def reject_earning(earning_id: int, *, actor: str = "local", reason: str = "") -> None:
    with db() as con:
        row = con.execute(
            "SELECT status,amount,currency FROM iso_hungry_earnings WHERE id=?",
            (int(earning_id),),
        ).fetchone()
        if not row:
            raise ValueError("earning not found")
        if row["status"] in {"batched", "exported", "paid"}:
            raise ValueError("batched or paid earning cannot be rejected")
        if row["status"] == "rejected":
            return
        con.execute(
            """UPDATE iso_hungry_earnings
               SET status='rejected',rejected_by=?,rejected_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (actor, int(earning_id)),
        )
    record_event(
        event_type="ISO_HUNGRY_EARNING",
        action="REJECT",
        module="iso_hungry",
        entity_type="payable_earning",
        entity_id=int(earning_id),
        actor=actor,
        reason=reason or "Payable earning rejected",
        data={"amount": row["amount"], "currency": row["currency"]},
    )


def create_pay_batch(
    period_start: str,
    period_end: str,
    *,
    pay_group: str = "",
    batch_key: str = "",
    notes: str = "",
    actor: str = "local",
) -> int:
    period_start = (period_start or "").strip()
    period_end = (period_end or "").strip()
    if not period_start or not period_end or period_start > period_end:
        raise ValueError("valid period_start and period_end are required")
    pay_group = (pay_group or "").strip()
    batch_key = (batch_key or f"ISOH-{period_end}-{uuid.uuid4().hex[:10]}").strip()

    with db() as con:
        cur = con.execute(
            """INSERT INTO iso_hungry_pay_batches(
                 batch_key,period_start,period_end,pay_group,status,created_by,notes
               ) VALUES(?,?,?,?,'draft',?,?)""",
            (batch_key, period_start, period_end, pay_group, actor, notes),
        )
        batch_id = int(cur.lastrowid)
        rows = con.execute(
            """SELECT e.*,pr.employee_ref,pr.payroll_ref,pr.pay_group profile_pay_group
               FROM iso_hungry_earnings e
               JOIN iso_hungry_pay_profiles pr ON pr.id=e.profile_id
               WHERE e.status='approved'
                 AND pr.status='active'
                 AND pr.allow_cash_awards=1
                 AND date(e.created_at) BETWEEN date(?) AND date(?)
                 AND (?='' OR COALESCE(pr.pay_group,'')=?)
                 AND NOT EXISTS(
                   SELECT 1 FROM iso_hungry_pay_batch_items i WHERE i.earning_id=e.id
                 )
               ORDER BY pr.employee_ref,e.id""",
            (period_start, period_end, pay_group, pay_group),
        ).fetchall()
        if not rows:
            raise ValueError("no approved ISO-Hungry earnings are available for this pay period")

        currency = rows[0]["currency"]
        if any(row["currency"] != currency for row in rows):
            raise ValueError("mixed currencies require separate pay batches")

        total = Decimal("0")
        for row in rows:
            con.execute(
                """INSERT INTO iso_hungry_pay_batch_items(
                     batch_id,earning_id,profile_id,employee_ref,payroll_ref,pay_group,
                     earning_code,currency,amount,reward_event_id,source_event_id,category,reason
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    batch_id,
                    int(row["id"]),
                    int(row["profile_id"]),
                    row["employee_ref"],
                    row["payroll_ref"] or "",
                    row["profile_pay_group"] or "",
                    row["earning_code"],
                    row["currency"],
                    row["amount"],
                    int(row["reward_event_id"]),
                    row["source_event_id"] or "",
                    row["category"],
                    row["reason"],
                ),
            )
            con.execute(
                "UPDATE iso_hungry_earnings SET status='batched' WHERE id=?",
                (int(row["id"]),),
            )
            total += _decimal(row["amount"])
        total_amount = _money(total)
        con.execute(
            """UPDATE iso_hungry_pay_batches
               SET currency=?,item_count=?,total_amount=?
               WHERE id=?""",
            (currency, len(rows), total_amount, batch_id),
        )

    record_event(
        event_type="ISO_HUNGRY_PAY_BATCH",
        action="CREATE",
        module="iso_hungry",
        entity_type="pay_batch",
        entity_id=batch_id,
        actor=actor,
        data={
            "batch_key": batch_key,
            "period_start": period_start,
            "period_end": period_end,
            "pay_group": pay_group,
            "item_count": len(rows),
            "total_amount": total_amount,
            "currency": currency,
        },
    )
    publish(
        "iso_hungry.pay_batch.created",
        source_module="iso_hungry",
        entity_type="pay_batch",
        entity_id=str(batch_id),
        actor=actor,
        payload={"item_count": len(rows), "total_amount": total_amount, "currency": currency},
    )
    return batch_id


def approve_pay_batch(batch_id: int, *, actor: str = "local") -> int:
    with db() as con:
        row = con.execute(
            "SELECT * FROM iso_hungry_pay_batches WHERE id=?", (int(batch_id),)
        ).fetchone()
        if not row:
            raise ValueError("pay batch not found")
        if row["status"] in {"approved", "exported", "paid"}:
            return int(batch_id)
        if row["status"] != "draft":
            raise ValueError(f"pay batch cannot be approved from status {row['status']}")
        con.execute(
            """UPDATE iso_hungry_pay_batches
               SET status='approved',approved_by=?,approved_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (actor, int(batch_id)),
        )
    record_event(
        event_type="ISO_HUNGRY_PAY_BATCH",
        action="APPROVE",
        module="iso_hungry",
        entity_type="pay_batch",
        entity_id=int(batch_id),
        actor=actor,
        data={"item_count": row["item_count"], "total_amount": row["total_amount"], "currency": row["currency"]},
    )
    return int(batch_id)


def _render_pay_batch_csv(batch_id: int) -> tuple[str, dict[str, Any]]:
    with db() as con:
        batch_row = con.execute(
            "SELECT * FROM iso_hungry_pay_batches WHERE id=?", (int(batch_id),)
        ).fetchone()
        if not batch_row:
            raise ValueError("pay batch not found")
        items = con.execute(
            """SELECT * FROM iso_hungry_pay_batch_items
               WHERE batch_id=? ORDER BY employee_ref,id""",
            (int(batch_id),),
        ).fetchall()
    batch = dict(batch_row)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "batch_key",
            "period_start",
            "period_end",
            "employee_ref",
            "payroll_ref",
            "pay_group",
            "earning_code",
            "currency",
            "amount",
            "earning_id",
            "reward_event_id",
            "source_event_id",
            "category",
            "reason",
        ]
    )
    for item in items:
        writer.writerow(
            [
                batch["batch_key"],
                batch["period_start"],
                batch["period_end"],
                item["employee_ref"],
                item["payroll_ref"] or "",
                item["pay_group"] or "",
                item["earning_code"],
                item["currency"],
                f"{_money(item['amount']):.2f}",
                item["earning_id"],
                item["reward_event_id"],
                item["source_event_id"] or "",
                item["category"],
                item["reason"],
            ]
        )
    return output.getvalue(), batch


def export_pay_batch_csv(batch_id: int, *, actor: str = "local") -> str:
    csv_text, batch = _render_pay_batch_csv(int(batch_id))
    if batch["status"] not in {"approved", "exported", "paid"}:
        raise ValueError("pay batch must be approved before export")
    sha256 = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    if batch["export_sha256"] and batch["export_sha256"] != sha256:
        raise ValueError("pay batch export content changed after the recorded export")
    if batch["status"] == "approved":
        with db() as con:
            con.execute(
                """UPDATE iso_hungry_pay_batches
                   SET status='exported',exported_by=?,exported_at=CURRENT_TIMESTAMP,export_sha256=?
                   WHERE id=?""",
                (actor, sha256, int(batch_id)),
            )
            con.execute(
                """UPDATE iso_hungry_earnings
                   SET status='exported'
                   WHERE id IN(
                     SELECT earning_id FROM iso_hungry_pay_batch_items WHERE batch_id=?
                   )""",
                (int(batch_id),),
            )
        record_event(
            event_type="ISO_HUNGRY_PAY_BATCH",
            action="EXPORT",
            module="iso_hungry",
            entity_type="pay_batch",
            entity_id=int(batch_id),
            actor=actor,
            data={
                "batch_key": batch["batch_key"],
                "item_count": batch["item_count"],
                "total_amount": batch["total_amount"],
                "currency": batch["currency"],
                "sha256": sha256,
            },
        )
        publish(
            "iso_hungry.payroll_exported",
            source_module="iso_hungry",
            entity_type="pay_batch",
            entity_id=str(batch_id),
            actor=actor,
            payload={
                "batch_key": batch["batch_key"],
                "item_count": batch["item_count"],
                "total_amount": batch["total_amount"],
                "currency": batch["currency"],
                "sha256": sha256,
            },
        )
    return csv_text


def mark_pay_batch_paid(
    batch_id: int,
    *,
    payment_reference: str,
    actor: str = "local",
) -> int:
    payment_reference = (payment_reference or "").strip()
    if not payment_reference:
        raise ValueError("payment_reference is required")
    with db() as con:
        row = con.execute(
            "SELECT * FROM iso_hungry_pay_batches WHERE id=?", (int(batch_id),)
        ).fetchone()
        if not row:
            raise ValueError("pay batch not found")
        if row["status"] == "paid":
            return int(batch_id)
        if row["status"] != "exported":
            raise ValueError("pay batch must be exported before it can be marked paid")
        con.execute(
            """UPDATE iso_hungry_pay_batches
               SET status='paid',payment_reference=?,paid_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (payment_reference, int(batch_id)),
        )
        con.execute(
            """UPDATE iso_hungry_earnings
               SET status='paid'
               WHERE id IN(
                 SELECT earning_id FROM iso_hungry_pay_batch_items WHERE batch_id=?
               )""",
            (int(batch_id),),
        )
    record_event(
        event_type="ISO_HUNGRY_PAY_BATCH",
        action="PAID_CONFIRMED",
        module="iso_hungry",
        entity_type="pay_batch",
        entity_id=int(batch_id),
        actor=actor,
        reason="External payroll/payment system confirmed the batch",
        data={
            "payment_reference": payment_reference,
            "item_count": row["item_count"],
            "total_amount": row["total_amount"],
            "currency": row["currency"],
        },
    )
    publish(
        "iso_hungry.payroll_paid",
        source_module="iso_hungry",
        entity_type="pay_batch",
        entity_id=str(batch_id),
        actor=actor,
        payload={
            "payment_reference": payment_reference,
            "total_amount": row["total_amount"],
            "currency": row["currency"],
        },
    )
    return int(batch_id)


def void_pay_batch(batch_id: int, *, actor: str = "local", reason: str = "") -> None:
    with db() as con:
        row = con.execute(
            "SELECT * FROM iso_hungry_pay_batches WHERE id=?", (int(batch_id),)
        ).fetchone()
        if not row:
            raise ValueError("pay batch not found")
        if row["status"] == "void":
            return
        if row["status"] not in {"draft", "approved"}:
            raise ValueError("exported or paid batches cannot be voided")
        con.execute(
            """UPDATE iso_hungry_earnings
               SET status='approved'
               WHERE status='batched' AND id IN(
                 SELECT earning_id FROM iso_hungry_pay_batch_items WHERE batch_id=?
               )""",
            (int(batch_id),),
        )
        con.execute(
            """UPDATE iso_hungry_pay_batches
               SET status='void',voided_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (int(batch_id),),
        )
    record_event(
        event_type="ISO_HUNGRY_PAY_BATCH",
        action="VOID",
        module="iso_hungry",
        entity_type="pay_batch",
        entity_id=int(batch_id),
        actor=actor,
        reason=reason or "Pay batch voided before export",
    )


def reporting_snapshot() -> dict[str, Any]:
    with db() as con:
        pending = con.execute(
            "SELECT COUNT(*) n,COALESCE(SUM(amount),0) total FROM iso_hungry_earnings WHERE status IN ('pending','held_limit')"
        ).fetchone()
        approved = con.execute(
            "SELECT COUNT(*) n,COALESCE(SUM(amount),0) total FROM iso_hungry_earnings WHERE status='approved'"
        ).fetchone()
        exported = con.execute(
            "SELECT COUNT(*) n,COALESCE(SUM(total_amount),0) total FROM iso_hungry_pay_batches WHERE status='exported'"
        ).fetchone()
        paid = con.execute(
            "SELECT COUNT(*) n,COALESCE(SUM(total_amount),0) total FROM iso_hungry_pay_batches WHERE status='paid'"
        ).fetchone()
        exceptions = con.execute(
            "SELECT COUNT(*) n FROM iso_hungry_exceptions WHERE status='open'"
        ).fetchone()
    return {
        "pending_earnings": int(pending["n"]),
        "pending_amount": _money(pending["total"]),
        "approved_earnings": int(approved["n"]),
        "approved_amount": _money(approved["total"]),
        "exported_batches": int(exported["n"]),
        "exported_amount": _money(exported["total"]),
        "paid_batches": int(paid["n"]),
        "paid_amount": _money(paid["total"]),
        "open_exceptions": int(exceptions["n"]),
    }
