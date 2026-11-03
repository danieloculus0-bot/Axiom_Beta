from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .audit import record_event
from .access_control import verified_actor
from .db import db

@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    event_type: str
    source_module: str
    entity_type: str
    entity_id: str
    actor: str
    reason: str
    payload: dict[str,Any]
    correlation_id: str
    parent_event_id: str=""

Handler=Callable[[DomainEvent],None]
_HANDLERS: dict[str,list[Handler]]={}

def subscribe(event_type:str,handler:Handler)->None:
    _HANDLERS.setdefault(event_type,[]).append(handler)

def _insert_event(event:DomainEvent,target_module:str="")->None:
    with db() as con:
        con.execute(
            """INSERT INTO event_ledger(event_id,parent_event_id,correlation_id,event_type,source_module,target_module,entity_type,entity_id,actor,reason,payload_json,status)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,'recorded')""",
            (event.event_id,event.parent_event_id,event.correlation_id,event.event_type,event.source_module,target_module,event.entity_type,event.entity_id,event.actor,event.reason,json.dumps(event.payload,sort_keys=True,default=str)),
        )
    record_event(
        event_type=event.event_type,action="EVENT_RECORDED",module="event_bus",source_module=event.source_module,
        target_module=target_module or event.source_module,entity_type=event.entity_type,entity_id=event.entity_id,
        actor=event.actor,reason=event.reason,data=event.payload,event_id=event.event_id,parent_event_id=event.parent_event_id,
        correlation_id=event.correlation_id,
    )

def _handler_key(handler:Handler)->str:
    return f"{getattr(handler,'__module__','unknown')}.{getattr(handler,'__qualname__',getattr(handler,'__name__','handler'))}"


def _record_delivery(event:DomainEvent,handler:Handler,status:str,error_text:str="")->bool:
    """Only acknowledge a handler when its receipt is durably stored in SQL."""
    try:
        with db() as con:
            con.execute(
                """INSERT INTO event_delivery_receipts(event_id,event_type,handler_key,status,error_text)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(event_id,handler_key) DO UPDATE SET
                     status=excluded.status,error_text=excluded.error_text,updated_at=CURRENT_TIMESTAMP""",
                (event.event_id,event.event_type,_handler_key(handler),status,error_text[:4000]),
            )
    except Exception:
        return False
    return True


def _handlers_for(event_type:str)->list[Handler]:
    ordered=list(_HANDLERS.get(event_type,[]))+list(_HANDLERS.get("*",[]))
    result=[]
    seen=set()
    for handler in ordered:
        marker=id(handler)
        if marker not in seen:
            seen.add(marker)
            result.append(handler)
    return result


def _deliver(event:DomainEvent,*,skip_delivered:bool=False)->dict[str,int]:
    """Dispatch to current subscribers, retaining successful delivery receipts."""
    delivered=failed=skipped=0
    handlers=_handlers_for(event.event_type)
    for handler in handlers:
        if skip_delivered:
            with db() as con:
                receipt=con.execute(
                    "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
                    (event.event_id,_handler_key(handler)),
                ).fetchone()
            if receipt and receipt["status"]=="delivered":
                skipped+=1
                continue
        try:
            handler(event)
        except Exception as exc:
            failed+=1
            error_text=f"{type(exc).__name__}: {exc}"
            _record_delivery(event,handler,"failed",error_text)
            record_event(
                event_type="EVENT_HANDLER_FAILURE",action="HANDLER_FAILED",module="event_bus",
                source_module=event.source_module,target_module=_handler_key(handler),
                entity_type=event.entity_type,entity_id=event.entity_id,actor=event.actor,
                reason=error_text,data={"source_event_type":event.event_type,"handler":_handler_key(handler)},
                parent_event_id=event.event_id,correlation_id=event.correlation_id,
            )
        else:
            if _record_delivery(event,handler,"delivered"):
                delivered+=1
            else:
                # The handler may have committed side effects. Without a durable
                # receipt it MUST remain retryable; consumers must be idempotent.
                failed+=1
                try:
                    record_event(
                        event_type="EVENT_RECEIPT_FAILURE",action="RECEIPT_WRITE_FAILED",
                        module="event_bus",source_module=event.source_module,
                        target_module=_handler_key(handler),entity_type=event.entity_type,
                        entity_id=event.entity_id,actor=event.actor,
                        reason="Handler completed but its SQL delivery receipt was not saved",
                        data={"source_event_type":event.event_type,"handler":_handler_key(handler)},
                        parent_event_id=event.event_id,correlation_id=event.correlation_id,
                    )
                except Exception:
                    # If audit storage also fails, the ledger remains retryable.
                    pass

    # An event with no registered consumers stays pending for later recovery.
    if handlers:
        with db() as con:
            con.execute(
                "UPDATE event_ledger SET status=? WHERE event_id=?",
                ("partial_failure" if failed else "delivered",event.event_id),
            )
    return {"delivered":delivered,"failed":failed,"skipped":skipped}


def stage_event(con, event_type:str,*,source_module:str,entity_type:str,entity_id:str,
                actor:str="",reason:str="",payload:dict[str,Any]|None=None,
                parent_event_id:str="",correlation_id:str="")->DomainEvent:
    """Insert a domain event in the caller's SQL transaction, alongside its source data.

    The caller must commit first, then call deliver_staged(event_id). If execution
    stops between commit and dispatch, recover_undelivered can resume delivery.
    """
    event=DomainEvent(
        event_id=f"evt_{uuid.uuid4().hex}",event_type=event_type,source_module=source_module,
        entity_type=entity_type,entity_id=str(entity_id),actor=verified_actor(actor),
        reason=reason,payload=payload or {},correlation_id=correlation_id or f"corr_{uuid.uuid4().hex}",
        parent_event_id=parent_event_id,
    )
    con.execute(
        """INSERT INTO event_ledger(event_id,parent_event_id,correlation_id,event_type,
           source_module,target_module,entity_type,entity_id,actor,reason,payload_json,status)
           VALUES(?,?,?,?,?,'',?,?,?,?,?,'pending_delivery')""",
        (event.event_id,event.parent_event_id,event.correlation_id,event.event_type,
         event.source_module,event.entity_type,event.entity_id,event.actor,event.reason,
         json.dumps(event.payload,sort_keys=True,default=str)),
    )
    return event


def deliver_staged(event_id:str)->dict[str,int]:
    """Recover and deliver a committed event without duplicating successful handlers."""
    with db() as con:
        row=con.execute("SELECT * FROM event_ledger WHERE event_id=?",(event_id,)).fetchone()
    if row is None:
        raise ValueError("Event not found")
    event=DomainEvent(
        event_id=row["event_id"],event_type=row["event_type"],
        source_module=row["source_module"],entity_type=row["entity_type"],
        entity_id=row["entity_id"],actor=row["actor"] or "",
        reason=row["reason"] or "",payload=json.loads(row["payload_json"]),
        correlation_id=row["correlation_id"] or "",parent_event_id=row["parent_event_id"] or "",
    )
    result=_deliver(event,skip_delivered=True)
    return result


def recover_undelivered(limit:int=100, *, after_id:int=0)->dict[str,int]:
    """Replay one ordered page of committed events, skipping earlier ledger IDs.

    The cursor lets startup reach later events even when an earlier subscriber
    repeatedly fails and its event remains eligible for a future retry.
    """
    if not isinstance(limit,int) or not 1<=limit<=10000:
        raise ValueError("Recovery limit must be 1 through 10000")
    if not isinstance(after_id,int) or after_id<0:
        raise ValueError("Recovery cursor must be a nonnegative ledger ID")
    types=[key for key in _HANDLERS if key!="*" and _HANDLERS[key]]
    wildcard=bool(_HANDLERS.get("*"))
    if not types and not wildcard:
        return {"events":0,"delivered":0,"failed":0,"skipped":0,"last_id":after_id}
    with db() as con:
        if wildcard:
            rows=con.execute(
                """SELECT id,event_id FROM event_ledger
                   WHERE id>? AND status IN ('pending_delivery','partial_failure')
                   ORDER BY id LIMIT ?""",
                (after_id,limit),
            ).fetchall()
        else:
            marks=",".join("?" for _ in types)
            rows=con.execute(
                f"""SELECT id,event_id FROM event_ledger
                    WHERE id>? AND status IN ('pending_delivery','partial_failure')
                      AND event_type IN ({marks}) ORDER BY id LIMIT ?""",
                (after_id,*types,limit),
            ).fetchall()
    result={"events":len(rows),"delivered":0,"failed":0,"skipped":0,
            "last_id":int(rows[-1]["id"]) if rows else after_id}
    for row in rows:
        receipt=deliver_staged(row["event_id"])
        for field in ("delivered","failed","skipped"):
            result[field]+=receipt[field]
    return result



def delivery_diagnostics() -> dict[str, Any]:
    """Read-only SQL delivery evidence compared with this process's subscribers.

    A wildcard observer is not proof that a domain module consumed an event.
    A delivered ledger status without a receipt for a current handler is flagged,
    not silently replayed or mistaken for verified downstream state.
    """
    with db() as con:
        checked_at = con.execute("SELECT CURRENT_TIMESTAMP").fetchone()[0]
        rows = con.execute(
            """SELECT event_type,status,COUNT(*) AS n FROM event_ledger
               WHERE status IN ('recorded','pending_delivery','partial_failure','delivered')
               GROUP BY event_type,status ORDER BY event_type,status"""
        ).fetchall()
        by_type: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = by_type.setdefault(row["event_type"], {
                "event_type": row["event_type"], "total": 0,
                "recorded": 0, "pending_delivery": 0,
                "partial_failure": 0, "delivered": 0,
            })
            count = int(row["n"])
            item[row["status"]] += count
            item["total"] += count

        totals = {
            "events": 0, "recorded": 0, "pending_delivery": 0,
            "partial_failure": 0, "delivered": 0,
            "without_typed_subscriber_events": 0,
            "delivered_missing_current_receipts": 0,
            "failed_receipts": 0,
        }
        for event_type, item in by_type.items():
            typed = _HANDLERS.get(event_type, [])
            handlers = _handlers_for(event_type)
            item["typed_subscribers"] = len(typed)
            item["current_subscribers"] = len(handlers)
            item["without_typed_subscriber_events"] = item["total"] if not typed else 0
            missing = 0
            for handler in handlers:
                missing += int(con.execute(
                    """SELECT COUNT(*) FROM event_ledger AS e
                       WHERE e.event_type=? AND e.status='delivered'
                         AND NOT EXISTS (
                           SELECT 1 FROM event_delivery_receipts AS r
                           WHERE r.event_id=e.event_id AND r.handler_key=?
                             AND r.status='delivered'
                         )""",
                    (event_type, _handler_key(handler)),
                ).fetchone()[0])
            item["delivered_missing_current_receipts"] = missing
            item["failed_receipts"] = int(con.execute(
                """SELECT COUNT(*) FROM event_delivery_receipts AS r
                   JOIN event_ledger AS e ON e.event_id=r.event_id
                   WHERE e.event_type=? AND r.status='failed'""",
                (event_type,),
            ).fetchone()[0])
            for key in totals:
                if key in item:
                    totals[key] += item[key]
            totals["events"] += item["total"]

    attention = any(totals[key] for key in (
        "recorded", "pending_delivery", "partial_failure",
        "without_typed_subscriber_events", "delivered_missing_current_receipts",
        "failed_receipts",
    ))
    return {
        "schema": "axiom.sql-delivery-diagnostics.v1",
        "source": "local_axiom_sql",
        "checked_at_utc": checked_at,
        "status": "attention_required" if attention else (
            "no_ledger_events" if not totals["events"] else "no_detected_delivery_gaps"
        ),
        "totals": totals,
        "event_types": [by_type[key] for key in sorted(by_type)],
        "limitations": (
            "Only the current process subscriber registry and local SQL receipts are checked. "
            "Wildcard observers do not establish a domain consumer. Missing receipts can "
            "also mean a handler was registered after earlier delivery. This is not proof "
            "of live ERP, BEAN, Jetson, or remote module connectivity."
        ),
    }

def publish(event_type:str,*,source_module:str,entity_type:str,entity_id:str,actor:str="",
            reason:str="",payload:dict[str,Any]|None=None,parent_event_id:str="",
            correlation_id:str="")->DomainEvent:
    event=DomainEvent(
        event_id=f"evt_{uuid.uuid4().hex}",event_type=event_type,source_module=source_module,
        entity_type=entity_type,entity_id=str(entity_id),actor=verified_actor(actor),
        reason=reason,payload=payload or {},correlation_id=correlation_id or f"corr_{uuid.uuid4().hex}",
        parent_event_id=parent_event_id,
    )
    _insert_event(event)
    _deliver(event)
    return event

def create_action(event:DomainEvent,*,workflow_key:str,step_key:str,target_module:str,assigned_to:str="",due_date:str="",input_data:dict|None=None)->int:
    with db() as con:
        # Lock before the lookup so replayed events cannot enqueue the same action twice.
        con.execute("BEGIN IMMEDIATE")
        prior=con.execute(
            """SELECT id FROM workflow_actions
               WHERE event_id=? AND workflow_key=? AND step_key=? AND target_module=?
               ORDER BY id LIMIT 1""",
            (event.event_id,workflow_key,step_key,target_module),
        ).fetchone()
        if prior:
            return int(prior["id"])
        cur=con.execute(
            """INSERT INTO workflow_actions(event_id,workflow_key,step_key,source_module,target_module,entity_type,entity_id,assigned_to,status,due_date,input_json)
               VALUES(?,?,?,?,?,?,?,?, 'open', ?, ?)""",
            (event.event_id,workflow_key,step_key,event.source_module,target_module,event.entity_type,event.entity_id,assigned_to,due_date,json.dumps(input_data or event.payload,sort_keys=True,default=str)),
        )
        action_id=int(cur.lastrowid)
    record_event(event_type="WORKFLOW_ACTION",action="CREATED",module="workflow",source_module=event.source_module,target_module=target_module,
        entity_type=event.entity_type,entity_id=event.entity_id,actor=event.actor,reason=workflow_key,data={"action_id":action_id,"step_key":step_key},
        parent_event_id=event.event_id,correlation_id=event.correlation_id)
    return action_id

def metric(event:DomainEvent,name:str,value:float,unit:str,target:float|None=None,scope:str="",scope_id:str="")->None:
    """Persist one snapshot per source event, metric name and scope.

    A handler may run again if its delivery receipt failed after its KPI write.
    Keep the original snapshot rather than inflating metrics during SQL replay.
    """
    status=""
    if target is not None:
        status="good" if value>=target else "watch"
    with db() as con:
        # Serialize the lookup and insert across concurrent at-least-once retries.
        con.execute("BEGIN IMMEDIATE")
        existing=con.execute(
            """SELECT id FROM kpi_snapshots
               WHERE source_event_id=? AND metric_name=?
                 AND COALESCE(metric_scope,'')=? AND COALESCE(scope_id,'')=?
               LIMIT 1""",
            (event.event_id,name,scope or "",scope_id or ""),
        ).fetchone()
        if existing:
            return
        con.execute("""INSERT INTO kpi_snapshots(metric_date,metric_name,metric_scope,scope_id,value,unit,target,status,source_event_id)
                       VALUES(date('now'),?,?,?,?,?,?,?,?)""",(name,scope,scope_id,value,unit,target,status,event.event_id))

def _quality_created(event:DomainEvent)->None:
    create_action(event,workflow_key="quality-response",step_key="containment",target_module="quality")
    create_action(event,workflow_key="quality-to-job",step_key="review-job-risk",target_module="job_tracker")
    if event.payload.get("supplier_id") or event.payload.get("po_id"):
        create_action(event,workflow_key="supplier-quality",step_key="review-supplier-po",target_module="purchase_orders")
    if event.payload.get("machine_id"):
        create_action(event,workflow_key="quality-to-pm",step_key="review-machine-condition",target_module="pm")
    qty=float(event.payload.get("quantity_affected") or 0)
    shipped=float(event.payload.get("quantity_shipped") or 0)
    if shipped>0:
        metric(event,"PPM",(qty/shipped)*1_000_000,"ppm",scope="quality",scope_id=event.entity_id)

def _quality_closed(event:DomainEvent)->None:
    create_action(event,workflow_key="quality-effectiveness",step_key="verify-effectiveness",target_module="quality")
    create_action(event,workflow_key="learning-outcome",step_key="capture-outcome",target_module="bean")

def _fai_failed(event:DomainEvent)->None:
    create_action(event,workflow_key="fai-failure",step_key="open-or-link-ncr",target_module="quality")
    create_action(event,workflow_key="fai-failure",step_key="review-job-hold",target_module="job_tracker")

def _pm_failed(event:DomainEvent)->None:
    create_action(event,workflow_key="machine-failure",step_key="review-active-jobs",target_module="job_tracker")
    create_action(event,workflow_key="machine-failure",step_key="review-capacity",target_module="planning")
    create_action(event,workflow_key="machine-failure",step_key="quality-risk-review",target_module="quality")

def _po_late(event:DomainEvent)->None:
    create_action(event,workflow_key="late-po",step_key="expedite",target_module="purchase_orders")
    create_action(event,workflow_key="late-po",step_key="job-impact",target_module="job_tracker")
    create_action(event,workflow_key="late-po",step_key="inventory-impact",target_module="inventory")

def _inventory_short(event:DomainEvent)->None:
    create_action(event,workflow_key="inventory-shortage",step_key="buy-or-reallocate",target_module="purchase_orders")
    create_action(event,workflow_key="inventory-shortage",step_key="job-material-risk",target_module="job_tracker")
    create_action(event,workflow_key="inventory-shortage",step_key="quote-material-risk",target_module="quoting")

def _clocking_error(event:DomainEvent)->None:
    create_action(event,workflow_key="clocking-error",step_key="correct-time-record",target_module="clocking")
    create_action(event,workflow_key="clocking-error",step_key="review-job-cost-impact",target_module="job_tracker")
    create_action(event,workflow_key="clocking-error",step_key="pattern-observation",target_module="bean")

def _job_changed(event:DomainEvent)->None:
    create_action(event,workflow_key="job-change",step_key="check-po-material-quality",target_module="planning")

def _methods_plan_created(event:DomainEvent)->None:
    create_action(event,workflow_key="methods-release",step_key="review-routing-readiness",target_module="planning")
    create_action(event,workflow_key="methods-supply-readiness",step_key="verify-material-tool-dependencies",target_module="purchase_orders")

def _methods_dependency_blocked(event:DomainEvent)->None:
    create_action(event,workflow_key="methods-shortage",step_key="expedite-required-resource",target_module="purchase_orders")
    create_action(event,workflow_key="methods-shortage",step_key="review-job-operation-date",target_module="job_tracker")
    create_action(event,workflow_key="methods-shortage",step_key="recompute-routing-readiness",target_module="ez_methods")

def _morale_pulse_recorded(event:DomainEvent)->None:
    try:
        risk=float(event.payload.get("risk_score") or 0)
    except (TypeError,ValueError):
        risk=0.0
    if risk>=60:
        create_action(event,workflow_key="morale-response",step_key="leadership-review",target_module="leadership")
    if risk>=40:
        create_action(event,workflow_key="morale-learning",step_key="compare-quality-delivery-workforce-trends",target_module="bean")

def _erp_sync(event:DomainEvent)->None:
    create_action(event,workflow_key="erp-sync",step_key="reconcile",target_module="integrations")
    create_action(event,workflow_key="erp-sync",step_key="refresh-intelligence",target_module="bean")

def register_default_logic()->None:
    from .integrations.controlled_revision_review import review_controlled_fai_revision
    pairs={
        "fai.imported":review_controlled_fai_revision,
        "quality.created":_quality_created,
        "quality.closed":_quality_closed,
        "fai.failed":_fai_failed,
        "pm.failed":_pm_failed,
        "po.late":_po_late,
        "inventory.shortage":_inventory_short,
        "clocking.error":_clocking_error,
        "job.changed":_job_changed,
        "methods.plan.created":_methods_plan_created,
        "methods.dependency.blocked":_methods_dependency_blocked,
        "erp.sync.completed":_erp_sync,
        "morale.pulse.recorded":_morale_pulse_recorded,
    }
    for key,handler in pairs.items():
        if handler not in _HANDLERS.get(key,[]):
            subscribe(key,handler)

def logic_matrix()->list[dict[str,str]]:
    return [
        {"source":"Quality","event":"NCR/RMA/DMR/CAR/deviation","targets":"KPI, PPM, jobs, POs, supplier, machine/PM, BEAN"},
        {"source":"EZ FAIR","event":"FAI fail or characteristic fail","targets":"Quality, job hold review, drawing history, KPI"},
        {"source":"PM","event":"Failed PM / downtime","targets":"Jobs, planning, quality risk, quoting capacity"},
        {"source":"Purchase Orders","event":"Late/short PO","targets":"Jobs, inventory, planning, supplier performance"},
        {"source":"Inventory","event":"Shortage / allocation change","targets":"POs, jobs, quoting, planning"},
        {"source":"Clocking","event":"Clocking error","targets":"Job cost, correction workflow, BEAN pattern learning"},
        {"source":"Jobs","event":"Status/due/operation change","targets":"PO, inventory, quality, PM/capacity, planning"},
        {"source":"Vault","event":"Revision/release change","targets":"Jobs, EZ FAIR, EZ Methods, quality, quoting, ERP export"},
        {"source":"EZ Methods","event":"Plan/revision/resource readiness","targets":"Purchasing, jobs, planning, EZ FAIR/inspection, quality, audit"},
        {"source":"ERP integration","event":"Sync completed/conflict","targets":"Reconciliation, all trackers, BEAN"},
        {"source":"Leadership / Company Pulse","event":"Aggregate morale risk / recognition / training","targets":"Leadership review, training, reward ledger, BEAN trend analysis, audit"},
        {"source":"Automation","event":"Configured event rule matched","targets":"Assigned and due-dated workflow action with execution receipt"},
        {"source":"Collaboration","event":"Cross-module suggestion","targets":"Human-reviewed suggestion queue; accepted suggestions become workflow actions"},
        {"source":"Event Bus","event":"Subscriber delivery","targets":"Per-handler delivery receipt; subscriber failures are isolated and audited"},
        {"source":"BEAN","event":"Pattern/proposal","targets":"Human-reviewed rule proposal only"},
    ]
