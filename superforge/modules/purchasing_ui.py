"""Local purchasing workbench for Axiom's shared inventory and methods engine."""
from __future__ import annotations

from html import escape
import json
import uuid
from datetime import date

from flask import Blueprint, redirect, request

from ..db import db
from ..ui import page
from . import purchasing as engine

purchasing_blueprint=Blueprint("purchasing_intelligence",__name__)


def h(value):
    return escape("" if value is None else str(value),quote=True)


def form_for(action, controls, button):
    return ("<form method='post' action='/purchasing' class='toolbar'>"
            "<input type='hidden' name='action' value='"+h(action)+"'>"
            +controls+"<button class='secondary'>"+h(button)+"</button></form>")


def select(name, rows, key, label, *, empty="Select"):
    opts="<option value=''>"+h(empty)+"</option>"
    opts+="".join("<option value='"+h(r[key])+"'>"+h(r[label])+"</option>" for r in rows)
    return "<select name='"+h(name)+"' required>"+opts+"</select>"


@purchasing_blueprint.route("/purchasing",methods=["GET","POST"])
def purchasing_workbench():
    if request.method=="POST":
        f=request.form
        actor=(f.get("actor") or "local").strip()[:120] or "local"
        action=f.get("action")
        try:
            if action=="policy":
                engine.set_policy(f.get("item_id"),f.get("unit"),
                    f.get("minimum"),f.get("maximum"),f.get("lead_days") or "0",
                    f.get("multiple") or "1",actor=actor)
            elif action=="reserve":
                engine.reserve_for_job(f.get("item_id"),f.get("job_id"),
                                       f.get("quantity"),actor=actor)
            elif action=="consume":
                engine.consume(f.get("item_id"),f.get("quantity"),f.get("movement_key"),
                               job_id=f.get("job_id") or None,actor=actor)
            elif action=="request":
                engine.create_requisition(f.get("item_id"),f.get("quantity"),
                                          f.get("request_key"),job_id=f.get("job_id") or None,
                                          needed_by=f.get('needed_by') or None,
                                          supplier_preference=f.get('supplier_preference') or '',actor=actor)
            elif action=="approve":
                engine.approve_requisition(f.get("requisition_id"),actor=actor)
            elif action=="attach":
                engine.attach_to_po(f.get("requisition_id"),f.get("purchase_order_id"),actor=actor)
            elif action=="receive":
                engine.receive(f.get("line_id"),f.get("quantity"),f.get("movement_key"),
                               received_on=f.get('received_on') or None,actor=actor)
            elif action=='import_ezstimate':
                try:
                    document=json.loads(f.get('payload_json') or '{}')
                except (TypeError,ValueError) as exc:
                    raise ValueError('EZstimate input must be valid JSON') from exc
                engine.import_ezstimate_request(document,actor=actor)
            elif action=="method":
                engine.link_method_demand(f.get("dependency_id"),f.get("item_id"),f.get("quantity"),actor=actor)
            else:
                raise ValueError("Unknown purchasing action")
        except (ValueError,TypeError) as exc:
            return page("Purchasing input needs correction",
                        "<div class='panel'><h1>Purchasing operation not recorded</h1><p>"
                        +h(exc)+"</p><a class='button secondary' href='/purchasing'>Back to purchasing</a></div>",
                        module_key="purchasing"),400
        return redirect("/purchasing")

    metrics=engine.purchasing_snapshot()
    with db() as con:
        jobs=[dict(r) for r in con.execute("SELECT id,job_number FROM jobs ORDER BY id DESC LIMIT 200")]
        pos=[dict(r) for r in con.execute("""SELECT id,po_number,status FROM purchase_orders
                    WHERE lower(status) NOT IN ('received','cancelled','closed') ORDER BY id DESC LIMIT 200""")]
        reqs=[dict(r) for r in con.execute("""SELECT r.*,i.item_number,j.job_number,
                      l.id as linked_line_id,po.po_number FROM procurement_requisitions r
                      JOIN inventory_items i ON i.id=r.item_id
                      LEFT JOIN jobs j ON j.id=r.job_id
                      LEFT JOIN purchase_order_lines l ON l.requisition_id=r.id
                      LEFT JOIN purchase_orders po ON po.id=l.purchase_order_id
                      ORDER BY r.id DESC LIMIT 150""")]
        po_lines=[dict(r) for r in con.execute("""SELECT l.*,p.po_number,i.item_number
                      FROM purchase_order_lines l JOIN purchase_orders p ON p.id=l.purchase_order_id
                      JOIN inventory_items i ON i.id=l.item_id ORDER BY l.id DESC LIMIT 150""")]
        dep_rows=[dict(r) for r in con.execute("""SELECT d.id,d.description,d.required_qty,d.kind,
                     o.operation,m.job_number
                     FROM ezm_dependencies d JOIN ezm_operations o ON o.id=d.operation_id
                     JOIN ezm_method_plans m ON m.id=o.plan_id
                     WHERE upper(d.kind) IN ('MATERIAL','PURCHASED_PART')
                     ORDER BY d.id DESC LIMIT 100""")]
        link_rows=[dict(r) for r in con.execute("""SELECT d.dependency_id,d.item_id,d.required_qty,
                     i.item_number,e.description
                     FROM procurement_method_links d
                     JOIN inventory_items i ON i.id=d.item_id
                     JOIN ezm_dependencies e ON e.id=d.dependency_id
                     ORDER BY d.dependency_id DESC LIMIT 100""")]

    body="<section class='page-head'><div><p class='eyebrow'>Purchasing / live local database</p>"
    body+="<h1>Material & Purchasing Intelligence</h1><p class='sub'>On-hand, reserved, received, consumed, supplier-inbound and method demand. "
    body+="Only recorded PO lines count as inbound. Forecasts are suggestions, never supplier orders; "
    body+="stocking units are explicit and unit conversions are not guessed.</p></div>"
    body+="<a class='button secondary' href='/purchase-orders'>Purchase Orders</a>"
    body+="<a class='button secondary' href='/purchasing/suppliers'>Supplier Pricing & Delivery</a></section>"

    ready=sum(1 for m in metrics if m["signal"]=="OK")
    alerts=sum(1 for m in metrics if m["signal"] in {'REORDER','EXPEDITE'})
    unknown=sum(1 for m in metrics if m["signal"]=="UNCONFIGURED")
    body+=("<div class='grid'>"
           f"<div class='card'><strong class='big'>{alerts}</strong><span class='label'>Reorder or expedite</span></div>"
           f"<div class='card'><strong class='big'>{ready}</strong><span class='label'>Within policy</span></div>"
           f"<div class='card'><strong class='big'>{unknown}</strong><span class='label'>Missing stocking policy</span></div>"
           f"<div class='card'><strong class='big'>{len(reqs)}</strong><span class='label'>Recorded requisitions</span></div></div>")
    body+="<div class='panel'><h2>Min/max and consumption forecast</h2>"
    body+="<p class='sub'>Position = on-hand minus allocated plus recorded unreceived PO lines minus unreserved method demand. "
    body+="Projected stock counts only POs expected within lead time, then subtracts trailing 30-day consumption rate times lead days. "
    body+="Late or undated inbound is visible but not assumed on time; EXPEDITE signals existing supply that should be reconciled before reordering. "
    body+="Below min, suggest replenishment towards max in purchasing multiples. A suggestion is not a commitment.</p>"
    body+="<div style='overflow:auto'><table><thead><tr><th>Item</th><th>Unit</th><th>On hand</th><th>Reserved</th>"
    body+="<th>Inbound total</th><th>Due in lead</th><th>Method need</th><th>Consumed 30d</th><th>Projected</th><th>Min / Max</th><th>Suggest</th><th>Signal</th><th>Action</th></tr></thead><tbody>"
    for x in metrics:
        body+="<tr><td>"+h(x["item_number"])+"</td><td>"+h(x["stocking_unit"] or "UNSET")+"</td>"
        for field in ("on_hand","allocated","inbound","inbound_due_in_lead","method_unreserved_demand","consumed_30d","projected"):
            body+="<td>"+h(round(x[field],4))+"</td>"
        body+="<td>"+h(x["min_qty"])+ " / "+h(x["max_qty"])+"</td><td>"+h(x["suggested_qty"])+"</td>"
        body+="<td>"+h(x["signal"])+"</td><td>"
        if x["suggested_qty"]>0:
            body+=form_for("request",
                "<input type='hidden' name='item_id' value='"+h(x["id"])+"'>"
                "<input type='hidden' name='quantity' value='"+h(x["suggested_qty"])+"'>"
                "<input type='hidden' name='request_key' value='"+uuid.uuid4().hex+"'>",
                "Draft suggested PR")
        body+="</td></tr>"
    body+="</tbody></table></div></div>"

    body+="<details class='panel'><summary><b>Configure inventory policy</b></summary>"
    body+=form_for("policy",
        "<label>Item"+select("item_id",metrics,"id","item_number")+"</label>"
        "<label>Stocking unit<select name='unit' required>"
        + "".join("<option value='"+u+"'>"+u+"</option>" for u in ("ea","sheet","lb","kg","ft","m"))
        +"</select></label>"
        "<label>Min<input name='minimum' type='number' min='0' step='.0001' required></label>"
        "<label>Max<input name='maximum' type='number' min='0' step='.0001' required></label>"
        "<label>Lead days<input name='lead_days' type='number' min='0' value='0' required></label>"
        "<label>Order multiple<input name='multiple' type='number' min='.0001' step='.0001' value='1' required></label>",
        "Save policy")
    body+="<p class='sub'>Update of a unit with recorded purchasing history is intentionally rejected. "
    body+="Always use a documented conversion instead of silently changing lb into sheet.</p></details>"

    body+="<div class='panel'><h2>Job allocation and consumption</h2>"
    body+="<p class='sub'>Set an absolute reservation for a job. Consuming a reserved quantity decreases both "
    body+="on-hand and that job's reservation. Idempotency references prevent duplicate consumption postings.</p>"
    body+=form_for("reserve",
        "<label>Item"+select("item_id",metrics,"id","item_number")+"</label>"
        "<label>Job"+select("job_id",jobs,"id","job_number")+"</label>"
        "<label>Set reserved qty<input name='quantity' type='number' min='0' step='.0001' required></label>",
        "Set reservation")
    body+=form_for("consume",
        "<label>Item"+select("item_id",metrics,"id","item_number")+"</label>"
        "<label>Job (optional)<select name='job_id'><option value=''>General consumption</option>"
        + "".join("<option value='"+h(j["id"])+"'>"+h(j["job_number"])+"</option>" for j in jobs)
        +"</select></label>"
        "<label>Qty consumed<input name='quantity' type='number' min='.0001' step='.0001' required></label>"
        "<label>Unique transaction ref<input name='movement_key' value='"+uuid.uuid4().hex+"' required></label>",
        "Post consumption")
    body+="</div>"

    body+="<div class='panel'><h2>Purchase requisitions</h2>"
    body+="<p class='sub'>Human-reviewed local drafts. An approval here does not authenticate a user or send an order. "
    body+="Only an approved request can be linked to an existing PO.</p>"
    body+=form_for("request",
       "<label>Item"+select("item_id",metrics,"id","item_number")+"</label>"
       "<label>Job (optional)<select name='job_id'><option value=''>Stock replenishment</option>"
       +"".join("<option value='"+h(j["id"])+"'>"+h(j["job_number"])+"</option>" for j in jobs)
       +"</select></label>"
       "<label>Qty<input name='quantity' type='number' min='.0001' step='.0001' required></label>"
       "<label>Need by<input name='needed_by' type='date'></label>"
       "<label>Supplier preference<input name='supplier_preference' maxlength='200'></label>"
       "<input type='hidden' name='request_key' value='"+uuid.uuid4().hex+"'>",
       "Draft requisition")
    body+="<div style='overflow:auto'><table><thead><tr><th>PR</th><th>Item</th><th>Job</th><th>Qty</th><th>Unit</th><th>Needed by</th><th>Source</th><th>Status</th><th>PO</th><th>Action</th></tr></thead><tbody>"
    for r in reqs:
        body+="<tr><td>PR-"+h(r["id"])+"</td><td>"+h(r["item_number"])+"</td><td>"+h(r["job_number"])+"</td>"
        body+="<td>"+h(r["quantity"])+"</td><td>"+h(r["unit"])+"</td>"
        body+="<td>"+h(r['needed_by'])+"</td><td>"+h(r['source_request_id'] or 'Local')+"</td><td>"+h(r["status"])+"</td>"
        body+="<td>"+h(r["po_number"])+"</td><td>"
        if r["status"]=="draft":
            body+=form_for("approve","<input type='hidden' name='requisition_id' value='"+h(r["id"])+"'>","Approve for local planning")
        elif r["status"]=="approved":
            body+=form_for("attach",
               "<input type='hidden' name='requisition_id' value='"+h(r["id"])+"'>"
               +select("purchase_order_id",pos,"id","po_number"),"Attach to PO")
        body+="</td></tr>"
    body+="</tbody></table></div></div>"

    body+="<details class='panel'><summary><b>Import EZstimate material requisition</b></summary>"
    body+="<p class='sub'>Paste an EZstimate saved PR object or dispatch envelope with request ID, payload and SHA-256. "
    body+="All lines must match Axiom inventory item codes, exact stocking units and known job numbers. "
    body+="Atomic import creates local review-required drafts and never places supplier orders.</p>"
    body+=form_for('import_ezstimate',
       "<label style='min-width:100%'>EZstimate JSON<textarea name='payload_json' rows='6' required "
       "placeholder='Paste source purchase request JSON'></textarea></label>","Import as local drafts")
    body+="</details>"
    body+="<div class='panel'><h2>Purchase order receiving</h2>"
    body+="<p class='sub'>Receipts increment inventory once, reduce PO outstanding quantities and record "
    body+="transaction evidence. Fully received PO lines close their requisitions; a fully received PO closes only when all its linked lines are complete.</p>"
    body+="<div style='overflow:auto'><table><thead><tr><th>PO</th><th>Item</th><th>Ordered</th><th>Received</th><th>Open</th><th>Unit</th><th>Action</th></tr></thead><tbody>"
    for l in po_lines:
        remainder=round(l["ordered_qty"]-l["received_qty"],4)
        body+="<tr><td>"+h(l["po_number"])+"</td><td>"+h(l["item_number"])+"</td><td>"+h(l["ordered_qty"])+"</td>"
        body+="<td>"+h(l["received_qty"])+"</td><td>"+h(remainder)+"</td><td>"+h(l["unit"])+"</td><td>"
        if remainder>0:
            body+=form_for("receive",
               "<input type='hidden' name='line_id' value='"+h(l["id"])+"'>"
               "<input name='quantity' type='number' min='.0001' max='"+h(remainder)+"' step='.0001' value='"+h(remainder)+"' required>"
               "<label>Actual received on<input name='received_on' type='date' value='"+h(date.today().isoformat())+"' required></label>"
               "<input type='hidden' name='movement_key' value='"+uuid.uuid4().hex+"'>",
               "Receive")
        body+="</td></tr>"
    body+="</tbody></table></div></div>"

    body+="<details class='panel'><summary><b>Connect EZ Methods dependencies to stock items</b></summary>"
    body+="<p class='sub'>Only explicitly mapped dependencies count as method demand. A text match on a description "
    body+="never automatically changes inventory. Review the unit and quantity before linking.</p>"
    body+=form_for("method",
       "<label>Methods dependency<select name='dependency_id' required><option value=''>Select dependency</option>"
       +"".join("<option value='"+h(d["id"])+"'>"+h(d["job_number"])+": "+h(d["description"])
                 +" ("+h(d["required_qty"])+")</option>" for d in dep_rows)
       +"</select></label><label>Stock item"+select("item_id",metrics,"id","item_number")+"</label>"
       "<label>Requirement in stocking unit<input name='quantity' type='number' min='.0001' step='.0001' required></label>",
       "Map dependency")
    body+="<div style='overflow:auto'><table><thead><tr><th>Dependency ID</th><th>Description</th><th>Mapped item</th><th>Stocking-unit need</th></tr></thead><tbody>"
    for l in link_rows:
        body+="<tr><td>"+h(l["dependency_id"])+"</td><td>"+h(l["description"])+"</td><td>"+h(l["item_number"])+"</td><td>"+h(l["required_qty"])+"</td></tr>"
    body+="</tbody></table></div></details>"
    return page("Purchasing Intelligence",body,module_key="purchasing")
