"""Review downstream EZ Methods sources when EZ FAIR imports a newer controlled drawing.

Consumes the existing fai.imported event. No drawing parsing, automatic revision
acceptance, released-route edits or BEAN service calls occur here.
"""
from __future__ import annotations

import json
from dataclasses import replace

from ..db import db
from ..event_bus import DomainEvent, create_action


def review_controlled_fai_revision(event: DomainEvent) -> None:
    """Request one human review for plans referencing an older controlled version."""
    if event.source_module != "ezfair" or event.entity_type != "fai":
        return
    if not isinstance(event.payload, dict) or event.payload.get("inspection_status") != "review_required":
        return
    try:
        fai_id = int(event.entity_id)
    except (TypeError, ValueError):
        return
    if fai_id <= 0:
        return

    with db() as con:
        current = con.execute(
            """SELECT f.id, f.status, f.drawing_revision, l.vault_record_id,
                      l.vault_version_id, l.release_package_number, l.pdf_sha256,
                      d.storage_reference, d.revision AS document_revision
               FROM fai_runs f
               JOIN fai_source_links l ON l.fai_run_id=f.id
               JOIN documents d ON d.id=f.drawing_document_id
               JOIN document_versions v ON v.document_id=d.id
                    AND v.storage_reference=d.storage_reference
                    AND v.revision=f.drawing_revision
                    AND v.sha256=l.pdf_sha256
               WHERE f.id=? AND f.status='review_required'
                 AND d.revision=f.drawing_revision AND d.sha256=l.pdf_sha256
                 AND d.storage_reference=('forgevault://' || l.vault_record_id || '/' || l.vault_version_id)""",
            (fai_id,),
        ).fetchall()
        if len(current) != 1:
            return
        new = dict(current[0])
        if (event.payload.get("vault_version") != new["vault_version_id"]
                or event.payload.get("drawing_sha256") != new["pdf_sha256"]):
            return
        sources = con.execute(
            """SELECT s.id AS source_id, s.plan_id, s.location, s.revision,
                      s.note, m.revision AS plan_revision, m.part_number,
                      m.job_id, m.part_id, m.job_number
               FROM ezm_sources s
               JOIN ezm_method_plans m ON m.id=s.plan_id
               WHERE s.source_type='CONTROLLED_DRAWING'
                 AND s.document_number=? AND s.location<>?
               ORDER BY s.id""",
            (new["vault_record_id"], new["storage_reference"]),
        ).fetchall()
        affected = []
        ewi_targets = {}
        ewi_ambiguous = set()
        for source in sources:
            try:
                note = json.loads(source["note"] or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(note, dict):
                continue
            old_version = note.get("file_version_id")
            old_hash = note.get("sha256")
            if (not isinstance(old_version, str) or not old_version
                    or not isinstance(old_hash, str) or len(old_hash) != 64
                    or source["revision"] != source["plan_revision"]
                    or source["location"] != "forgevault://" + new["vault_record_id"] + "/" + old_version):
                continue
            old_imports = con.execute(
                """SELECT f.id, f.job_id, f.part_id FROM fai_source_links l
                   JOIN fai_runs f ON f.id=l.fai_run_id
                   WHERE l.vault_record_id=? AND l.vault_version_id=?
                     AND l.pdf_sha256=? AND l.release_package_number=?
                     AND f.drawing_revision=?""",
                (new["vault_record_id"], old_version, old_hash,
                 note.get("release_package"), source["revision"]),
            ).fetchall()
            # Ambiguous prior FAI identities must not be treated as verified.
            if len(old_imports) != 1:
                continue
            affected.append({
                "plan_id": source["plan_id"],
                "method_source_id": source["source_id"],
                "previous_fai_run_id": int(old_imports[0]["id"]),
                "part_number": source["part_number"],
                "previous_revision": source["revision"],
                "previous_file_version_id": old_version,
                "previous_sha256": old_hash,
            })
            # EWI is a separate, job-scoped operator station. A Methods link
            # alone does not prove that a job's released packet uses this PDF.
            # Require canonical job/part identity, a unique released job PDF
            # with the exact prior SHA/revision, and an existing EWI route.
            if source["job_id"] is None or source["part_id"] is None:
                continue
            old_fai = old_imports[0]
            if (old_fai["job_id"] not in (None, source["job_id"])
                    or old_fai["part_id"] not in (None, source["part_id"])):
                continue
            candidates = con.execute(
                """SELECT j.id AS job_id, j.job_number, p.id AS part_id,
                          p.part_number
                   FROM jobs j
                   JOIN parts p ON p.id=j.part_id
                   JOIN documents d ON d.job_id=j.id
                   WHERE j.id=? AND j.part_id=? AND j.job_number=?
                     AND p.part_number=? AND p.revision=?
                     AND lower(d.status)='released' AND d.revision=?
                     AND d.sha256=? AND (d.part_id IS NULL OR d.part_id=p.id)
                     AND (SELECT COUNT(*) FROM documents d2
                          WHERE d2.job_id=j.id AND lower(d2.status)='released')=1
                     AND EXISTS(SELECT 1 FROM ewi_routes r WHERE r.job_id=j.id)""",
                (source["job_id"], source["part_id"], source["job_number"],
                 source["part_number"], source["revision"],
                 source["revision"], old_hash),
            ).fetchall()
            if len(candidates) != 1:
                continue
            job = dict(candidates[0])
            job_id = int(job["job_id"])
            candidate = {
                "job_id": job_id,
                "job_number": job["job_number"],
                "part_id": int(job["part_id"]),
                "part_number": job["part_number"],
                "method_source_id": int(source["source_id"]),
                "previous_fai_run_id": int(old_fai["id"]),
                "previous_revision": source["revision"],
                "previous_sha256": old_hash,
            }
            if job_id in ewi_targets and ewi_targets[job_id] != candidate:
                ewi_ambiguous.add(job_id)
            else:
                ewi_targets[job_id] = candidate
    if not affected:
        return
    evidence = {
        "contract_version": 1,
        "fai_run_id": fai_id,
        "vault_record_id": new["vault_record_id"],
        "new_revision": new["drawing_revision"],
        "new_file_version_id": new["vault_version_id"],
        "new_sha256": new["pdf_sha256"],
        "affected_methods": affected,
        "provenance": "EZ_FAIR_IMPORTED_CONTROLLED_DRAWING",
        "review_state": "REVIEW_REQUIRED",
    }
    # Both consumers use the same verified event and exact source identities.
    # A previous Planning delivery must not suppress a missing Quality review.
    for workflow_key, step_key, target_module, limitation in (
        ("controlled-drawing-revision-review", "reassess-linked-methods", "planning",
         "New controlled evidence may affect linked methods; human review required. No routing or EWI change was applied."),
        ("controlled-drawing-quality-review", "review-fai-characteristic-impact", "quality",
         "Compare old and new FAI characteristics manually; no inspection acceptance, plan edit, or release was applied."),
    ):
        with db() as con:
            already = con.execute(
                """SELECT 1 FROM workflow_actions
                   WHERE workflow_key=? AND entity_type='fai' AND entity_id=? LIMIT 1""",
                (workflow_key, str(fai_id)),
            ).fetchone()
        if not already:
            create_action(
                event, workflow_key=workflow_key, step_key=step_key,
                target_module=target_module,
                input_data={**evidence, "limitation": limitation},
            )

    # Create a distinct, idempotent action per verified EWI job. The action
    # keeps the original FAI event ID and correlation; only its review scope
    # is the canonical job ID. No job/drawing/route/clocking record is edited.
    for job_id, job in sorted(ewi_targets.items()):
        if job_id in ewi_ambiguous:
            continue
        step_key = f"review-job-packet-fai-{fai_id}"
        with db() as con:
            already = con.execute(
                """SELECT 1 FROM workflow_actions
                   WHERE workflow_key='controlled-drawing-ewi-review'
                     AND step_key=? AND entity_type='job' AND entity_id=?
                   LIMIT 1""",
                (step_key, str(job_id)),
            ).fetchone()
        if already:
            continue
        create_action(
            replace(event, entity_type="job", entity_id=str(job_id)),
            workflow_key="controlled-drawing-ewi-review",
            step_key=step_key,
            target_module="ewi",
            input_data={
                "contract_version": 1,
                "source_event_id": event.event_id,
                "fai_run_id": fai_id,
                "vault_record_id": new["vault_record_id"],
                "new_file_version_id": new["vault_version_id"],
                "new_sha256": new["pdf_sha256"],
                "new_revision": new["drawing_revision"],
                **job,
                "provenance": "EZ_FAIR_IMPORTED_CONTROLLED_DRAWING",
                "review_state": "REVIEW_REQUIRED",
                "limitation": "Advisory human EWI packet review only; no released drawing, routing, clocking or automatic hold was changed.",
            },
        )
