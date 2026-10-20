"""Import exact ForgeVault/EZ-FAIR source-version evidence into Axiom FAI.

This is a local, explicit import API. No automatic approval, measurements, or
authenticated actor claim. Shared-deployment authentication remains separate.
"""
from __future__ import annotations

import hashlib
import json
import math

from ..audit import record_event
from ..db import db
from ..event_bus import publish

SCHEMA = "ezfair.inspection_handoff.v1"
SOURCE_SCHEMA = "forgevault.released_drawing.v1"

def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def import_controlled_fai(payload: dict, pdf_bytes: bytes, *, fai_number: str, actor: str) -> dict:
    """Import review-pending characteristic proposals, tied to one released PDF."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("unsupported EZ-FAIR inspection handoff")
    if payload.get("status") != "review_required":
        raise ValueError("only review-pending FAI proposals may be imported")
    source = payload.get("source_drawing")
    if not isinstance(source, dict):
        raise ValueError("missing controlled drawing")
    keys = ("record_id", "file_version_id", "release_package_number",
            "customer_part_number", "customer_revision", "internal_revision",
            "filename", "sha256", "byte_size", "version_number")
    if any(not source.get(k) for k in keys):
        raise ValueError("source revision identity incomplete")
    if not source["filename"].lower().endswith(".pdf"):
        raise ValueError("only controlled PDF drawings accepted")
    if type(pdf_bytes) is not bytes or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("drawing bytes must contain a PDF")
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    if digest != source["sha256"] or len(pdf_bytes) != source["byte_size"]:
        raise ValueError("drawing checksum or length mismatch")
    if type(source["version_number"]) is not int or source["version_number"] < 1:
        raise ValueError("invalid source version")
    chars = payload.get("characteristics")
    if (not isinstance(chars, list) or not chars
            or len(chars) != payload.get("characteristic_count")):
        raise ValueError("incomplete characteristic list")
    numbers = set()
    for char in chars:
        if not isinstance(char, dict):
            raise ValueError("invalid characteristic")
        number = char.get("char_number")
        if type(number) is not int or number < 1 or number in numbers:
            raise ValueError("duplicate/invalid characteristic number")
        numbers.add(number)
        for key in ("nominal", "lsl", "usl"):
            value = char.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ValueError("nonfinite or invalid characteristic limit")
        lower, upper = char.get("lsl"), char.get("usl")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("characteristic limits reversed")
    if not fai_number or not fai_number.strip() or not actor or not actor.strip():
        raise ValueError("fai_number and actor are required")
    receipt_hash = _digest(payload)
    ref = "forgevault://" + source["record_id"] + "/" + source["file_version_id"]
    with db() as con:
        existing = con.execute(
            "SELECT id FROM fai_runs WHERE fai_number=?", (fai_number,)
        ).fetchone()
        if existing:
            link = con.execute(
                "SELECT payload_sha256, pdf_sha256, vault_version_id "
                "FROM fai_source_links WHERE fai_run_id=?", (existing["id"],)
            ).fetchone()
            if not link or link["payload_sha256"] != receipt_hash or link["pdf_sha256"] != digest or link["vault_version_id"] != source["file_version_id"]:
                raise ValueError("FAI number already used for conflicting drawing/inspection")
            return {"id": existing["id"], "fai_number": fai_number,
                    "status": "review_required", "idempotent": True,
                    "sha256": digest, "characteristics": len(chars)}

        document = con.execute(
            "SELECT * FROM documents WHERE storage_reference=?", (ref,)
        ).fetchone()
        if document:
            if document["sha256"] != digest or document["revision"] != source["customer_revision"]:
                raise ValueError("conflicting controlled source document")
            document_id = document["id"]
        else:
            cur = con.execute(
                "INSERT INTO documents(document_number,title,revision,document_type,status,storage_reference,sha256,notes) "
                "VALUES(?, ?, ?, 'drawing', 'Released', ?, ?, ?)",
                (source["record_id"], source["customer_part_number"] + " controlled drawing",
                 source["customer_revision"], ref, digest,
                 "Imported ForgeVault version: " + source["file_version_id"]),
            )
            document_id = cur.lastrowid
        doc_version = con.execute(
            "SELECT * FROM document_versions WHERE document_id=? AND version_number=?",
            (document_id, source["version_number"]),
        ).fetchone()
        if doc_version:
            if doc_version["sha256"] != digest or doc_version["storage_reference"] != ref:
                raise ValueError("conflicting drawing version number")
        else:
            con.execute(
                "INSERT INTO document_versions(document_id,version_number,revision,storage_reference,sha256,created_by) "
                "VALUES(?,?,?,?,?,?)",
                (document_id, source["version_number"], source["customer_revision"], ref, digest, actor),
            )
        cur = con.execute(
            "INSERT INTO fai_runs(fai_number,drawing_document_id,drawing_revision,status,characteristic_count,created_by) "
            "VALUES(?,?,?,'review_required',?,?)",
            (fai_number, document_id, source["customer_revision"], len(chars), actor),
        )
        fai_id = int(cur.lastrowid)
        for char in chars:
            metadata = {"vault_version_id": source["file_version_id"],
                        "vault_sha256": digest, "extraction": char.get("source_metadata") or {}}
            con.execute(
                "INSERT INTO fai_characteristics(fai_run_id,char_number,reference_location,raw_text,nominal,lsl,usl,characteristic_type,tooling,notes,source_metadata) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (fai_id, char["char_number"], char.get("reference_location"),
                 char.get("raw_text"), char.get("nominal"), char.get("lsl"), char.get("usl"),
                 char.get("characteristic_type"), char.get("tooling"), char.get("notes"),
                 json.dumps(metadata, sort_keys=True, default=str)),
            )
        con.execute(
            "INSERT INTO fai_source_links(fai_run_id,vault_record_id,vault_version_id,release_package_number,pdf_sha256,payload_sha256) "
            "VALUES(?,?,?,?,?,?)",
            (fai_id, source["record_id"], source["file_version_id"],
             source["release_package_number"], digest, receipt_hash),
        )
    record_event(
        event_type="FAI", action="IMPORTED_CONTROLLED_DRAWING", module="ezfair",
        entity_type="fai", entity_id=fai_id, actor=actor,
        data={"fai_number": fai_number, "vault_version": source["file_version_id"],
              "drawing_sha256": digest, "inspection_status": "review_required",
              "characteristics": len(chars)},
    )
    publish(
        "fai.imported", source_module="ezfair", entity_type="fai",
        entity_id=str(fai_id), actor=actor,
        payload={"vault_version": source["file_version_id"], "drawing_sha256": digest,
                 "inspection_status": "review_required"},
    )
    return {"id": fai_id, "fai_number": fai_number, "status": "review_required",
            "idempotent": False, "sha256": digest, "characteristics": len(chars)}
