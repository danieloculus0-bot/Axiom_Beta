"""Purchasing vertical-slice tests against real shared Axiom SQLite tables."""
from __future__ import annotations

import pytest


def initialized(tmp_path,monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"axiom"))
    from superforge.app import create_app
    from superforge.db import db
    app=create_app({"TESTING":True})
    with db() as con:
        job=con.execute("INSERT INTO jobs(job_number,status) VALUES('WO-PUR-1','open')").lastrowid
        other=con.execute("INSERT INTO jobs(job_number,status) VALUES('WO-PUR-2','open')").lastrowid
        stock=con.execute("""INSERT INTO inventory_items
                   (item_number,on_hand,allocated,reorder_point) VALUES('AL-6061',20,0,5)""").lastrowid
        po=con.execute("""INSERT INTO purchase_orders(po_number,job_id,status)
                          VALUES('PO-PUR-1',?,'open')""",(job,)).lastrowid
        other_po=con.execute("""INSERT INTO purchase_orders(po_number,job_id,status)
                                VALUES('PO-OTHER',?,'open')""",(other,)).lastrowid
        plan=con.execute("""INSERT INTO ezm_method_plans
          (job_id,job_number,part_number,revision,quantity,required_date,status)
          VALUES(?,?,?, ?,?,?,?)""",
          (job,"WO-PUR-1","BRACKET-42","C",10,"2026-11-01","DRAFT")).lastrowid
        op=con.execute("""INSERT INTO ezm_operations
          (plan_id,sequence,work_center,operation,scheduled_date,instruction)
          VALUES(?,10,'Mill','Rough machine','2026-10-27','Setup and mill')""",(plan,)).lastrowid
        dependency=con.execute("""INSERT INTO ezm_dependencies
          (operation_id,dependency_key,kind,description,required_qty,need_by)
          VALUES(?,'D-MAT','MATERIAL','6061 aluminum',16,'2026-10-26')""",(op,)).lastrowid
    return app,db,job,other,stock,po,other_po,dependency


def test_min_max_job_consumption_method_and_reservations(tmp_path,monkeypatch):
    app,db,job,other,stock,po,other_po,dependency=initialized(tmp_path,monkeypatch)
    from superforge.modules.purchasing import (
        set_policy,reserve_for_job,link_method_demand,consume,purchasing_snapshot,
        method_stock_signals,
    )
    from superforge.modules.ez_methods import method_dashboard

    set_policy(stock,"sheet",10,40,"0",5)
    link_method_demand(dependency,stock,16)
    state=purchasing_snapshot()[0]
    assert state["stock_position"]==4
    assert state["suggested_qty"]==40
    assert state["method_unreserved_demand"]==16
    assert state["signal"]=="REORDER"
    assert method_stock_signals()[dependency]["status"]=="STOCK SIGNAL ONLY"

    reserve_for_job(stock,job,10)
    reserve_for_job(stock,job,10) # absolute reservation: not additive
    with db() as con:
        assert con.execute("SELECT allocated FROM inventory_items WHERE id=?",(stock,)).fetchone()[0]==10
    with pytest.raises(ValueError,match="Insufficient unallocated"):
        reserve_for_job(stock,other,11)
    assert purchasing_snapshot()[0]["stock_position"]==4

    posted=consume(stock,6,"issue-unique-1",job_id=job)
    assert posted["duplicate"] is False
    assert consume(stock,6,"issue-unique-1",job_id=job)["duplicate"] is True
    with pytest.raises(ValueError,match="conflicting"):
        consume(stock,7,"issue-unique-1",job_id=job)
    with db() as con:
        item=con.execute("SELECT on_hand,allocated FROM inventory_items WHERE id=?",(stock,)).fetchone()
        assert (item["on_hand"],item["allocated"])==(14,4)
        outstanding=con.execute("""SELECT required_qty,fulfilled_qty FROM procurement_method_links
                       WHERE dependency_id=?""",(dependency,)).fetchone()
        assert (outstanding["required_qty"],outstanding["fulfilled_qty"])==(16,6)
        assert con.execute("""SELECT COUNT(*) FROM inventory_transactions
                            WHERE item_id=? AND txn_type='consumption'""",(stock,)).fetchone()[0]==1
    assert purchasing_snapshot()[0]["method_unreserved_demand"]==6
    assert purchasing_snapshot()[0]["projected"]==4
    assert method_stock_signals()[dependency]["required"]==10
    _,rows=method_dashboard("job",str(job))
    assert rows[0]["procurement_item"]=="AL-6061"
    assert rows[0]["procurement_signal"]=="STOCK SIGNAL ONLY"

    with pytest.raises(ValueError,match="exceeds available"):
        consume(stock,11,"issue-too-much",job_id=other)
    with pytest.raises(ValueError,match="Stocking unit cannot change"):
        set_policy(stock,"lb",10,40,0,5)
    # The browser page really binds to the same records and doesn't create sample data.
    client=app.test_client()
    assert client.get("/purchasing").status_code==200
    html=client.get("/purchasing").get_data(as_text=True)
    assert "AL-6061" in html and "REORDER" in html
    assert "Material & Purchasing Intelligence" in html
    assert client.get(f"/jobs/{job}/passport").status_code==200


def test_local_requisition_po_receipt_and_replay(tmp_path,monkeypatch):
    app,db,job,other,stock,po,other_po,dependency=initialized(tmp_path,monkeypatch)
    from superforge.modules.purchasing import (
        set_policy,create_requisition,approve_requisition,attach_to_po,receive,purchasing_snapshot
    )
    set_policy(stock,"sheet",8,40,5,5)
    first=create_requisition(stock,15,"request:abc",job_id=job)
    assert first["status"]=="draft"
    assert create_requisition(stock,15,"request:abc",job_id=job)["duplicate"]
    with pytest.raises(ValueError,match="conflicts"):
        create_requisition(stock,16,"request:abc",job_id=job)
    with pytest.raises(ValueError,match="approved"):
        attach_to_po(first["id"],po)
    with pytest.raises(ValueError,match="draft requisition"):
        # Here the first approval is fine; the second one is not.
        approve_requisition(first["id"])
        approve_requisition(first["id"])

    with pytest.raises(ValueError,match="different job"):
        attach_to_po(first["id"],other_po)

    linked=attach_to_po(first["id"],po)
    assert linked["duplicate"] is False
    assert attach_to_po(first["id"],po)["duplicate"] is True
    assert purchasing_snapshot()[0]["inbound"]==15
    with pytest.raises(ValueError,match="different PO"):
        attach_to_po(first["id"],other_po)

    received=receive(linked["line_id"],7,"delivery:001")
    assert received["duplicate"] is False
    assert receive(linked["line_id"],7,"delivery:001")["duplicate"] is True
    with pytest.raises(ValueError,match="conflicting"):
        receive(linked["line_id"],8,"delivery:001")
    with pytest.raises(ValueError,match="exceeds outstanding"):
        receive(linked["line_id"],9,"overdelivery")
    with db() as con:
        record=con.execute("SELECT on_hand FROM inventory_items WHERE id=?",(stock,)).fetchone()
        assert record["on_hand"]==27
        p=con.execute("SELECT status FROM purchase_orders WHERE id=?",(po,)).fetchone()
        assert p["status"]=="open"
        q=con.execute("SELECT status FROM procurement_requisitions WHERE id=?",(first["id"],)).fetchone()
        assert q["status"]=="ordered"
    receive(linked["line_id"],8,"delivery:002")
    with db() as con:
        assert con.execute("SELECT on_hand FROM inventory_items WHERE id=?",(stock,)).fetchone()[0]==35
        assert con.execute("SELECT status FROM purchase_orders WHERE id=?",(po,)).fetchone()[0]=="received"
        assert con.execute("SELECT status FROM procurement_requisitions WHERE id=?",(first["id"],)).fetchone()[0]=="received"
        assert con.execute("SELECT COUNT(*) FROM inventory_transactions WHERE txn_type='receipt'").fetchone()[0]==2
    assert purchasing_snapshot()[0]["inbound"]==0

    # App restart keeps all transactions, reservations and policy state.
    from superforge.app import create_app
    reloaded=create_app({"TESTING":True})
    assert reloaded.test_client().get("/purchasing").status_code==200
    assert receive(linked["line_id"],7,"delivery:001")["duplicate"] is True
    passport=reloaded.test_client().get(f"/jobs/{job}/passport").get_data(as_text=True)
    assert "Purchasing requisitions" in passport
    assert "Material movements" in passport


def test_policy_validation_and_http_400_do_not_mutate(tmp_path,monkeypatch):
    app,db,job,other,stock,po,other_po,dependency=initialized(tmp_path,monkeypatch)
    from superforge.modules.purchasing import set_policy,create_requisition,link_method_demand
    for unit,lo,hi in [("sheet",-1,5),("sheet",10,5),("evil",0,10),("sheet","nan",5)]:
        with pytest.raises(ValueError):
            set_policy(stock,unit,lo,hi)
    assert app.test_client().post("/purchasing",data={"action":"request","item_id":str(stock),
                                   "quantity":"1","request_key":"early"}).status_code==400
    set_policy(stock,"sheet",8,40)
    with pytest.raises(ValueError,match="at most four"):
        create_requisition(stock,0.123456,"bad-precision")
    with pytest.raises(ValueError,match="not found"):
        link_method_demand(999999,stock,3)
    client=app.test_client()
    assert client.post("/purchasing",data={"action":"request","item_id":str(stock),
        "quantity":"2","request_key":"web-r1"}).status_code==302
    assert client.post("/purchasing",data={"action":"policy","item_id":str(stock),
        "unit":"sheet","minimum":"9","maximum":"40","lead_days":"0","multiple":"5"}).status_code==302
    assert client.get("/methods").status_code==200
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM procurement_requisitions").fetchone()[0]==1
        assert con.execute("SELECT COUNT(*) FROM procurement_method_links").fetchone()[0]==0
