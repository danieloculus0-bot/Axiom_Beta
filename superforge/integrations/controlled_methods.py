"""Attach a controlled, already-verified ForgeVault drawing to an EZ Methods plan.

Requires an actual imported FAI receipt from the same file version; metadata
supplied by a caller alone never establishes a released PDM source.
"""
from __future__ import annotations

import json
from ..audit import record_event
from ..db import db
from ..event_bus import publish


def link_controlled_drawing_to_method(plan_id: int, source: dict, *, actor: str) -> dict:
    required = ("record_id", "file_version_id", "release_package_number",
                "sha256", "customer_part_number", "customer_revision")
    if not isinstance(source, dict) or any(not source.get(k) for k in required):
        raise ValueError("controlled drawing identity incomplete")
    if not actor or not str(actor).strip():
        raise ValueError("actor label is required")
    uri = "forgevault://" + source["record_id"] + "/" + source["file_version_id"]
    note = json.dumps({
        "file_version_id": source["file_version_id"],
        "release_package": source["release_package_number"],
        "sha256": source["sha256"],
    }, sort_keys=True)
    with db() as con:
        plan = con.execute("SELECT * FROM ezm_method_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise ValueError("method plan not found")
        if plan["part_number"] != source["customer_part_number"] or plan["revision"] != source["customer_revision"]:
            raise ValueError("method plan part/revision differs from released drawing")
        actual = con.execute(
            "SELECT f.id FROM fai_source_links l JOIN fai_runs f ON f.id=l.fai_run_id "
            "WHERE l.vault_record_id=? AND l.vault_version_id=? AND "
            "l.release_package_number=? AND l.pdf_sha256=? LIMIT 1",
            (source["record_id"], source["file_version_id"],
             source["release_package_number"], source["sha256"]),
        ).fetchone()
        if actual is None:
            raise ValueError("no verified FAI import for this controlled drawing version")
        documents = con.execute(
            "SELECT d.id FROM documents d JOIN document_versions v ON v.document_id=d.id "
            "WHERE d.storage_reference=? AND d.sha256=? AND d.revision=? "
            "AND v.storage_reference=? AND v.sha256=? LIMIT 1",
            (uri, source["sha256"], source["customer_revision"], uri, source["sha256"]),
        ).fetchone()
        if documents is None:
            raise ValueError("controlled drawing version is absent or mismatched in Axiom")
        existing = con.execute(
            "SELECT * FROM ezm_sources WHERE plan_id=? AND source_type='CONTROLLED_DRAWING' "
            "AND document_number=? LIMIT 1",
            (plan_id, source["record_id"]),
        ).fetchone()
        if existing:
            if (existing["revision"], existing["location"], existing["note"]) != (
                source["customer_revision"], uri, note
            ):
                raise ValueError("method plan already references conflicting drawing version")
            return {"source_id": existing["id"], "plan_id": plan_id,
                    "file_version_id": source["file_version_id"], "idempotent": True}
        cur = con.execute(
            "INSERT INTO ezm_sources(plan_id,source_type,document_number,revision,location,note) "
            "VALUES(?,'CONTROLLED_DRAWING',?,?,?,?)",
            (plan_id, source["record_id"], source["customer_revision"], uri, note),
        )
        source_id = int(cur.lastrowid)
    record_event(
        event_type="METHOD_SOURCE", action="LINK_RELEASED_DRAWING", module="methods",
        entity_type="method_source", entity_id=source_id, actor=actor,
        data={"plan_id": plan_id, "vault_version": source["file_version_id"],
              "sha256": source["sha256"], "release_package": source["release_package_number"]},
    )
    publish(
        "methods.source.linked", source_module="methods",
        entity_type="method_source", entity_id=str(source_id), actor=actor,
        payload={"plan_id": plan_id, "file_version_id": source["file_version_id"],
                 "drawing_sha256": source["sha256"]},
    )
    return {"source_id": source_id, "plan_id": plan_id,
            "file_version_id": source["file_version_id"], "idempotent": False}
