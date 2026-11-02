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
    """Find an undelivered EZ FAIR revision affecting this exact EWI job.

    Before a subscriber writes its review action, the committed FAI event is
    already durable. Join it to the job's verified Methods source through the
    canonical part/job and controlled vault identity, never a part-only guess.
    This is a conservative clock-in gate, not a release or reconciliation.
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
             AND e.status IN ('pending_delivery','partial_failure')
             AND f.status='review_required'
             AND m.job_id=? AND m.part_id=j.part_id
             AND m.part_number=p.part_number AND m.revision=s.revision
             AND s.revision<>f.drawing_revision
             AND EXISTS (SELECT 1 FROM ewi_routes r WHERE r.job_id=j.id)
           ORDER BY e.id DESC LIMIT 1""",
        (job_id,),
    ).fetchone()
