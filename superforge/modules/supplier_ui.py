"""Supplier history workbench: real Axiom offers, promises and receipt evidence."""
from __future__ import annotations

from datetime import date
from html import escape

from flask import Blueprint, redirect, request

from ..db import db
from ..ui import page
from . import supplier_intelligence as si

supplier_blueprint=Blueprint("supplier_purchasing",__name__)


def _h(v):
    return escape("" if v is None else str(v),quote=True)


def _select(name, rows, field, label):
    return ("<select name='"+_h(name)+"' required><option value=''>Select</option>"
            + "".join("<option value='"+_h(r[field])+"'>"+_h(r[label])+"</option>" for r in rows)
            + "</select>")


def _table(rows, cols):
    head="".join("<th>"+_h(title)+"</th>" for _,title in cols)
    body="".join("<tr>"+"".join("<td>"+_h(r.get(k))+"</td>" for k,_ in cols)+"</tr>" for r in rows)
    return "<div style='overflow:auto'><table><thead><tr>"+head+"</tr></thead><tbody>"+body+"</tbody></table></div>"


@supplier_blueprint.route("/purchasing/suppliers",methods=["GET","POST"])
def supplier_workbench():
    if request.method=="POST":
        action=request.form.get("action")
        f=request.form
        try:
            if action=="quote":
                si.record_supplier_price(
                    f.get("supplier_id"),f.get("item_id"),f.get("unit_price"),f.get("unit"),
                    min_order_qty=f.get("min_order_qty") or "1",
                    order_multiple=f.get("order_multiple") or "1",
                    quoted_lead_days=f.get("quoted_lead_days") or None,
                    quoted_on=f.get("quoted_on") or None,valid_until=f.get("valid_until") or None,
                    source_ref=f.get("source_ref") or "")
            elif action=="promise":
                si.record_supplier_promise(f.get("po_line_id"),f.get("promised_on"),
                                           source_ref=f.get("source_ref") or "")
            else:
                raise ValueError("Unsupported supplier action")
        except (ValueError,TypeError) as exc:
            return page("Supplier input needs correction",
                        "<div class='panel'><h2>Supplier action not recorded</h2><p>"
                        +_h(exc)+"</p><a class='button secondary' href='/purchasing/suppliers'>Back</a></div>",
                        module_key="purchasing"),400
        return redirect("/purchasing/suppliers")

    with db() as con:
        suppliers=[dict(x) for x in con.execute("SELECT id,name FROM suppliers ORDER BY name LIMIT 500")]
        items=[dict(x) for x in con.execute("""SELECT i.id,i.item_number,p.stocking_unit
                    FROM inventory_items i JOIN inventory_policies p ON p.item_id=i.id
                    ORDER BY i.item_number LIMIT 500""")]
        open_lines=[dict(x) for x in con.execute("""SELECT l.id,p.po_number,i.item_number,
                    s.name supplier_name,l.ordered_qty,l.received_qty
                    FROM purchase_order_lines l
                    JOIN purchase_orders p ON p.id=l.purchase_order_id
                    JOIN inventory_items i ON i.id=l.item_id
                    LEFT JOIN suppliers s ON s.id=p.supplier_id
                    WHERE l.received_qty < l.ordered_qty AND
                      lower(p.status) NOT IN ('cancelled','closed','received')
                    ORDER BY l.id DESC LIMIT 200""")]
        drafts=[dict(x) for x in con.execute("""SELECT r.id,r.item_id,r.quantity,
                    r.needed_by,r.status,i.item_number FROM procurement_requisitions r
                    JOIN inventory_items i ON i.id=r.item_id
                    WHERE r.status IN ('draft','approved') ORDER BY r.id DESC LIMIT 50""")]
    quotes=si.supplier_price_history(limit=100)
    stats=si.supplier_performance()
    restocks=si.supplier_suggestions()
    body=("<section class='page-head'><div><p class='eyebrow'>Purchasing / supplier evidence</p>"
          "<h1>Supplier Prices & Delivery Intelligence</h1>"
          "<p class='sub'>Price history is append-only. Compare real sourced quotes and"
          " full-receipt delivery dates against original supplier promises. Supplier"
          " selection is advisory; no supplier order or ERP dispatch occurs here.</p>"
          "</div><a class='button secondary' href='/purchasing'>Inventory & Purchasing</a></section>")

    body+="<div class='panel'><h2>Purchase recommendations from min/max & job demand</h2>"
    body+="<p class='sub'>Only items with an active reorder suggestion appear. Quotes must be current, in"
    body+=" the exact stocking unit, and sourced. Supplier MOQ and pack increments affect actual cost."
    body+=" Ranked first by ability to meet a known date, then price. Insufficient delivery samples"
    body+=" are never presented as a dependable supplier reliability score.</p>"
    proposals=[]
    for p in restocks:
        if p["best"]:
            b=p["best"]
            proposals.append({"item":p["item"],"qty":p["proposed_qty"],
                "need":p["earliest_need_by"] or "Unknown",
                "supplier":b["supplier"],"order_qty":b["purchase_qty"],
                "total":"$"+b["extended_usd"],"eta":b["eta"] or "Unconfirmed",
                "order_by":b["latest_order_by"] or "Unknown",
                "timing":b["timing"],"sample":b["sample_count"],
                "other":", ".join(x["supplier"]+" ($"+x["extended_usd"]+")"
                                 for x in p["options"][1:4])})
        else:
            proposals.append({"item":p["item"],"qty":p["proposed_qty"],"need":p["earliest_need_by"],
                "supplier":"No current sourced quotation","order_qty":"","total":"",
                "eta":"","order_by":"","timing":"REVIEW","sample":"","other":""})
    body+=_table(proposals,[("item","Item"),("qty","Restock qty"),("need","Need by"),
        ("supplier","Ranked supplier"),("order_qty","Buy qty"),("total","Quote total"),
        ("eta","Projected arrival"),("order_by","Order by"),("timing","Timing"),
        ("sample","Promise samples"),("other","Alternatives")])
    if not proposals:
        body+="<p class='sub'>No stock item currently has a new min/max order recommendation.</p>"
    body+="</div>"

    body+="<div class='panel'><h2>Compare suppliers for pending purchase requests</h2>"
    request_rows=[]
    for r in drafts:
        candidates=si.recommend_suppliers(r["item_id"],r["quantity"],r["needed_by"])
        chosen=candidates[0] if candidates else None
        request_rows.append({"pr":"PR-"+str(r["id"]),"item":r["item_number"],
           "qty":r["quantity"],"need":r["needed_by"] or "Unknown",
           "best":chosen["supplier"] if chosen else "No current quote",
           "total":chosen["extended_usd"] if chosen else "",
           "lead":chosen["lead_days"] if chosen else "",
           "timing":chosen["timing"] if chosen else "REVIEW",
           "other":", ".join(x["supplier"] for x in candidates[1:4])})
    body+=_table(request_rows,[("pr","Request"),("item","Stock item"),("qty","Quantity"),
          ("need","Need date"),("best","Best ranked quote"),("total","USD total"),
          ("lead","Estimated days"),("timing","Delivery risk"),("other","Alternatives")])
    body+="<p class='sub'>An Axiom approved PR is still not an accepted supplier PO. The comparison"
    body+=" does not silently change its preferred supplier or ordering quantities.</p></div>"

    body+="<div class='panel'><h2>Record a documented supplier quotation</h2>"
    body+="<form method='post' action='/purchasing/suppliers' class='form-grid'>"
    body+="<input type='hidden' name='action' value='quote'>"
    body+="<label>Supplier"+_select("supplier_id",suppliers,"id","name")+"</label>"
    body+="<label>Stock item"+_select("item_id",items,"id","item_number")+"</label>"
    body+="<label>Stocking unit<select name='unit' required>"
    body+="".join("<option value='"+u+"'>"+u+"</option>" for u in ("ea","sheet","lb","kg","ft","m"))
    body+="</select></label>"
    body+="<label>Price USD / unit<input name='unit_price' type='number' min='.0001' step='.0001' required></label>"
    body+="<label>Minimum order<input name='min_order_qty' type='number' min='.0001' step='.0001' value='1' required></label>"
    body+="<label>Supplier pack multiple<input name='order_multiple' type='number' min='.0001' step='.0001' value='1' required></label>"
    body+="<label>Quoted lead days<input name='quoted_lead_days' type='number' min='0' max='3650' step='1'></label>"
    body+="<label>Quoted on<input name='quoted_on' type='date' value='"+_h(date.today().isoformat())+"' required></label>"
    body+="<label>Valid until<input name='valid_until' type='date'></label>"
    body+="<label>Quote/document reference<input name='source_ref' maxlength='250' required></label>"
    body+="<button>Record supplier price history</button></form>"
    body+="<h3>Recorded quotations</h3>"
    body+=_table(quotes,[("id","Quote ID"),("supplier","Supplier"),("item_number","Item"),
      ("unit_price","Price USD"),("stocking_unit","Unit"),("min_order_qty","MOQ"),
      ("order_multiple","Pack"),("quoted_lead_days","Quoted days"),
      ("quoted_on","Quoted"),("valid_until","Expires"),("source_ref","Source")])
    body+="</div>"

    body+="<div class='panel'><h2>Promised versus actual lead time</h2>"
    body+="<p class='sub'>Only complete PO lines backed by dated receiving movements count."
    body+=" Punctuality compares the final receipt to the FIRST recorded supplier promise."
    body+=" Later promise revisions remain traceable but do not erase a missed commitment."
    body+=" Median actual lead requires both a dated PO and final documented receipt."
    body+=" Fewer than three on-time samples is insufficient evidence for reliability.</p>"
    body+=_table(stats,[("supplier","Supplier"),("complete_lines","Dated completed lines"),
       ("promise_samples","Promise samples"),("on_time_lines","On time"),
       ("on_time_pct","On time %"),("lead_samples","Lead-time samples"),
       ("median_actual_lead_days","Median actual days"),
       ("revised_promise_lines","Revised promises"),("reliability","Confidence")])
    body+="<h3>Record a new or updated supplier promise</h3>"
    body+="<form method='post' action='/purchasing/suppliers' class='form-grid'>"
    body+="<input type='hidden' name='action' value='promise'>"
    body+="<label>Open PO line<select name='po_line_id' required><option value=''>Select PO line</option>"
    body+="".join("<option value='"+_h(l["id"])+"'>"+_h(l["po_number"])+"/"+
                   _h(l["item_number"])+" / "+_h(l["supplier_name"])+
                   " (line "+_h(l["id"])+")</option>" for l in open_lines)
    body+="</select></label>"
    body+="<label>Promised delivery<input name='promised_on' type='date' required></label>"
    body+="<label>Confirmation reference<input name='source_ref' maxlength='250' required></label>"
    body+="<button>Record supplier promise revision</button></form>"
    body+="</div>"
    body+="<p class='sub'>Stock-level calculations and postings remain in"
    body+=" <a href='/purchasing'>Material & Purchasing Intelligence</a>."
    body+=" Historical legacy receipts without explicit arrival dates are not imputed.</p>"
    return page("Supplier Intelligence",body,module_key="purchasing")
