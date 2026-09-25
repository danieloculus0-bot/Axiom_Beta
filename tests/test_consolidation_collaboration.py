from __future__ import annotations


def test_module_collaboration_and_delivery_receipts(tmp_path,monkeypatch):
    monkeypatch.setenv("SUPERFORGE_DATA_DIR",str(tmp_path/"data"))
    from superforge.app import create_app
    from superforge.db import db
    from superforge.event_bus import publish, subscribe
    from superforge.modules.collaboration import accept_suggestion, open_suggestions

    create_app({"TESTING":True})
    delivered=[]
    def bad_handler(event):
        raise RuntimeError("intentional subscriber failure")
    def good_handler(event):
        delivered.append(event.event_id)
    subscribe("test.collaboration.delivery",bad_handler)
    subscribe("test.collaboration.delivery",good_handler)
    event=publish("test.collaboration.delivery",source_module="test",entity_type="job",entity_id="77",actor="tester",payload={"ok":True})
    assert delivered==[event.event_id]
    with db() as con:
        ledger=con.execute("SELECT status FROM event_ledger WHERE event_id=?",(event.event_id,)).fetchone()
        receipts=con.execute("SELECT status FROM event_delivery_receipts WHERE event_id=?",(event.event_id,)).fetchall()
    assert ledger["status"]=="partial_failure"
    assert {row["status"] for row in receipts}>={"failed","delivered"}

    vault_event=publish("vault.document.created",source_module="vault",entity_type="document",entity_id="15",actor="tester",payload={"document_number":"DWG-100","revision":"C","document_type":"drawing","part_id":4,"job_id":9})
    linked=[s for s in open_suggestions() if s["source_event_id"]==vault_event.event_id]
    assert {"ezfair","ez_methods"}.issubset({s["target_module"] for s in linked})
    suggestion=next(s for s in linked if s["target_module"]=="ez_methods")
    action_id=accept_suggestion(int(suggestion["id"]),actor="planner",assigned_to="Methods")
    with db() as con:
        action=con.execute("SELECT * FROM workflow_actions WHERE id=?",(action_id,)).fetchone()
        reviewed=con.execute("SELECT * FROM module_suggestions WHERE id=?",(suggestion["id"],)).fetchone()
    assert action["target_module"]=="ez_methods"
    assert action["assigned_to"]=="Methods"
    assert reviewed["status"]=="accepted"


def test_core_mutations_publish_collaboration_events(tmp_path,monkeypatch):
    monkeypatch.setenv("SUPERFORGE_DATA_DIR",str(tmp_path/"data2"))
    from superforge.app import create_app
    from superforge.db import db
    app=create_app({"TESTING":True})
    client=app.test_client()

    assert client.post("/jobs",data={"job_number":"WO-COLLAB","quantity":"5"}).status_code in {302,303}
    assert client.post("/purchase-orders",data={"po_number":"PO-COLLAB","job_id":"1","required_date":"2026-10-01"}).status_code in {302,303}
    assert client.post("/inventory",data={"item_number":"MAT-COLLAB","on_hand":"0","allocated":"0","reorder_point":"1"}).status_code in {302,303}
    assert client.post("/pm",data={"machine_number":"M-100","name":"Test Mill","department":"Machining","criticality":"high"}).status_code in {302,303}
    assert client.post("/vault",data={"document_number":"DWG-COLLAB","title":"Test Drawing","revision":"A","document_type":"drawing","job_id":"1"}).status_code in {302,303}
    assert client.post("/suppliers",data={"name":"Supplier Collaboration Test","code":"SCT"}).status_code in {302,303}

    with db() as con:
        event_types={r["event_type"] for r in con.execute("SELECT event_type FROM event_ledger").fetchall()}
        suggestion_count=con.execute("SELECT COUNT(*) n FROM module_suggestions").fetchone()["n"]
    assert {"po.created","inventory.item.created","inventory.shortage","pm.machine.created","vault.document.created","supplier.created"}.issubset(event_types)
    assert suggestion_count>=6
    payload=client.get("/api/collaboration/suggestions").get_json()
    assert payload["suggestions"]


def test_ezfair_enhancement_layer_imports():
    from superforge.modules.ezfair_enhancements import ExtractionSettings, GDT_SYMBOLS
    settings=ExtractionSettings(enable_ocr_fallback=False)
    assert settings.two_place>0
    assert "⌖" in GDT_SYMBOLS
