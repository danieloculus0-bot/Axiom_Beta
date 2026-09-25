from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from typing import Any

from .models import AvailabilityState, OperationDependency, RoutingOperation


READY_STATES = {AvailabilityState.ON_HAND, AvailabilityState.RECEIVED}


def evaluate_dependency(dep: OperationDependency, as_of: date | None = None) -> dict[str, Any]:
    """Evaluate whether a dependency will be physically available when the operation needs it.

    Ordered is not treated as ready. The promised date must support the operation
    need-by date, and quantity must be sufficient.
    """
    as_of = as_of or date.today()
    total_available = max(dep.on_hand_qty, 0)
    if dep.availability == AvailabilityState.RECEIVED:
        total_available = max(total_available, dep.ordered_qty, dep.required_qty)

    if dep.availability in READY_STATES and total_available >= dep.required_qty:
        return {
            "status": "READY",
            "reason": f"{dep.description} available for operation.",
            "days_margin": (dep.need_by - as_of).days,
        }

    if dep.promised_date:
        margin = (dep.need_by - dep.promised_date).days
        if dep.ordered_qty >= dep.required_qty and margin >= 0:
            return {
                "status": "AT_RISK" if margin <= 0 else "PLANNED",
                "reason": (
                    f"{dep.description} promised {dep.promised_date.isoformat()} "
                    f"for need-by {dep.need_by.isoformat()}."
                ),
                "days_margin": margin,
            }
        if dep.ordered_qty >= dep.required_qty and margin < 0:
            return {
                "status": "BLOCKED",
                "reason": (
                    f"{dep.description} promised {dep.promised_date.isoformat()} "
                    f"AFTER need-by {dep.need_by.isoformat()}."
                ),
                "days_margin": margin,
            }

    if total_available < dep.required_qty and dep.availability == AvailabilityState.UNKNOWN:
        return {
            "status": "BLOCKED",
            "reason": f"{dep.description} has no confirmed availability or purchasing commitment.",
            "days_margin": None,
        }

    return {
        "status": "AT_RISK",
        "reason": f"{dep.description} is not yet physically ready for the operation.",
        "days_margin": None,
    }


def evaluate_operation_readiness(op: RoutingOperation, as_of: date | None = None) -> dict[str, Any]:
    checks = [evaluate_dependency(d, as_of) for d in op.dependencies]
    rank = {"READY": 0, "PLANNED": 1, "AT_RISK": 2, "BLOCKED": 3}
    status = max((c["status"] for c in checks), key=lambda s: rank[s], default="READY")
    blockers = [c["reason"] for c in checks if c["status"] == "BLOCKED"]
    risks = [c["reason"] for c in checks if c["status"] in {"AT_RISK", "PLANNED"}]
    return {
        "sequence": op.sequence,
        "operation": op.operation,
        "scheduled_date": op.scheduled_date.isoformat(),
        "status": status,
        "blockers": blockers,
        "risks": risks,
        "dependency_checks": checks,
    }


def build_purchase_event(
    dep: OperationDependency,
    job_number: str,
    part_number: str,
    operation_sequence: int,
) -> dict[str, Any]:
    """Create an EZ Expedite compatible purchasing/shortage occurrence payload."""
    readiness = evaluate_dependency(dep)
    priority = "Critical" if readiness["status"] == "BLOCKED" else "High"
    return {
        "occurrence_type": "PURCHASING / SHORTAGE",
        "title": f"{dep.description} required for Job {job_number}",
        "description": (
            f"Required for PN {part_number}, operation {operation_sequence}. "
            f"Need-by {dep.need_by.isoformat()}. {readiness['reason']}"
        ),
        "supplier": dep.supplier,
        "part_number": part_number,
        "purchase_order": dep.purchase_order,
        "owner_name": dep.owner,
        "owner_email": dep.owner_email,
        "priority": priority,
        "status": "AWAITING MATERIAL",
        "next_action": dep.next_action or "Confirm source, order status, and committed delivery date.",
        "due_date": dep.need_by.isoformat(),
        "external_id": dep.dependency_id,
        "metadata": {
            "dependency_kind": dep.kind.value,
            "supplier_part_number": dep.supplier_part_number,
            "internal_tool_id": dep.internal_tool_id,
            "required_qty": dep.required_qty,
            "ordered_qty": dep.ordered_qty,
            "promised_date": dep.promised_date.isoformat() if dep.promised_date else None,
            "operation_sequence": operation_sequence,
            "readiness_status": readiness["status"],
        },
    }


def append_audit_hash(previous_hash: str, event: dict[str, Any]) -> str:
    """Hash-chain helper for the shared SuperForge event ledger."""
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(f"{previous_hash}|{canonical}".encode("utf-8")).hexdigest()


def context_actions(context: dict[str, Any]) -> list[dict[str, str]]:
    """Right-click actions exposed to the SuperForge context router."""
    actions = [
        {"id": "open_methods", "label": "Open EZ Methods"},
        {"id": "view_audit", "label": "View Audit Trail"},
    ]
    if context.get("job_number"):
        actions.extend([
            {"id": "open_job", "label": "Open Job"},
            {"id": "check_readiness", "label": "Check Operation Readiness"},
        ])
    if context.get("dependency_id"):
        actions.extend([
            {"id": "open_purchase", "label": "Open Purchasing / Expedite"},
            {"id": "supplier_history", "label": "Supplier History"},
        ])
    if context.get("characteristic_id"):
        actions.extend([
            {"id": "open_fai", "label": "Open FAI / Inspection Characteristic"},
            {"id": "gage_history", "label": "Gage / Tool History"},
        ])
    return actions
