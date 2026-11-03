"""Bounded, restart-resumable replay over Axiom's existing SQL event ledger.

The checkpoint is a single key in the canonical system_meta table, not a
second queue, event bus, or source of truth. A crash before checkpoint commit
may replay a page; the existing per-handler SQL receipts and idempotent
consumers remain responsible for safe retries.
"""
from __future__ import annotations

from .db import db
from .event_bus import recover_undelivered

CURSOR_KEY = "event_bus.startup_recovery_after_id"


def recover_startup_backlog(*, page_size: int = 1000, max_events: int = 10000) -> dict[str, int | bool]:
    """Scan a bounded number of ledger events, resuming on the next startup.

    Resume after the last completed page. Once the tail is reached on a later
    startup, wrap once to retry older partial failures. Never wrap on the
    initial zero-cursor scan: that would immediately retry a failing handler
    within the same startup and obscure its first failure.
    """
    if type(page_size) is not int or not 1 <= page_size <= 10000:
        raise ValueError("Recovery page size must be 1 through 10000")
    if type(max_events) is not int or not 1 <= max_events <= 10000:
        raise ValueError("Recovery event budget must be 1 through 10000")

    with db() as con:
        row = con.execute(
            "SELECT value FROM system_meta WHERE key=?", (CURSOR_KEY,),
        ).fetchone()
    try:
        start_cursor = max(0, int(row["value"])) if row else 0
    except (ValueError, TypeError):
        start_cursor = 0

    cursor = start_cursor
    wrapped = False
    totals: dict[str, int | bool] = {
        "events": 0, "delivered": 0, "failed": 0, "skipped": 0,
        "last_id": cursor, "wrapped": False,
    }
    while totals["events"] < max_events:
        limit = min(page_size, max_events - totals["events"])
        batch = recover_undelivered(limit=limit, after_id=cursor)
        if batch["events"]:
            # Only advance after every event in this page has been attempted.
            # An interrupted page is replayed after restart using SQL receipts.
            cursor = batch["last_id"]
            with db() as con:
                con.execute(
                    """INSERT INTO system_meta(key,value) VALUES(?,?)
                       ON CONFLICT(key) DO UPDATE SET
                         value=excluded.value,updated_at=CURRENT_TIMESTAMP""",
                    (CURSOR_KEY, str(cursor)),
                )
            for key in ("events", "delivered", "failed", "skipped"):
                totals[key] += batch[key]
            totals["last_id"] = cursor

        if batch["events"] < limit:
            if start_cursor > 0 and not wrapped:
                # Revisit older partial failures only after reaching the tail
                # of a subsequent startup, never in an unbounded retry loop.
                cursor = 0
                wrapped = True
                totals["wrapped"] = True
                continue
            break
    return totals
