"""Atomic EZ FAIR source import and recoverable SQL event regressions.

Every source record, drawing byte and identifier below is fictional.
"""
from __future__ import annotations

import hashlib

import pytest

from superforge.db import db
from superforge.integrations import controlled_fai


def _fixture():
    pdf = b"%PDF-1.4\n% wholly fictional test drawing\n%%EOF\n"
    source = {
        "record_id": "SYN-ATOMIC-VAULT-001",
        "file_version_id": "SYN-ATOMIC-V01",
        "release_package_number": "SYN-ATOMIC-RELEASE-01",
        "customer_part_number": "SYN-ATOMIC-PART-001",
        "customer_revision": "A",
        "internal_revision": "A",
        "filename": "synthetic-atomic.pdf",
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "byte_size": len(pdf),
        "version_number": 1,
    }
    payload = {
        "schema": "ezfair.inspection_handoff.v1",
        "status": "review_required",
        "source_drawing": source,
        "characteristic_count": 1,
        "characteristics": [{
            "char_number": 1, "reference_location": "SYN-R1",
            "raw_text": "FICTIONAL LENGTH 12",
            "nominal": 12.0, "lsl": 11.9, "usl": 12.1,
            "characteristic_type": "LINEAR",
        }],
    }
    return payload, pdf


def test_stage_failure_rolls_back_fai_and_event_together(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "synthetic-rollback"))
    from superforge.app import create_app
    create_app({"TESTING": True})
    payload, pdf = _fixture()

    def stage_failure(*args, **kwargs):
        raise RuntimeError("synthetic failure before SQL commit")

    with monkeypatch.context() as patch:
        patch.setattr(controlled_fai, "stage_event", stage_failure)
        with pytest.raises(RuntimeError, match="before SQL commit"):
            controlled_fai.import_controlled_fai(
                payload, pdf, fai_number="SYN-ATOMIC-FAI-001",
                actor="synthetic-test",
            )

    with db() as con:
        for table in ("documents", "document_versions", "fai_runs",
                      "fai_characteristics", "fai_source_links"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='fai.imported'"
        ).fetchone()[0] == 0

    # The same input remains importable after the rolled-back attempt.
    result = controlled_fai.import_controlled_fai(
        payload, pdf, fai_number="SYN-ATOMIC-FAI-001",
        actor="synthetic-test",
    )
    assert result["idempotent"] is False
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM fai_runs").fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='fai.imported'"
        ).fetchone()[0] == 1


def test_committed_fai_event_survives_dispatch_crash_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "synthetic-restart"))
    from superforge.app import create_app
    from superforge.event_bus import deliver_staged
    create_app({"TESTING": True})
    payload, pdf = _fixture()

    def dispatch_crash(event_id):
        raise RuntimeError("synthetic crash after SQL commit")

    with monkeypatch.context() as patch:
        patch.setattr(controlled_fai, "deliver_staged", dispatch_crash)
        with pytest.raises(RuntimeError, match="after SQL commit"):
            controlled_fai.import_controlled_fai(
                payload, pdf, fai_number="SYN-ATOMIC-FAI-002",
                actor="synthetic-test",
            )

    with db() as con:
        fai = con.execute(
            "SELECT id FROM fai_runs WHERE fai_number='SYN-ATOMIC-FAI-002'"
        ).fetchone()
        assert fai is not None
        assert con.execute(
            "SELECT COUNT(*) FROM fai_characteristics WHERE fai_run_id=?",
            (fai["id"],),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM fai_source_links WHERE fai_run_id=?",
            (fai["id"],),
        ).fetchone()[0] == 1
        ledger = con.execute(
            "SELECT event_id,status,entity_id FROM event_ledger "
            "WHERE event_type='fai.imported'"
        ).fetchall()
        assert len(ledger) == 1
        event_id = ledger[0]["event_id"]
        assert ledger[0]["status"] == "pending_delivery"
        assert ledger[0]["entity_id"] == str(fai["id"])
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=?",
            (event_id,),
        ).fetchone()[0] == 0

    # Reinitializing the existing app replays the committed pending event.
    create_app({"TESTING": True})
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event_id,)
        ).fetchone()[0] == "delivered"
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts "
            "WHERE event_id=? AND status='delivered' "
            "AND handler_key LIKE '%review_controlled_fai_revision'",
            (event_id,),
        ).fetchone()[0] == 1
        receipt_count = con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=?",
            (event_id,),
        ).fetchone()[0]

    replay = deliver_staged(event_id)
    assert replay["failed"] == 0 and replay["delivered"] == 0
    assert replay["skipped"] == receipt_count
    repeated = controlled_fai.import_controlled_fai(
        payload, pdf, fai_number="SYN-ATOMIC-FAI-002",
        actor="synthetic-test",
    )
    assert repeated["idempotent"] is True
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='fai.imported'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=?",
            (event_id,),
        ).fetchone()[0] == receipt_count
