"""Axiom purchasing inventory model: single stocking unit per item, explicit job demand,
local requisition review, PO receipt, and idempotent consumption. No network dispatch.

This module shares Axiom inventory, jobs, POs and EZ Methods rather than maintaining
a second disconnected purchasing ledger. All quantities are in the item policy's
stocking unit; no implicit sheet-to-lb, ft-to-ea, or ERP material conversion.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import uuid

from ..db import db
from ..audit import record_event
from ..event_bus import publish

POLICY_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_policies (
  item_id INTEGER PRIMARY KEY REFERENCES inventory_items(id),
  stocking_unit TEXT NOT NULL CHECK(stocking_unit IN ('ea','sheet','lb','kg','ft','m')),
  min_qty REAL NOT NULL CHECK(min_qty>=0),
  max_qty REAL NOT NULL CHECK(max_qty>0),
  lead_days INTEGER NOT NULL DEFAULT 0 CHECK(lead_days>=0),
  order_multiple REAL NOT NULL DEFAULT 1 CHECK(order_multiple>0),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK(min_qty<=max_qty)
);
CREATE TABLE IF NOT EXISTS inventory_reservations (
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  quantity REAL NOT NULL CHECK(quantity>=0),
  PRIMARY KEY(item_id,job_id)
);
CREATE TABLE IF NOT EXISTS procurement_requisitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_key TEXT NOT NULL UNIQUE,
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  job_id INTEGER REFERENCES jobs(id),
  quantity REAL NOT NULL CHECK(quantity>0),
  unit TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','approved','ordered','received','cancelled')),
  approved_by TEXT,
  needed_by TEXT,
  supplier_preference TEXT,
  source_ref TEXT,
  description TEXT,
  source_request_id TEXT,
  source_line_index INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_at TEXT,
  UNIQUE(source_request_id,source_line_index)
);
CREATE TABLE IF NOT EXISTS procurement_source_imports (
  source_request_id TEXT PRIMARY KEY,
  source_system TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  line_count INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS purchase_order_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
  requisition_id INTEGER NOT NULL UNIQUE REFERENCES procurement_requisitions(id),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  ordered_qty REAL NOT NULL CHECK(ordered_qty>0),
  received_qty REAL NOT NULL DEFAULT 0 CHECK(received_qty>=0 AND received_qty<=ordered_qty),
  unit TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pol_item ON purchase_order_lines(item_id,purchase_order_id);
CREATE TABLE IF NOT EXISTS procurement_movements (
  movement_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('consumption','receipt')),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  job_id INTEGER REFERENCES jobs(id),
  purchase_order_line_id INTEGER REFERENCES purchase_order_lines(id),
  quantity REAL NOT NULL CHECK(quantity>0),
  transaction_id INTEGER NOT NULL UNIQUE REFERENCES inventory_transactions(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS procurement_method_links (
  dependency_id INTEGER PRIMARY KEY REFERENCES ezm_dependencies(id),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  required_qty REAL NOT NULL CHECK(required_qty>0),
  fulfilled_qty REAL NOT NULL DEFAULT 0 CHECK(fulfilled_qty>=0 AND fulfilled_qty<=required_qty),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_purchasing():
    with db() as con:
        con.executescript(POLICY_SCHEMA)


def _qty(value, field="quantity", *, allow_zero=False):
    if isinstance(value, bool):
        raise ValueError(field + " must be numeric")
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError(field + " must be numeric") from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero) or number > 1000000000:
        raise ValueError(field + " must be finite, nonnegative and within range")
    if number.as_tuple().exponent < -4:
        raise ValueError(field + " supports at most four decimal places")
    return float(number)


def _id(value, field="ID"):
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(field + " must be a positive ID") from exc
    if isinstance(value, bool) or n <= 0 or str(n) != str(value):
        raise ValueError(field + " must be a positive ID")
    return n


def _exists(con, table, identifier):
    # All callers pass fixed table names declared in this module.
    row = con.execute("SELECT id FROM " + table + " WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise ValueError(table + " record not found")


def _policy(con, item_id):
    row = con.execute("SELECT * FROM inventory_policies WHERE item_id=?", (item_id,)).fetchone()
    if row is None:
        raise ValueError("Stocking unit and min/max policy must be configured for this item")
    return dict(row)


def _event(action, item_id, actor, data):
    record_event(event_type="PURCHASING", action=action, module="purchasing",
                 entity_type="inventory_item", entity_id=item_id, actor=actor, data=data)
    publish("purchasing."+action.lower(), source_module="purchasing",
            entity_type="inventory_item", entity_id=str(item_id), actor=actor, payload=data)


def set_policy(item_id, unit, minimum, maximum, lead_days=0, order_multiple=1, *, actor="local"):
    item_id = _id(item_id, "item ID")
    if unit not in {"ea", "sheet", "lb", "kg", "ft", "m"}:
        raise ValueError("Unsupported stocking unit")
    lo = _qty(minimum, "minimum", allow_zero=True)
    hi = _qty(maximum, "maximum")
    multiple = _qty(order_multiple, "purchase multiple")
    if lo > hi:
        raise ValueError("Minimum must not exceed maximum")
    try:
        lead = int(lead_days)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid lead time") from exc
    if lead < 0 or lead > 3650 or str(lead) != str(lead_days):
        raise ValueError("Invalid lead time")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        _exists(con, "inventory_items", item_id)
        previous = con.execute("SELECT stocking_unit FROM inventory_policies WHERE item_id=?", (item_id,)).fetchone()
        if previous and previous["stocking_unit"] != unit:
            balance=con.execute("SELECT on_hand,allocated FROM inventory_items WHERE id=?",(item_id,)).fetchone()
            if abs(float(balance['on_hand']))>1e-7 or abs(float(balance['allocated']))>1e-7:
                raise ValueError("Cannot reinterpret nonempty inventory in another stocking unit")
            n = con.execute("""SELECT
              (SELECT COUNT(*) FROM procurement_requisitions WHERE item_id=? AND status!='cancelled')
              +(SELECT COUNT(*) FROM purchase_order_lines WHERE item_id=?)
              +(SELECT COUNT(*) FROM procurement_movements WHERE item_id=?)
              +(SELECT COUNT(*) FROM inventory_reservations WHERE item_id=? AND quantity>0)
              +(SELECT COUNT(*) FROM procurement_method_links WHERE item_id=?)
              AS n""", (item_id, item_id, item_id, item_id, item_id)).fetchone()["n"]
            if n:
                raise ValueError("Stocking unit cannot change with purchasing/consumption history; use an explicit conversion process")
        con.execute("""INSERT INTO inventory_policies(item_id,stocking_unit,min_qty,max_qty,lead_days,order_multiple)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(item_id) DO UPDATE SET stocking_unit=excluded.stocking_unit,
                       min_qty=excluded.min_qty,max_qty=excluded.max_qty,lead_days=excluded.lead_days,
                       order_multiple=excluded.order_multiple,updated_at=CURRENT_TIMESTAMP""",
                    (item_id, unit, lo, hi, lead, multiple))
    _event("POLICY_SET", item_id, actor, {"unit":unit, "min":lo, "max":hi, "lead_days":lead})
    return {"item_id":item_id,"unit":unit,"min":lo,"max":hi,"lead_days":lead}


def reserve_for_job(item_id, job_id, quantity, *, actor="local"):
    item_id, job_id = _id(item_id,"item ID"), _id(job_id,"job ID")
    qty = _qty(quantity, allow_zero=True)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        _policy(con,item_id)
        _exists(con,"jobs",job_id)
        item = con.execute("SELECT on_hand,allocated FROM inventory_items WHERE id=?", (item_id,)).fetchone()
        row = con.execute("SELECT quantity FROM inventory_reservations WHERE item_id=? AND job_id=?",
                          (item_id,job_id)).fetchone()
        old = float(row["quantity"]) if row else 0
        delta = round(qty-old,4)
        if delta > float(item["on_hand"])-float(item["allocated"])+1e-7:
            raise ValueError("Insufficient unallocated stock to reserve")
        if float(item["allocated"])+delta < -1e-7:
            raise ValueError("Invalid legacy stock allocation")
        con.execute("""INSERT INTO inventory_reservations(item_id,job_id,quantity) VALUES(?,?,?)
                       ON CONFLICT(item_id,job_id) DO UPDATE SET quantity=excluded.quantity""",
                    (item_id,job_id,qty))
        con.execute("UPDATE inventory_items SET allocated=ROUND(allocated+?,4),updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (delta,item_id))
    _event("RESERVATION_SET",item_id,actor,{"job_id":job_id,"quantity":qty,"delta":delta})
    return {"item_id":item_id,"job_id":job_id,"quantity":qty}


def _prior(con, key, kind, item_id, qty, job_id=None, line_id=None):
    row = con.execute("SELECT * FROM procurement_movements WHERE movement_key=?", (key,)).fetchone()
    if row is not None:
        if (row["kind"]!=kind or row["item_id"]!=item_id
                or abs(row["quantity"]-qty)>1e-7 or row["job_id"]!=job_id
                or row["purchase_order_line_id"]!=line_id):
            raise ValueError("Movement key already recorded with conflicting details")
        return {"duplicate":True,"transaction_id":row["transaction_id"],"item_id":item_id,"quantity":qty}
    return None


def consume(item_id, quantity, movement_key, *, job_id=None, actor="local"):
    item_id, qty = _id(item_id,"item ID"), _qty(quantity)
    job_id = _id(job_id,"job ID") if job_id not in (None,"") else None
    if not isinstance(movement_key,str) or not 1<=len(movement_key.strip())<=120:
        raise ValueError("A stable consumption reference is required")
    key = movement_key.strip()
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        old = _prior(con,key,"consumption",item_id,qty,job_id)
        if old: return old
        _policy(con,item_id)
        if job_id is not None: _exists(con,"jobs",job_id)
        item = con.execute("SELECT on_hand,allocated FROM inventory_items WHERE id=?", (item_id,)).fetchone()
        reserved = con.execute("SELECT quantity FROM inventory_reservations WHERE item_id=? AND job_id=?",
                               (item_id,job_id)).fetchone() if job_id else None
        reserved_qty = float(reserved["quantity"]) if reserved else 0
        use_reserved = min(qty,reserved_qty)
        free = max(0,float(item["on_hand"])-float(item["allocated"]))
        if qty > float(item["on_hand"])+1e-7 or qty-use_reserved > free+1e-7:
            raise ValueError("Consumption exceeds available or job-reserved stock")
        if reserved:
            con.execute("""UPDATE inventory_reservations SET quantity=ROUND(quantity-?,4)
                           WHERE item_id=? AND job_id=?""",(use_reserved,item_id,job_id))
        con.execute("""UPDATE inventory_items SET on_hand=ROUND(on_hand-?,4),
                       allocated=ROUND(allocated-?,4),updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (qty,use_reserved,item_id))
        if job_id is not None:
            # Consumed stock satisfies explicit method demand, starting with the
            # earliest mapped dependency. Posting the same key never repeats it.
            pending=con.execute("""SELECT l.dependency_id,l.required_qty,l.fulfilled_qty
                FROM procurement_method_links l
                JOIN ezm_dependencies d ON d.id=l.dependency_id
                JOIN ezm_operations o ON o.id=d.operation_id
                JOIN ezm_method_plans m ON m.id=o.plan_id
                WHERE l.item_id=? AND m.job_id=?
                  AND upper(m.status) NOT IN ('COMPLETE','CLOSED','CANCELLED')
                ORDER BY d.need_by,l.dependency_id""",(item_id,job_id)).fetchall()
            left=qty
            for demand in pending:
                if left<=0:break
                take=min(left,round(demand['required_qty']-demand['fulfilled_qty'],4))
                if take>0:
                    con.execute("UPDATE procurement_method_links SET fulfilled_qty=ROUND(fulfilled_qty+?,4) WHERE dependency_id=?",
                                (take,demand['dependency_id']))
                    left=round(left-take,4)
        cur=con.execute("""INSERT INTO inventory_transactions(item_id,job_id,txn_type,quantity,reference,actor)
                           VALUES(?,?,'consumption',?,?,?)""",(item_id,job_id,-qty,key,actor))
        txn=int(cur.lastrowid)
        con.execute("""INSERT INTO procurement_movements
                       (movement_key,kind,item_id,job_id,quantity,transaction_id)
                       VALUES(?,'consumption',?,?,?,?)""",(key,item_id,job_id,qty,txn))
    _event("CONSUMED",item_id,actor,{"quantity":qty,"job_id":job_id,"movement_key":key,"txn_id":txn})
    return {"duplicate":False,"transaction_id":txn,"item_id":item_id,"quantity":qty}


def create_requisition(item_id, quantity, request_key, *, job_id=None, actor="local",
                       needed_by=None, supplier_preference="", source_ref="", description=""):
    item_id,qty = _id(item_id,"item ID"),_qty(quantity)
    job_id = _id(job_id,"job ID") if job_id not in (None,"") else None
    if not isinstance(request_key,str) or not 1<=len(request_key.strip())<=120:
        raise ValueError("Request key required")
    key=request_key.strip()
    if needed_by not in (None,''):
        try:
            if date.fromisoformat(needed_by).isoformat()!=needed_by:
                raise ValueError('Bad date')
        except (ValueError,TypeError) as exc:
            raise ValueError('Needed-by date must be YYYY-MM-DD') from exc
    needed_by=needed_by or None
    for name,value in [('supplier preference',supplier_preference),('source ref',source_ref),('description',description)]:
        if not isinstance(value,str) or len(value)>400:
            raise ValueError(name+' invalid')
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        old=con.execute("SELECT * FROM procurement_requisitions WHERE request_key=?",(key,)).fetchone()
        if old:
            if (old["item_id"]!=item_id or old["job_id"]!=job_id or abs(old["quantity"]-qty)>1e-7
                or old['needed_by']!=needed_by or (old['supplier_preference'] or '')!=supplier_preference
                or (old['source_ref'] or '')!=source_ref or (old['description'] or '')!=description):
                raise ValueError("Request key conflicts with an earlier requisition")
            return {"id":old["id"],"duplicate":True,"status":old["status"]}
        policy=_policy(con,item_id)
        if job_id is not None:_exists(con,"jobs",job_id)
        cur=con.execute("""INSERT INTO procurement_requisitions
                           (request_key,item_id,job_id,quantity,unit,requested_by,
                            needed_by,supplier_preference,source_ref,description)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",(key,item_id,job_id,qty,policy["stocking_unit"],actor,
                                                       needed_by,supplier_preference,source_ref,description))
        rid=int(cur.lastrowid)
    _event("REQUISITION_DRAFTED",item_id,actor,{"requisition_id":rid,"quantity":qty,"job_id":job_id})
    return {"id":rid,"duplicate":False,"status":"draft"}


def approve_requisition(requisition_id, *, actor="local"):
    rid=_id(requisition_id,"requisition ID")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT * FROM procurement_requisitions WHERE id=?",(rid,)).fetchone()
        if not row:raise ValueError("Requisition not found")
        if row["status"]!="draft":raise ValueError("Only a draft requisition can be reviewed")
        con.execute("""UPDATE procurement_requisitions SET status='approved',approved_by=?,
                       approved_at=CURRENT_TIMESTAMP WHERE id=?""",(actor,rid))
    _event("REQUISITION_APPROVED",row["item_id"],actor,{"requisition_id":rid,
                                                         "approval_scope":"local review, not verified identity"})
    return {"id":rid,"status":"approved"}


def attach_to_po(requisition_id, purchase_order_id, *, actor="local"):
    rid,pid=_id(requisition_id,"requisition ID"),_id(purchase_order_id,"PO ID")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        req=con.execute("SELECT * FROM procurement_requisitions WHERE id=?",(rid,)).fetchone()
        po=con.execute("SELECT * FROM purchase_orders WHERE id=?",(pid,)).fetchone()
        if req is None or po is None:raise ValueError("Requisition or purchase order not found")
        prior=con.execute("SELECT id,purchase_order_id FROM purchase_order_lines WHERE requisition_id=?",(rid,)).fetchone()
        if prior:
            if prior["purchase_order_id"]!=pid:raise ValueError("Requisition already attached to a different PO")
            return {"line_id":prior["id"],"duplicate":True}
        if req["status"]!="approved":raise ValueError("Only a locally approved requisition can be placed on a PO")
        if str(po["status"]).lower() in {"cancelled","closed","received"}:
            raise ValueError("This PO cannot take new order lines")
        if req["job_id"] is not None and po["job_id"] not in (None,req["job_id"]):
            raise ValueError("Purchase order is linked to a different job")
        if _policy(con,req["item_id"])["stocking_unit"]!=req["unit"]:
            raise ValueError("Requisition unit differs from inventory stocking unit")
        cur=con.execute("""INSERT INTO purchase_order_lines
                           (purchase_order_id,requisition_id,item_id,ordered_qty,unit)
                           VALUES(?,?,?,?,?)""",(pid,rid,req["item_id"],req["quantity"],req["unit"]))
        line_id=int(cur.lastrowid)
        if po["expected_date"]:
            # Snapshot original PO promise, instead of silently rewriting history
            # when someone later changes the freeform PO header date.
            from .supplier_intelligence import _capture_promise
            _capture_promise(con,line_id,po["expected_date"],"PO header at attachment")
        con.execute("UPDATE procurement_requisitions SET status='ordered' WHERE id=?",(rid,))
    _event("REQUISITION_LINKED_TO_PO",req["item_id"],actor,{"po_id":pid,"line_id":line_id,"requisition_id":rid})
    return {"line_id":line_id,"duplicate":False}


def receive(line_id, quantity, movement_key, *, received_on=None, actor="local"):
    line_id,qty=_id(line_id,"PO line ID"),_qty(quantity)
    if not isinstance(movement_key,str) or not 1<=len(movement_key.strip())<=120:
        raise ValueError("A unique receiving reference is required")
    key=movement_key.strip()
    from .supplier_intelligence import _day, _receipt_date
    actual = _day(received_on or date.today().isoformat(), future_ok=False)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        line=con.execute("""SELECT l.*,p.job_id,p.status po_status,p.order_date FROM purchase_order_lines l
                            JOIN purchase_orders p ON p.id=l.purchase_order_id WHERE l.id=?""",(line_id,)).fetchone()
        if not line:raise ValueError("PO line not found")
        old=_prior(con,key,"receipt",line["item_id"],qty,None,line_id)
        if old:
            if received_on is not None:
                stamped=con.execute("SELECT received_on FROM supplier_receipt_dates WHERE movement_key=?",(key,)).fetchone()
                if stamped and stamped["received_on"]!=actual:
                    raise ValueError("Receipt key already has a different delivery date")
            return old
        if line["order_date"] and actual < _day(line["order_date"]):
            raise ValueError("Receipt date cannot predate purchase order date")
        if str(line["po_status"]).lower()=="cancelled":
            raise ValueError("Cannot receive a cancelled purchase order")
        _policy(con,line["item_id"])
        if qty > line["ordered_qty"]-line["received_qty"]+1e-7:
            raise ValueError("Receipt exceeds outstanding purchase order quantity")
        con.execute("""UPDATE purchase_order_lines SET received_qty=ROUND(received_qty+?,4)
                       WHERE id=?""",(qty,line_id))
        con.execute("""UPDATE inventory_items SET on_hand=ROUND(on_hand+?,4),
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",(qty,line["item_id"]))
        cur=con.execute("""INSERT INTO inventory_transactions
                           (item_id,job_id,po_id,txn_type,quantity,reference,actor)
                           VALUES(?,?,?,'receipt',?,?,?)""",
                        (line["item_id"],line["job_id"],line["purchase_order_id"],qty,key,actor))
        txn=int(cur.lastrowid)
        con.execute("""INSERT INTO procurement_movements
                       (movement_key,kind,item_id,purchase_order_line_id,quantity,transaction_id)
                       VALUES(?,'receipt',?,?,?,?)""",(key,line["item_id"],line_id,qty,txn))
        _receipt_date(con,key,actual)
        remaining=con.execute("""SELECT COUNT(*) AS n FROM purchase_order_lines
                          WHERE purchase_order_id=? AND received_qty<ordered_qty-0.0000001""",
                          (line["purchase_order_id"],)).fetchone()["n"]
        if remaining==0:
            con.execute("""UPDATE purchase_orders SET status='received',received_date=CURRENT_DATE,
                           updated_at=CURRENT_TIMESTAMP WHERE id=?""",(line["purchase_order_id"],))
        if abs((line["received_qty"]+qty)-line["ordered_qty"])<1e-7:
            con.execute("UPDATE procurement_requisitions SET status='received' WHERE id=?",
                        (line["requisition_id"],))
    _event("STOCK_RECEIVED",line["item_id"],actor,{"po_id":line["purchase_order_id"],"line_id":line_id,
                                                  "quantity":qty,"movement_key":key,"received_on":actual,"txn_id":txn})
    return {"duplicate":False,"transaction_id":txn,"item_id":line["item_id"],"quantity":qty,
            "received_on":actual}


def link_method_demand(dependency_id, item_id, quantity, *, actor="local"):
    did,iid=_id(dependency_id,"dependency ID"),_id(item_id,"item ID")
    qty=_qty(quantity)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        _policy(con,iid)
        row=con.execute("SELECT kind FROM ezm_dependencies WHERE id=?",(did,)).fetchone()
        if not row:raise ValueError("Method dependency not found")
        if str(row["kind"]).upper() not in {"MATERIAL","PURCHASED_PART"}:
            raise ValueError("Only physical material and purchased-part requirements can map to stock inventory")
        con.execute("""INSERT INTO procurement_method_links(dependency_id,item_id,required_qty)
                       VALUES(?,?,?) ON CONFLICT(dependency_id) DO UPDATE
                       SET fulfilled_qty=CASE WHEN item_id=excluded.item_id
                              THEN MIN(fulfilled_qty,excluded.required_qty) ELSE 0 END,
                           item_id=excluded.item_id,required_qty=excluded.required_qty""",(did,iid,qty))
    _event("METHOD_DEMAND_LINKED",iid,actor,{"dependency_id":did,"quantity":qty})
    return {"dependency_id":did,"item_id":iid,"quantity":qty}


def method_stock_signals():
    """Evidence only: available stock is shared across jobs and is not allocated automatically."""
    with db() as con:
        rows=con.execute("""SELECT l.dependency_id,l.item_id,l.required_qty,
                             l.fulfilled_qty,i.item_number,i.on_hand,i.allocated,
                             COALESCE((SELECT r.quantity FROM inventory_reservations r
                               WHERE r.item_id=l.item_id AND r.job_id=m.job_id),0) AS reserved_for_job
                             FROM procurement_method_links l
                             JOIN ezm_dependencies d ON d.id=l.dependency_id
                             JOIN ezm_operations o ON o.id=d.operation_id
                             JOIN ezm_method_plans m ON m.id=o.plan_id
                             JOIN inventory_items i ON i.id=l.item_id""").fetchall()
    signals={}
    for r in rows:
        ready=max(0,float(r["on_hand"])-float(r["allocated"]))+float(r["reserved_for_job"])
        remaining=round(max(0,r['required_qty']-r['fulfilled_qty']),4)
        signals[r["dependency_id"]]={"item":r["item_number"],"available_not_promised":round(ready,4),
             "required":remaining,"fulfilled":r['fulfilled_qty'],
             "short":round(max(0,remaining-ready),4),
             "status":"FULFILLED" if remaining==0 else
                      "STOCK SIGNAL ONLY" if ready>=remaining else "SHORTAGE"}
    return signals


def purchasing_snapshot():
    """Read actual stock, confirmed inbound, linked method demand and consumption history."""
    with db() as con:
        items=[dict(x) for x in con.execute("""SELECT i.*,p.stocking_unit,p.min_qty,p.max_qty,
                  p.lead_days,p.order_multiple
                  FROM inventory_items i LEFT JOIN inventory_policies p ON p.item_id=i.id
                  ORDER BY i.item_number""")]
        incoming={x["item_id"]:float(x["q"]) for x in con.execute("""
          SELECT l.item_id,SUM(l.ordered_qty-l.received_qty) q
          FROM purchase_order_lines l JOIN purchase_orders p ON p.id=l.purchase_order_id
          WHERE lower(p.status) NOT IN ('cancelled','closed','received')
          GROUP BY l.item_id""")}
        inbound_due={x['item_id']:float(x['q']) for x in con.execute("""
          SELECT l.item_id,SUM(l.ordered_qty-l.received_qty) q
          FROM purchase_order_lines l
          JOIN purchase_orders po ON po.id=l.purchase_order_id
          JOIN inventory_policies pol ON pol.item_id=l.item_id
          WHERE lower(po.status) NOT IN ('cancelled','closed','received')
            AND date(COALESCE(
                 (SELECT x.promised_on FROM supplier_line_promises x
                  WHERE x.po_line_id=l.id ORDER BY x.id DESC LIMIT 1),
                 po.expected_date))>=date('now')
            AND date(COALESCE(
                 (SELECT x.promised_on FROM supplier_line_promises x
                  WHERE x.po_line_id=l.id ORDER BY x.id DESC LIMIT 1),
                 po.expected_date))<=date('now','+'||pol.lead_days||' days')
          GROUP BY l.item_id""")}
        consumed={x["item_id"]:float(x["q"]) for x in con.execute("""
          SELECT item_id,-SUM(quantity) q FROM inventory_transactions
          WHERE txn_type='consumption' AND created_at>=datetime('now','-30 days')
          GROUP BY item_id""")}
        reservations={(x["item_id"],x["job_id"]):float(x["quantity"]) for x in con.execute(
          "SELECT item_id,job_id,quantity FROM inventory_reservations")}
        jobs={}
        for x in con.execute("""SELECT l.item_id,m.job_id,SUM(l.required_qty-l.fulfilled_qty) qty
                     FROM procurement_method_links l
                     JOIN ezm_dependencies d ON d.id=l.dependency_id
                     JOIN ezm_operations o ON o.id=d.operation_id
                     JOIN ezm_method_plans m ON m.id=o.plan_id
                     WHERE upper(m.status) NOT IN ('COMPLETE','CLOSED','CANCELLED')
                     GROUP BY l.item_id,m.job_id"""):
            key=(x["item_id"],x["job_id"])
            jobs[key]=float(x["qty"])
    demands={}
    for (item_id,job_id),q in jobs.items():
        demands[item_id]=demands.get(item_id,0)+max(0,q-reservations.get((item_id,job_id),0))
    result=[]
    for item in items:
        item_id=item["id"]
        on=float(item["on_hand"])
        allocated=float(item["allocated"])
        available=round(on-allocated,4)
        inbound=incoming.get(item_id,0)
        due_inbound=inbound_due.get(item_id,0)
        demand=round(demands.get(item_id,0),4)
        last30=round(consumed.get(item_id,0),4)
        lead=int(item["lead_days"] or 0)
        during_lead=round(last30/30*lead,4)
        position=round(available+inbound-demand,4)
        projected=round(available+due_inbound-demand-during_lead,4)
        min_qty=item["min_qty"]
        suggested=0.0
        if min_qty is not None and projected<=float(min_qty)+1e-7:
            # An existing PO arriving after the lead window is an expedite risk,
            # not an excuse to generate duplicate purchasing commitments.
            target=max(0,Decimal(str(item["max_qty"]))-Decimal(str(position-during_lead)))
            multiple=Decimal(str(item["order_multiple"]))
            suggested=float((target/multiple).to_integral_value(rounding=ROUND_CEILING)*multiple)
        result.append({**item,"available":available,"inbound":round(inbound,4),
                       "inbound_due_in_lead":round(due_inbound,4),
                       "method_unreserved_demand":demand,"consumed_30d":last30,
                       "lead_demand":during_lead,"stock_position":position,
                       "projected":projected,"suggested_qty":round(suggested,4),
                       "signal":("UNCONFIGURED" if min_qty is None else
                                "REORDER" if suggested>0 else
                                "EXPEDITE" if projected<=float(min_qty)+1e-7 else "OK")})
    return result


def import_ezstimate_request(document, *, actor="local"):
    """Stage an EZstimate PR as local Axiom drafts, never an approved order.

    Accepts the EZstimate request record (with request_id + payload) or its
    dispatch envelope. Requires exact matching item code, stocking unit and
    named job. Atomic for all lines, version checked and idempotent.
    """
    if not isinstance(document,dict):
        raise ValueError("EZstimate request must be a JSON object")
    wrapper=document.get("request",document)
    if not isinstance(wrapper,dict):
        raise ValueError("EZstimate request wrapper is invalid")
    rid=wrapper.get("request_id")
    if not isinstance(rid,str) or not re.fullmatch(r"PR-[A-Za-z0-9]{8,32}",rid):
        raise ValueError("Valid EZstimate request_id required")
    payload=wrapper.get("payload")
    if not isinstance(payload,dict) or payload.get("schema")!="axiom.purchase_request.v1":
        raise ValueError("Unsupported EZstimate PR payload")
    if payload.get("source_system")!="EZstimate":
        raise ValueError("Unexpected purchase request source")
    rows=payload.get("lines")
    if not isinstance(rows,list) or not 1<=len(rows)<=100:
        raise ValueError("Expected 1 to 100 material lines")
    who=payload.get("requested_by")
    if not isinstance(who,str) or not 1<=len(who.strip())<=120:
        raise ValueError("Missing EZstimate requested_by")
    encoded=json.dumps(payload,sort_keys=True,separators=(",",":"))
    if len(encoded)>100000:
        raise ValueError("EZstimate request exceeds maximum source size")
    digest=hashlib.sha256(encoded.encode()).hexdigest()
    if wrapper.get("payload_sha256")!=digest:
        raise ValueError("EZstimate source digest differs from payload")
    normalized=[]
    for n,line in enumerate(rows,1):
        if not isinstance(line,dict):
            raise ValueError(f"Line {n} must be an object")
        code=line.get("material_key")
        if not isinstance(code,str) or not code.strip() or len(code)>200:
            raise ValueError(f"Line {n} missing material key")
        unit=line.get("unit")
        if unit not in {"ea","sheet","lb","kg","ft","m"}:
            raise ValueError(f"Line {n} unit invalid")
        qty=_qty(line.get("quantity"),f"line {n} quantity")
        need=line.get("needed_by") or None
        if need is not None:
            try:
                if date.fromisoformat(need).isoformat()!=need: raise ValueError()
            except (ValueError,TypeError) as exc:
                raise ValueError(f"Line {n} needed-by date invalid") from exc
        job=line.get("job") or None
        source_ref=line.get("source_ref") or ""
        supplier=line.get("supplier_preference") or ""
        description=line.get("description") or ""
        if not all(isinstance(x,str) and len(x)<=400 for x in (source_ref,supplier,description)):
            raise ValueError(f"Line {n} source text invalid")
        if job is not None and (not isinstance(job,str) or len(job)>100):
            raise ValueError(f"Line {n} job reference invalid")
        normalized.append((code.strip(),unit,qty,need,job,supplier,source_ref,description))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        prior=con.execute("SELECT * FROM procurement_source_imports WHERE source_request_id=?",(rid,)).fetchone()
        if prior:
            if prior["payload_sha256"]!=digest:
                raise ValueError("EZstimate request ID reused with different content")
            ids=[r[0] for r in con.execute(
                 "SELECT id FROM procurement_requisitions WHERE source_request_id=? ORDER BY source_line_index",(rid,))]
            if len(ids)!=len(rows):
                raise ValueError("Previously imported requisition lines are inconsistent")
            return {"request_id":rid,"duplicate":True,"requisitions":ids}
        resolved=[]
        for n,(code,unit,qty,need,job,supplier,source_ref,description) in enumerate(normalized,1):
            row=con.execute("SELECT id FROM inventory_items WHERE item_number=?",(code,)).fetchone()
            if not row:
                raise ValueError(f"Line {n} unknown Axiom inventory item {code}")
            item_id=row["id"]
            policy=_policy(con,item_id)
            if unit!=policy["stocking_unit"]:
                raise ValueError(f"Line {n} unit mismatch: {unit} vs Axiom {policy['stocking_unit']}")
            job_id=None
            if job:
                found=con.execute("SELECT id FROM jobs WHERE job_number=?",(job,)).fetchone()
                if not found:
                    raise ValueError(f"Line {n} unknown Axiom job {job}")
                job_id=found["id"]
            resolved.append((n,item_id,unit,qty,need,job_id,supplier,source_ref,description))
        con.execute("""INSERT INTO procurement_source_imports
                       (source_request_id,source_system,payload_sha256,payload_json,line_count)
                       VALUES(?,'EZstimate',?,?,?)""",(rid,digest,encoded,len(rows)))
        ids=[]
        for n,item_id,unit,qty,need,job_id,supplier,source_ref,description in resolved:
            cur=con.execute("""INSERT INTO procurement_requisitions
                (request_key,item_id,job_id,quantity,unit,requested_by,status,needed_by,
                 supplier_preference,source_ref,description,source_request_id,source_line_index)
                VALUES(?,?,?,?,?,?,'draft',?,?,?,?,?,?)""",
                (f"EZ:{rid}:{n}",item_id,job_id,qty,unit,who.strip(),need,
                 supplier,source_ref,description,rid,n))
            ids.append(int(cur.lastrowid))
    _event("EZSTIMATE_PR_IMPORTED",resolved[0][1],actor,
           {"source_request_id":rid,"sha256":digest,"lines":len(ids),
            "status":"draft; review required; no ERP or supplier dispatch"})
    return {"request_id":rid,"duplicate":False,"requisitions":ids}
