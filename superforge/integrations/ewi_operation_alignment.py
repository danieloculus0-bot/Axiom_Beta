"""Read-only alignment of SQL Methods evidence with EWI route and PDF evidence.

This compares independent local records for operator review only. A matching
operation label is not a verified JobBOSS operation ID or a route release.
"""
from __future__ import annotations

import sqlite3

from ..db import db
from ..modules.ewi import packet
from .operation_freshness import inspect_operation_event



def _controlled_revision_review_gate(job_id: int) -> dict | None:
    """Fail closed on any recorded EZ FAIR EWI revision review for this job.

    Completing a workflow action records a human task state, not evidence that
    the controlled drawing, Methods source and EWI routing were reconciled.
    Existing EWI routes have no revision-scoped provenance to verify that.
    Until a separately tested reconciliation contract exists, even a completed
    action (or an unverified output_json claim) cannot restore alignment.
    This read-only guard never changes routes, drawings or workflow actions.
    """
    with db() as con:
        con.execute("PRAGMA query_only=ON")
        action = con.execute(
            """SELECT a.id,a.status,a.event_id,e.event_type,e.source_module
               FROM workflow_actions a
               LEFT JOIN event_ledger e ON e.event_id=a.event_id
               WHERE a.workflow_key='controlled-drawing-ewi-review'
                 AND a.target_module='ewi'
                 AND a.entity_type='job' AND a.entity_id=?
               ORDER BY CASE WHEN a.status='open' THEN 0 ELSE 1 END,
                        a.id DESC LIMIT 1""",
            (str(job_id),),
        ).fetchone()
    if action is None:
        return None
    verified = (action["event_type"] == "fai.imported"
                and action["source_module"] == "ezfair")
    is_open = action["status"] == "open"
    return {
        "status": ("controlled_revision_review_pending" if is_open
                   else "controlled_revision_reconciliation_unverified"),
        "revision_review_action_id": int(action["id"]),
        "revision_review_action_status": action["status"],
        "revision_review_source_event_id": action["event_id"] if verified else None,
        "limitation": (
            "An open EZ FAIR controlled drawing revision review requires human "
            "reconciliation before EWI operation alignment can be offered. "
            if is_open else
            "Closing a drawing revision review does not verify the current "
            "drawing, Methods source or revision-scoped EWI route. Alignment "
            "remains unavailable until independent reconciliation evidence "
            "can be verified. "
        ) + "No released drawing, route or clocking state was changed.",
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
        pending = _controlled_revision_review_gate(job_id)
        if pending:
            result.update(pending)
            return result

        ewi = packet(job_id)
        if ewi is None:
            result["status"] = "job_not_found"
            return result
        if not ewi["ready"]:
            # Packet readiness now blocks stale routes for clock-in. Preserve
            # the established, specific read-only alignment status instead of
            # collapsing that evidence into a generic packet-not-ready result.
            issues = ewi.get("issues") or []
            if any("routing revision stale" in issue for issue in issues):
                result["status"] = "ewi_route_revision_stale"
            elif any("routing revision snapshot unverified" in issue for issue in issues):
                result["status"] = "ewi_route_revision_unverified"
            else:
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

        # A route pull records the *local* part revision seen at capture time.
        # The JobBOSS route API does not provide verified drawing/revision
        # provenance. Missing legacy snapshots or mismatches fail closed; even
        # a match is not evidence of remote ERP revision approval.
        captured_revision = str(route.get("local_part_revision_at_pull") or "").strip()
        current_revision = str(evidence.get("part_revision") or "").strip()
        if not captured_revision or not current_revision:
            result["status"] = "ewi_route_revision_unverified"
            return result
        if captured_revision.casefold() != current_revision.casefold():
            result["status"] = "ewi_route_revision_stale"
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
        pending = _controlled_revision_review_gate(job_id)
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
            "route_local_part_revision_at_pull": captured_revision,
            "remote_erp_revision_verified": False,
            "drawing_document_id": drawing["id"],
            "drawing_revision": drawing["revision"],
            "drawing_sha256": drawing["sha256"],
            "part_revision": evidence["part_revision"],
            "planning_action_id": evidence["planning_action_id"],
            "methods_suggestion_id": evidence["methods_suggestion_id"],
            "limitation": (
                "Exact operation-label and local revision-snapshot agreement; "
                "the remote ERP drawing revision and external operation ID remain unverified. "
                "Human verification of the routed step and drawing is required."
            ),
        })
        return result
    except (OSError, sqlite3.Error):
        result["status"] = "evidence_unavailable"
        return result
