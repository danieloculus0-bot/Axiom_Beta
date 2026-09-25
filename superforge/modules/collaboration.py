from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

from ..audit import record_event
from ..db import db
from ..event_bus import DomainEvent, subscribe

collaboration_blueprint=Blueprint("collaboration_module",__name__)
_REGISTERED=False


def _priority(value:str)->str:
    value=(value or "normal").strip().lower()
    return value if value in {"low","normal","high","critical"} else "normal"


def create_suggestion(event:DomainEvent,*,target_module:str,suggestion_key:str,title:str,rationale:str,recommended_action:str,priority:str="normal",evidence:dict[str,Any]|None=None)->int|None:
    if target_module==event.source_module:
        return None
    with db() as con:
        cur=con.execute(
            """INSERT OR IGNORE INTO module_suggestions(
                 source_event_id,correlation_id,source_module,target_module,suggestion_key,title,
                 rationale,recommended_action,priority,entity_type,entity_id,evidence_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.event_id,event.correlation_id,event.source_module,target_module,suggestion_key,title,
                rationale,recommended_action,_priority(priority),event.entity_type,event.entity_id,
                json.dumps(evidence or event.payload,sort_keys=True,default=str),
            ),
        )
        if not cur.rowcount:
            row=con.execute(
                "SELECT id FROM module_suggestions WHERE source_event_id=? AND target_module=? AND suggestion_key=?",
                (event.event_id,target_module,suggestion_key),
            ).fetchone()
            return int(row["id"]) if row else None
        suggestion_id=int(cur.lastrowid)
    record_event(
        event_type="MODULE_SUGGESTION",action="CREATED",module="collaboration",
        source_module=event.source_module,target_module=target_module,
        entity_type=event.entity_type,entity_id=event.entity_id,actor=event.actor,
        reason=title,data={"suggestion_id":suggestion_id,"suggestion_key":suggestion_key,"recommended_action":recommended_action,"priority":_priority(priority)},
        parent_event_id=event.event_id,correlation_id=event.correlation_id,
    )
    return suggestion_id


def _suggest(event:DomainEvent)->None:
    if event.source_module=="collaboration" or event.event_type.startswith("collaboration."):
        return
    p=event.payload or {}
    t=event.event_type

    if t=="quality.created":
        if p.get("part_id") or p.get("job_id"):
            create_suggestion(event,target_module="ezfair",suggestion_key="quality-inspection-scope",title="Review inspection scope after the quality event",rationale="A new quality record is linked to production context. Inspection coverage may need to change.",recommended_action="Check FAI/inspection characteristics, sampling, tooling, and hold points against the failure mode.",priority="high" if str(p.get("severity","")).lower() in {"high","critical"} else "normal")
            create_suggestion(event,target_module="ez_methods",suggestion_key="quality-method-review",title="Check whether the routing or method needs a control change",rationale="Quality evidence can reveal a missing method step, tooling control, or in-process verification.",recommended_action="Compare the quality evidence with the current routing and add a reviewed method change only if justified.")
        create_suggestion(event,target_module="bean",suggestion_key="quality-pattern-review",title="Compare this failure with prior outcomes",rationale="Repeated quality events are useful supervised-learning evidence.",recommended_action="Look for recurrence by part, operation, machine, supplier, or failure mode and propose a reviewed improvement if a pattern exists.",priority="low")

    elif t=="quality.closed":
        create_suggestion(event,target_module="bean",suggestion_key="quality-effectiveness-learning",title="Capture the closed quality outcome",rationale="The final disposition and effectiveness result are valuable outcome labels.",recommended_action="Compare the corrective action with later quality, delivery, and rework results before proposing broader changes.",priority="low")

    elif t=="fai.failed":
        create_suggestion(event,target_module="ez_methods",suggestion_key="fai-method-check",title="Review the manufacturing method behind the failed characteristic",rationale="A failed FAI characteristic can originate in sequence, setup, tooling, fixture, gage, or process capability.",recommended_action="Trace the characteristic to its producing operation and verify method, tooling, fixture, and inspection controls.",priority="high")
        create_suggestion(event,target_module="vault",suggestion_key="fai-revision-check",title="Confirm the controlled drawing revision",rationale="FAI conclusions are only valid against the correct released drawing/specification revision.",recommended_action="Verify drawing, specification, and customer revision identity before disposition.",priority="high")

    elif t=="fai.completed":
        create_suggestion(event,target_module="quality",suggestion_key="fai-result-trend",title="Feed the completed FAI result into quality history",rationale="Completed first-article evidence should be available to later NCR, PPAP, and control-plan reviews.",recommended_action="Link the FAI result to part/revision quality history and retain the evidence reference.",priority="low")

    elif t=="methods.plan.created":
        create_suggestion(event,target_module="ezfair",suggestion_key="methods-inspection-plan",title="Generate or refresh inspection planning from the method",rationale="Routing operations, GD&T, hold points, and controlled operations define where inspection evidence belongs.",recommended_action="Reconcile drawing characteristics with operation-level inspection requirements and identify required gages.")

    elif t=="methods.dependency.blocked":
        create_suggestion(event,target_module="suppliers",suggestion_key="blocked-resource-alternative",title="Check approved alternatives for the blocked resource",rationale="A material, tap, gage, fixture, or outside-process dependency is blocking the method plan.",recommended_action="Review approved supplier/source alternatives and lead times without substituting an unapproved requirement.",priority="high")
        create_suggestion(event,target_module="quoting",suggestion_key="blocked-resource-quote-learning",title="Capture this dependency as future quoting evidence",rationale="A real production shortage is useful evidence for future lead-time and cost estimates.",recommended_action="Feed the actual resource lead-time/cost outcome into future quote assumptions after the job outcome is known.",priority="low")

    elif t=="po.created" and p.get("job_id"):
        create_suggestion(event,target_module="ez_methods",suggestion_key="po-method-dependency-link",title="Link this PO to the method dependency it satisfies",rationale="A job-linked purchase order should close the loop on material/tool/outside-process readiness.",recommended_action="Match the PO to required operation dependencies and compare promised date with need-by date.")
        create_suggestion(event,target_module="planning",suggestion_key="po-job-date-check",title="Check the PO promise against the job schedule",rationale="Purchased-resource timing can change routing readiness and delivery risk.",recommended_action="Compare expected receipt with the first consuming operation and job due date.")

    elif t=="inventory.item.created":
        try:
            available=float(p.get("available") or 0); reorder=float(p.get("reorder_point") or 0)
        except (TypeError,ValueError):
            available=reorder=0
        if available<=reorder:
            create_suggestion(event,target_module="purchase_orders",suggestion_key="inventory-replenishment-review",title="Review replenishment for the new low-stock item",rationale="Available quantity is at or below the configured reorder point.",recommended_action="Confirm demand, approved source, lead time, and need-by date before placing or expediting an order.",priority="high")

    elif t=="pm.machine.created":
        create_suggestion(event,target_module="planning",suggestion_key="machine-capacity-profile",title="Add the new machine to capacity planning",rationale="A machine record is more useful when planning knows its work center, capacity, constraints, and alternates.",recommended_action="Define capacity assumptions, compatible operations, criticality, and backup routing options.",priority="low")
        create_suggestion(event,target_module="quality",suggestion_key="machine-quality-controls",title="Review machine-specific quality controls",rationale="New equipment may require calibration, validation, capability, inspection, or special-process controls.",recommended_action="Confirm required qualification, calibration, capability, and control-plan evidence before production use.")

    elif t=="vault.document.created":
        doc_type=str(p.get("document_type") or "").lower()
        if doc_type in {"drawing","spec","specification","customer drawing"}:
            create_suggestion(event,target_module="ezfair",suggestion_key="document-fai-review",title="Check whether the controlled document changes inspection requirements",rationale="Drawings and specifications drive FAI and inspection characteristics.",recommended_action="Extract or review characteristics against the controlled revision before inspection release.",priority="high" if p.get("revision") else "normal")
            create_suggestion(event,target_module="ez_methods",suggestion_key="document-method-review",title="Check whether the controlled document changes the routing",rationale="Released drawing/specification requirements can change operations, tooling, material, and hold points.",recommended_action="Compare the document revision against the active method plan before production release.")

    elif t=="supplier.created":
        create_suggestion(event,target_module="quality",suggestion_key="supplier-qualification",title="Complete supplier quality qualification",rationale="A new supplier should not silently become an approved production source.",recommended_action="Review scope, certifications, process capability, risk, and approval status before controlled purchasing.")
        create_suggestion(event,target_module="purchase_orders",suggestion_key="supplier-commercial-setup",title="Complete purchasing setup for the supplier",rationale="The supplier record needs commercial and lead-time context before it can support planning.",recommended_action="Confirm contacts, terms, standard lead times, approved commodities/processes, and escalation path.",priority="low")

    elif t=="erp.connection.created":
        create_suggestion(event,target_module="bean",suggestion_key="erp-data-quality-baseline",title="Establish a data-quality baseline for the new integration",rationale="New ERP feeds can introduce mapping, duplicate, stale, or missing-field patterns.",recommended_action="Observe sync errors, conflict rate, missing required fields, and reconciliation outcomes before proposing mapping improvements.",priority="low")

    elif t=="job.changed":
        create_suggestion(event,target_module="ez_methods",suggestion_key="job-method-readiness",title="Verify method readiness for the changed job",rationale="Job quantity, due date, priority, or operation changes can invalidate resource timing.",recommended_action="Recheck routing, material/tool dependencies, inspection requirements, and operation dates.")

    elif t=="training.completed":
        create_suggestion(event,target_module="bean",suggestion_key="training-outcome-followup",title="Compare training with later operating outcomes",rationale="Verified training completion is useful only if later quality, throughput, and compliance outcomes are observed.",recommended_action="Retain the completion as an outcome feature and look for measurable changes without scoring an individual.",priority="low")


def register_collaboration_logic()->None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe("*",_suggest)
    _REGISTERED=True


def open_suggestions(*,target_module:str="",limit:int=200)->list[dict[str,Any]]:
    sql="SELECT * FROM module_suggestions WHERE status='open'"
    args:list[Any]=[]
    if target_module:
        sql+=" AND target_module=?"; args.append(target_module)
    sql+=" ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,id DESC LIMIT ?"
    args.append(max(1,min(int(limit),1000)))
    with db() as con:
        return [dict(r) for r in con.execute(sql,tuple(args))]


def accept_suggestion(suggestion_id:int,*,actor:str="local",assigned_to:str="")->int:
    with db() as con:
        row=con.execute("SELECT * FROM module_suggestions WHERE id=?",(int(suggestion_id),)).fetchone()
        if not row: raise ValueError("suggestion not found")
        if row["status"]=="accepted" and row["accepted_action_id"]: return int(row["accepted_action_id"])
        if row["status"]!="open": raise ValueError(f"suggestion cannot be accepted from status {row['status']}")
        source=con.execute("SELECT * FROM event_ledger WHERE event_id=?",(row["source_event_id"],)).fetchone()
        payload={"suggestion_id":int(row["id"]),"title":row["title"],"rationale":row["rationale"],"recommended_action":row["recommended_action"],"evidence":json.loads(row["evidence_json"] or "{}")}
        cur=con.execute(
            """INSERT INTO workflow_actions(event_id,workflow_key,step_key,source_module,target_module,entity_type,entity_id,assigned_to,status,due_date,input_json)
               VALUES(?,?,?,?,?,?,?,?, 'open','',?)""",
            (row["source_event_id"],f"collaboration:{row['suggestion_key']}","review-suggestion",row["source_module"],row["target_module"],row["entity_type"],row["entity_id"],assigned_to,json.dumps(payload,sort_keys=True,default=str)),
        )
        action_id=int(cur.lastrowid)
        con.execute("UPDATE module_suggestions SET status='accepted',accepted_action_id=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(action_id,actor,int(suggestion_id)))
        correlation_id=(source["correlation_id"] if source else row["correlation_id"]) or ""
    record_event(event_type="MODULE_SUGGESTION",action="ACCEPTED",module="collaboration",source_module=row["source_module"],target_module=row["target_module"],entity_type=row["entity_type"] or "",entity_id=row["entity_id"] or "",actor=actor,reason=row["title"],data={"suggestion_id":int(suggestion_id),"workflow_action_id":action_id},parent_event_id=row["source_event_id"],correlation_id=correlation_id)
    return action_id


def dismiss_suggestion(suggestion_id:int,*,actor:str="local",reason:str="")->None:
    with db() as con:
        row=con.execute("SELECT * FROM module_suggestions WHERE id=?",(int(suggestion_id),)).fetchone()
        if not row: raise ValueError("suggestion not found")
        if row["status"]=="dismissed": return
        if row["status"]!="open": raise ValueError(f"suggestion cannot be dismissed from status {row['status']}")
        con.execute("UPDATE module_suggestions SET status='dismissed',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(actor,int(suggestion_id)))
    record_event(event_type="MODULE_SUGGESTION",action="DISMISSED",module="collaboration",source_module=row["source_module"],target_module=row["target_module"],entity_type=row["entity_type"] or "",entity_id=row["entity_id"] or "",actor=actor,reason=reason or row["title"],data={"suggestion_id":int(suggestion_id)},parent_event_id=row["source_event_id"],correlation_id=row["correlation_id"] or "")


def suggestion_snapshot()->dict[str,Any]:
    with db() as con:
        rows=con.execute("SELECT status,priority,COUNT(*) n FROM module_suggestions GROUP BY status,priority").fetchall()
        failed=con.execute("SELECT COUNT(*) n FROM event_delivery_receipts WHERE status='failed'").fetchone()["n"]
    return {"suggestions":{f"{r['status']}:{r['priority']}":int(r["n"]) for r in rows},"failed_deliveries":int(failed)}


@collaboration_blueprint.get("/api/collaboration/suggestions")
def suggestions_api():
    return jsonify({"suggestions":open_suggestions(target_module=request.args.get("target_module",""),limit=request.args.get("limit",200)),"snapshot":suggestion_snapshot()})


@collaboration_blueprint.post("/api/collaboration/suggestions/<int:suggestion_id>/accept")
def suggestion_accept_api(suggestion_id:int):
    data=request.get_json(silent=True) or request.form
    action_id=accept_suggestion(suggestion_id,actor=data.get("actor") or "local",assigned_to=data.get("assigned_to") or "")
    return jsonify({"ok":True,"suggestion_id":suggestion_id,"workflow_action_id":action_id})


@collaboration_blueprint.post("/api/collaboration/suggestions/<int:suggestion_id>/dismiss")
def suggestion_dismiss_api(suggestion_id:int):
    data=request.get_json(silent=True) or request.form
    dismiss_suggestion(suggestion_id,actor=data.get("actor") or "local",reason=data.get("reason") or "")
    return jsonify({"ok":True,"suggestion_id":suggestion_id})
