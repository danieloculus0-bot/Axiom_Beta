"""One read-only SQL predicate for EWI controlled revision review obligations.

No secondary registry, inferred release or write-side side effects.
"""
from __future__ import annotations

import sqlite3


def blocking_ewi_revision_review(con: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    """Any recorded job review blocks clock-in until separately verified reconciliation.

    A completed human task is not proof that the controlled drawing and route agree.
    Caller owns the transaction, allowing the clock-in gate to lock before reading.
    """
    return con.execute(
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

def pending_ewi_revision_event(con: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    """Find an undelivered FAI revision or a delivered one missing its EWI review.

    The latter requires the same uniquely verified old FAI, job-linked released
    drawing, controlled Methods source and route that the real EWI subscriber
    requires. A delivered ledger status alone does not prove a consumer wrote
    its expected action. This is read-only and never infers a job from a part.
    """
    return con.execute(
        """SELECT e.event_id, e.status AS delivery_status,
                  f.id AS fai_run_id, f.drawing_revision AS new_revision
           FROM event_ledger e
           JOIN fai_runs f ON e.entity_id=CAST(f.id AS TEXT)
           JOIN fai_source_links l ON l.fai_run_id=f.id
           JOIN ezm_sources s ON s.source_type='CONTROLLED_DRAWING'
                AND s.document_number=l.vault_record_id
                AND substr(s.location,1,length('forgevault://' || l.vault_record_id || '/'))
                    = ('forgevault://' || l.vault_record_id || '/')
                AND s.location<>('forgevault://' || l.vault_record_id || '/' || l.vault_version_id)
           JOIN ezm_method_plans m ON m.id=s.plan_id
           JOIN jobs j ON j.id=m.job_id
           JOIN parts p ON p.id=j.part_id
           WHERE e.event_type='fai.imported' AND e.source_module='ezfair'
             AND e.entity_type='fai'
             AND e.status IN ('pending_delivery','partial_failure','delivered')
             AND f.status='review_required'
             AND m.job_id=? AND m.part_id=j.part_id
             AND m.part_number=p.part_number AND m.revision=s.revision
             AND s.revision<>f.drawing_revision
             AND EXISTS (SELECT 1 FROM ewi_routes r WHERE r.job_id=j.id)
             AND (
               e.status IN ('pending_delivery','partial_failure')
               OR (
                 e.status='delivered'
                 AND json_valid(e.payload_json)=1 AND json_valid(s.note)=1
                 AND json_extract(e.payload_json,'$.inspection_status')='review_required'
                 AND json_extract(e.payload_json,'$.vault_version')=l.vault_version_id
                 AND json_extract(e.payload_json,'$.drawing_sha256')=l.pdf_sha256
                 AND j.job_number=m.job_number AND p.revision=s.revision
                 AND NOT EXISTS (
                   SELECT 1 FROM workflow_actions a
                   WHERE a.event_id=e.event_id
                     AND a.workflow_key='controlled-drawing-ewi-review'
                     AND a.step_key=('review-job-packet-fai-' || CAST(f.id AS TEXT))
                     AND a.target_module='ewi'
                     AND a.entity_type='job' AND a.entity_id=CAST(j.id AS TEXT)
                 )
                 AND EXISTS (
                   SELECT 1 FROM documents d
                   JOIN document_versions v ON v.document_id=d.id
                     AND v.storage_reference=d.storage_reference
                     AND v.revision=f.drawing_revision AND v.sha256=l.pdf_sha256
                   WHERE d.id=f.drawing_document_id
                     AND d.revision=f.drawing_revision AND d.sha256=l.pdf_sha256
                     AND d.storage_reference=('forgevault://' || l.vault_record_id || '/' || l.vault_version_id)
                 )
                 AND EXISTS (
                   SELECT 1 FROM documents d
                   WHERE d.job_id=j.id AND (d.part_id IS NULL OR d.part_id=p.id)
                     AND lower(d.status)='released' AND d.revision=s.revision
                     AND d.sha256=(CASE WHEN json_valid(s.note)=1
                         THEN json_extract(s.note,'$.sha256') END)
                     AND (SELECT COUNT(*) FROM documents d2
                          WHERE d2.job_id=j.id AND lower(d2.status)='released')=1
                 )
                 AND (
                   SELECT CASE WHEN COUNT(*)=1
                       AND MIN(CASE WHEN (old_f.job_id IS NULL OR old_f.job_id=j.id)
                                     AND (old_f.part_id IS NULL OR old_f.part_id=p.id)
                                THEN 1 ELSE 0 END)=1
                       THEN 1 ELSE 0 END
                   FROM fai_source_links old_l
                   JOIN fai_runs old_f ON old_f.id=old_l.fai_run_id
                   WHERE old_l.vault_record_id=l.vault_record_id
                     AND old_l.vault_version_id=(CASE WHEN json_valid(s.note)=1
                         THEN json_extract(s.note,'$.file_version_id') END)
                     AND old_l.pdf_sha256=(CASE WHEN json_valid(s.note)=1
                         THEN json_extract(s.note,'$.sha256') END)
                     AND old_l.release_package_number=(CASE WHEN json_valid(s.note)=1
                         THEN json_extract(s.note,'$.release_package') END)
                     AND old_f.drawing_revision=s.revision
                 )=1
               )
             )
           ORDER BY e.id DESC LIMIT 1""",
        (job_id,),
    ).fetchone()
