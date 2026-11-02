"""Resolve a changed SQL job's EZ Methods operation without guessing identities.

Read-only and called inside the importer's existing source/event SQL transaction.
The returned ID is a review candidate, never a released route or instruction.
"""
from __future__ import annotations


def resolve_method_operation(con, identity: dict) -> dict:
    """Require one plan for the canonical job and one exact operation label.

    Do not resolve from job/part numbers alone, a mismatched revision, or a
    duplicate operation label. Every result still requires human review.
    """
    result = {
        "method_match_status": "incomplete_canonical_scope",
        "method_plan_id": None,
        "method_plan_status": None,
        "operation_sequence": None,
    }
    if (
        identity.get("job_id") is None
        or identity.get("part_id") is None
        or not identity.get("job_number")
        or not identity.get("part_number")
        or not identity.get("part_revision")
        or not identity.get("operation_label")
    ):
        return result

    plans = con.execute(
        """SELECT id,part_id,job_number,part_number,revision,status
           FROM ezm_method_plans WHERE job_id=? ORDER BY id LIMIT 2""",
        (identity["job_id"],),
    ).fetchall()
    if not plans:
        result["method_match_status"] = "no_method_plan"
        return result
    if len(plans) != 1:
        result["method_match_status"] = "ambiguous_method_plans"
        return result

    plan = plans[0]
    if (
        plan["part_id"] != identity["part_id"]
        or plan["job_number"] != identity["job_number"]
        or plan["part_number"] != identity["part_number"]
    ):
        result["method_match_status"] = "method_identity_mismatch"
        return result
    if plan["revision"] != identity["part_revision"]:
        result["method_match_status"] = "stale_part_revision"
        return result

    operations = con.execute(
        """SELECT id,sequence FROM ezm_operations
           WHERE plan_id=? AND operation=? ORDER BY id LIMIT 2""",
        (plan["id"], identity["operation_label"]),
    ).fetchall()
    if not operations:
        result["method_match_status"] = "operation_label_not_found"
        return result
    if len(operations) != 1:
        result["method_match_status"] = "ambiguous_operation_label"
        return result

    result.update({
        "method_match_status": "unique_exact_candidate_review_required",
        "method_plan_id": int(plan["id"]),
        "method_plan_status": plan["status"],
        "operation_sequence": int(operations[0]["sequence"]),
        "operation_id": int(operations[0]["id"]),
        "operation_status": "matched_methods_candidate_review_required",
    })
    return result
