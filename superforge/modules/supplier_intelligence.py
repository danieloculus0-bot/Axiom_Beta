"""Supplier price history and evidence-based purchasing lead-time recommendations.

All offers are append-only, USD per *Axiom stocking unit*. Only complete,
dated receipts from Axiom's purchasing engine contribute delivery evidence.
Neither a quotation nor a recommendation places a supplier order.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, InvalidOperation
from statistics import median
from typing import Any

from ..db import db
from .purchasing import _id, _policy, _qty, _event, purchasing_snapshot

SUPPLIER_SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_price_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  stocking_unit TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency='USD'),
  unit_price TEXT NOT NULL,
  min_order_qty REAL NOT NULL CHECK(min_order_qty>0),
  order_multiple REAL NOT NULL CHECK(order_multiple>0),
  quoted_lead_days INTEGER CHECK(quoted_lead_days>=0),
  quoted_on TEXT NOT NULL,
  valid_until TEXT,
  source_ref TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_supplier_quotes
  ON supplier_price_history(item_id,supplier_id,quoted_on DESC,id DESC);
CREATE TABLE IF NOT EXISTS supplier_line_origins (
  po_line_id INTEGER PRIMARY KEY REFERENCES purchase_order_lines(id),
  supplier_id INTEGER REFERENCES suppliers(id),
  order_placed_on TEXT,
  captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS supplier_line_promises (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  po_line_id INTEGER NOT NULL REFERENCES purchase_order_lines(id),
  promised_on TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_supplier_line_promises
  ON supplier_line_promises(po_line_id,id);
CREATE TABLE IF NOT EXISTS supplier_receipt_dates (
  movement_key TEXT PRIMARY KEY REFERENCES procurement_movements(movement_key),
  received_on TEXT NOT NULL,
  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_supplier_intelligence():
    with db() as con:
        con.executescript(SUPPLIER_SCHEMA)


def _day(value: Any, *, required=True, future_ok=True) -> str | None:
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str):
        raise ValueError("Date must be ISO YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Noncanonical ISO date")
    except ValueError as exc:
        raise ValueError("Date must be ISO YYYY-MM-DD") from exc
    if not future_ok and parsed > date.today():
        raise ValueError("Recorded transaction date cannot be in the future")
    return value


def _text(value: Any, label: str, limit: int = 200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(label + " is required and must be short text")
    return value.strip()


def _price(value):
    try:
        n = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Supplier unit price must be numeric") from exc
    if isinstance(value, bool) or not n.is_finite() or n <= 0 or n > 100000000 or n.as_tuple().exponent < -4:
        raise ValueError("Supplier unit price must be positive, finite and have at most 4 decimals")
    return str(n.normalize())


def _lead(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("Lead days must be an integer")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Lead days must be an integer") from exc
    if str(value) != str(n) or n < 0 or n > 3650:
        raise ValueError("Lead days must be an integer between 0 and 3650")
    return n


def record_supplier_price(supplier_id, item_id, unit_price, unit, *,
                          min_order_qty=1, order_multiple=1, quoted_lead_days=None,
                          quoted_on=None, valid_until=None, source_ref="", actor="local"):
    """Append a documented supplier quotation; never overwrite earlier offers."""
    supplier_id = _id(supplier_id, "supplier ID")
    item_id = _id(item_id, "item ID")
    amount = _price(unit_price)
    min_qty = _qty(min_order_qty, "minimum order")
    pack = _qty(order_multiple, "supplier multiple")
    lead = _lead(quoted_lead_days)
    quoted = _day(quoted_on or date.today().isoformat(), future_ok=False)
    expiry = _day(valid_until, required=False)
    if expiry and expiry < quoted:
        raise ValueError("Price expiry must not precede quote date")
    ref = _text(source_ref, "Supplier quote reference", 250)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        supplier = con.execute("SELECT name FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if supplier is None:
            raise ValueError("Supplier not found")
        policy = _policy(con, item_id)
        if policy["stocking_unit"] != unit:
            raise ValueError("Supplier quote unit does not match Axiom stocking unit")
        cur = con.execute("""INSERT INTO supplier_price_history
            (supplier_id,item_id,stocking_unit,unit_price,min_order_qty,
             order_multiple,quoted_lead_days,quoted_on,valid_until,source_ref)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (supplier_id, item_id, unit, amount, min_qty, pack, lead, quoted, expiry, ref))
        quote_id = int(cur.lastrowid)
    _event("SUPPLIER_QUOTE_RECORDED", item_id, actor,
           {"quote_id": quote_id, "supplier_id": supplier_id, "unit": unit,
            "unit_price_usd": amount, "source_ref": ref})
    return {"id": quote_id, "item_id": item_id, "supplier_id": supplier_id,
            "unit": unit, "price_usd": amount}


def _capture_origin(con, line_id, supplier_id, order_placed_on):
    """Freeze supplier and PO placement date at the time the line is created.

    A later edit to the legacy PO header cannot rewrite historical supplier
    attribution or order-to-delivery lead time.
    """
    ordered = _day(order_placed_on,required=False)
    con.execute("""INSERT INTO supplier_line_origins(po_line_id,supplier_id,order_placed_on)
                   VALUES(?,?,?)""",(line_id,supplier_id,ordered))


def _capture_promise(con, line_id, when, source_ref):
    # Called in the same transaction as PO-line insertion or explicit update.
    day = _day(when)
    ref = _text(source_ref, "Promise reference", 250)
    prior = con.execute("""SELECT promised_on FROM supplier_line_promises
                           WHERE po_line_id=? ORDER BY id DESC LIMIT 1""",
                        (line_id,)).fetchone()
    if prior is not None and prior["promised_on"] == day:
        return False
    con.execute("""INSERT INTO supplier_line_promises(po_line_id,promised_on,source_ref)
                   VALUES(?,?,?)""", (line_id, day, ref))
    return True


def record_supplier_promise(line_id, promised_on, *, source_ref="", actor="local"):
    """Record initial/revised supplier promise. Original promise is retained."""
    line_id = _id(line_id, "PO line ID")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("""SELECT l.item_id,l.ordered_qty,l.received_qty,p.status
                             FROM purchase_order_lines l JOIN purchase_orders p
                             ON p.id=l.purchase_order_id WHERE l.id=?""",
                          (line_id,)).fetchone()
        if row is None:
            raise ValueError("PO line not found")
        if row["received_qty"] >= row["ordered_qty"] - 1e-7:
            raise ValueError("Cannot change supplier promise after full receipt")
        if str(row["status"]).lower() in {"cancelled", "closed", "received"}:
            raise ValueError("Cannot change promise on inactive purchase order")
        saved = _capture_promise(con, line_id, promised_on, source_ref)
    if saved:
        _event("SUPPLIER_PROMISE_RECORDED", row["item_id"], actor,
               {"po_line_id": line_id, "promised_on": promised_on, "source_ref": source_ref})
    return {"line_id": line_id, "promised_on": promised_on, "new": saved}


def _receipt_date(con, movement_key, actual_on):
    """Atomic partner to Axiom receipt posting. Never reconstruct absent dates."""
    date_text = _day(actual_on, future_ok=False)
    existing = con.execute("""SELECT received_on FROM supplier_receipt_dates
                               WHERE movement_key=?""", (movement_key,)).fetchone()
    if existing:
        if existing["received_on"] != date_text:
            raise ValueError("Receipt key already has a different actual delivery date")
        return False
    con.execute("""INSERT INTO supplier_receipt_dates(movement_key,received_on)
                   VALUES(?,?)""", (movement_key, date_text))
    return True


def _completed_lines(con, supplier_id=None):
    """Only fully received, completely date-evidenced lines qualify for actual KPI."""
    sql = """SELECT l.id,origin.supplier_id,l.item_id,
             l.ordered_qty,l.received_qty,origin.order_placed_on AS order_date
             FROM purchase_order_lines l
             JOIN supplier_line_origins origin ON origin.po_line_id=l.id
             WHERE l.received_qty >= l.ordered_qty-0.0000001
               AND origin.supplier_id IS NOT NULL"""
    args = ()
    if supplier_id is not None:
        sql += " AND origin.supplier_id=?"
        args = (supplier_id,)
    completed = []
    for row in con.execute(sql, args).fetchall():
        receipts = con.execute("""SELECT m.quantity,d.received_on FROM procurement_movements m
                                  LEFT JOIN supplier_receipt_dates d ON d.movement_key=m.movement_key
                                  WHERE m.kind='receipt' AND m.purchase_order_line_id=?""",
                               (row["id"],)).fetchall()
        if not receipts or any(r["received_on"] is None for r in receipts):
            continue
        if abs(sum(float(r["quantity"]) for r in receipts) - float(row["ordered_qty"])) > 1e-5:
            continue
        actual = max(r["received_on"] for r in receipts)
        promises = con.execute("""SELECT promised_on FROM supplier_line_promises
                                  WHERE po_line_id=? ORDER BY id""",
                               (row["id"],)).fetchall()
        initial = promises[0]["promised_on"] if promises else None
        current = promises[-1]["promised_on"] if promises else None
        order_day = row["order_date"]
        lead = None
        if order_day:
            try:
                lead = (date.fromisoformat(actual)-date.fromisoformat(order_day)).days
                if lead < 0:
                    lead = None
            except ValueError:
                lead = None
        completed.append({"line_id": row["id"], "supplier_id": row["supplier_id"],
                          "item_id": row["item_id"], "actual_received_on": actual,
                          "original_promised_on": initial, "latest_promised_on": current,
                          "promise_revisions": max(0,len(promises)-1),
                          "actual_lead_days": lead,
                          "days_late": (date.fromisoformat(actual)-date.fromisoformat(initial)).days
                                       if initial else None})
    return completed


def supplier_performance(supplier_id=None):
    """Full-receipt punctuality vs ORIGINAL promise, with separate lead-time coverage."""
    if supplier_id is not None:
        supplier_id = _id(supplier_id, "supplier ID")
    with db() as con:
        suppliers = [dict(r) for r in con.execute(
            "SELECT id,name FROM suppliers WHERE id=?" if supplier_id is not None
            else "SELECT id,name FROM suppliers ORDER BY name",
            (supplier_id,) if supplier_id is not None else ())]
        completed = _completed_lines(con, supplier_id)
    summary = []
    for supplier in suppliers:
        lines = [x for x in completed if x["supplier_id"] == supplier["id"]]
        promised = [x for x in lines if x["original_promised_on"] is not None]
        timed = [x["actual_lead_days"] for x in lines if x["actual_lead_days"] is not None]
        on_time = sum(1 for x in promised if x["days_late"] <= 0)
        summary.append({"supplier_id": supplier["id"], "supplier": supplier["name"],
                        "complete_lines": len(lines),
                        "promise_samples": len(promised),
                        "on_time_lines": on_time,
                        "on_time_pct": round(100*on_time/len(promised),1) if promised else None,
                        "lead_samples": len(timed),
                        "median_actual_lead_days": median(timed) if timed else None,
                        "reliability": ("sampled" if len(promised)>=3 else "insufficient samples"),
                        "revised_promise_lines": sum(x["promise_revisions"]>0 for x in lines)})
    return summary


def latest_offers(item_id, *, as_of=None):
    item_id = _id(item_id, "item ID")
    day = _day(as_of or date.today().isoformat())
    with db() as con:
        rows = [dict(r) for r in con.execute("""SELECT q.*,s.name AS supplier FROM supplier_price_history q
                   JOIN suppliers s ON s.id=q.supplier_id
                   WHERE q.item_id=? AND q.quoted_on<=?
                   ORDER BY q.supplier_id,q.quoted_on DESC,q.id DESC""", (item_id,day))]
    latest = {}
    for row in rows:
        # A superseding expired quote must NOT resurrect an older lower price.
        if row["supplier_id"] not in latest:
            latest[row["supplier_id"]] = row
    return [r for r in latest.values() if not r["valid_until"] or r["valid_until"]>=day]


def _money(value):
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def recommend_suppliers(item_id, required_qty, needed_by=None, *, as_of=None):
    """Rank dated quotations: on-time viable first, then unknown, then late.

    Low-sample delivery observations are displayed but not disguised as a
    reliable forecast. Missing quote lead time and receipt history is UNKNOWN,
    not implicitly a zero-day delivery.
    """
    item_id = _id(item_id, "item ID")
    needed = _day(needed_by, required=False)
    day = _day(as_of or date.today().isoformat())
    qty = Decimal(str(_qty(required_qty,"purchase quantity")))
    with db() as con:
        policy = _policy(con, item_id)
    perf = {r["supplier_id"]:r for r in supplier_performance()}
    evaluated = []
    for quote in latest_offers(item_id,as_of=day):
        if quote["stocking_unit"] != policy["stocking_unit"]:
            continue
        purchase_qty = max(qty,Decimal(str(quote["min_order_qty"])))
        pack = Decimal(str(quote["order_multiple"]))
        purchase_qty = (purchase_qty/pack).to_integral_value(rounding=ROUND_CEILING)*pack
        cost = purchase_qty*Decimal(quote["unit_price"])
        history = perf[quote["supplier_id"]]
        past_days = history["median_actual_lead_days"]
        # Use the worse of quoted and observed lead times when observation exists.
        days = quote["quoted_lead_days"]
        if past_days is not None:
            observed = int(Decimal(str(past_days)).to_integral_value(rounding=ROUND_CEILING))
            days = max(days,observed) if days is not None else observed
        eta = (date.fromisoformat(day)+timedelta(days=days)).isoformat() if days is not None else None
        last_order = (date.fromisoformat(needed)-timedelta(days=days)).isoformat() if needed and days is not None else None
        timing = ("UNKNOWN" if needed and days is None else
                  "ON_TIME" if needed and eta<=needed else
                  "LATE" if needed else "NO_NEED_DATE")
        evaluated.append({
            "supplier_id":quote["supplier_id"],"supplier":quote["supplier"],
            "quote_id":quote["id"],"unit":quote["stocking_unit"],
            "unit_price_usd":quote["unit_price"],"quote_ref":quote["source_ref"],
            "quoted_on":quote["quoted_on"],"valid_until":quote["valid_until"],
            "required_qty":format(qty.normalize(),"f"),"purchase_qty":format(purchase_qty.normalize(),"f"),
            "extended_usd":_money(cost),"lead_days":days,
            "quoted_lead_days":quote["quoted_lead_days"],
            "historical_median_lead_days":past_days,
            "eta":eta,"latest_order_by":last_order,"needed_by":needed,
            "timing":timing,"sample_count":history["promise_samples"],
            "on_time_pct":history["on_time_pct"],
            "lead_samples":history["lead_samples"],
            "reliability":history["reliability"]
        })
    order={"ON_TIME":0,"NO_NEED_DATE":0,"UNKNOWN":1,"LATE":2}
    evaluated.sort(key=lambda x: (
        order[x["timing"]],
        Decimal(x["extended_usd"]) if x["timing"]!="LATE" else
           Decimal(str((date.fromisoformat(x["eta"])-date.fromisoformat(needed)).days)),
        Decimal(x["extended_usd"]),
        -(x["on_time_pct"] if x["sample_count"]>=3 else -1),
        x["supplier_id"]))
    for i,r in enumerate(evaluated,1):
        r["rank"] = i
        r["reason"] = ("Lead time unknown; confirm with supplier" if r["timing"]=="UNKNOWN" else
                       "Estimated arrival exceeds required date" if r["timing"]=="LATE" else
                       "On-time projection based on quoted/observed lead" if r["timing"]=="ON_TIME" else
                       "Lowest priced eligible offer, delivery date unspecified")
    return evaluated


def _earliest_need_by(con,item_id):
    dates=[r[0] for r in con.execute("""SELECT d.need_by
        FROM procurement_method_links l
        JOIN ezm_dependencies d ON d.id=l.dependency_id
        JOIN ezm_operations o ON o.id=d.operation_id
        JOIN ezm_method_plans m ON m.id=o.plan_id
        WHERE l.item_id=? AND l.fulfilled_qty<l.required_qty
          AND upper(m.status) NOT IN ('CLOSED','COMPLETE','CANCELLED')
          AND date(d.need_by) IS NOT NULL ORDER BY date(d.need_by)""",(item_id,))]
    dates.extend(r[0] for r in con.execute("""SELECT needed_by FROM procurement_requisitions
        WHERE item_id=? AND needed_by IS NOT NULL AND status IN ('draft','approved')
        ORDER BY needed_by""",(item_id,)))
    return min(dates) if dates else None


def supplier_suggestions():
    """Cross-module proposal records; no side effects or outgoing orders."""
    snapshot=purchasing_snapshot()
    with db() as con:
        due={r["id"]:_earliest_need_by(con,r["id"]) for r in snapshot}
    proposals=[]
    for item in snapshot:
        q=item["suggested_qty"]
        if q<=0:
            continue
        candidates=recommend_suppliers(item["id"],q,needed_by=due[item["id"]])
        proposals.append({
            "item_id":item["id"],"item":item["item_number"],
            "stocking_unit":item["stocking_unit"],"proposed_qty":q,
            "earliest_need_by":due[item["id"]],"stock_signal":item["signal"],
            "best":candidates[0] if candidates else None,
            "options":candidates
        })
    return proposals


def supplier_price_history(item_id=None, *, limit=100):
    with db() as con:
        sql="""SELECT q.*,s.name AS supplier,i.item_number FROM supplier_price_history q
               JOIN suppliers s ON s.id=q.supplier_id
               JOIN inventory_items i ON i.id=q.item_id"""
        params=()
        if item_id is not None:
            sql+=" WHERE q.item_id=?"
            params=(_id(item_id,"item ID"),)
        sql+=" ORDER BY q.id DESC LIMIT ?"
        params+= (max(1,min(int(limit),500)),)
        return [dict(r) for r in con.execute(sql,params)]


def supplier_promise_history(line_id, *, con=None):
    if con is not None:
        return [dict(r) for r in con.execute(
           "SELECT * FROM supplier_line_promises WHERE po_line_id=? ORDER BY id",
           (_id(line_id,"PO line ID"),))]
    with db() as con2:
        return supplier_promise_history(line_id,con=con2)
