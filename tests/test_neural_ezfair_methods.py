"""Synthetic EZ FAIR to EZ Methods to Planning event handoff.

No drawing is parsed again, no released route is edited and no real data is used.
"""
from __future__ import annotations

import json

from superforge.app import create_app
from superforge.db import db
from superforge.event_bus import publish
from superforge.integrations.controlled_methods import link_controlled_drawing_to_method
from superforge.modules.ez_methods import create_method_plan


def _seed(tmp_path,monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"axiom"))
    create_app({"TESTING":True})
    source={
        "record_id":"SYN-VAULT-01","file_version_id":"SYN-VERSION-01",
        "release_package_number":"SYN-RELEASE-01","sha256":"a"*64,
        "customer_part_number":"SYN-PART-01","customer_revision":"B",
    }
    uri="forgevault://"+source["record_id"]+"/"+source["file_version_id"]
    with db() as con:
        doc=con.execute(
            "INSERT INTO documents(document_number,title,revision,status,storage_reference,sha256) VALUES(?,?,?,?,?,?)",
            ("SYN-DRAWING-01","Fictional bracket","B","Released",uri,source["sha256"]),
        ).lastrowid
        con.execute(
            "INSERT INTO document_versions(document_id,version_number,revision,storage_reference,sha256) VALUES(?,?,?,?,?)",
            (doc,1,"B",uri,source["sha256"]),
        )
        fai=con.execute(
            "INSERT INTO fai_runs(fai_number,drawing_document_id,drawing_revision,status,characteristic_count) VALUES(?,?,?,?,?)",
            ("SYN-FAI-01",doc,"B","review_required",1),
        ).lastrowid
        con.execute(
            "INSERT INTO fai_source_links(fai_run_id,vault_record_id,vault_version_id,release_package_number,pdf_sha256,payload_sha256) VALUES(?,?,?,?,?,?)",
            (fai,source["record_id"],source["file_version_id"],source["release_package_number"],source["sha256"],"b"*64),
        )
        con.execute(
            "INSERT INTO fai_characteristics(fai_run_id,char_number,reference_location,raw_text,nominal,lsl,usl,characteristic_type) VALUES(?,?,?,?,?,?,?,?)",
            (fai,1,"P1-R1C1","WIDTH 20.00",20.0,19.98,20.02,"LINEAR"),
        )
    plan=create_method_plan(
        {"job_number":"SYN-JOB-01","part_number":"SYN-PART-01",
         "revision":"B","quantity":2,"required_date":"2026-12-01"},
        actor="synthetic-tester",
    )
    return source,plan,fai


def test_controlled_fai_link_fires_one_planning_review_without_mutation(tmp_path,monkeypatch):
    source,plan,fai=_seed(tmp_path,monkeypatch)
    first=link_controlled_drawing_to_method(plan,source,actor="synthetic-tester")
    assert first["idempotent"] is False
    with db() as con:
        actions=con.execute(
            "SELECT * FROM workflow_actions WHERE workflow_key='controlled-fai-evidence'"
        ).fetchall()
        assert len(actions)==1
        action=dict(actions[0])
        assert action["target_module"]=="planning"
        assert action["entity_type"]=="method_source"
        assert action["entity_id"]==str(first["source_id"])
        assert action["status"]=="open"
        evidence=json.loads(action["input_json"])
        assert evidence["contract_version"]==1
        assert evidence["plan_id"]==plan and evidence["fai_run_id"]==fai
        assert evidence["drawing_revision"]=="B"
        assert evidence["characteristic_count"]==1
        assert evidence["drawing_sha256"]==source["sha256"]
        assert evidence["review_state"]=="REVIEW_REQUIRED"
        event=con.execute(
            "SELECT * FROM event_ledger WHERE event_type='methods.source.linked'"
        ).fetchone()
        assert event is not None and event["status"]=="delivered"
        receipt=con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key LIKE '%_methods_source_linked'",
            (event["event_id"],),
        ).fetchone()
        assert receipt is not None and receipt["status"]=="delivered"
        assert con.execute("SELECT status FROM ezm_method_plans WHERE id=?",(plan,)).fetchone()["status"]=="DRAFT"
        assert con.execute("SELECT status FROM fai_runs WHERE id=?",(fai,)).fetchone()["status"]=="review_required"
    again=link_controlled_drawing_to_method(plan,source,actor="synthetic-tester")
    assert again["idempotent"] is True
    publish("methods.source.linked",source_module="methods",entity_type="method_source",
            entity_id=str(first["source_id"]),actor="synthetic-tester",
            payload={"plan_id":plan,"file_version_id":source["file_version_id"],
                     "drawing_sha256":source["sha256"]})
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-fai-evidence'"
        ).fetchone()[0]==1


def test_mismatched_provenance_or_revision_cannot_create_planning_review(tmp_path,monkeypatch):
    source,plan,fai=_seed(tmp_path,monkeypatch)
    uri="forgevault://"+source["record_id"]+"/"+source["file_version_id"]
    note=json.dumps({"file_version_id":source["file_version_id"],
                     "release_package":source["release_package_number"],
                     "sha256":source["sha256"]},sort_keys=True)
    with db() as con:
        source_id=con.execute(
            "INSERT INTO ezm_sources(plan_id,source_type,document_number,revision,location,note) VALUES(?,'CONTROLLED_DRAWING',?,?,?,?)",
            (plan,source["record_id"],"B",uri,note),
        ).lastrowid
    def emit(digest):
        publish("methods.source.linked",source_module="methods",
                entity_type="method_source",entity_id=str(source_id),
                actor="synthetic-tester",
                payload={"plan_id":plan,"file_version_id":source["file_version_id"],
                         "drawing_sha256":digest})
    emit("f"*64)
    with db() as con:
        con.execute("UPDATE ezm_method_plans SET revision='C' WHERE id=?",(plan,))
    emit(source["sha256"])
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-fai-evidence'"
        ).fetchone()[0]==0
        con.execute("UPDATE ezm_method_plans SET revision='B' WHERE id=?",(plan,))
        # Two FAI runs claiming the same source are ambiguous: do not choose one.
        other=con.execute(
            "INSERT INTO fai_runs(fai_number,drawing_document_id,drawing_revision,status,characteristic_count) SELECT 'SYN-FAI-02',drawing_document_id,drawing_revision,status,characteristic_count FROM fai_runs WHERE id=?",
            (fai,),
        ).lastrowid
        con.execute(
            "INSERT INTO fai_source_links(fai_run_id,vault_record_id,vault_version_id,release_package_number,pdf_sha256,payload_sha256) VALUES(?,?,?,?,?,?)",
            (other,source["record_id"],source["file_version_id"],source["release_package_number"],source["sha256"],"c"*64),
        )
    emit(source["sha256"])
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-fai-evidence'"
        ).fetchone()[0]==0


def test_drifted_document_or_exact_version_hash_blocks_planning_review(tmp_path,monkeypatch):
    """The event consumer must revalidate controlled evidence after link-time."""
    for changed_table in ("documents","document_versions"):
        case_dir=tmp_path/changed_table
        source,plan,fai=_seed(case_dir,monkeypatch)
        uri="forgevault://"+source["record_id"]+"/"+source["file_version_id"]
        note=json.dumps({"file_version_id":source["file_version_id"],
                         "release_package":source["release_package_number"],
                         "sha256":source["sha256"]},sort_keys=True)
        with db() as con:
            source_id=con.execute(
                "INSERT INTO ezm_sources(plan_id,source_type,document_number,revision,location,note) "
                "VALUES(?,'CONTROLLED_DRAWING',?,?,?,?)",
                (plan,source["record_id"],"B",uri,note),
            ).lastrowid
            doc_id=con.execute(
                "SELECT drawing_document_id FROM fai_runs WHERE id=?",(fai,)
            ).fetchone()[0]
            if changed_table=="documents":
                con.execute("UPDATE documents SET sha256=? WHERE id=?",("c"*64,doc_id))
            else:
                con.execute(
                    "UPDATE document_versions SET sha256=? WHERE document_id=? AND storage_reference=?",
                    ("c"*64,doc_id,uri),
                )
        publish("methods.source.linked",source_module="methods",
                entity_type="method_source",entity_id=str(source_id),
                actor="synthetic-tester",
                payload={"plan_id":plan,"file_version_id":source["file_version_id"],
                         "drawing_sha256":source["sha256"]})
        with db() as con:
            assert con.execute(
                "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-fai-evidence'"
            ).fetchone()[0]==0
            assert con.execute(
                "SELECT status FROM ezm_method_plans WHERE id=?",(plan,)
            ).fetchone()[0]=="DRAFT"
            assert con.execute(
                "SELECT status FROM fai_runs WHERE id=?",(fai,)
            ).fetchone()[0]=="review_required"
            assert con.execute(
                "SELECT pdf_sha256 FROM fai_source_links WHERE fai_run_id=?",(fai,)
            ).fetchone()[0]==source["sha256"]


def _import_next_synthetic_fai_version():
    """Use the existing EZ FAIR import producer, not a fabricated bus-only event."""
    import hashlib
    from superforge.integrations.controlled_fai import import_controlled_fai

    pdf=b"%PDF-1.4\nfictional revision C\n%%EOF\n"
    digest=hashlib.sha256(pdf).hexdigest()
    source={
        "record_id":"SYN-VAULT-01", "file_version_id":"SYN-VERSION-02",
        "release_package_number":"SYN-RELEASE-02",
        "customer_part_number":"SYN-PART-01", "customer_revision":"C",
        "internal_revision":"C", "filename":"synthetic-drawing.pdf",
        "sha256":digest, "byte_size":len(pdf), "version_number":2,
    }
    payload={
        "schema":"ezfair.inspection_handoff.v1", "status":"review_required",
        "source_drawing":source, "characteristic_count":1,
        "characteristics":[{
            "char_number":1, "reference_location":"P1-R1C1",
            "raw_text":"WIDTH 21.00", "nominal":21.0,
            "lsl":20.98, "usl":21.02, "characteristic_type":"LINEAR",
        }],
    }
    imported=import_controlled_fai(payload,pdf,fai_number="SYN-FAI-REV-C",actor="synthetic-tester")
    return imported,digest


def test_new_controlled_fai_revision_flags_existing_methods_without_release(tmp_path,monkeypatch):
    source,plan,old_fai=_seed(tmp_path,monkeypatch)
    linked=link_controlled_drawing_to_method(plan,source,actor="synthetic-tester")
    imported,digest=_import_next_synthetic_fai_version()
    with db() as con:
        actions=con.execute(
            "SELECT * FROM workflow_actions WHERE workflow_key='controlled-drawing-revision-review'"
        ).fetchall()
        assert len(actions)==1
        action=dict(actions[0])
        assert action["target_module"]=="planning" and action["status"]=="open"
        assert action["entity_type"]=="fai" and action["entity_id"]==str(imported["id"])
        evidence=json.loads(action["input_json"])
        assert evidence["contract_version"]==1
        assert evidence["new_revision"]=="C"
        assert evidence["new_file_version_id"]=="SYN-VERSION-02"
        assert evidence["new_sha256"]==digest
        assert evidence["review_state"]=="REVIEW_REQUIRED"
        assert evidence["affected_methods"]==[{
            "plan_id":plan,"method_source_id":linked["source_id"],
            "part_number":"SYN-PART-01","previous_revision":"B",
            "previous_file_version_id":"SYN-VERSION-01","previous_sha256":source["sha256"],
        }]
        event=con.execute(
            "SELECT event_id,status FROM event_ledger WHERE event_type='fai.imported' AND entity_id=?",
            (str(imported["id"]),),
        ).fetchone()
        assert event and event["status"]=="delivered"
        receipt=con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key LIKE '%review_controlled_fai_revision'",
            (event["event_id"],),
        ).fetchone()
        assert receipt and receipt["status"]=="delivered"
        assert con.execute("SELECT status FROM ezm_method_plans WHERE id=?",(plan,)).fetchone()[0]=="DRAFT"
        assert con.execute("SELECT status FROM fai_runs WHERE id=?",(old_fai,)).fetchone()[0]=="review_required"
        assert con.execute("SELECT status FROM fai_runs WHERE id=?",(imported["id"],)).fetchone()[0]=="review_required"
    publish(
        "fai.imported",source_module="ezfair",entity_type="fai",
        entity_id=str(imported["id"]),actor="synthetic-tester",
        payload={"vault_version":"SYN-VERSION-02","drawing_sha256":digest,
                 "inspection_status":"review_required"},
    )
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-drawing-revision-review'"
        ).fetchone()[0]==1


def test_revision_consumer_rejects_unlinked_and_forged_evidence(tmp_path,monkeypatch):
    source,plan,_=_seed(tmp_path,monkeypatch)
    imported,digest=_import_next_synthetic_fai_version()
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-drawing-revision-review'"
        ).fetchone()[0]==0
    link_controlled_drawing_to_method(plan,source,actor="synthetic-tester")
    publish(
        "fai.imported",source_module="ezfair",entity_type="fai",
        entity_id=str(imported["id"]),actor="synthetic-tester",
        payload={"vault_version":"SYN-VERSION-02","drawing_sha256":"f"*64,
                 "inspection_status":"review_required"},
    )
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='controlled-drawing-revision-review'"
        ).fetchone()[0]==0
        assert con.execute("SELECT status FROM ezm_method_plans WHERE id=?",(plan,)).fetchone()[0]=="DRAFT"
