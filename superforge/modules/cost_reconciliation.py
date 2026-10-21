"""Real PO / receipt / vendor invoice cost reconciliation for Axiom.

No vendor dispatch, invoice payment, general-ledger posting, or inferred physical
lot tracing. Monetary inputs are Decimal strings; stored amounts are immutable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from ..db import db
from .purchasing import _id, _qty, _event
from .supplier_intelligence import _day, _text

COST_SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_price_baselines (
  po_line_id INTEGER PRIMARY KEY REFERENCES purchase_order_lines(id),
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  unit TEXT NOT NULL,
  unit_price TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  supplier_quote_id INTEGER REFERENCES supplier_price_history(id),
  captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS vendor_invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  invoice_number TEXT NOT NULL,
  invoice_date TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  document_sha256 TEXT,
  payload_sha256 TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(supplier_id,invoice_number)
);
CREATE TABLE IF NOT EXISTS vendor_invoice_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES vendor_invoices(id),
  po_line_id INTEGER NOT NULL REFERENCES purchase_order_lines(id),
  billed_qty REAL NOT NULL CHECK(billed_qty>0),
  unit TEXT NOT NULL,
  unit_price TEXT NOT NULL,
  freight_amount TEXT NOT NULL,
  other_amount TEXT NOT NULL,
  tax_amount TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  UNIQUE(invoice_id,po_line_id)
);
CREATE TABLE IF NOT EXISTS vendor_cost_reviews (
  invoice_line_id INTEGER PRIMARY KEY REFERENCES vendor_invoice_lines(id),
  reviewed_by TEXT NOT NULL,
  reason TEXT NOT NULL,
  reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS job_consumption_cost_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  consumption_key TEXT NOT NULL REFERENCES procurement_movements(movement_key),
  invoice_line_id INTEGER NOT NULL REFERENCES vendor_invoice_lines(id),
  assigned_qty REAL NOT NULL CHECK(assigned_qty>0),
  source_ref TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(consumption_key,invoice_line_id)
);
CREATE INDEX IF NOT EXISTS ix_vendor_invoice_line_po ON vendor_invoice_lines(po_line_id);
CREATE INDEX IF NOT EXISTS ix_cost_consumption_invoice ON job_consumption_cost_links(invoice_line_id);
"""


def init_cost_reconciliation():
    with db() as con:
        con.executescript(COST_SCHEMA)


def _amount(value, name="amount", *, positive=False):
    if isinstance(value,bool):
        raise ValueError(name+" must be numeric")
    try:
        v=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError(name+" must be numeric") from exc
    if not v.is_finite() or v<0 or (positive and v==0) or v>Decimal("1000000000"):
        raise ValueError(name+" must be finite and "+("positive" if positive else "nonnegative"))
    if v.as_tuple().exponent < -4:
        raise ValueError(name+" supports at most four decimal places")
    return v


def _money(v):
    return format(v.quantize(Decimal(".01"), rounding=ROUND_HALF_UP),"f")


def _record_po_baseline(con, po_line_id, supplier_id, item_id, unit, price, ref, quote_id):
    existing=con.execute("SELECT po_line_id FROM purchase_price_baselines WHERE po_line_id=?",
                         (po_line_id,)).fetchone()
    if existing:
        raise ValueError("PO price is immutable after capture; handle amendments explicitly")
    con.execute("""INSERT INTO purchase_price_baselines
                   (po_line_id,supplier_id,item_id,unit,unit_price,source_ref,supplier_quote_id)
                   VALUES(?,?,?,?,?,?,?)""",
                (po_line_id,supplier_id,item_id,unit,str(price),ref,quote_id))


def record_po_price(po_line_id, unit_price, source_ref, *, supplier_quote_id=None, actor="local"):
    """Capture the actual buyer-agreed PO unit price, not simply the latest quote."""
    line_id=_id(po_line_id,"PO line ID")
    price=_amount(unit_price,"PO unit price",positive=True)
    ref=_text(source_ref,"PO price evidence",250)
    quote_id=_id(supplier_quote_id,"supplier quote ID") if supplier_quote_id not in (None,"") else None
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        line=con.execute("""SELECT l.item_id,l.unit,l.ordered_qty,l.received_qty,
                                   origin.supplier_id,p.status
                            FROM purchase_order_lines l JOIN purchase_orders p
                            ON p.id=l.purchase_order_id
                            JOIN supplier_line_origins origin ON origin.po_line_id=l.id
                            WHERE l.id=?""",(line_id,)).fetchone()
        if line is None:
            raise ValueError("Purchase order line not found")
        if line["supplier_id"] is None:
            raise ValueError("PO must identify an actual supplier before pricing")
        if str(line["status"]).lower() in {"cancelled","closed"}:
            raise ValueError("Inactive PO cannot receive a price commitment")
        if quote_id:
            quote=con.execute("SELECT * FROM supplier_price_history WHERE id=?",
                              (quote_id,)).fetchone()
            if quote is None or (quote["supplier_id"]!=line["supplier_id"]
                  or quote["item_id"]!=line["item_id"] or quote["stocking_unit"]!=line["unit"]):
                raise ValueError("Quoted source does not match PO supplier, item and unit")
            if _amount(quote["unit_price"])!=price:
                raise ValueError("PO agreed price differs from selected quote; omit quote ID and document actual agreement")
        _record_po_baseline(con,line_id,line["supplier_id"],line["item_id"],
                            line["unit"],price,ref,quote_id)
    _event("PO_AGREED_PRICE_RECORDED",line["item_id"],actor,
           {"po_line_id":line_id,"unit_price_usd":str(price),"source_ref":ref})
    return {"po_line_id":line_id,"unit_price_usd":str(price)}


def record_vendor_invoice(supplier_id, invoice_number, invoice_date, lines, source_ref,
                          *, document_sha256=None, actor="local"):
    """Capture complete invoice evidence in one atomic operation; no payment or stock mutation."""
    supplier_id=_id(supplier_id,"supplier ID")
    number=_text(invoice_number,"Invoice number",120)
    day=_day(invoice_date,future_ok=False)
    ref=_text(source_ref,"Invoice source",250)
    if document_sha256 is not None:
        if (not isinstance(document_sha256,str) or len(document_sha256)!=64
            or any(c not in "0123456789abcdef" for c in document_sha256)):
            raise ValueError("Document SHA-256 must be 64 lowercase hexadecimal characters")
    if not isinstance(lines,list) or not 1<=len(lines)<=100:
        raise ValueError("Invoice requires 1 to 100 line records")
    canonical=[]
    seen=set()
    for input_line in lines:
        if not isinstance(input_line,dict):
            raise ValueError("Invoice line must be a record")
        pid=_id(input_line.get("po_line_id"),"PO line ID")
        if pid in seen:
            raise ValueError("Duplicate PO line on invoice")
        seen.add(pid)
        qty=_qty(input_line.get("quantity"),"billed quantity")
        unit=_text(input_line.get("unit"),"Stocking unit",20)
        price=_amount(input_line.get("unit_price"),"Invoice unit price",positive=True)
        freight=_amount(input_line.get("freight",0),"Freight")
        other=_amount(input_line.get("other",0),"Other landed charges")
        tax=_amount(input_line.get("tax",0),"Tax")
        line_ref=_text(input_line.get("source_ref") or ref,"Invoice line source",250)
        canonical.append({"po_line_id":pid,"quantity":qty,"unit":unit,
                          "unit_price":str(price),"freight":str(freight),
                          "other":str(other),"tax":str(tax),"source_ref":line_ref})
    canonical.sort(key=lambda x:x["po_line_id"])
    payload={"supplier_id":supplier_id,"invoice_number":number,"invoice_date":day,
             "source_ref":ref,"document_sha256":document_sha256,"lines":canonical}
    data=json.dumps(payload,sort_keys=True,separators=(",",":"))
    sha=hashlib.sha256(data.encode()).hexdigest()
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        exists=con.execute("""SELECT id,payload_sha256 FROM vendor_invoices
                              WHERE supplier_id=? AND invoice_number=?""",(supplier_id,number)).fetchone()
        if exists:
            if exists["payload_sha256"]!=sha:
                raise ValueError("Invoice number already recorded with different evidence")
            return {"invoice_id":exists["id"],"duplicate":True}
        if con.execute("SELECT id FROM suppliers WHERE id=?",(supplier_id,)).fetchone() is None:
            raise ValueError("Supplier not found")
        for x in canonical:
            row=con.execute("""SELECT l.unit,l.item_id,p.supplier_id,origin.supplier_id AS original_supplier
                               FROM purchase_order_lines l
                               JOIN purchase_orders p ON p.id=l.purchase_order_id
                               LEFT JOIN supplier_line_origins origin ON origin.po_line_id=l.id
                               WHERE l.id=?""",(x["po_line_id"],)).fetchone()
            if row is None:
                raise ValueError("Invoice references unknown PO line")
            if (row["original_supplier"] if row["original_supplier"] is not None
                else row["supplier_id"])!=supplier_id:
                raise ValueError("Invoice supplier does not match ordered supplier")
            if row["unit"]!=x["unit"]:
                raise ValueError("Invoice stocking unit differs from PO line")
        cur=con.execute("""INSERT INTO vendor_invoices
                           (supplier_id,invoice_number,invoice_date,source_ref,document_sha256,payload_sha256,payload_json)
                           VALUES(?,?,?,?,?,?,?)""",
                        (supplier_id,number,day,ref,document_sha256,sha,data))
        invoice_id=cur.lastrowid
        for x in canonical:
            con.execute("""INSERT INTO vendor_invoice_lines
                 (invoice_id,po_line_id,billed_qty,unit,unit_price,
                  freight_amount,other_amount,tax_amount,source_ref)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
                (invoice_id,x["po_line_id"],x["quantity"],x["unit"],
                 x["unit_price"],x["freight"],x["other"],x["tax"],x["source_ref"]))
    _event("VENDOR_INVOICE_RECORDED",0,actor,{"invoice_id":invoice_id,
             "supplier_id":supplier_id,"invoice_number":number,"sha256":sha})
    return {"invoice_id":invoice_id,"duplicate":False}


def _line_state(con,line):
    id_=line["id"]
    po_line_id=line["po_line_id"]
    baseline=con.execute("SELECT * FROM purchase_price_baselines WHERE po_line_id=?",
                         (po_line_id,)).fetchone()
    purchase=con.execute("""SELECT l.ordered_qty,l.received_qty,l.unit,l.item_id,p.po_number,
                        p.job_id AS po_job,r.job_id AS requisition_job
                        FROM purchase_order_lines l
                        JOIN purchase_orders p ON p.id=l.purchase_order_id
                        JOIN procurement_requisitions r ON r.id=l.requisition_id
                        WHERE l.id=?""",(po_line_id,)).fetchone()
    total_qty=sum((Decimal(str(r[0])) for r in con.execute(
         "SELECT billed_qty FROM vendor_invoice_lines WHERE po_line_id=?",(po_line_id,))),Decimal(0))
    qty=Decimal(str(line["billed_qty"]))
    billed=_amount(line["unit_price"])*qty
    freight=_amount(line["freight_amount"])
    other=_amount(line["other_amount"])
    tax=_amount(line["tax_amount"])
    landed=billed+freight+other+tax
    reasons=[]
    if total_qty>Decimal(str(purchase["ordered_qty"])):
        reasons.append("OVER_ORDERED_QTY")
    if total_qty>Decimal(str(purchase["received_qty"])):
        reasons.append("NOT_YET_RECEIVED")
    if not baseline:
        reasons.append("MISSING_PO_PRICE")
        expected=None
        variance=None
    else:
        if baseline["unit"]!=line["unit"]:
            reasons.append("PO_UNIT_MISMATCH")
        expected=_amount(baseline["unit_price"])*qty
        variance=billed-expected
        if variance!=0:
            reasons.append("PRICE_VARIANCE")
    # Other charges do not disappear into the material price; the costs
    # are separately visible and considered potential review variance.
    if freight or other or tax:
        reasons.append("LANDED_CHARGES")
    review=con.execute("SELECT * FROM vendor_cost_reviews WHERE invoice_line_id=?",(id_,)).fetchone()
    blockers={"OVER_ORDERED_QTY","NOT_YET_RECEIVED","MISSING_PO_PRICE","PO_UNIT_MISMATCH"}
    blocking=any(x in blockers for x in reasons)
    if blocking:
        status="HOLD"
    elif reasons and review is None:
        status="VARIANCE_REVIEW"
    else:
        status="RECONCILED"
    return {"id":id_,"invoice_id":line["invoice_id"],"po_line_id":po_line_id,
            "po_number":purchase["po_number"],"item_id":purchase["item_id"],
            "po_job_id":purchase["po_job"],"requisition_job_id":purchase["requisition_job"],
            "qty":str(qty),"unit":line["unit"],"billed_unit_price":line["unit_price"],
            "po_unit_price":baseline["unit_price"] if baseline else None,
            "material_total":_money(billed),"po_expected_total":_money(expected) if expected is not None else None,
            "material_price_variance":_money(variance) if variance is not None else None,
            "freight":_money(freight),"other":_money(other),"tax":_money(tax),
            "landed_total":_money(landed),"landed_unit_cost":str(landed/qty),
            "ordered_qty":purchase["ordered_qty"],"received_qty":purchase["received_qty"],
            "cumulative_billed_qty":str(total_qty),"status":status,"reasons":reasons,
            "reviewed_by":review["reviewed_by"] if review else None,
            "review_reason":review["reason"] if review else None}


def reconcile_invoice(invoice_id):
    inv=_id(invoice_id,"invoice ID")
    with db() as con:
        exists=con.execute("SELECT id FROM vendor_invoices WHERE id=?",(inv,)).fetchone()
        if exists is None:
            raise ValueError("Invoice not found")
        lines=[_line_state(con,row) for row in con.execute(
            "SELECT * FROM vendor_invoice_lines WHERE invoice_id=? ORDER BY id",(inv,))]
    return {"invoice_id":inv,"lines":lines,
            "status":"HOLD" if any(x["status"]=="HOLD" for x in lines)
                    else "VARIANCE_REVIEW" if any(x["status"]=="VARIANCE_REVIEW" for x in lines)
                    else "RECONCILED"}


def review_invoice_line(invoice_line_id, reason, *, actor="local"):
    id_=_id(invoice_line_id,"invoice line ID")
    reason=_text(reason,"Variance explanation",500)
    actor=_text(actor,"Local reviewer",120)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT * FROM vendor_invoice_lines WHERE id=?",(id_,)).fetchone()
        if row is None:
            raise ValueError("Invoice line not found")
        state=_line_state(con,row)
        if state["status"]=="HOLD":
            raise ValueError("Cannot review past missing PO prices, receipt gaps, or overbilling")
        if state["status"]=="RECONCILED":
            return {"invoice_line_id":id_,"status":"RECONCILED","duplicate":True}
        con.execute("""INSERT INTO vendor_cost_reviews(invoice_line_id,reviewed_by,reason)
                       VALUES(?,?,?)""",(id_,actor,reason))
    _event("INVOICE_VARIANCE_REVIEWED",state["item_id"],actor,
           {"invoice_line_id":id_,"reason":reason})
    return {"invoice_line_id":id_,"status":"RECONCILED","duplicate":False}


def reconciliation_snapshot():
    with db() as con:
        invoices=[dict(x) for x in con.execute("""SELECT v.*,s.name supplier FROM vendor_invoices v
               JOIN suppliers s ON s.id=v.supplier_id ORDER BY v.id DESC""")]
        states=[_line_state(con,x) for x in con.execute(
               "SELECT * FROM vendor_invoice_lines ORDER BY id DESC")]
    by_id={v["id"]:v for v in invoices}
    return [{**s,"supplier":by_id[s["invoice_id"]]["supplier"],
             "invoice_number":by_id[s["invoice_id"]]["invoice_number"]} for s in states]


def assign_consumption_cost(consumption_key, invoice_line_id, quantity, source_ref, *, actor="local"):
    """Explicit manual cost assignment, not a proven physical-lot identity."""
    key=_text(consumption_key,"Consumption reference",120)
    inv_line=_id(invoice_line_id,"invoice line ID")
    qty=_qty(quantity,"assigned quantity")
    ref=_text(source_ref,"Cost association evidence",250)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        consumption=con.execute("""SELECT m.* FROM procurement_movements m
            WHERE m.movement_key=? AND m.kind='consumption'""",(key,)).fetchone()
        if consumption is None or consumption["job_id"] is None:
            raise ValueError("A posted job consumption movement is required")
        invoice=con.execute("SELECT * FROM vendor_invoice_lines WHERE id=?",(inv_line,)).fetchone()
        if invoice is None:
            raise ValueError("Vendor invoice line not found")
        state=_line_state(con,invoice)
        if state["status"]!="RECONCILED":
            raise ValueError("Vendor invoice must first be reconciled")
        if state["item_id"]!=consumption["item_id"]:
            raise ValueError("Cost source item does not match consumed item")
        old=con.execute("""SELECT * FROM job_consumption_cost_links
                           WHERE consumption_key=? AND invoice_line_id=?""",(key,inv_line)).fetchone()
        if old:
            if abs(old["assigned_qty"]-qty)>1e-7 or old["source_ref"]!=ref:
                raise ValueError("Existing consumption cost assignment conflicts")
            return {"id":old["id"],"duplicate":True}
        taken=Decimal(str(con.execute("""SELECT COALESCE(SUM(assigned_qty),0) FROM job_consumption_cost_links
                               WHERE consumption_key=?""",(key,)).fetchone()[0]))
        from_invoice=Decimal(str(con.execute("""SELECT COALESCE(SUM(assigned_qty),0) FROM job_consumption_cost_links
                               WHERE invoice_line_id=?""",(inv_line,)).fetchone()[0]))
        if taken+Decimal(str(qty))>Decimal(str(consumption["quantity"])):
            raise ValueError("Cost assignment exceeds actual job consumption")
        if from_invoice+Decimal(str(qty))>Decimal(str(invoice["billed_qty"])):
            raise ValueError("Cost assignment exceeds invoiced item quantity")
        new=con.execute("""INSERT INTO job_consumption_cost_links
                           (consumption_key,invoice_line_id,assigned_qty,source_ref)
                           VALUES(?,?,?,?)""",(key,inv_line,qty,ref))
        link_id=int(new.lastrowid)
    _event("JOB_COST_ASSIGNED",state["item_id"],actor,
           {"job_id":consumption["job_id"],"invoice_line_id":inv_line,
            "consumption_key":key,"quantity":qty})
    return {"id":link_id,"duplicate":False}


def job_material_costs(job_id):
    jid=_id(job_id,"job ID")
    with db() as con:
        raw=[dict(x) for x in con.execute("""SELECT l.*,m.job_id,m.item_id,i.item_number
             FROM job_consumption_cost_links l
             JOIN procurement_movements m ON m.movement_key=l.consumption_key
             JOIN inventory_items i ON i.id=m.item_id
             WHERE m.job_id=? ORDER BY l.id""",(jid,))]
        links=[]
        for r in raw:
            invoice=con.execute("SELECT * FROM vendor_invoice_lines WHERE id=?",
                                (r["invoice_line_id"],)).fetchone()
            state=_line_state(con,invoice)
            cost=Decimal(state["landed_unit_cost"])*Decimal(str(r["assigned_qty"]))
            links.append({**r,"landed_unit_cost":state["landed_unit_cost"],
                          "assigned_landed_cost":_money(cost),
                          "reconciliation_status":state["status"]})
    confirmed=[x for x in links if x["reconciliation_status"]=="RECONCILED"]
    return {"job_id":jid,"links":links,
            "documented_consumption_cost":_money(sum(
                (Decimal(x["assigned_landed_cost"]) for x in confirmed),Decimal(0))),
            "unreconciled_cost_links":len(links)-len(confirmed),
            "limitations":"Manual material cost association, not physical lot provenance or complete job profitability"}



def estimator_price_feedback():
    """Reconciled observed cost feed for explicit EZstimate price-memory review.

    Supplier quotes remain a separate evidence family. Invoiced cost is NOT
    imported silently into an estimate and is not necessarily job-consumed.
    """
    lines=reconciliation_snapshot()
    with db() as con:
        result=[]
        for entry in lines:
            if entry["status"]!="RECONCILED":
                continue
            invoice=con.execute("""SELECT v.invoice_number,v.invoice_date,v.source_ref,v.document_sha256,
                                    s.name AS supplier,i.item_number
                         FROM vendor_invoice_lines l
                         JOIN vendor_invoices v ON v.id=l.invoice_id
                         JOIN suppliers s ON s.id=v.supplier_id
                         JOIN inventory_items i ON i.id=?
                         WHERE l.id=?""",(entry["item_id"],entry["id"])).fetchone()
            result.append({
                "source":"Axiom.vendor_invoice_reconciliation",
                "price_memory_status":"review_required",
                "material_key":invoice["item_number"],"supplier":invoice["supplier"],
                "unit":entry["unit"],"currency":"USD",
                "invoiced_unit_price":entry["billed_unit_price"],
                "landed_unit_cost":entry["landed_unit_cost"],
                "purchase_order_unit_price":entry["po_unit_price"],
                "material_variance_total":entry["material_price_variance"],
                "invoice_number":invoice["invoice_number"],
                "invoice_date":invoice["invoice_date"],
                "source_ref":invoice["source_ref"],
                "document_sha256":invoice["document_sha256"],
                "po_line_id":entry["po_line_id"],"invoice_line_id":entry["id"]})
    return {"schema":"axiom.actual_material_cost_feedback.v1",
            "note":"Review before EZstimate pricing adoption. Not physical-lot costing or posted AP.",
            "observations":result}
