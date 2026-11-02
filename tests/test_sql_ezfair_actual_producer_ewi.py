"""Real EZ FAIR controlled-import producer to SQL EWI clocking consumer.

All records, PDF bytes, names and identifiers are wholly fictional.
No remote ERP, Jetson, released route mutation or duplicate parser is involved.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from superforge.db import db
from superforge.event_bus import publish
from superforge.integrations.controlled_fai import import_controlled_fai
from superforge.integrations.controlled_methods import link_controlled_drawing_to_method
from superforge.modules.ez_methods import create_method_plan


def _controlled_source(pdf: bytes, revision: str, version: int) -> dict:
    return {
        "record_id": "SYN-VAULT-ONLY-001",
        "file_version_id": f"SYN-VERSION-{version:02d}",
        "release_package_number": f"SYN-RELEASE-{version:02d}",
        "customer_part_number": "SYN-PLATE-001",
        "customer_revision": revision,
        "internal_revision": revision,
        "filename": f"fictional-{revision}.pdf",
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "byte_size": len(pdf),
        "version_number": version,
    }


def _fai_payload(source: dict) -> dict:
    return {
        "schema": "ezfair.inspection_handoff.v1",
        "status": "review_required",
        "source_drawing": source,
        "characteristic_count": 1,
        "characteristics": [{
            "char_number": 1,
            "reference_location": "SYN-P1-R1",
            "raw_text": "SYNTHETIC WIDTH 20",
            "nominal": 20.0,
            "lsl": 19.9,
            "usl": 20.1,
            "characteristic_type": "LINEAR",
        }],
    }


def test_actual_controlled_fai_import_blocks_sql_ewi_clock_in_and_survives_restart(
    tmp_path, monkeypatch,
):
    """Use the real import and real subscriber, never a fabricated review action."""
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "fictional-db"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    root = tmp_path / "fictional-pdfs"
    root.mkdir()
    monkeypatch.setenv("AXIOM_EWI_DOCUMENT_ROOT", str(root))

    from superforge.app import create_app
    from superforge.modules.ewi import (
        clock_start, clock_stop, packet, save_remote_routes,
    )

    app = create_app({"TESTING": True})
    old_pdf = b"%PDF-1.4\n% fictional source revision A\n%%EOF\n"
    old_source = _controlled_source(old_pdf, "A", 1)
    old_fai = import_controlled_fai(
        _fai_payload(old_source), old_pdf,
        fai_number="SYN-FAI-A", actor="synthetic-test",
    )
    with db() as con:
        part_id = int(con.execute(
            "INSERT INTO parts(part_number,revision) VALUES('SYN-PLATE-001','A')"
        ).lastrowid)
        job_id = int(con.execute(
            """INSERT INTO jobs(job_number,part_id,status)
               VALUES('SYN-WO-001',?,'open')""", (part_id,),
        ).lastrowid)

    plan_id = create_method_plan({
        "job_id": job_id,
        "part_id": part_id,
        "job_number": "SYN-WO-001",
        "part_number": "SYN-PLATE-001",
        "revision": "A",
        "quantity": 1,
        "required_date": "2099-01-01",
    }, actor="synthetic-test")
    linked = link_controlled_drawing_to_method(
        plan_id, old_source, actor="synthetic-test",
    )
    assert linked["idempotent"] is False

    (root / "fictional-A.pdf").write_bytes(old_pdf)
    with db() as con:
        con.execute(
            """INSERT INTO documents
               (document_number,title,revision,document_type,status,
                job_id,part_id,storage_reference,sha256)
               VALUES('SYN-EWI-DWG','Fictional job PDF','A','drawing',
                      'released',?,?,?,?)""",
            (job_id, part_id, "fictional-A.pdf", old_source["sha256"]),
        )
    assert save_remote_routes(job_id, [{
        "step": "10", "operation": "SYN-CUT",
        "work_center": "SYN-CELL", "part_number": "SYN-PLATE-001",
        "external_id": "SYN-ROUTE-10",
    }]) == 1
    assert packet(job_id)["ready"] is True
    active_session = clock_start(
        job_id, "10", "SYN-TECH-OLD", "synthetic-test",
    )

    new_pdf = b"%PDF-1.4\n% fictional source revision B\n%%EOF\n"
    new_source = _controlled_source(new_pdf, "B", 2)
    new_fai = import_controlled_fai(
        _fai_payload(new_source), new_pdf,
        fai_number="SYN-FAI-B", actor="synthetic-test",
    )
    assert new_fai["idempotent"] is False

    with db() as con:
        ledger = con.execute(
            """SELECT event_id,status,entity_type,entity_id
               FROM event_ledger
               WHERE event_type='fai.imported' AND entity_id=?
               ORDER BY id DESC LIMIT 1""",
            (str(new_fai["id"]),),
        ).fetchone()
        assert ledger is not None and ledger["status"] == "delivered"
        assert (ledger["entity_type"], ledger["entity_id"]) == (
            "fai", str(new_fai["id"]),
        )
        receipt = con.execute(
            """SELECT status FROM event_delivery_receipts
               WHERE event_id=? AND handler_key LIKE '%review_controlled_fai_revision'""",
            (ledger["event_id"],),
        ).fetchone()
        assert receipt is not None and receipt["status"] == "delivered"
        actions = con.execute(
            """SELECT * FROM workflow_actions
               WHERE event_id=? AND workflow_key='controlled-drawing-ewi-review'""",
            (ledger["event_id"],),
        ).fetchall()
        assert len(actions) == 1
        action = dict(actions[0])
        assert (action["entity_type"], action["entity_id"], action["target_module"]) == (
            "job", str(job_id), "ewi",
        )
        evidence = json.loads(action["input_json"])
        assert evidence["contract_version"] == 1
        assert evidence["source_event_id"] == ledger["event_id"]
        assert evidence["job_id"] == job_id and evidence["part_id"] == part_id
        assert evidence["previous_fai_run_id"] == old_fai["id"]
        assert evidence["fai_run_id"] == new_fai["id"]
        assert (evidence["previous_revision"], evidence["new_revision"]) == ("A", "B")
        assert evidence["previous_sha256"] == old_source["sha256"]
        assert evidence["new_sha256"] == new_source["sha256"]
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE event_id=? AND workflow_key='controlled-drawing-revision-review'""",
            (ledger["event_id"],),
        ).fetchone()[0] == 1
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE event_id=? AND workflow_key='controlled-drawing-quality-review'""",
            (ledger["event_id"],),
        ).fetchone()[0] == 1
        before = (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )
        assert before == (1, 1)
        assert con.execute(
            "SELECT revision FROM parts WHERE id=?", (part_id,),
        ).fetchone()[0] == "A"
        assert con.execute(
            "SELECT status FROM ezm_method_plans WHERE id=?", (plan_id,),
        ).fetchone()[0] == "DRAFT"

    assert packet(job_id)["ready"] is False
    assert f"revision review action #{action['id']}" in app.test_client().get(
        f"/ewi/jobs/{job_id}"
    ).get_data(as_text=True)
    with pytest.raises(ValueError, match="revision review action"):
        clock_start(job_id, "10", "SYN-TECH-NEW", "synthetic-test")

    # Completing an advisory task is not an independently verified route release.
    with db() as con:
        con.execute(
            """UPDATE workflow_actions
               SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE id=?""",
            (action["id"],),
        )
    create_app({"TESTING": True})
    assert packet(job_id)["ready"] is False
    with pytest.raises(ValueError, match="revision review action"):
        clock_start(job_id, "10", "SYN-TECH-NEW", "synthetic-test")

    repeated = import_controlled_fai(
        _fai_payload(new_source), new_pdf,
        fai_number="SYN-FAI-B", actor="synthetic-test",
    )
    assert repeated["idempotent"] is True
    publish(
        "fai.imported", source_module="ezfair", entity_type="fai",
        entity_id=str(new_fai["id"]), actor="synthetic-test",
        payload={
            "vault_version": new_source["file_version_id"],
            "drawing_sha256": new_source["sha256"],
            "inspection_status": "review_required",
        },
    )
    with db() as con:
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE workflow_key='controlled-drawing-ewi-review'
                 AND entity_id=?""", (str(job_id),),
        ).fetchone()[0] == 1
        assert before == (
            con.execute("SELECT COUNT(*) FROM ewi_clock_sessions").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0],
        )
    # Existing sessions must remain stoppable even while new starts are blocked.
    clock_stop(active_session, "SYN-TECH-OLD", "synthetic-test")
    with db() as con:
        assert con.execute(
            "SELECT ended_utc FROM ewi_clock_sessions WHERE id=?",
            (active_session,),
        ).fetchone()[0] is not None
        assert con.execute(
            "SELECT COUNT(*) FROM ewi_outbox WHERE event_kind='STOP'",
        ).fetchone()[0] == 1
