"""Real controlled FAI producer to EWI review consumer, interrupted mid-handler.

Only fictional PDF bytes, part/job identifiers and operator references are used.
This tests the existing canonical SQL event ledger, not a second event system.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from superforge.db import db
from superforge.event_bus import deliver_staged
from superforge.integrations import controlled_revision_review
from superforge.integrations.controlled_fai import import_controlled_fai
from superforge.integrations.controlled_methods import link_controlled_drawing_to_method
from superforge.modules.ez_methods import create_method_plan


def _source(pdf: bytes, revision: str, version: int) -> dict:
    return {
        "record_id": "SYN-RECOVERY-VAULT-001",
        "file_version_id": f"SYN-RECOVERY-V{version:02d}",
        "release_package_number": f"SYN-RECOVERY-REL-{version:02d}",
        "customer_part_number": "SYN-RECOVERY-PART-001",
        "customer_revision": revision,
        "internal_revision": revision,
        "filename": f"fictional-recovery-{revision}.pdf",
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "byte_size": len(pdf),
        "version_number": version,
    }


def _payload(source: dict) -> dict:
    return {
        "schema": "ezfair.inspection_handoff.v1",
        "status": "review_required",
        "source_drawing": source,
        "characteristic_count": 1,
        "characteristics": [{
            "char_number": 1, "reference_location": "SYN-C1",
            "raw_text": "FICTIONAL WIDTH 20", "nominal": 20.0,
            "lsl": 19.9, "usl": 20.1, "characteristic_type": "LINEAR",
        }],
    }


@pytest.mark.parametrize("new_revision", ["B", "A"])
def test_partial_fai_handler_failure_replays_ewi_review_after_restart(tmp_path, monkeypatch, new_revision):
    """A failure after Planning/Quality commits must not strand EWI or duplicate actions."""
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "fictional-db"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    root = tmp_path / "fictional-pdfs"
    root.mkdir()
    monkeypatch.setenv("AXIOM_EWI_DOCUMENT_ROOT", str(root))

    from superforge.app import create_app
    from superforge.modules.ewi import clock_start, clock_stop, packet, save_remote_routes
    from superforge.modules import ewi as ewi_module
    from superforge.integrations.ewi_revision_evidence import pending_ewi_revision_event

    create_app({"TESTING": True})
    old_pdf = b"%PDF-1.4\n% fictional revision A\n%%EOF\n"
    old_source = _source(old_pdf, "A", 1)
    old_fai = import_controlled_fai(
        _payload(old_source), old_pdf,
        fai_number="SYN-RECOVERY-FAI-A", actor="synthetic-test",
    )
    with db() as con:
        part_id = int(con.execute(
            "INSERT INTO parts(part_number,revision) VALUES('SYN-RECOVERY-PART-001','A')"
        ).lastrowid)
        job_id = int(con.execute(
            "INSERT INTO jobs(job_number,part_id,status) VALUES('SYN-RECOVERY-JOB-001',?,'open')",
            (part_id,),
        ).lastrowid)

    plan_id = create_method_plan({
        "job_id": job_id, "part_id": part_id,
        "job_number": "SYN-RECOVERY-JOB-001",
        "part_number": "SYN-RECOVERY-PART-001",
        "revision": "A", "quantity": 1, "required_date": "2099-01-01",
    }, actor="synthetic-test")
    assert link_controlled_drawing_to_method(
        plan_id, old_source, actor="synthetic-test",
    )["idempotent"] is False
    (root / "fictional-recovery-A.pdf").write_bytes(old_pdf)
    with db() as con:
        con.execute(
            """INSERT INTO documents
               (document_number,title,revision,document_type,status,
                job_id,part_id,storage_reference,sha256)
               VALUES('SYN-RECOVERY-DWG','Fictional job drawing','A','drawing',
                      'released',?,?,?,?)""",
            (job_id, part_id, "fictional-recovery-A.pdf", old_source["sha256"]),
        )
    assert save_remote_routes(job_id, [{
        "step": "10", "operation": "SYN-OP-10",
        "work_center": "SYN-CELL", "part_number": "SYN-RECOVERY-PART-001",
        "external_id": "SYN-ROUTE-10",
    }]) == 1
    ready_packet = packet(job_id)
    assert ready_packet["ready"] is True
    active_session = clock_start(job_id, "10", "SYN-OPERATOR-OLD", "synthetic-test")

    # The real review subscriber creates Planning and Quality actions first.
    # Inject an interruption only when it reaches its EWI action.
    original_create = controlled_revision_review.create_action
    failures = {"ewi": 0}

    def interrupted_ewi_action(event, **kwargs):
        if kwargs.get("target_module") == "ewi" and failures["ewi"] == 0:
            failures["ewi"] += 1
            raise RuntimeError("fictional EWI handler interruption")
        return original_create(event, **kwargs)

    new_pdf = b"%PDF-1.4\n% fictional changed controlled version V2\n%%EOF\n"
    new_source = _source(new_pdf, new_revision, 2)
    with monkeypatch.context() as patch:
        patch.setattr(controlled_revision_review, "create_action", interrupted_ewi_action)
        new_fai = import_controlled_fai(
            _payload(new_source), new_pdf,
            fai_number="SYN-RECOVERY-FAI-B", actor="synthetic-test",
        )
    assert failures["ewi"] == 1
    assert new_fai["idempotent"] is False

    with db() as con:
        event = con.execute(
            """SELECT event_id,status,entity_id FROM event_ledger
               WHERE event_type='fai.imported' AND entity_id=?""",
            (str(new_fai["id"]),),
        ).fetchone()
        assert event is not None and event["status"] == "partial_failure"
        event_id = event["event_id"]
        receipt = con.execute(
            """SELECT status FROM event_delivery_receipts
               WHERE event_id=? AND handler_key LIKE '%review_controlled_fai_revision'""",
            (event_id,),
        ).fetchone()
        assert receipt is not None and receipt["status"] == "failed"
        assert con.execute(
            "SELECT COUNT(*) FROM fai_source_links WHERE fai_run_id=?",
            (new_fai["id"],),
        ).fetchone()[0] == 1
        before = [dict(row) for row in con.execute(
            """SELECT id,workflow_key,target_module,entity_type,entity_id,input_json
               FROM workflow_actions WHERE event_id=? ORDER BY id""",
            (event_id,),
        )]
        assert {row["target_module"] for row in before} == {"planning", "quality"}
        assert len(before) == 2
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE event_id=? AND target_module='ewi'""",
            (event_id,),
        ).fetchone()[0] == 0
        pending = pending_ewi_revision_event(con, job_id)
        assert pending is not None
        assert (pending["event_id"], pending["delivery_status"]) == (event_id, "partial_failure")
        unrelated_part = con.execute(
            "INSERT INTO parts(part_number,revision) VALUES('SYN-UNRELATED-PART','A')"
        ).lastrowid
        unrelated_job = con.execute(
            "INSERT INTO jobs(job_number,part_id,status) VALUES('SYN-UNRELATED-JOB',?,'open')",
            (unrelated_part,),
        ).lastrowid
        assert pending_ewi_revision_event(con, unrelated_job) is None

    # The real producer committed the revision but EWI's review action is absent.
    # The operator must not be able to start work during this recovery interval.
    blocked = packet(job_id)
    assert blocked["ready"] is False
    assert any(f"EZ FAIR revision event {event_id}" in issue for issue in blocked["issues"])
    with pytest.raises(ValueError, match="EZ FAIR revision event"):
        clock_start(job_id, "10", "SYN-OPERATOR-NEW", "synthetic-test")
    # Simulate a stale operator packet from before the committed event. The
    # BEGIN IMMEDIATE clock-in transaction must independently catch it.
    with monkeypatch.context() as patch:
        patch.setattr(ewi_module, "packet", lambda _job_id: ready_packet)
        with pytest.raises(ValueError, match="EZ FAIR revision event"):
            clock_start(job_id, "10", "SYN-OPERATOR-NEW", "synthetic-test")
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM ewi_clock_sessions WHERE job_id=?", (job_id,)).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0] == 1
        # Exercise the same committed event in the pre-dispatch status. The
        # atomic-import crash test separately proves actual pending durability.
        con.execute("UPDATE event_ledger SET status='pending_delivery' WHERE event_id=?", (event_id,))
        assert pending_ewi_revision_event(con, job_id)["delivery_status"] == "pending_delivery"
    assert packet(job_id)["ready"] is False
    with pytest.raises(ValueError, match="EZ FAIR revision event"):
        clock_start(job_id, "10", "SYN-OPERATOR-NEW", "synthetic-test")
    with db() as con:
        con.execute("UPDATE event_ledger SET status='partial_failure' WHERE event_id=?", (event_id,))
        assert con.execute("SELECT COUNT(*) FROM ewi_clock_sessions WHERE job_id=?", (job_id,)).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0] == 1

    # Existing clock-outs stay usable even while new clock-ins are blocked.
    clock_stop(active_session, "SYN-OPERATOR-OLD", "synthetic-test")
    with db() as con:
        assert con.execute("SELECT ended_utc FROM ewi_clock_sessions WHERE id=?", (active_session,)).fetchone()[0]
        assert con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0] == 2

    # Reinitialize the actual app. Its existing SQL recovery cursor retries
    # the partial event and the real subscriber creates only the missing action.
    app = create_app({"TESTING": True})
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event_id,),
        ).fetchone()[0] == "delivered"
        assert con.execute(
            """SELECT status FROM event_delivery_receipts
               WHERE event_id=? AND handler_key LIKE '%review_controlled_fai_revision'""",
            (event_id,),
        ).fetchone()[0] == "delivered"
        actions = [dict(row) for row in con.execute(
            """SELECT id,workflow_key,target_module,entity_type,entity_id,input_json
               FROM workflow_actions WHERE event_id=? ORDER BY id""",
            (event_id,),
        )]
        assert len(actions) == 3
        assert {row["target_module"] for row in actions} == {"planning", "quality", "ewi"}
        assert [row["id"] for row in actions[:2]] == [row["id"] for row in before]
        ewi = next(row for row in actions if row["target_module"] == "ewi")
        assert ewi["entity_type"] == "job" and ewi["entity_id"] == str(job_id)
        evidence = json.loads(ewi["input_json"])
        assert evidence["source_event_id"] == event_id
        assert evidence["previous_fai_run_id"] == old_fai["id"]
        assert evidence["fai_run_id"] == new_fai["id"]
        assert (evidence["previous_revision"], evidence["new_revision"]) == ("A", new_revision)
        assert evidence["job_id"] == job_id and evidence["part_id"] == part_id
        assert evidence["previous_sha256"] == old_source["sha256"]
        assert evidence["new_sha256"] == new_source["sha256"]
        receipt_count = con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=?",
            (event_id,),
        ).fetchone()[0]

    assert packet(job_id)["ready"] is False
    assert f"revision review action #{ewi['id']}" in app.test_client().get(
        f"/ewi/jobs/{job_id}"
    ).get_data(as_text=True)
    with pytest.raises(ValueError, match="revision review action"):
        clock_start(job_id, "10", "SYN-OPERATOR", "synthetic-test")

    replay = deliver_staged(event_id)
    assert replay["failed"] == 0 and replay["delivered"] == 0
    assert replay["skipped"] == receipt_count
    repeated = import_controlled_fai(
        _payload(new_source), new_pdf,
        fai_number="SYN-RECOVERY-FAI-B", actor="synthetic-test",
    )
    assert repeated["idempotent"] is True
    create_app({"TESTING": True})
    with db() as con:
        assert [row["id"] for row in con.execute(
            "SELECT id FROM workflow_actions WHERE event_id=? ORDER BY id",
            (event_id,),
        )] == [row["id"] for row in actions]
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='fai.imported' AND entity_id=?",
            (str(new_fai["id"]),),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=?",
            (event_id,),
        ).fetchone()[0] == receipt_count
        assert con.execute(
            "SELECT COUNT(*) FROM ewi_clock_sessions WHERE job_id=?", (job_id,),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM ewi_outbox",
        ).fetchone()[0] == 2

    # A delivered event is not proof that its EWI review action survived.
    # Simulate an action lost after successful subscriber acknowledgement.
    # The ledger and delivered receipt must not silently authorize clocking.
    with db() as con:
        assert pending_ewi_revision_event(con, job_id) is None
        con.execute("DELETE FROM workflow_actions WHERE id=?", (ewi["id"],))
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event_id,)
        ).fetchone()[0] == "delivered"
        assert con.execute(
            """SELECT status FROM event_delivery_receipts
               WHERE event_id=? AND handler_key LIKE '%review_controlled_fai_revision'""",
            (event_id,),
        ).fetchone()[0] == "delivered"
        missing = pending_ewi_revision_event(con, job_id)
        assert missing is not None
        assert (missing["event_id"], missing["delivery_status"]) == (event_id, "delivered")
        assert pending_ewi_revision_event(con, unrelated_job) is None

        # A mismatched released job PDF cannot be used to invent EWI scope.
        con.execute(
            "UPDATE documents SET sha256='SYN-TAMPERED' WHERE job_id=?",
            (job_id,),
        )
        assert pending_ewi_revision_event(con, job_id) is None
        con.execute(
            "UPDATE documents SET sha256=? WHERE job_id=?",
            (old_source["sha256"], job_id),
        )
        assert pending_ewi_revision_event(con, job_id) is not None

    blocked_missing = packet(job_id)
    assert blocked_missing["ready"] is False
    assert any("delivered without its required EWI review action" in issue
               for issue in blocked_missing["issues"])
    with pytest.raises(ValueError, match="delivered without its required EWI review action"):
        clock_start(job_id, "10", "SYN-OPERATOR-NEW", "synthetic-test")
    with monkeypatch.context() as patch:
        patch.setattr(ewi_module, "packet", lambda _job_id: ready_packet)
        with pytest.raises(ValueError, match="delivered without its required EWI review action"):
            clock_start(job_id, "10", "SYN-OPERATOR-NEW", "synthetic-test")

    # Delivered receipts are skipped on replay, so startup alone cannot
    # reconstruct a missing action. The SQL guard remains in force.
    skipped = deliver_staged(event_id)
    assert skipped["failed"] == 0 and skipped["delivered"] == 0
    assert skipped["skipped"] == receipt_count
    create_app({"TESTING": True})
    assert packet(job_id)["ready"] is False
    with db() as con:
        assert pending_ewi_revision_event(con, job_id)["delivery_status"] == "delivered"
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND target_module='ewi'",
            (event_id,),
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM ewi_clock_sessions WHERE job_id=?", (job_id,),
        ).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ewi_outbox").fetchone()[0] == 2
