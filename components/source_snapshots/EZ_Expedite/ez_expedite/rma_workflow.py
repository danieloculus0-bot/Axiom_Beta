from __future__ import annotations

from dataclasses import dataclass

from .db import get_setting, log_activity, utcnow


@dataclass(frozen=True)
class RMAStage:
    key: str
    label: str
    role_key: str
    role_label: str
    action: str


STAGES = [
    RMAStage("INTAKE", "Intake", "csr", "Customer Service", "Complete intake fields."),
    RMAStage("AWAITING CUSTOMER RETURN", "Product Returned to WMF", "shipping", "Shipping", "Receive the return and confirm RMA hold-area placement."),
    RMAStage("RMA REVIEW", "RMA Review", "quality", "Quality", "Review product and issue a work order when required."),
    RMAStage("RETURN TO CUSTOMER", "Product Returned to Customer", "shipping", "Shipping", "Complete final inspection and shipment confirmation."),
    RMAStage("COMPLETE", "Complete", "shipping", "Shipping", "Verify completion and close."),
]

_STAGE_BY_KEY = {stage.key: stage for stage in STAGES}
_NEXT = {
    "INTAKE": "AWAITING CUSTOMER RETURN",
    "AWAITING CUSTOMER RETURN": "RMA REVIEW",
    "RMA REVIEW": "RETURN TO CUSTOMER",
    "RETURN TO CUSTOMER": "COMPLETE",
}
_STATUS_BY_STAGE = {
    "INTAKE": "NEW",
    "AWAITING CUSTOMER RETURN": "AWAITING MATERIAL",
    "RMA REVIEW": "INVESTIGATING",
    "RETURN TO CUSTOMER": "AWAITING INTERNAL ACTION",
    "COMPLETE": "READY TO CLOSE",
}


def stage_info(stage_key: str | None) -> RMAStage:
    return _STAGE_BY_KEY.get(stage_key or "", STAGES[0])


def stage_index(stage_key: str | None) -> int:
    for index, stage in enumerate(STAGES):
        if stage.key == stage_key:
            return index
    return 0


def _present(value) -> bool:
    return bool(str(value or "").strip())


def stage_blockers(row) -> list[str]:
    stage = row["rma_stage"] or "INTAKE"
    blockers: list[str] = []
    if stage == "INTAKE":
        required = [
            ("RMA Number", row["rma_number"]),
            ("Defect Type", row["defect_type"]),
            ("CSR Name", row["csr_name"]),
            ("PO #", row["purchase_order"]),
            ("Customer Name", row["customer"]),
            ("Contact Name", row["contact_name"]),
            ("Contact #", row["contact_phone"]),
        ]
        blockers.extend(f"{label} is required." for label, value in required if not _present(value))
        if not _present(row["description"]) and not _present(row["sales_comment"]):
            blockers.append("Notes are required.")
    elif stage == "AWAITING CUSTOMER RETURN":
        if str(row["received_from_customer"] or "").upper() != "YES":
            blockers.append("Received from Customer must be YES before advancing.")
        if not row["hold_area_confirmed"]:
            blockers.append("RMA hold-area placement must be confirmed.")
    elif stage == "RMA REVIEW":
        if not row["product_reviewed"]:
            blockers.append("Product review must be completed.")
        required = str(row["work_order_required"] or "").upper()
        if required not in {"YES", "NO"}:
            blockers.append("Work Order Required must be answered YES or NO.")
        if required == "YES":
            if str(row["work_order_issued"] or "").upper() != "YES":
                blockers.append("A required work order has not been issued.")
            if not _present(row["work_order"]):
                blockers.append("Work Order # is required.")
    elif stage == "RETURN TO CUSTOMER":
        result = str(row["final_quality_result"] or "").upper()
        if result not in {"PASS", "FAIL"}:
            blockers.append("Final Quality Inspection must be PASS or FAIL.")
        elif result == "FAIL":
            blockers.append("Final Quality Inspection failed.")
        if str(row["approved_to_ship"] or "").upper() != "YES":
            blockers.append("Approved to Ship must be YES.")
        if str(row["ready_to_ship"] or "").upper() != "YES":
            blockers.append("Ready to Ship must be YES.")
        if not row["shipped_to_customer"]:
            blockers.append("Shipment to customer must be confirmed.")
    return blockers


def primary_delegates(con, role_key: str) -> list[dict]:
    result = []
    for suffix in ("", "_2"):
        name = get_setting(con, f"rma_role_{role_key}_name{suffix}", "").strip()
        email = get_setting(con, f"rma_role_{role_key}_email{suffix}", "").strip().lower()
        if name or email:
            result.append({"name": name, "email": email})
    return result[:2]


def stage_delegates(con, stage_key: str) -> list[dict]:
    return primary_delegates(con, stage_info(stage_key).role_key)


def assign_stage_owner(con, occurrence_id: int, stage_key: str) -> list[dict]:
    delegates = stage_delegates(con, stage_key)
    first = delegates[0] if delegates else {"name": "", "email": ""}
    con.execute(
        "UPDATE occurrences SET owner_name=?,owner_email=?,updated_at=? WHERE id=?",
        (first["name"], first["email"], utcnow(), occurrence_id),
    )
    return delegates


def cc_recipients(con) -> list[str]:
    recipients = []
    seen = set()
    for key in ("quality", "operations", "customer_service", "design"):
        raw = get_setting(con, f"rma_cc_{key}", "")
        for part in str(raw or "").replace(";", ",").split(","):
            email = part.strip().lower()
            if email and email not in seen:
                seen.add(email)
                recipients.append(email)
    return recipients


def can_advance(con, stage_key: str, user_email: str) -> bool:
    email = str(user_email or "").strip().lower()
    if not email:
        return False
    return any(d["email"] == email for d in stage_delegates(con, stage_key) if d["email"])


def occurrence_url(con, occurrence_id: int) -> str:
    base = get_setting(con, "public_base_url", "").strip().rstrip("/")
    return f"{base}/occurrence/{occurrence_id}" if base else ""


def stage_message(row, stage_key: str, read_only: bool = False, url: str = "") -> str:
    stage = stage_info(stage_key)
    heading = "RMA UPDATE - READ ONLY" if read_only else "RMA - ACTION REQUIRED"
    lines = [
        heading,
        f"RMA: {row['rma_number'] or row['case_number']}",
        f"Stage: {stage.label}",
        f"Primary Department: {stage.role_label}",
        f"Customer: {row['customer'] or 'Not entered'}",
        f"Defect: {row['defect_type'] or row['discrepancy'] or 'Not entered'}",
        f"PO: {row['purchase_order'] or 'Not entered'}",
        f"Next Action: {stage.action}",
        f"Due: {row['due_date'] or 'Not assigned'}",
    ]
    if url:
        lines.append(f"Open RMA: {url}")
    return "\n".join(lines)


def notification_package(con, occurrence_id: int, stage_key: str) -> dict:
    row = con.execute(
        """SELECT o.*,r.* FROM occurrences o
           JOIN rma_details r ON r.occurrence_id=o.id
           WHERE o.id=?""",
        (occurrence_id,),
    ).fetchone()
    if not row:
        return {"delegates": [], "cc": [], "primary_message": "", "cc_message": ""}
    delegates = stage_delegates(con, stage_key)
    url = occurrence_url(con, occurrence_id)
    return {
        "delegates": delegates,
        "cc": cc_recipients(con),
        "primary_message": stage_message(row, stage_key, False, url),
        "cc_message": stage_message(row, stage_key, True, url),
    }


def deliver_notifications(package: dict, notify) -> int:
    errors = 0
    primary_emails = set()
    for delegate in package.get("delegates", []):
        email = str(delegate.get("email") or "").strip().lower()
        if not email:
            continue
        primary_emails.add(email)
        try:
            notify(email, package.get("primary_message", ""))
        except Exception:
            errors += 1
    for email in package.get("cc", []):
        email = str(email or "").strip().lower()
        if not email or email in primary_emails:
            continue
        try:
            notify(email, package.get("cc_message", ""))
        except Exception:
            errors += 1
    return errors


def advance_rma(con, occurrence_id: int, actor: str = "") -> dict:
    row = con.execute(
        """SELECT o.*,r.* FROM occurrences o
           JOIN rma_details r ON r.occurrence_id=o.id WHERE o.id=?""",
        (occurrence_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "blockers": ["RMA occurrence not found."]}

    current = row["rma_stage"] or "INTAKE"
    if current == "RETURN TO CUSTOMER" and str(row["final_quality_result"] or "").upper() == "FAIL":
        new_stage = "RMA REVIEW"
    else:
        blockers = stage_blockers(row)
        if blockers:
            return {"ok": False, "blockers": blockers}
        new_stage = _NEXT.get(current)
        if not new_stage:
            return {"ok": False, "blockers": ["RMA workflow is already complete."]}

    con.execute("UPDATE rma_details SET rma_stage=? WHERE occurrence_id=?", (new_stage, occurrence_id))
    con.execute(
        "UPDATE occurrences SET status=?,next_action=?,updated_at=? WHERE id=?",
        (_STATUS_BY_STAGE[new_stage], stage_info(new_stage).action, utcnow(), occurrence_id),
    )
    delegates = assign_stage_owner(con, occurrence_id, new_stage)
    log_activity(
        con,
        occurrence_id,
        "RMA STAGE",
        f"{stage_info(current).label} -> {stage_info(new_stage).label}.",
        actor,
    )
    package = notification_package(con, occurrence_id, new_stage)
    return {
        "ok": True,
        "new_stage": new_stage,
        **package,
    }


def stage_rail(stage_key: str | None) -> list[dict]:
    current_index = stage_index(stage_key)
    return [
        {
            "key": stage.key,
            "label": stage.label,
            "role_label": stage.role_label,
            "state": "done" if index < current_index else "current" if index == current_index else "future",
        }
        for index, stage in enumerate(STAGES)
    ]
