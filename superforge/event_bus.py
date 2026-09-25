from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .audit import record_event
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


def _record_delivery(event:DomainEvent,handler:Handler,status:str,error_text:str="")->None:
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
        pass


def publish(event_type:str,*,source_module:str,entity_type:str,entity_id:str,actor:str="",reason:str="",payload:dict[str,Any]|None=None,parent_event_id:str="",correlation_id:str="")->DomainEvent:
    event=DomainEvent(
        event_id=f"evt_{uuid.uuid4().hex}",event_type=event_type,source_module=source_module,entity_type=entity_type,
        entity_id=str(entity_id),actor=actor,reason=reason,payload=payload or {},correlation_id=correlation_id or f"corr_{uuid.uuid4().hex}",
        parent_event_id=parent_event_id,
    )
    _insert_event(event)
    ordered=list(_HANDLERS.get(event_type,[]))+list(_HANDLERS.get("*",[]))
    handlers=[]
    seen=set()
    for handler in ordered:
        marker=id(handler)
        if marker in seen:
            continue
        seen.add(marker)
        handlers.append(handler)

    failed=False
    for handler in handlers:
        try:
            handler(event)
        except Exception as exc:
            failed=True
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
            _record_delivery(event,handler,"delivered")

    if handlers:
        try:
            with db() as con:
                con.execute(
                    "UPDATE event_ledger SET status=? WHERE event_id=?",
                    ("partial_failure" if failed else "delivered",event.event_id),
                )
        except Exception:
            pass
    return event

def create_action(event:DomainEvent,*,workflow_key:str,step_key:str,target_module:str,assigned_to:str="",due_date:str="",input_data:dict|None=None)->int:
    with db() as con:
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
    status=""
    if target is not None:
        status="good" if value>=target else "watch"
    with db() as con:
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
    pairs={
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
