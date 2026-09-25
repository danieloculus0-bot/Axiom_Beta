from __future__ import annotations

from datetime import date, datetime
from typing import Any

from modules.ez_methods.engine import evaluate_dependency
from modules.ez_methods.models import AvailabilityState, DependencyKind, OperationDependency

from ..audit import record_event
from ..db import db
from ..event_bus import publish


def create_method_plan(data: dict[str, Any], actor: str = "local") -> int:
    with db() as con:
        cur = con.execute(
            """INSERT INTO ezm_method_plans(
               job_id,part_id,job_number,part_number,revision,customer,quantity,required_date,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?, 'DRAFT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (
                data.get("job_id") or None,
                data.get("part_id") or None,
                data.get("job_number") or "",
                data.get("part_number") or "",
                data.get("revision") or "",
                data.get("customer") or "",
                float(data.get("quantity") or 0),
                data.get("required_date") or "",
            ),
        )
        plan_id = int(cur.lastrowid)
    record_event(
        event_type="METHOD_PLAN",
        action="CREATE",
        module="methods",
        entity_type="method_plan",
        entity_id=plan_id,
        actor=actor,
        data={"job_number": data.get("job_number"), "part_number": data.get("part_number"), "revision": data.get("revision")},
    )
    publish(
        "methods.plan.created",
        source_module="methods",
        entity_type="method_plan",
        entity_id=str(plan_id),
        actor=actor,
        payload={"job_id": data.get("job_id"), "part_id": data.get("part_id"), "required_date": data.get("required_date")},
    )
    return plan_id


def dependency_readiness(row: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    promised = row.get("promised_date")
    need_by = row.get("need_by")
    dep = OperationDependency(
        dependency_id=str(row.get("dependency_key") or row.get("id")),
        kind=DependencyKind(str(row.get("kind") or "MATERIAL")),
        description=str(row.get("description") or ""),
        required_qty=float(row.get("required_qty") or 0),
        need_by=datetime.strptime(str(need_by), "%Y-%m-%d").date(),
        availability=AvailabilityState(str(row.get("availability") or "UNKNOWN")),
        on_hand_qty=float(row.get("on_hand_qty") or 0),
        ordered_qty=float(row.get("ordered_qty") or 0),
        promised_date=datetime.strptime(str(promised), "%Y-%m-%d").date() if promised else None,
        supplier=str(row.get("supplier") or ""),
        supplier_part_number=str(row.get("supplier_part_number") or ""),
        internal_tool_id=str(row.get("internal_tool_id") or ""),
        purchase_order=str(row.get("purchase_order") or ""),
        owner=str(row.get("owner") or ""),
        owner_email=str(row.get("owner_email") or ""),
        next_action=str(row.get("next_action") or ""),
    )
    return evaluate_dependency(dep, as_of=as_of)


def method_dashboard(context_type: str = "", context_id: str = "") -> tuple[list[Any], list[dict[str, Any]]]:
    sql = """SELECT m.id,m.job_id,m.part_id,m.job_number,m.part_number,m.revision,m.customer,m.quantity,
                    m.required_date,m.status,m.updated_at
             FROM ezm_method_plans m"""
    args: tuple[Any, ...] = ()
    if context_type == "job":
        sql += " WHERE m.job_id=?"
        args = (context_id,)
    elif context_type == "part":
        sql += " WHERE m.part_id=?"
        args = (context_id,)
    sql += " ORDER BY m.id DESC LIMIT 300"

    with db() as con:
        plans = con.execute(sql, args).fetchall()
        deps = con.execute(
            """SELECT d.*,o.sequence,o.operation,o.scheduled_date,m.job_number,m.part_number,m.id plan_id
               FROM ezm_dependencies d
               JOIN ezm_operations o ON o.id=d.operation_id
               JOIN ezm_method_plans m ON m.id=o.plan_id
               ORDER BY d.need_by,d.id"""
        ).fetchall()

    readiness: list[dict[str, Any]] = []
    for row in deps:
        d = dict(row)
        check = dependency_readiness(d)
        d["readiness"] = check["status"]
        d["readiness_reason"] = check["reason"]
        readiness.append(d)
    return plans, readiness
