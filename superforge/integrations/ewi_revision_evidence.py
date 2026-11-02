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
