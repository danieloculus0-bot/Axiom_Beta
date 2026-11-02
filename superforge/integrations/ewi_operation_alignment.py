"""Read-only alignment of SQL Methods evidence with EWI route and PDF evidence.

This compares independent local records for operator review only. A matching
operation label is not a verified JobBOSS operation ID or a route release.
"""
from __future__ import annotations

import sqlite3

from ..db import db
from ..modules.ewi import packet
from .operation_freshness import inspect_operation_event



def _pending_controlled_revision_review(job_id: int) -> dict | None:
    """Consume PR #106's existing job-scoped EZ FAIR review action, if present.

    An open review is evidence that the previously linked controlled drawing
    may be superseded. Fail closed even if its source event is missing, rather
    than treating an orphaned review action as permission to use the old route.
    No new table, subscription or workflow action is created here.
    """
    with db() as con:
        con.execute("PRAGMA query_only=ON")
        action = con.execute(
            """SELECT a.id,a.event_id,e.event_type,e.source_module
               FROM workflow_actions a
               LEFT JOIN event_ledger e ON e.event_id=a.event_id
               WHERE a.workflow_key='controlled-drawing-ewi-review'
                 AND a.target_module='ewi'
                 AND a.entity_type='job' AND a.entity_id=?
                 AND a.status='open'
               ORDER BY a.id LIMIT 1""",
            (str(job_id),),
        ).fetchone()
    if action is None:
        return None
    verified = (action["event_type"] == "fai.imported"
                and action["source_module"] == "ezfair")
    return {
        "status": "controlled_revision_review_pending",
        "revision_review_action_id": int(action["id"]),
        "revision_review_source_event_id": action["event_id"] if verified else None,
        "limitation": (
            "An open EZ FAIR controlled drawing revision review requires human "
            "reconciliation before EWI operation alignment can be offered. "
            "No released drawing, route or clocking state was changed."
        ),
    }


def inspect_ewi_operation_alignment(job_id: int, event_id: str) -> dict:
    """Fail closed unless current SQL evidence, one route and a real PDF agree."""
    result = {
        "schema": "axiom.ewi-operation-alignment.v1",
        "source": "local_axiom_sql",
        "job_id": job_id,
        "event_id": event_id,
        "status": "evidence_unavailable",
        "human_review_required": True,
        "method_operation_id": None,
        "ewi_step": None,
        "drawing_document_id": None,
        "remote_erp_verified": False,
        "released_route_approved": False,
    }
    try:
        evidence = inspect_operation_event(job_id, event_id)
        if evidence["status"] != "current_review_candidate":
            result["status"] = evidence["status"]
            return result

        # PR #106's verified FAI revision review is a separate producer. A
        # still-open review invalidates an otherwise current SQL/route match.
        pending = _pending_controlled_revision_review(job_id)
        if pending:
            result.update(pending)
            return result

        ewi = packet(job_id)
        if ewi is None:
            result["status"] = "job_not_found"
            return result
        if not ewi["ready"]:
            result["status"] = "ewi_packet_not_ready"
            return result

        drawing = ewi["drawing"]
        if (not drawing or not ewi["pdf_path"]
                or str(drawing.get("document_type") or "").strip().casefold()
                not in {"drawing", "customer drawing"}):
            result["status"] = "controlled_drawing_unverified"
            return result

        with db() as con:
            con.execute("PRAGMA query_only=ON")
            row = con.execute(
                """SELECT j.part_id,o.operation
                   FROM jobs j
                   JOIN ezm_method_plans p ON p.job_id=j.id
                   JOIN ezm_operations o ON o.plan_id=p.id
                   WHERE j.id=? AND p.id=? AND o.id=?""",
                (job_id, evidence["method_plan_id"], evidence["operation_id"]),
            ).fetchone()
        if row is None:
            result["status"] = "method_operation_changed"
            return result
        if drawing.get("part_id") != row["part_id"]:
            result["status"] = "drawing_part_scope_mismatch"
            return result

        matches = [route for route in ewi["routes"]
                   if route["operation"] == row["operation"]]
        if not matches:
            result["status"] = "ewi_operation_label_mismatch"
            return result
        if len(matches) != 1:
            result["status"] = "ambiguous_ewi_operation"
            return result
        route = matches[0]
        if not route["part_number"] or route["part_number"] != ewi["job"]["part_number"]:
            result["status"] = "ewi_route_part_unverified"
            return result

        # A PDF hash check performs file I/O outside the SQL read snapshot.
        # Recheck both sources to avoid returning an already-stale candidate.
        again = inspect_operation_event(job_id, event_id)
        if again["status"] != "current_review_candidate":
            result["status"] = again["status"]
            return result
        second = packet(job_id)
        if (second is None or not second["ready"]
                or second["job"] != ewi["job"]
                or second["routes"] != ewi["routes"]
                or second["drawing"] != drawing):
            result["status"] = "ewi_evidence_changed_during_read"
            return result

        # Recheck after PDF I/O, so a revision review created during the
        # alignment read cannot be overlooked by the final response.
        pending = _pending_controlled_revision_review(job_id)
        if pending:
            result.update(pending)
            return result

        result.update({
            "status": "cross_source_candidate_review_required",
            "method_operation_id": evidence["operation_id"],
            "method_plan_id": evidence["method_plan_id"],
            "ewi_step": route["step"],
            "ewi_route_external_id": route["external_id"] or None,
            "ewi_route_pulled_at": route["pulled_at"],
            "drawing_document_id": drawing["id"],
            "drawing_revision": drawing["revision"],
            "drawing_sha256": drawing["sha256"],
            "part_revision": evidence["part_revision"],
            "planning_action_id": evidence["planning_action_id"],
            "methods_suggestion_id": evidence["methods_suggestion_id"],
            "limitation": (
                "Exact operation-label agreement between independent local records; "
                "no shared external operation ID or live ERP synchronization is proven. "
                "Human verification of the routed step and drawing is required."
            ),
        })
        return result
    except (OSError, sqlite3.Error):
        result["status"] = "evidence_unavailable"
        return result
