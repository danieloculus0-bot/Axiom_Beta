"""Purchasing cost and invoice variance workbench. Real local records, no AP payment."""
from __future__ import annotations

import json
from datetime import date
from html import escape
from flask import Blueprint, redirect, request, jsonify

from ..db import db
from ..ui import page
from . import cost_reconciliation as costs

cost_blueprint=Blueprint("purchase_costs",__name__)


def h(value):
    return escape("" if value is None else str(value),quote=True)


def selector(name, rows, key, label, *, optional=False):
    options="<option value=''>"+("None" if optional else "Select")+"</option>"
    options+="".join("<option value='"+h(r[key])+"'>"+h(r[label])+"</option>" for r in rows)
    return "<select name='"+h(name)+"' "+("" if optional else "required")+">"+options+"</select>"


def table(rows, cols):
    th="".join("<th>"+h(label)+"</th>" for _,label in cols)
    body="".join("<tr>"+"".join("<td>"+h(row.get(k))+"</td>" for k,_ in cols)+"</tr>" for row in rows)
    return "<div style='overflow:auto'><table><thead><tr>"+th+"</tr></thead><tbody>"+body+"</tbody></table></div>"


@cost_blueprint.get("/purchasing/costs/feedback.json")
def cost_feedback_json():
    return jsonify(costs.estimator_price_feedback())


@cost_blueprint.route("/purchasing/costs",methods=["GET","POST"])
def actual_purchasing_costs():
    if request.method=="POST":
        f=request.form
        action=f.get("action")
        try:
            if action=="po_price":
                costs.record_po_price(f.get("line_id"),f.get("unit_price"),
                                      f.get("source_ref") or "",
                                      supplier_quote_id=f.get("quote_id") or None)
            elif action=="invoice":
                raw=f.get("lines_json") or ""
                if raw.strip():
                    lines=json.loads(raw)
                else:
                    lines=[{"po_line_id":f.get("po_line_id"),"quantity":f.get("quantity"),
                            "unit":f.get("unit"),"unit_price":f.get("unit_price"),
                            "freight":f.get("freight") or "0","other":f.get("other") or "0",
                            "tax":f.get("tax") or "0"}]
                costs.record_vendor_invoice(
                   f.get("supplier_id"),f.get("invoice_number"),f.get("invoice_date"),lines,
                   f.get("source_ref") or "",document_sha256=f.get("document_sha256") or None)
            elif action=="review":
                costs.review_invoice_line(f.get("invoice_line_id"),f.get("reason") or "")
            elif action=="allocate":
                costs.assign_consumption_cost(
                    f.get("consumption_key"),f.get("invoice_line_id"),
                    f.get("quantity"),f.get("source_ref") or "")
            else:
                raise ValueError("Unknown purchasing cost action")
        except (ValueError,TypeError,OverflowError) as exc:
            return page("Purchasing reconciliation input needs correction",
                "<section class='panel'><h2>Not recorded</h2><p>"+h(exc)+
                "</p><a href='/purchasing/costs'>Back to cost reconciliation</a></section>",
                module_key="purchasing"),400
        return redirect("/purchasing/costs")

    with db() as con:
        suppliers=[dict(r) for r in con.execute("SELECT id,name FROM suppliers ORDER BY name")]
        polines=[dict(r) for r in con.execute("""SELECT l.id,l.unit,l.item_id,l.ordered_qty,
                   p.po_number,p.supplier_id,i.item_number,s.name supplier
                   FROM purchase_order_lines l
                   JOIN purchase_orders p ON p.id=l.purchase_order_id
                   JOIN inventory_items i ON i.id=l.item_id
                   LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY l.id DESC LIMIT 300""")]
        baselines=[dict(r) for r in con.execute("""SELECT b.*,p.po_number,i.item_number,
                   s.name supplier FROM purchase_price_baselines b
                   JOIN purchase_order_lines l ON l.id=b.po_line_id
                   JOIN purchase_orders p ON p.id=l.purchase_order_id
                   JOIN inventory_items i ON i.id=b.item_id
                   JOIN suppliers s ON s.id=b.supplier_id
                   ORDER BY b.po_line_id DESC""")]
        quotes=[dict(r) for r in con.execute("""SELECT q.id,s.name supplier,i.item_number
                    FROM supplier_price_history q
                    JOIN suppliers s ON s.id=q.supplier_id
                    JOIN inventory_items i ON i.id=q.item_id ORDER BY q.id DESC LIMIT 200""")]
        invoices=[dict(r) for r in con.execute("""SELECT v.id,v.invoice_number,v.invoice_date,
                    s.name supplier,v.source_ref
                    FROM vendor_invoices v JOIN suppliers s ON s.id=v.supplier_id
                    ORDER BY v.id DESC LIMIT 150""")]
        consumed=[dict(r) for r in con.execute("""SELECT m.movement_key,m.job_id,m.item_id,
                 j.job_number,i.item_number,m.quantity FROM procurement_movements m
                 JOIN jobs j ON j.id=m.job_id JOIN inventory_items i ON i.id=m.item_id
                 WHERE m.kind='consumption' ORDER BY m.created_at DESC LIMIT 150""")]
        jobs=[dict(r) for r in con.execute("SELECT id,job_number FROM jobs ORDER BY id DESC LIMIT 150")]
    states=costs.reconciliation_snapshot()
    ready=sum(s["status"]=="RECONCILED" for s in states)
    variance=sum(s["status"]=="VARIANCE_REVIEW" for s in states)
    hold=sum(s["status"]=="HOLD" for s in states)

    body="<section class='page-head'><div><p class='eyebrow'>Purchasing / true cost evidence</p>"
    body+="<h1>PO, Receipt & Invoice Reconciliation</h1>"
    body+="<p class='sub'>Three-way matching between the agreed PO unit price,"
    body+=" physically received quantities and the supplier invoice. Freight,"
    body+=" tax and other charges stay visible, not buried in a rewritten material price."
    body+=" No payment, AP posting, supplier purchase or GL transaction is triggered.</p></div>"
    body+="<a class='button secondary' href='/purchasing'>Material purchasing</a>"
    body+="<a class='button secondary' href='/purchasing/suppliers'>Supplier quotes</a>"
    body+="<a class='button secondary' href='/purchasing/costs/feedback.json'>EZstimate Actual Cost Feedback JSON</a></section>"
    body+="<div class='grid'>"
    for n,name in [(ready,"Reconciled invoice lines"),(variance,"Variance review"),
                   (hold,"Quantity or source holds"),(len(consumed),"Recent consumed movements")]:
        body+="<div class='card'><strong class='big'>"+h(n)+"</strong><span class='label'>"+h(name)+"</span></div>"
    body+="</div>"

    body+="<section class='panel'><h2>Supplier invoices and variance review</h2>"
    body+="<p class='sub'>An invoice with excess billed quantities, missing receipts or no source-confirmed"
    body+=" PO price stays on HOLD. Price differences and landed charges require explicit local variance review."
    body+=" Review does not authorize payment or change inventory quantity.</p>"
    report=[{**s,"reasons":", ".join(s["reasons"]),"reviewed_by":s["reviewed_by"] or "",
             "variance":s["material_price_variance"] if s["material_price_variance"] is not None else "Unknown"} for s in states]
    body+=table(report,[("invoice_number","Invoice"),("supplier","Supplier"),("po_number","PO"),
      ("id","Invoice line"),("qty","Billed qty"),("received_qty","Received qty"),
      ("po_unit_price","Agreed unit price"),("billed_unit_price","Actual unit price"),
      ("variance","Material price variance"),("freight","Freight"),("other","Other"),
      ("tax","Tax"),("landed_total","Invoice landed total"),
      ("status","Match status"),("reasons","Reasons"),("reviewed_by","Reviewed by")])
    body+="<h3>Review a price or landed charge variance</h3>"
    body+="<form method='post' action='/purchasing/costs' class='form-grid'>"
    body+="<input type='hidden' name='action' value='review'>"
    body+="<label>Invoice line"+selector("invoice_line_id",states,"id","id")+"</label>"
    body+="<label>Variance explanation<input name='reason' maxlength='500' required></label>"
    body+="<button>Record local variance review</button></form></section>"

    body+="<section class='panel'><h2>Capture actual agreed PO price</h2>"
    body+="<p class='sub'>A current supplier offer is not necessarily the price the buyer agreed to."
    body+=" Record the ordered price and a PO confirmation source once. Historical baselines cannot be overwritten.</p>"
    body+="<form method='post' action='/purchasing/costs' class='form-grid'>"
    body+="<input type='hidden' name='action' value='po_price'>"
    body+="<label>PO line<select name='line_id' required><option value=''>Select</option>"
    body+="".join("<option value='"+h(l["id"])+"'>"+h(l["po_number"])+
                " / "+h(l["item_number"])+" / "+h(l["unit"])+"</option>" for l in polines)
    body+="</select></label>"
    body+="<label>Agreed USD price per stocking unit<input name='unit_price' type='number' min='.0001' step='.0001' required></label>"
    body+="<label>Optional matching source quote"+selector("quote_id",quotes,"id","id",optional=True)+"</label>"
    body+="<label>PO confirmation reference<input name='source_ref' required maxlength='250'></label>"
    body+="<button>Save immutable PO price</button></form>"
    body+=table(baselines,[("po_number","PO"),("item_number","Material"),("supplier","Supplier"),
       ("unit","Stocking unit"),("unit_price","Agreed USD/unit"),("source_ref","Evidence"),
       ("supplier_quote_id","Supplier quote")])+"</section>"

    body+="<section class='panel'><h2>Enter actual supplier invoice</h2>"
    body+="<p class='sub'>One-line invoices can be entered directly. For multi-line invoices, paste a JSON array"
    body+=" with each line's PO line ID, quantity, unit, unit_price, freight, other and tax. Entire"
    body+=" invoice is recorded atomically. Amounts are USD in the exact inventory stocking unit.</p>"
    body+="<form method='post' action='/purchasing/costs' class='form-grid'>"
    body+="<input type='hidden' name='action' value='invoice'>"
    body+="<label>Supplier"+selector("supplier_id",suppliers,"id","name")+"</label>"
    body+="<label>Supplier invoice number<input name='invoice_number' maxlength='120' required></label>"
    body+="<label>Invoice date<input name='invoice_date' type='date' required value='"+h(date.today().isoformat())+"'></label>"
    body+="<label>PO line<select name='po_line_id'><option value=''>For single-line invoice</option>"
    body+="".join("<option value='"+h(l["id"])+"'>"+h(l["po_number"])+"/"+
                    h(l["item_number"])+" / "+h(l["unit"])+"</option>" for l in polines)
    body+="</select></label>"
    for name,label,default in [("quantity","Billed qty",""),("unit","Stocking unit (ea, sheet, lb, kg, ft, m)",""),
                              ("unit_price","Actual unit price USD",""),("freight","Freight USD","0"),
                              ("other","Other charges USD","0"),("tax","Tax USD","0")]:
        body+="<label>"+h(label)+"<input name='"+h(name)+"' value='"+h(default)+"'></label>"
    body+="<label>Invoice source reference<input name='source_ref' maxlength='250' required></label>"
    body+="<label>Optional PDF SHA-256<input name='document_sha256' maxlength='64'></label>"
    body+="<label style='min-width:100%'>Advanced multi-line invoice JSON<textarea rows='4' name='lines_json' placeholder='Optional JSON array; overrides single-line inputs'></textarea></label>"
    body+="<button>Record immutable invoice</button></form>"
    body+=table(invoices,[("invoice_number","Invoice"),("supplier","Supplier"),
                         ("invoice_date","Date"),("source_ref","Source reference")])+"</section>"

    body+="<section class='panel'><h2>Assign documented material cost to posted job consumption</h2>"
    body+="<p class='sub'>A job's inventory consumption and its supplier's invoice are different records."
    body+=" Explicitly match the same item and assign quantity from a reconciled invoice."
    body+=" Totals cannot exceed either the consumed movement or billed invoice quantity."
    body+=" Assignment is a documented cost association, NOT a verified physical-lot trace.</p>"
    body+="<form method='post' action='/purchasing/costs' class='form-grid'>"
    body+="<input type='hidden' name='action' value='allocate'>"
    body+="<label>Job consumption<select name='consumption_key' required><option value=''>Select</option>"
    body+="".join("<option value='"+h(m["movement_key"])+"'>"+h(m["job_number"])+
                  " / "+h(m["item_number"])+" / "+h(m["quantity"])+"</option>" for m in consumed)
    body+="</select></label>"
    body+="<label>Reconciled invoice line"+selector("invoice_line_id",states,"id","id")+"</label>"
    body+="<label>Assigned qty<input name='quantity' min='.0001' step='.0001' type='number' required></label>"
    body+="<label>Assignment evidence<input name='source_ref' maxlength='250' required></label>"
    body+="<button>Associate actual material cost</button></form>"
    jobcost=[{"job":j["job_number"],**costs.job_material_costs(j["id"])} for j in jobs]
    body+=table(jobcost,[("job","Job"),("documented_consumption_cost","Documented consumption cost"),
                        ("limitations","Coverage limitation")])
    body+="<p class='sub'>Partial documented material costs do not represent complete COGS or job profitability."
    body+=" Unassigned/legacy stock and incomplete invoice evidence remain explicitly uncosted.</p></section>"
    return page("Purchasing Cost Reconciliation",body,module_key="purchasing")
