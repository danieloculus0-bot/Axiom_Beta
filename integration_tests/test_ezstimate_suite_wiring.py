"""Real controlled-PDF, EZstimate, Axiom quoting and BEAN wiring."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for n in ("forgevault-src","ezstimate-src","ezfair-src","bean-core"):
    if not (ROOT/n).is_dir():raise RuntimeError("missing real repo "+n)
    sys.path.insert(0,str(ROOT/n))
sys.path.insert(0,str(ROOT/"forgevault-src"/"backend"))
import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from forgevault.config import settings
from forgevault.database import Base
from forgevault.services.metadata import create_record
from forgevault.services.versioning import append_version_bytes
from forgevault.services.lifecycle import transition_record
from forgevault.services.fai_handoff import released_pdf_handoff
from ezstimate.engine import inspect_document, price_quote
from ezstimate.bean import local_review,journal
from controlled_handoff import inspect_released_pdf

def test_real_estimate_and_erp(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"local_vault_root",str(tmp_path/"vault_objects"))
    engine=create_engine("sqlite+pysqlite:///"+str(tmp_path/"vault.db"))
    Base.metadata.create_all(engine)
    drawing=fitz.open()
    page=drawing.new_page(width=600,height=800)
    page.insert_text((80,95),"WIDTH 20.00")
    page.insert_text((340,615),"MATERIAL: ASTM A36")
    page.insert_text((340,640),"PART NO: EZ-500")
    page.insert_text((340,665),"REV: C")
    pdf=drawing.tobytes();drawing.close()
    with Session(engine,expire_on_commit=False) as session:
        record=create_record(session,customer_part_number="EZ-500",
                             customer_revision="C",internal_revision="03",
                             metadata={},actor="fixture")
        ver=append_version_bytes(session,record=record,filename="EZ-500.pdf",
                                 original_source_path="fixture/EZ-500.pdf",content=pdf,
                                 customer_revision="C",internal_revision="03",metadata={},
                                 actor="fixture",mime_type="application/pdf")
        session.flush()
        with pytest.raises(ValueError,match="Released"):
            released_pdf_handoff(session,record_id=record.internal_record_id,version_id=str(ver.id))
        transition_record(session,record=record,to_state_name="Review",actor="fixture")
        session.flush();session.expire(record,["lifecycle_state"])
        transition_record(session,record=record,to_state_name="Released",actor="fixture")
        session.flush();session.expire(record,["lifecycle_state"])
        manifest,content=released_pdf_handoff(session,record_id=record.internal_record_id,
                                               version_id=str(ver.id))
        session.commit()
    engine.dispose()
    assert hashlib.sha256(content).hexdigest()==manifest["sha256"]
    extracted=inspect_document("EZ-500.pdf",content)
    assert extracted["fields"]["material"]["value"]=="ASTM A36"
    inputs={"part_number":"EZ-500","quantity":4,"material_cost_each":10,
            "labor_hours_each":0.5,"shop_rate_per_hour":60,"outside_cost_each":5,
            "setup_cost_total":20,"scrap_pct":10,"margin_pct":20}
    quote=price_quote({"lines":[inputs]})
    assert quote["total"]=="255.00"
    proposal={"schema":"ezstimate.quote_proposal.v1","source_system":"EZstimate",
              "status":"review_required","quote_number":"EZ-Q-500",
              "source_drawing":manifest,"documents":[extracted],
              "lines":[inputs],"pricing":quote}
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"axiom"))
    from superforge.app import create_app
    from superforge.db import db
    from superforge.integrations.ezstimate_quote import import_ezstimate_quote
    app=create_app({"TESTING":True})
    receipt=import_ezstimate_quote(proposal,pdf_bytes=content,actor="fixture")
    assert receipt["status"]=="review_required"
    assert import_ezstimate_quote(proposal,pdf_bytes=content,actor="fixture")["idempotent"]
    with db() as con:
        item=con.execute("SELECT * FROM quote_intakes WHERE id=?",(receipt["quote_id"],)).fetchone()
        link=con.execute("SELECT * FROM ezstimate_quote_evidence WHERE quote_intake_id=?",(receipt["quote_id"],)).fetchone()
        assert item["status"]=="review_required"
        assert item["estimated_value"]==255
        assert link["source_version_id"]==manifest["file_version_id"]
        assert link["drawing_sha256"]==manifest["sha256"]
    # Join FAI and estimating from the identical released PDF bytes and identity.
    from superforge.integrations.controlled_fai import import_controlled_fai
    fai_proposal = inspect_released_pdf(manifest, content)
    assert fai_proposal["status"] == "review_required"
    assert fai_proposal["characteristic_count"] > 0
    fai_receipt = import_controlled_fai(
        fai_proposal, content, fai_number="FAI-EZ-500", actor="fixture"
    )
    assert fai_receipt["status"] == "review_required"
    assert import_controlled_fai(
        fai_proposal, content, fai_number="FAI-EZ-500", actor="fixture"
    )["idempotent"]
    with db() as con:
        fai = con.execute(
            "SELECT * FROM fai_runs WHERE id=?", (fai_receipt["id"],)
        ).fetchone()
        fai_link = con.execute(
            "SELECT * FROM fai_source_links WHERE fai_run_id=?", (fai_receipt["id"],)
        ).fetchone()
        quote_link = con.execute(
            "SELECT * FROM ezstimate_quote_evidence WHERE quote_intake_id=?", (receipt["quote_id"],)
        ).fetchone()
        assert fai["status"] == "review_required"
        assert fai["pass_count"] == 0 and fai["fail_count"] == 0
        assert fai_link["pdf_sha256"] == quote_link["drawing_sha256"] == manifest["sha256"]
        assert quote_link["source_version_id"] == manifest["file_version_id"]
        assert fai["drawing_revision"] == manifest["customer_revision"]

    receipt_dir = os.environ.get("AXIOM_JOINED_RECEIPT_DIR")
    if receipt_dir:
        evidence_path = Path(receipt_dir)
        evidence_path.mkdir(parents=True, exist_ok=True)
        def git_head(folder):
            return subprocess.check_output(
                ["git", "-C", str(ROOT / folder), "rev-parse", "HEAD"],
                text=True,
            ).strip()
        joined = {
            "evidence_kind": "synthetic_cross_repository_contract_test",
            "production_deployment": False,
            "source_pdf_sha256": manifest["sha256"],
            "source_file_version_id": manifest["file_version_id"],
            "source_revision": manifest["customer_revision"],
            "quote_id": receipt["quote_id"],
            "quote_status": receipt["status"],
            "quote_value": quote["total"],
            "fai_id": fai_receipt["id"],
            "fai_status": fai_receipt["status"],
            "fai_characteristic_count": fai_proposal["characteristic_count"],
            "fai_measured_passes": fai["pass_count"],
            "component_commits": {
                "ForgeVault": git_head("forgevault-src"),
                "EZstimate": git_head("ezstimate-src"),
                "EZ-FAIR": git_head("ezfair-src"),
                "BEAN": git_head("bean-core"),
                "Axiom": subprocess.check_output(
                    ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
                ).strip(),
            },
        }
        assert joined["quote_status"] == joined["fai_status"] == "review_required"
        (evidence_path / "receipt.json").write_text(
            json.dumps(joined, sort_keys=True, indent=2), encoding="utf-8"
        )

    html=app.test_client().get("/quoting")
    assert html.status_code==200
    assert b"EZ-Q-500" in html.data
    assert manifest["file_version_id"].encode() in html.data
    with pytest.raises(ValueError,match="checksum"):
        import_ezstimate_quote(proposal,pdf_bytes=content+b"tamper",actor="fixture")
    bad=json.loads(json.dumps(proposal));bad["pricing"]["total"]="999.00"
    with pytest.raises(ValueError,match="recomputed"):
        import_ezstimate_quote(bad,pdf_bytes=content,actor="fixture")
    # Real BEAN persistence, not a simulated autonomous review.
    monkeypatch.setenv("EZSTIMATE_BEAN_DB",str(tmp_path/"bean.db"))
    advice=local_review([extracted],quote)
    assert advice["bean_core_invoked"] is False
    bean_receipt=journal([extracted],quote,advice)
    assert bean_receipt["connected"] and bean_receipt["bean_core_invoked"]



def test_real_ezstimate_pr_to_axiom_local_draft(tmp_path,monkeypatch):
    """Actual EZstimate canonical DB PR, staged into real Axiom stock tables."""
    from ezstimate.procurement import create_request
    from superforge.modules.purchasing import set_policy,import_ezstimate_request
    from superforge.app import create_app
    from superforge.db import db
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"axiom-pr"))
    create_app({"TESTING":True})
    with db() as con:
        con.execute("INSERT INTO jobs(job_number) VALUES('WO-REAL-PR')")
        con.execute("INSERT INTO inventory_items(item_number,on_hand) VALUES('AL-6061',4)")
    with db() as con:
        item=con.execute("SELECT id FROM inventory_items WHERE item_number='AL-6061'").fetchone()[0]
    set_policy(item,"sheet",2,12,7,1)
    body={
        "requested_by":"Fixture buyer","department":"Purchasing",
        "justification":"Machine job planned material shortage",
        "lines":[{"material_key":"AL-6061","description":"Aluminum plate",
                  "quantity":"5","unit":"sheet","needed_by":"2026-11-01",
                  "job":"WO-REAL-PR","supplier_preference":"Supplier A",
                  "source_ref":"EZstimate material forecast case 1"}]
    }
    saved=create_request(body,path=tmp_path/"ezstimate-pr.sqlite3")["request"]
    result=import_ezstimate_request(saved,actor="cross-repo-fixture")
    assert result["duplicate"] is False
    assert import_ezstimate_request(saved,actor="cross-repo-fixture")["duplicate"] is True
    with db() as con:
        pr=con.execute("SELECT * FROM procurement_requisitions WHERE id=?",
                       (result["requisitions"][0],)).fetchone()
        assert pr["status"]=="draft"
        assert pr["quantity"]==5
        assert pr["unit"]=="sheet"
        assert pr["source_request_id"]==saved["request_id"]
        assert pr["needed_by"]=="2026-11-01"
        assert pr["supplier_preference"]=="Supplier A"
        assert con.execute("SELECT COUNT(*) FROM purchase_order_lines").fetchone()[0]==0
    tampered=json.loads(json.dumps(saved))
    tampered["payload"]["lines"][0]["quantity"]="999"
    with pytest.raises(ValueError,match="digest"):
        import_ezstimate_request(tampered)
    wrong_unit=create_request({**body,"lines":[{**body["lines"][0],"unit":"lb"}]},
                  path=tmp_path/"ezstimate-pr.sqlite3")["request"]
    with pytest.raises(ValueError,match="unit mismatch"):
        import_ezstimate_request(wrong_unit)
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM procurement_requisitions").fetchone()[0]==1



def test_real_axiom_invoice_cost_to_ezstimate_price_memory(tmp_path,monkeypatch):
    """End-to-end cross-repo price evidence: receipt, three-way match, stage, adopt."""
    from datetime import date
    from decimal import Decimal
    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.purchasing import (
        set_policy,create_requisition,approve_requisition,attach_to_po,receive
    )
    from superforge.modules.cost_reconciliation import (
        record_po_price,record_vendor_invoice,review_invoice_line,
        reconcile_invoice,estimator_price_feedback
    )
    from ezstimate.axiom_cost_feedback import (
        stage_axiom_cost_feedback,actual_cost_inbox,adopt_axiom_cost
    )
    from ezstimate.pricing import price_history

    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"axiom_cost_bridge"))
    create_app({"TESTING":True})
    with db() as con:
        supplier=con.execute(
           "INSERT INTO suppliers(name) VALUES('Cross Repo Metals')").lastrowid
        item=con.execute(
           "INSERT INTO inventory_items(item_number,on_hand) VALUES('SHT-AL-6061',0)").lastrowid
        job=con.execute(
           "INSERT INTO jobs(job_number) VALUES('WO-XREPO-10')").lastrowid
        po=con.execute("""INSERT INTO purchase_orders
          (po_number,supplier_id,job_id,order_date,status)
          VALUES('PO-XREPO',?,?,?,'open')""",
          (supplier,job,date.today().isoformat())).lastrowid
    set_policy(item,"sheet",1,10,4,1)
    request=create_requisition(item,5,"xrepo-invoice-request",job_id=job)
    approve_requisition(request["id"])
    line=attach_to_po(request["id"],po)["line_id"]
    record_po_price(line,"22.50","Signed purchase order for aluminum")
    receive(line,5,"xrepo-delivery",received_on=date.today().isoformat())
    inv=record_vendor_invoice(supplier,"INV-XREPO",date.today().isoformat(),[
        {"po_line_id":line,"quantity":"5","unit":"sheet",
         "unit_price":"23.50","freight":"5","other":"0","tax":"0"}
    ],"Vendor invoice PDF reference")
    pending=reconcile_invoice(inv["invoice_id"])
    assert pending["status"]=="VARIANCE_REVIEW"
    invoice_line_id=pending["lines"][0]["id"]
    review_invoice_line(invoice_line_id,"Accepted documented price difference and freight")
    assert reconcile_invoice(inv["invoice_id"])["status"]=="RECONCILED"
    feed=estimator_price_feedback()
    assert feed["schema"]=="axiom.actual_material_cost_feedback.v1"
    assert len(feed["observations"])==1
    assert Decimal(feed["observations"][0]["invoiced_qty"])==Decimal("5")
    ez_db=tmp_path/"ez_actual_prices.db"
    assert stage_axiom_cost_feedback(feed,path=ez_db)["staged"]==1
    assert stage_axiom_cost_feedback(feed,path=ez_db)["staged"]==0
    assert actual_cost_inbox(path=ez_db)[0]["status"]=="pending"
    assert price_history("SHT-AL-6061","sheet",
                         as_of=date.today().isoformat(),path=ez_db)["candidate"] is None
    adopt_axiom_cost("AXIOM-INVOICE-LINE-"+str(invoice_line_id),
                     "fixture purchasing reviewer",path=ez_db)
    price=price_history("SHT-AL-6061","sheet",
                        as_of=date.today().isoformat(),path=ez_db)["candidate"]
    assert price["source_type"]=="invoice"
    assert price["unit_price"]=="23.50"
    assert Decimal(price["quantity"])==Decimal("5")
    assert "24.5" in price["notes"]  # all-in USD 122.50 for five sheets
    assert price["source_ref"]=="AXIOM-INVOICE-LINE-"+str(invoice_line_id)
