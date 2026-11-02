"""Review downstream EZ Methods sources when EZ FAIR imports a newer controlled drawing.

Consumes the existing fai.imported event. No drawing parsing, automatic revision
acceptance, released-route edits or BEAN service calls occur here.
"""
from __future__ import annotations

import json

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
        if con.execute(
            """SELECT 1 FROM workflow_actions
               WHERE workflow_key='controlled-drawing-revision-review'
                 AND entity_type='fai' AND entity_id=? LIMIT 1""",
            (str(fai_id),),
        ).fetchone():
            return

        sources = con.execute(
            """SELECT s.id AS source_id, s.plan_id, s.location, s.revision,
                      s.note, m.revision AS plan_revision, m.part_number
               FROM ezm_sources s
               JOIN ezm_method_plans m ON m.id=s.plan_id
               WHERE s.source_type='CONTROLLED_DRAWING'
                 AND s.document_number=? AND s.location<>?
               ORDER BY s.id""",
            (new["vault_record_id"], new["storage_reference"]),
        ).fetchall()
        affected = []
        for source in sources:
            try:
                note = json.loads(source["note"] or "{}")
            except (TypeError, ValueError):
                continue
            old_version = note.get("file_version_id")
            old_hash = note.get("sha256")
            if (not isinstance(old_version, str) or not old_version
                    or not isinstance(old_hash, str) or len(old_hash) != 64
                    or source["revision"] != source["plan_revision"]
                    or source["location"] != "forgevault://" + new["vault_record_id"] + "/" + old_version):
                continue
            old_import = con.execute(
                """SELECT 1 FROM fai_source_links l
                   JOIN fai_runs f ON f.id=l.fai_run_id
                   WHERE l.vault_record_id=? AND l.vault_version_id=?
                     AND l.pdf_sha256=? AND l.release_package_number=?
                     AND f.drawing_revision=? LIMIT 1""",
                (new["vault_record_id"], old_version, old_hash,
                 note.get("release_package"), source["revision"]),
            ).fetchone()
            if old_import is None:
                continue
            affected.append({
                "plan_id": source["plan_id"],
                "method_source_id": source["source_id"],
                "part_number": source["part_number"],
                "previous_revision": source["revision"],
                "previous_file_version_id": old_version,
                "previous_sha256": old_hash,
            })
    if not affected:
        return
    create_action(
        event, workflow_key="controlled-drawing-revision-review",
        step_key="reassess-linked-methods", target_module="planning",
        input_data={
            "contract_version": 1,
            "fai_run_id": fai_id,
            "vault_record_id": new["vault_record_id"],
            "new_revision": new["drawing_revision"],
            "new_file_version_id": new["vault_version_id"],
            "new_sha256": new["pdf_sha256"],
            "affected_methods": affected,
            "provenance": "EZ_FAIR_IMPORTED_CONTROLLED_DRAWING",
            "review_state": "REVIEW_REQUIRED",
            "limitation": "New controlled evidence may affect linked methods; human review required. No routing or EWI change was applied.",
        },
    )
