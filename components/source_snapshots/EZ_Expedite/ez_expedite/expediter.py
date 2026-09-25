from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Callable

from .db import utcnow
from .rma_workflow import stage_delegates

Notifier = Callable[[str, str], None]


def overdue_days(due_date: str | None, today: date) -> int:
    if not due_date:
        return 0
    try:
        due = datetime.strptime(due_date, "%Y-%m-%d").date()
    except ValueError:
        return 0
    return max((today - due).days, 0)


def _latest_progress(con, occurrence_id: int) -> str:
    row = con.execute(
        """SELECT detail FROM activities
           WHERE occurrence_id=? AND activity_type IN ('PROGRESS','NOTE')
           ORDER BY id DESC LIMIT 1""",
        (occurrence_id,),
    ).fetchone()
    return str(row["detail"] or "").strip() if row else ""


def _digest_message(items: list[dict], today: date) -> str:
    lines = [f"EZ Expedite - Past Due - {today.isoformat()}", ""]
    for item in sorted(items, key=lambda x: (-x["days_overdue"], x["case_number"])):
        note = item["last_note"] or "No progress note"
        if len(note) > 180:
            note = note[:177] + "..."
        lines.extend(
            [
                f"{item['case_number']} | {item['days_overdue']} day{'s' if item['days_overdue'] != 1 else ''} past due",
                f"{item['type_name']} | {item['title']}",
                f"Next: {item['next_action'] or 'Not entered'}",
                f"Last note: {note}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def run_expeditor(con, notify_teams: Notifier | None = None, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    rows = con.execute(
        """SELECT o.*,t.name type_name,r.rma_stage
           FROM occurrences o
           JOIN occurrence_types t ON t.id=o.occurrence_type_id
           LEFT JOIN rma_details r ON r.occurrence_id=o.id
           WHERE o.status!='CLOSED'"""
    ).fetchall()
    result = {
        "checked": 0,
        "digests_sent": 0,
        "overdue_items": 0,
        "unassigned": 0,
        "due_without_action": 0,
        "errors": 0,
    }
    overdue_by_owner: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        result["checked"] += 1
        if not (row["owner_name"] or row["owner_email"]):
            result["unassigned"] += 1
            if row["status"] == "NEW":
                con.execute(
                    "UPDATE occurrences SET status='ASSIGNMENT REQUIRED',updated_at=? WHERE id=?",
                    (utcnow(), row["id"]),
                )

        if row["due_date"] and not str(row["next_action"] or "").strip():
            result["due_without_action"] += 1

        days = overdue_days(row["due_date"], today)
        if days <= 0:
            continue

        recipients = []
        if row["type_name"] == "RMA":
            recipients = [
                d["email"] for d in stage_delegates(con, row["rma_stage"] or "INTAKE") if d.get("email")
            ]
        if not recipients and row["owner_email"]:
            recipients = [str(row["owner_email"]).strip().lower()]
        recipients = list(dict.fromkeys(x.strip().lower() for x in recipients if x and x.strip()))
        if not recipients:
            continue

        result["overdue_items"] += 1
        payload = {
            "id": row["id"],
            "case_number": row["case_number"],
            "type_name": row["type_name"],
            "title": row["title"],
            "next_action": row["next_action"],
            "days_overdue": days,
            "last_note": _latest_progress(con, row["id"]),
        }
        for recipient in recipients:
            overdue_by_owner[recipient].append(payload)

    if notify_teams is None:
        return result

    digest_date = today.isoformat()
    for recipient, items in overdue_by_owner.items():
        already_sent = con.execute(
            """SELECT 1 FROM digest_notifications
               WHERE recipient=? AND digest_type='PAST_DUE' AND digest_date=?""",
            (recipient, digest_date),
        ).fetchone()
        if already_sent:
            continue

        try:
            notify_teams(recipient, _digest_message(items, today))
            con.execute(
                """INSERT INTO digest_notifications(
                   recipient,digest_type,digest_date,sent_at,item_count)
                   VALUES(?,?,?,?,?)""",
                (recipient, "PAST_DUE", digest_date, utcnow(), len(items)),
            )
            result["digests_sent"] += 1
        except Exception:
            result["errors"] += 1

    return result
