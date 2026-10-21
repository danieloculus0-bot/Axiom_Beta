"""Real Axiom supplier price, promised vs actual and cross-module procurement tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


def setup_shop(tmp_path,monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"supplier-shop"))
    from superforge.app import create_app
    from superforge.db import db
    app=create_app({"TESTING":True})
    with db() as con:
        a=con.execute("INSERT INTO suppliers(name) VALUES('Supplier Alpha')").lastrowid
        b=con.execute("INSERT INTO suppliers(name) VALUES('Supplier Bravo')").lastrowid
        item=con.execute("""INSERT INTO inventory_items(item_number,on_hand,allocated)
                            VALUES('MAT-01',4,0)""").lastrowid
        job=con.execute("INSERT INTO jobs(job_number) VALUES('WO-SUPPLIER')").lastrowid
        po=con.execute("""INSERT INTO purchase_orders
            (po_number,job_id,supplier_id,status,order_date,expected_date)
            VALUES('PO-SUPPLIER',?,?,'open',?,?)""",
            (job,a,(date.today()-timedelta(days=10)).isoformat(),
             (date.today()-timedelta(days=2)).isoformat())).lastrowid
    from superforge.modules.purchasing import set_policy
    set_policy(item,"sheet",10,40,7,5)
    return app,db,a,b,item,job,po


def test_immutable_supplier_quote_history_and_ranked_minimum_packs(tmp_path,monkeypatch):
    app,db,a,b,item,job,po=setup_shop(tmp_path,monkeypatch)
    from superforge.modules.supplier_intelligence import (
        record_supplier_price,latest_offers,recommend_suppliers,supplier_price_history
    )
    today=date.today()
    old=record_supplier_price(a,item,"12.50","sheet",min_order_qty=1,order_multiple=1,
         quoted_lead_days=2,source_ref="Supplier Alpha old quote",
         quoted_on=(today-timedelta(days=8)).isoformat())
    new=record_supplier_price(a,item,"14.75","sheet",min_order_qty=10,order_multiple=5,
         quoted_lead_days=2,source_ref="Supplier Alpha revised quote",
         quoted_on=(today-timedelta(days=1)).isoformat())
    faster=record_supplier_price(b,item,"17.25","sheet",min_order_qty=5,
         order_multiple=5,quoted_lead_days=1,source_ref="Supplier Bravo quote")
    assert len(supplier_price_history(item))==3
    offers=latest_offers(item)
    assert {x["id"] for x in offers}=={new["id"],faster["id"]}
    assert old["id"] not in {x["id"] for x in offers}
    candidates=recommend_suppliers(item,6,
                (today+timedelta(days=3)).isoformat())
    assert [x["supplier_id"] for x in candidates]==[a,b]
    assert candidates[0]["purchase_qty"]=="1E+1" or candidates[0]["purchase_qty"]=="10"
    assert candidates[0]["extended_usd"]=="147.50"
    assert candidates[0]["latest_order_by"]==(today+timedelta(days=1)).isoformat()
    assert candidates[0]["sample_count"]==0
    assert candidates[0]["reliability"]=="insufficient samples"
    with pytest.raises(ValueError,match="stocking unit"):
        record_supplier_price(a,item,"5","lb",source_ref="invalid unit")
    with pytest.raises(ValueError,match="finite"):
        record_supplier_price(a,item,"nan","sheet",source_ref="invalid price")
    with pytest.raises(ValueError,match="at most 4"):
        record_supplier_price(a,item,"1.123456","sheet",source_ref="bad precision")
    with pytest.raises(ValueError,match="required"):
        record_supplier_price(a,item,"15","sheet",source_ref="")
    # Once latest quote expires, the older quote must not reappear.
    record_supplier_price(a,item,"13.20","sheet",source_ref="short-lived",
        quoted_on=(today-timedelta(days=1)).isoformat(),
        valid_until=(today-timedelta(days=1)).isoformat())
    assert {x["supplier_id"] for x in latest_offers(item)}=={b}
    assert app.test_client().get("/purchasing/suppliers").status_code==200


def test_dated_partial_receipts_original_promise_and_revisions(tmp_path,monkeypatch):
    app,db,a,b,item,job,po=setup_shop(tmp_path,monkeypatch)
    from superforge.modules.purchasing import (
        create_requisition,approve_requisition,attach_to_po,receive,purchasing_snapshot
    )
    from superforge.modules.supplier_intelligence import (
        record_supplier_promise,supplier_performance,supplier_promise_history
    )
    today=date.today()
    req=create_requisition(item,10,"supplier-req-1",job_id=job)
    approve_requisition(req["id"])
    line=attach_to_po(req["id"],po)["line_id"]
    # An internal PO expected date alone is NOT evidence that the supplier
    # ever promised that date: require an explicit confirmation record.
    assert supplier_promise_history(line)==[]
    record_supplier_promise(line,(today-timedelta(days=2)).isoformat(),
                            source_ref="Supplier original confirmation")
    hist=supplier_promise_history(line)
    assert hist[0]["promised_on"]==(today-timedelta(days=2)).isoformat()
    # Later changing the promise does not erase the original lateness.
    assert record_supplier_promise(line,(today+timedelta(days=4)).isoformat(),
                                   source_ref="Supplier revised confirmation")["new"]
    assert not record_supplier_promise(line,(today+timedelta(days=4)).isoformat(),
                                       source_ref="Repeat")["new"]
    assert len(supplier_promise_history(line))==2
    assert purchasing_snapshot()[0]["inbound_due_in_lead"]==10
    first=receive(line,4,"receipt-first",
                  received_on=(today-timedelta(days=1)).isoformat())
    assert first["received_on"]==(today-timedelta(days=1)).isoformat()
    # Partial receipt never counts as a complete, on-time delivery.
    before=supplier_performance(a)[0]
    assert before["complete_lines"]==0
    assert before["promise_samples"]==0
    assert receive(line,4,"receipt-first")["duplicate"]
    with pytest.raises(ValueError,match="different delivery date"):
        receive(line,4,"receipt-first",received_on=today.isoformat())
    receive(line,6,"receipt-final",received_on=today.isoformat())
    perf=supplier_performance(a)[0]
    assert perf["complete_lines"]==1
    assert perf["promise_samples"]==1
    assert perf["on_time_lines"]==0
    assert perf["on_time_pct"]==0
    assert perf["median_actual_lead_days"]==10
    assert perf["revised_promise_lines"]==1
    assert perf["reliability"]=="insufficient samples"
    with db() as con:
        # Legacy PO headers are editable, but historical supplier/lead scoring
        # must not be silently reassigned to a new supplier or order date.
        con.execute("UPDATE purchase_orders SET supplier_id=?,order_date=? WHERE id=?",
                    (b,(today-timedelta(days=1)).isoformat(),po))
    assert supplier_performance(a)[0]["median_actual_lead_days"]==10
    assert supplier_performance(b)[0]["complete_lines"]==0
    with pytest.raises(ValueError,match="after full receipt"):
        record_supplier_promise(line,(today+timedelta(days=9)).isoformat(),
                                source_ref="too late")
    assert purchasing_snapshot()[0]["inbound"]==0
    # Restart still retains original promise, arrival dates and unit-price records.
    from superforge.app import create_app
    again=create_app({"TESTING":True})
    assert again.test_client().get("/purchasing/suppliers").status_code==200
    assert supplier_performance(a)[0]["on_time_pct"]==0


def test_competing_supplier_leads_override_cheapest_late_offer(tmp_path,monkeypatch):
    app,db,a,b,item,job,po=setup_shop(tmp_path,monkeypatch)
    from superforge.modules.purchasing import create_requisition
    from superforge.modules.supplier_intelligence import (
        record_supplier_price,recommend_suppliers,supplier_suggestions
    )
    today=date.today()
    record_supplier_price(a,item,"2.00","sheet",quoted_lead_days=14,
                          source_ref="Alpha cheaper but later")
    record_supplier_price(b,item,"4.00","sheet",quoted_lead_days=2,
                          source_ref="Bravo more expensive but on time")
    needed=(today+timedelta(days=5)).isoformat()
    candidates=recommend_suppliers(item,25,needed)
    assert candidates[0]["supplier_id"]==b
    assert candidates[0]["timing"]=="ON_TIME"
    assert candidates[1]["supplier_id"]==a
    assert candidates[1]["timing"]=="LATE"
    create_requisition(item,25,"supplier-compare-pr",job_id=job,needed_by=needed)
    proposals=supplier_suggestions()
    assert proposals and proposals[0]["earliest_need_by"]==needed
    assert proposals[0]["best"]["supplier_id"]==b
    html=app.test_client().get("/purchasing/suppliers").get_data(as_text=True)
    assert "Supplier Prices" in html
    assert "Supplier Bravo" in html
    assert "Promised versus actual" in html


def test_supplier_workbench_persists_quote_and_promise_and_validates_receipt(tmp_path,monkeypatch):
    app,db,a,b,item,job,po=setup_shop(tmp_path,monkeypatch)
    from superforge.modules.purchasing import (
        create_requisition,approve_requisition,attach_to_po
    )
    client=app.test_client()
    data={"action":"quote","supplier_id":str(a),"item_id":str(item),
          "unit_price":"18.25","unit":"sheet","min_order_qty":"2",
          "order_multiple":"2","quoted_lead_days":"3",
          "quoted_on":date.today().isoformat(),"source_ref":"QUOTE-101"}
    assert client.post("/purchasing/suppliers",data=data).status_code==302
    assert client.post("/purchasing/suppliers",data={**data,"unit":"lb"}).status_code==400
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM supplier_price_history").fetchone()[0]==1
    req=create_requisition(item,10,"quote-po",job_id=job)
    approve_requisition(req["id"])
    line=attach_to_po(req["id"],po)["line_id"]
    assert client.post("/purchasing/suppliers",data={
        "action":"promise","po_line_id":str(line),
        "promised_on":date.today().isoformat(),"source_ref":"PO-CONFIRM"}).status_code==302
    invalid_date=(date.today()+timedelta(days=1)).isoformat()
    assert client.post("/purchasing",data={"action":"receive",
        "line_id":str(line),"quantity":"1","movement_key":"must-not-receive-future",
        "received_on":invalid_date}).status_code==400
    with db() as con:
        assert con.execute("SELECT received_qty FROM purchase_order_lines WHERE id=?",
                           (line,)).fetchone()[0]==0
