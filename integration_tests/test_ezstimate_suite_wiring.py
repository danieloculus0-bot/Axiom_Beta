"""Real controlled-PDF, EZstimate, Axiom quoting and BEAN wiring."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for n in ("forgevault-src","ezstimate-src","bean-core"):
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

def test_real_estimate_and_erp(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"local_vault_root",str(tmp_path/"vault_objects"))
    engine=create_engine("sqlite+pysqlite:///"+str(tmp_path/"vault.db"))
    Base.metadata.create_all(engine)
    drawing=fitz.open()
    page=drawing.new_page(width=600,height=800)
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
