from __future__ import annotations
import csv
import json
import os
from pathlib import Path

def test_unified_smoke(tmp_path,monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"data"))
    from superforge.app import create_app
    from superforge.audit import verify_journal
    from superforge.db import db
    from superforge.integrations.service import IntegrationService

    app=create_app({"TESTING":True})
    client=app.test_client()

    health=client.get("/health")
    assert health.get_json()["app"]=="Axiom"

    for route in ["/","/jobs","/purchase-orders","/inventory","/clocking-errors","/quality","/pm","/vault","/ez-fair","/methods","/ppap","/quoting","/planning","/suppliers","/integrations","/leadership","/automation","/intelligence","/logic","/audit","/appearance","/health"]:
        response=client.get(route)
        assert response.status_code==200,route

    response=client.post("/jobs",data={"job_number":"WO-1001","quantity":"10","status":"open"},follow_redirects=True)
    assert response.status_code==200
    response=client.post("/purchase-orders",data={"po_number":"PO-1001","job_id":"1","status":"open"},follow_redirects=True)
    assert response.status_code==200
    response=client.post("/inventory",data={"item_number":"MAT-100","on_hand":"5","allocated":"2","reorder_point":"1"},follow_redirects=True)
    assert response.status_code==200
    response=client.post("/clocking-errors",data={"job_id":"1","error_type":"wrong operation","reported_by":"tester","description":"Clocked to wrong operation"},follow_redirects=True)
    assert response.status_code==200

    response=client.post("/quality/new",data={
        "record_type":"NCR","record_number":"NCR-1001","job_id":"1","po_id":"1",
        "quantity_affected":"2","quantity_shipped":"1000","description":"Test nonconformance","actor":"tester",
    },follow_redirects=False)
    assert response.status_code in {302,303}

    with db() as con:
        q=con.execute("SELECT * FROM quality_records WHERE record_number='NCR-1001'").fetchone()
        assert q is not None
        actions=con.execute("SELECT COUNT(*) n FROM workflow_actions WHERE entity_type='quality_record' AND entity_id=?",(str(q["id"]),)).fetchone()["n"]
        assert actions>=2
        ppm=con.execute("SELECT value FROM kpi_snapshots WHERE metric_name='PPM' ORDER BY id DESC LIMIT 1").fetchone()
        assert ppm is not None and round(ppm["value"])==2000

    menu=client.get("/api/context-menu?entity_type=job&entity_id=1&current_module=job_tracker").get_json()
    labels={x["label"] for x in menu["items"]}
    assert "Purchase Order Tracker" in labels
    assert "Inventory Tracker" in labels
    assert "Job Clocking Errors" in labels
    assert "EZ FAIR / FAI" in labels
    assert "EZ Methods / Routings" in labels
    assert "Leadership / Company Pulse" in labels
    assert "Audit Trail" in labels

    source=tmp_path/"jobs.csv"
    with source.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["Job","Status"])
        writer.writeheader(); writer.writerow({"Job":"WO-ERP-1","Status":"open"})
    with db() as con:
        cur=con.execute("INSERT INTO erp_connections(name,erp_type,adapter_type,direction,config_json) VALUES(?,?,?,?,?)",
            ("Test ERP","generic","flatfile","in",json.dumps({"path":str(source),"external_id_field":"Job"})))
        connection_id=cur.lastrowid
        con.execute("INSERT INTO erp_mappings(connection_id,entity_type,external_field,internal_field,transform,direction,required) VALUES(?,?,?,?,?,'in',1)",
            (connection_id,"job","Job","job_number","strip"))
        con.execute("INSERT INTO erp_mappings(connection_id,entity_type,external_field,internal_field,transform,direction,required) VALUES(?,?,?,?,?,'in',0)",
            (connection_id,"job","Status","status","lower"))
    result=IntegrationService().pull(connection_id,"job",actor="tester")
    assert result["applied"]==1
    with db() as con:
        assert con.execute("SELECT id FROM jobs WHERE job_number='WO-ERP-1'").fetchone() is not None
        assert con.execute("SELECT COUNT(*) n FROM integration_runs").fetchone()["n"]>=1

    verdict=verify_journal()
    assert verdict["ok"] is True
    assert verdict["entries"]>=8

def test_ezfair_engine_imports():
    from superforge.modules.ezfair_engine import Characteristic, calculate_tolerance_limits
    lsl,usl=calculate_tolerance_limits(1.0,"1.000","LINEAR","")
    assert lsl<1.0<usl
    c=Characteristic(1,"P1-R1C1",1.0,lsl,usl,"LINEAR",0,(0,0,1,1))
    assert c.to_row()["Char Number"]==1
