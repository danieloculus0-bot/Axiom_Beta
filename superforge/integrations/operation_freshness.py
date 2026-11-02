"""Read-only freshness gate for a SQL job event's EZ Methods operation candidate.

EWI, Quality and CAM may inspect this local SQL evidence, but a positive
result is never an authorization to run, inspect, release or edit a route.
No second event bus, database or drawing parser is involved.
"""
from __future__ import annotations

import json

from ..db import db
from ..event_bus import _handler_key, _job_changed
from ..modules.collaboration import _suggest
from .service import _job_event_identity

IDENTITY_FIELDS = (
    "job_id", "job_number", "part_id", "part_number", "part_revision",
    "part_link_status", "operation_label", "operation_id", "operation_status",
    "method_match_status", "method_plan_id", "method_plan_status",
    "operation_sequence", "human_review_required",
)
REQUIRED_RECEIPTS = (_handler_key(_job_changed), _handler_key(_suggest))


def inspect_operation_event(job_id: int, event_id: str) -> dict:
    """Check a committed event against current canonical SQL in one read snapshot.

    A returned operation is only an exact *review candidate*. Consumers must
    recheck before acting; there is no live subscription or approval here.
    """
    result = {
        "schema": "axiom.operation-evidence.v1",
        "source": "local_axiom_sql",
        "job_id": job_id,
        "event_id": event_id,
        "status": "event_not_found",
        "human_review_required": True,
        "operation_id": None,
        "method_plan_id": None,
    }
    if not event_id or len(event_id) > 160:
        result["status"] = "invalid_event_id"
        return result

    with db() as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")  # one consistent read snapshot, never a mutation
        row = con.execute(
            """SELECT id,event_id,event_type,source_module,entity_type,entity_id,
                      status,payload_json,correlation_id,created_at
               FROM event_ledger WHERE event_id=?""", (event_id,),
        ).fetchone()
        if row is None:
            return result
        if (row["event_type"], row["source_module"], row["entity_type"],
                row["entity_id"]) != ("job.changed", "integrations", "job", str(job_id)):
            result["status"] = "event_scope_mismatch"
            return result
        result.update({
            "event_status": row["status"],
            "correlation_id": row["correlation_id"],
            "event_created_at": row["created_at"],
        })
        if row["status"] != "delivered":
            result["status"] = "event_not_delivered"
            return result
        try:
            payload = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            result["status"] = "invalid_event_identity"
            return result
        identity = payload.get("identity") if isinstance(payload, dict) else None
        if (not isinstance(identity, dict)
                or identity.get("schema") != "axiom.job-identity.v1"
                or identity.get("source") != "local_axiom_sql"
                or any(key not in identity for key in IDENTITY_FIELDS)
                or identity["job_id"] != job_id):
            result["status"] = "invalid_event_identity"
            return result

        latest = con.execute(
            """SELECT event_id FROM event_ledger
               WHERE event_type='job.changed' AND source_module='integrations'
                 AND entity_type='job' AND entity_id=?
               ORDER BY id DESC LIMIT 1""", (str(job_id),),
        ).fetchone()
        if latest is None or latest["event_id"] != event_id:
            result["status"] = "superseded_event"
            return result

        # A delivered ledger flag alone is not evidence that the actual
        # Planning and Methods consumers persisted their receipts and work.
        receipts = {
            r["handler_key"] for r in con.execute(
                """SELECT handler_key FROM event_delivery_receipts
                   WHERE event_id=? AND status='delivered'""", (event_id,),
            )
        }
        action = con.execute(
            """SELECT id FROM workflow_actions WHERE event_id=?
                 AND workflow_key='job-change' AND target_module='planning'
               LIMIT 1""", (event_id,),
        ).fetchone()
        suggestion = con.execute(
            """SELECT id FROM module_suggestions WHERE source_event_id=?
                 AND suggestion_key='job-method-readiness'
                 AND target_module='ez_methods' LIMIT 1""", (event_id,),
        ).fetchone()
        if not set(REQUIRED_RECEIPTS).issubset(receipts) or not action or not suggestion:
            result["status"] = "consumer_evidence_incomplete"
            return result

        job = con.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            result["status"] = "job_not_found"
            return result
        current = _job_event_identity(con, job_id)
        changed = [key for key in IDENTITY_FIELDS if identity[key] != current.get(key)]
        if changed:
            result.update(status="stale_identity", changed_fields=changed)
            return result
        if (identity["method_match_status"] != "unique_exact_candidate_review_required"
                or identity["operation_id"] is None
                or identity["method_plan_id"] is None):
            result["status"] = "unresolved_operation"
            return result

        result.update({
            "status": "current_review_candidate",
            "operation_id": identity["operation_id"],
            "method_plan_id": identity["method_plan_id"],
            "part_id": identity["part_id"],
            "part_revision": identity["part_revision"],
            "operation_sequence": identity["operation_sequence"],
            "planning_action_id": action["id"],
            "methods_suggestion_id": suggestion["id"],
        })
        return result
