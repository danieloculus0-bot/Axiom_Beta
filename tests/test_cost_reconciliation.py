"""Actual material purchasing cost reconciliation tests against shared Axiom SQLite."""
from __future__ import annotations

from datetime import date
import pytest


def scenario(tmp_path,monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"costs"))
    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.purchasing import (
        set_policy,create_requisition,approve_requisition,attach_to_po
    )
    app=create_app({"TESTING":True})
    with db() as con:
        supplier=con.execute("INSERT INTO suppliers(name) VALUES('Supplier Actual')").lastrowid
        other=con.execute("INSERT INTO suppliers(name) VALUES('Supplier Other')").lastrowid
        item=con.execute("INSERT INTO inventory_items(item_number,on_hand) VALUES('STOCK-CR',3)").lastrowid
        another=con.execute("INSERT INTO inventory_items(item_number,on_hand) VALUES('STOCK-OTHER',0)").lastrowid
        job=con.execute("INSERT INTO jobs(job_number) VALUES('WO-COST')").lastrowid
        order=con.execute("""INSERT INTO purchase_orders(po_number,supplier_id,job_id,status,order_date)
                   VALUES('PO-COST',?,?,'open',?)""",(supplier,job,date.today().isoformat())).lastrowid
    set_policy(item,"sheet",2,10,7,1)
    set_policy(another,"ea",0,5,7,1)
    def add_line(item_id,unit,qty,key):
        req=create_requisition(item_id,qty,key,job_id=job)
        approve_requisition(req["id"])
        return attach_to_po(req["id"],order)["line_id"]
    line=add_line(item,"sheet",10,"requisition-1")
    other_line=add_line(another,"ea",2,"requisition-2")
    return app,db,supplier,other,item,another,job,order,line,other_line


def record_invoice(c,supplier,line,*,number="BILL-101",qty="10",price="14",
                   freight="5",other="3",tax="2",unit="sheet",source="vendor-email"):
    return c.record_vendor_invoice(supplier,number,date.today().isoformat(),
        [{"po_line_id":line,"quantity":qty,"unit":unit,"unit_price":price,
          "freight":freight,"other":other,"tax":tax}],source)


def test_three_way_match_holds_and_variance_review(tmp_path,monkeypatch):
    app,db,supplier,other,item,another,job,po,line,other_line=scenario(tmp_path,monkeypatch)
    from superforge.modules import cost_reconciliation as c
    from superforge.modules.purchasing import receive
    from superforge.modules.supplier_intelligence import record_supplier_price

    quote=record_supplier_price(supplier,item,"12","sheet",source_ref="Vendor quotation")
    with pytest.raises(ValueError,match="differs"):
        c.record_po_price(line,"13","PO agreement",supplier_quote_id=quote["id"])
    baseline=c.record_po_price(line,"12","Signed PO",supplier_quote_id=quote["id"])
    assert baseline["unit_price_usd"]=="12"
    with pytest.raises(ValueError,match="immutable"):
        c.record_po_price(line,"15","Amended PO without process")
    with pytest.raises(ValueError,match="source does not match"):
        c.record_po_price(other_line,"12","Wrong item",supplier_quote_id=quote["id"])
    with pytest.raises(ValueError,match="supplier"):
        record_invoice(c,other,line)

    saved=record_invoice(c,supplier,line)
    assert saved["duplicate"] is False
    assert record_invoice(c,supplier,line)["duplicate"] is True
    with pytest.raises(ValueError,match="different evidence"):
        record_invoice(c,supplier,line,price="14.01")
    assert c.reconcile_invoice(saved["invoice_id"])["status"]=="HOLD"
    pending=c.reconcile_invoice(saved["invoice_id"])["lines"][0]
    assert "NOT_YET_RECEIVED" in pending["reasons"]
    with pytest.raises(ValueError,match="Cannot review"):
        c.review_invoice_line(pending["id"],"Approve ahead of receipt")
    # Partial goods receiving does not silently clear invoice hold.
    receive(line,4,"receipt-s1")
    assert c.reconcile_invoice(saved["invoice_id"])["status"]=="HOLD"
    receive(line,6,"receipt-s2")
    result=c.reconcile_invoice(saved["invoice_id"])
    assert result["status"]=="VARIANCE_REVIEW"
    state=result["lines"][0]
    assert state["po_expected_total"]=="120.00"
    assert state["material_total"]=="140.00"
    assert state["material_price_variance"]=="20.00"
    assert state["landed_total"]=="150.00"
    assert state["freight"]=="5.00"
    assert state["other"]=="3.00"
    assert state["tax"]=="2.00"
    assert set(state["reasons"])=={"PRICE_VARIANCE","LANDED_CHARGES"}
    c.review_invoice_line(state["id"],"Verified supplier surcharge and price revision")
    assert c.reconcile_invoice(saved["invoice_id"])["status"]=="RECONCILED"
    assert c.review_invoice_line(state["id"],"Already reviewed")["duplicate"] is True
    # Unlike receiving, reviewing an invoice never changes stock or posts to the GL.
    with db() as con:
        assert con.execute("SELECT on_hand FROM inventory_items WHERE id=?",(item,)).fetchone()[0]==13
        assert con.execute("SELECT COUNT(*) FROM finance_journals").fetchone()[0]==0


def test_quantity_overbilling_and_atomic_multi_line_invoices(tmp_path,monkeypatch):
    app,db,supplier,other,item,another,job,po,line,other_line=scenario(tmp_path,monkeypatch)
    from superforge.modules import cost_reconciliation as c
    from superforge.modules.purchasing import receive
    c.record_po_price(line,"10","PO price")
    c.record_po_price(other_line,"2.50","Other PO price")
    receive(line,10,"rec-l1")
    receive(other_line,2,"rec-l2")
    multi=c.record_vendor_invoice(supplier,"TWO-LINES",date.today().isoformat(),[
        {"po_line_id":line,"quantity":"6","unit":"sheet","unit_price":"10"},
        {"po_line_id":other_line,"quantity":"2","unit":"ea","unit_price":"2.50"}
    ],"Two-line actual invoice")
    assert c.reconcile_invoice(multi["invoice_id"])["status"]=="RECONCILED"
    with pytest.raises(ValueError,match="Duplicate PO line"):
        c.record_vendor_invoice(supplier,"BAD-1",date.today().isoformat(),[
          {"po_line_id":line,"quantity":"2","unit":"sheet","unit_price":"10"},
          {"po_line_id":line,"quantity":"1","unit":"sheet","unit_price":"10"}],"bad")
    with pytest.raises(ValueError,match="stocking unit"):
        c.record_vendor_invoice(supplier,"BAD-2",date.today().isoformat(),[
          {"po_line_id":line,"quantity":"1","unit":"sheet","unit_price":"10"},
          {"po_line_id":other_line,"quantity":"1","unit":"sheet","unit_price":"2.50"}],"bad")
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM vendor_invoices").fetchone()[0]==1
    second=record_invoice(c,supplier,line,number="BILL-SECOND",qty="5",price="10",
                          freight="0",other="0",tax="0")
    status=c.reconcile_invoice(second["invoice_id"])["status"]
    assert status=="HOLD"
    with pytest.raises(ValueError,match="Cannot review"):
        c.review_invoice_line(c.reconcile_invoice(second["invoice_id"])["lines"][0]["id"],
                              "Try to pass overbilling")
    assert "OVER_ORDERED_QTY" in c.reconcile_invoice(multi["invoice_id"])["lines"][0]["reasons"]


def test_job_consumption_cost_attribution_and_estimator_feedback(tmp_path,monkeypatch):
    app,db,supplier,other,item,another,job,po,line,other_line=scenario(tmp_path,monkeypatch)
    from superforge.modules import cost_reconciliation as c
    from superforge.modules.purchasing import receive,consume
    c.record_po_price(line,"9","Verified PO")
    receive(line,10,"arrival")
    saved=record_invoice(c,supplier,line,number="MATCHED",price="9",
             freight="10",other="0",tax="0")
    line_id=c.reconcile_invoice(saved["invoice_id"])["lines"][0]["id"]
    assert c.reconcile_invoice(saved["invoice_id"])["status"]=="VARIANCE_REVIEW"
    c.review_invoice_line(line_id,"Approved freight allocation")
    consume(item,4,"WO-COST-ISSUE-1",job_id=job)
    first=c.assign_consumption_cost("WO-COST-ISSUE-1",line_id,4,"Material traveler")
    assert first["duplicate"] is False
    assert c.assign_consumption_cost("WO-COST-ISSUE-1",line_id,4,"Material traveler")["duplicate"]
    with pytest.raises(ValueError,match="conflicts"):
        c.assign_consumption_cost("WO-COST-ISSUE-1",line_id,3,"Changed qty")
    jobcost=c.job_material_costs(job)
    assert jobcost["documented_consumption_cost"]=="40.00"
    assert jobcost["unreconciled_cost_links"]==0
    assert len(jobcost["links"])==1
    assert jobcost["links"][0]["reconciliation_status"]=="RECONCILED"
    feedback=c.estimator_price_feedback()
    assert feedback["schema"]=="axiom.actual_material_cost_feedback.v1"
    assert feedback["observations"][0]["landed_unit_cost"]=="10"
    assert feedback["observations"][0]["price_memory_status"]=="review_required"
    client=app.test_client()
    assert client.get("/purchasing/costs").status_code==200
    assert client.get("/purchasing/costs/feedback.json").json["observations"]
    passport=client.get(f"/jobs/{job}/passport").get_data(as_text=True)
    assert "Documented actual material costs" in passport
    assert "40.00" in passport
    # Multiple job consumptions cannot claim more than the invoiced stock.
    consume(item,7,"WO-COST-ISSUE-2",job_id=job)
    with pytest.raises(ValueError,match="exceeds invoiced item quantity"):
        c.assign_consumption_cost("WO-COST-ISSUE-2",line_id,7,"Cannot oversubscribe")
    from superforge.app import create_app
    restarted=create_app({"TESTING":True})
    assert restarted.test_client().get("/purchasing/costs").status_code==200
    assert c.job_material_costs(job)["documented_consumption_cost"]=="40.00"


def test_missing_po_price_can_be_added_without_inventing_cost(tmp_path,monkeypatch):
    app,db,supplier,other,item,another,job,po,line,other_line=scenario(tmp_path,monkeypatch)
    from superforge.modules import cost_reconciliation as c
    from superforge.modules.purchasing import receive
    receive(line,10,"all-goods")
    saved=record_invoice(c,supplier,line,number="NO-PO-PRICE",price="5",freight="0",other="0",tax="0")
    state=c.reconcile_invoice(saved["invoice_id"])["lines"][0]
    assert state["status"]=="HOLD"
    assert "MISSING_PO_PRICE" in state["reasons"]
    assert state["material_price_variance"] is None
    assert c.estimator_price_feedback()["observations"]==[]
    c.record_po_price(line,"5","Located signed PO after invoice")
    assert c.reconcile_invoice(saved["invoice_id"])["status"]=="RECONCILED"
    assert len(c.estimator_price_feedback()["observations"])==1
    client=app.test_client()
    invalid=client.post("/purchasing/costs",data={
       "action":"po_price","line_id":str(line),"unit_price":"9","source_ref":"second price"})
    assert invalid.status_code==400
