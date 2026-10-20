"""Local-only review-required EZstimate quote intake, independent of quote engine."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from ..db import db
from ..audit import record_event
from ..event_bus import publish

CENT=Decimal("0.01")

def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def numeric(value,name,required=True):
    if value is None or value=="":
        if required:raise ValueError(f"{name} missing")
        return Decimal(0)
    if isinstance(value,bool):raise ValueError(f"{name} cannot be boolean")
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError) as exc:raise ValueError(f"{name} invalid") from exc
    if not n.is_finite() or n<0:raise ValueError(f"{name} invalid")
    return n

def independent_total(lines):
    """Verify quote arithmetic independently from the EZstimate source package."""
    if not isinstance(lines,list) or not lines:raise ValueError("at least one pricing line required")
    amount=Decimal(0)
    for index,line in enumerate(lines,1):
        if not isinstance(line,dict) or not str(line.get("part_number") or "").strip():
            raise ValueError("part number required on each line")
        q=numeric(line.get("quantity"),"quantity")
        if q<1 or q!=q.to_integral_value():raise ValueError("quantity must be positive integer")
        material=numeric(line.get("material_cost_each"),"material cost")
        hours=numeric(line.get("labor_hours_each"),"labor hours")
        rate=numeric(line.get("shop_rate_per_hour"),"shop rate") if hours else Decimal(0)
        outside=numeric(line.get("outside_cost_each"),"outside cost",False)
        setup=numeric(line.get("setup_cost_total"),"setup cost",False)
        scrap=numeric(line.get("scrap_pct"),"scrap percentage",False)
        margin=numeric(line.get("margin_pct"),"margin percentage",False)
        if scrap>100 or margin>=100:raise ValueError("invalid scrap or gross margin percentage")
        cost=(material*(1+scrap/100)+hours*rate+outside)*q+setup
        amount+=cost/(1-margin/100)
    return str(amount.quantize(CENT,rounding=ROUND_HALF_UP))

def import_ezstimate_quote(proposal:dict, *, pdf_bytes:bytes, actor:str):
    """Import a source-verified quote proposal; never approve or submit a PO."""
    if not isinstance(proposal,dict) or proposal.get("schema")!="ezstimate.quote_proposal.v1":
        raise ValueError("unrecognized quote contract")
    if proposal.get("source_system")!="EZstimate" or proposal.get("status")!="review_required":
        raise ValueError("only unapproved EZstimate drafts may be imported")
    if not actor or not str(actor).strip():raise ValueError("actor label required")
    quote_number=proposal.get("quote_number")
    if not isinstance(quote_number,str) or not quote_number.strip() or len(quote_number)>120:
        raise ValueError("valid quote number required")
    doc=proposal.get("source_drawing")
    if not isinstance(doc,dict):raise ValueError("controlled drawing reference required")
    required=("record_id","file_version_id","release_package_number","sha256",
              "customer_part_number","customer_revision","internal_revision")
    if any(not doc.get(key) for key in required) or doc.get("lifecycle")!="Released":
        raise ValueError("complete released drawing identity required")
    if not isinstance(pdf_bytes,bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("actual PDF bytes required")
    observed=hashlib.sha256(pdf_bytes).hexdigest()
    if observed!=doc["sha256"] or (doc.get("byte_size") is not None and len(pdf_bytes)!=doc["byte_size"]):
        raise ValueError("controlled drawing PDF checksum/size mismatch")
    inspected=proposal.get("documents")
    if not isinstance(inspected,list) or not inspected:
        raise ValueError("EZstimate source document observations required")
    pricing=proposal.get("pricing")
    if not isinstance(pricing,dict) or pricing.get("status")!="draft_review" or pricing.get("approval")!="not approved":
        raise ValueError("no approved or incomplete quote permitted")
    if pricing.get("issues") or pricing.get("total") is None:
        raise ValueError("estimate is incomplete")
    expected=independent_total(proposal.get("lines"))
    if pricing["total"]!=expected:
        raise ValueError("quote total differs from independently recomputed input costs")
    if len(pricing.get("lines",[]))!=len(proposal["lines"]):
        raise ValueError("priced lines do not match source inputs")
    # External proof is not just a claimed file version. It must still be a
    # verified local handoff from a released vault PDF in the calling workflow.
    proof_hash=hashlib.sha256(canonical(proposal).encode()).hexdigest()
    with db() as con:
        existing=con.execute("SELECT id FROM quote_intakes WHERE quote_number=?",(quote_number,)).fetchone()
        if existing:
            link=con.execute("SELECT payload_sha256, drawing_sha256 FROM ezstimate_quote_evidence WHERE quote_intake_id=?",(existing["id"],)).fetchone()
            if not link or link["payload_sha256"]!=proof_hash or link["drawing_sha256"]!=observed:
                raise ValueError("quote number already has different estimating evidence")
            return {"quote_id":existing["id"],"status":"review_required","idempotent":True,"total":expected}
        cur=con.execute(
            "INSERT INTO quote_intakes(quote_number,status,owner,estimated_value,notes,material_risk) VALUES(?,'review_required',?,?,?,?)",
            (quote_number,actor,float(Decimal(expected)),
             "Imported EZstimate draft. Source and costing require human quote approval.",
             "review_required"),
        )
        quote_id=cur.lastrowid
        con.execute(
            "INSERT INTO ezstimate_quote_evidence(quote_intake_id,source_record_id,source_version_id,release_package_number,"
            "drawing_sha256,payload_sha256,payload_json) VALUES(?,?,?,?,?,?,?)",
            (quote_id,doc["record_id"],doc["file_version_id"],doc["release_package_number"],
             observed,proof_hash,canonical(proposal)),
        )
    record_event(event_type="QUOTE",action="EZSTIMATE_DRAFT_IMPORTED",module="quoting",
                 entity_type="quote_intake",entity_id=quote_id,actor=actor,
                 data={"quote_number":quote_number,"source_version":doc["file_version_id"],
                       "pdf_sha256":observed,"quote_status":"review_required"})
    publish("quote.estimate.draft_imported",source_module="quoting",
            entity_type="quote_intake",entity_id=str(quote_id),actor=actor,
            payload={"source_version":doc["file_version_id"],"drawing_sha256":observed,
                     "status":"review_required"})
    return {"quote_id":quote_id,"status":"review_required","idempotent":False,"total":expected}
