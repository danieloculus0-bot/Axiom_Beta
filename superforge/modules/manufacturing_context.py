"""Canonical, read-only manufacturing context from Axiom's existing SQL database.

This endpoint is a local integration contract. It does not produce CNC programs,
approve routing, activate a machine, or connect a public browser to local SQL.
The absence of a verified job/part/revision match never falls back to a demo part.
"""
from __future__ import annotations

from flask import Blueprint, jsonify
from ..db import db

manufacturing_context_blueprint = Blueprint("manufacturing_context", __name__)


def job_manufacturing_context(job_id: int) -> dict | None:
    with db() as con:
        row = con.execute(
            """SELECT j.id,j.job_number,j.part_id,j.status,j.quantity,
                      j.current_operation,j.updated_at,
                      p.part_number,p.revision AS part_revision
               FROM jobs j LEFT JOIN parts p ON p.id=j.part_id
               WHERE j.id=?""", (job_id,),
        ).fetchone()
        if row is None:
            return None
        job = dict(row)
        plans = [dict(x) for x in con.execute(
            """SELECT id,job_id,part_id,job_number,part_number,revision,
                      status,updated_at
               FROM ezm_method_plans WHERE job_id=? ORDER BY id""", (job_id,),
        )]
        ewi = [dict(x) for x in con.execute(
            """SELECT step,operation,work_center,part_number,external_id,pulled_at
               FROM ewi_routes WHERE job_id=? ORDER BY CAST(step AS INTEGER),step""",
            (job_id,),
        )]
        released = [dict(x) for x in con.execute(
            """SELECT id,document_number,revision,sha256
               FROM documents
               WHERE job_id=? AND lower(status)='released'
                 AND lower(coalesce(document_type,'')) IN ('drawing','customer drawing')
               ORDER BY id""", (job_id,),
        )]

        # A missing or ambiguous link is a first-class state. Never silently choose
        # the latest of multiple candidate method plans or infer a machining step.
        status = "ready_for_review"
        plan = None
        operations = []
        if not job["part_id"] or not job["part_number"] or not job["part_revision"]:
            status = "missing_canonical_part"
        elif not plans:
            status = "no_method_plan"
        elif len(plans) != 1:
            status = "ambiguous_method_plans"
        else:
            candidate = plans[0]
            if candidate["job_number"] != job["job_number"]:
                status = "job_identity_mismatch"
            elif candidate["part_id"] is not None and candidate["part_id"] != job["part_id"]:
                status = "part_identity_mismatch"
            elif candidate["part_number"] != job["part_number"]:
                status = "part_number_mismatch"
            elif candidate["revision"] != job["part_revision"]:
                status = "revision_mismatch"
            else:
                plan = candidate
                operations = [dict(x) for x in con.execute(
                    """SELECT id,sequence,work_center,operation,scheduled_date,
                              inspection_requirement,hold_point,controlled_operation
                       FROM ezm_operations WHERE plan_id=?
                       ORDER BY sequence""", (plan["id"],),
                )]

        drawing = None
        drawing_status = "no_released_job_drawing"
        if len(released) > 1:
            drawing_status = "ambiguous_released_drawings"
        elif len(released) == 1:
            candidate = released[0]
            if not job["part_revision"] or candidate["revision"] != job["part_revision"]:
                drawing_status = "drawing_revision_mismatch"
            elif not candidate["sha256"]:
                drawing_status = "drawing_without_checksum"
            else:
                drawing = candidate
                drawing_status = "released_record_present_unverified_file"

    # This response deliberately separates independent planning and EWI records.
    # A reviewed plan does not establish machine qualification or a CNC-ready path.
    return {
        "schema": "axiom.manufacturing-context.v1",
        "source": "local_axiom_sql",
        "job": job,
        "method_status": status,
        "method_plan": plan,
        "method_plan_candidates": len(plans),
        "method_operations": operations,
        "ewi_status": "separate_source_unverified" if ewi else "no_ewi_routing",
        "ewi_operations": ewi,
        "drawing_status": drawing_status,
        "drawing": drawing,
        "cam": {"machine_program_ready": False, "job_geometry_loaded": False,
                "operation_must_be_selected": True},
    }


@manufacturing_context_blueprint.get("/api/v1/jobs/<int:job_id>/manufacturing-context")
def api_job_manufacturing_context(job_id: int):
    payload = job_manufacturing_context(job_id)
    if payload is None:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    return jsonify({"ok": True, **payload})
