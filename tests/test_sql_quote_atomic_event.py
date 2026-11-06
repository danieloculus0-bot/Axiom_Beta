"""Fictional EZstimate quote transaction and delivery recovery regressions."""
from __future__ import annotations

import hashlib

import pytest

from superforge.db import db
from superforge.integrations import ezstimate_quote


def _proposal():
    pdf = b"%PDF-1.4\n% fictional quote drawing\n%%EOF\n"
    doc = {
        "record_id": "SYN-QUOTE-VAULT-1",
        "file_version_id": "SYN-QUOTE-VERSION-1",
        "release_package_number": "SYN-QUOTE-RELEASE-1",
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "byte_size": len(pdf),
        "customer_part_number": "SYN-PART-1",
        "customer_revision": "A",
        "internal_revision": "A",
        "lifecycle": "Released",
    }
    proposal = {
        "schema": "ezstimate.quote_proposal.v1",
        "source_system": "EZstimate",
        "status": "review_required",
        "quote_number": "SYN-QUOTE-001",
        "source_drawing": doc,
        "documents": [{"source": "fictional controlled drawing"}],
        "lines": [{"part_number": "SYN-PART-1", "quantity": 2,
                   "material_cost_each": "10.00", "labor_hours_each": "0"}],
        "pricing": {"status": "draft_review", "approval": "not approved",
                    "issues": [], "total": "20.00", "lines": [{}, {}][:1]},
    }
    return proposal, pdf


def test_stage_failure_rolls_back_quote_evidence_and_event(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "rollback"))
    from superforge.app import create_app
    create_app({"TESTING": True})
    proposal, pdf = _proposal()

    def fail_stage(*args, **kwargs):
        raise RuntimeError("synthetic staging failure")

    with monkeypatch.context() as patch:
        patch.setattr(ezstimate_quote, "stage_event", fail_stage)
        with pytest.raises(RuntimeError, match="staging failure"):
            ezstimate_quote.import_ezstimate_quote(
                proposal, pdf_bytes=pdf, actor="synthetic-reviewer")

    with db() as con:
        for table in ("quote_intakes", "ezstimate_quote_evidence"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='quote.estimate.draft_imported'"
        ).fetchone()[0] == 0


def test_committed_quote_recovers_after_dispatch_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "recovery"))
    from superforge.app import create_app
    from superforge.event_bus import deliver_staged
    create_app({"TESTING": True})
    proposal, pdf = _proposal()

    def crash_after_commit(event_id):
        raise RuntimeError("synthetic post-commit crash")

    with monkeypatch.context() as patch:
        patch.setattr(ezstimate_quote, "deliver_staged", crash_after_commit)
        with pytest.raises(RuntimeError, match="post-commit crash"):
            ezstimate_quote.import_ezstimate_quote(
                proposal, pdf_bytes=pdf, actor="synthetic-reviewer")

    with db() as con:
        quote = con.execute(
            "SELECT id,status FROM quote_intakes WHERE quote_number='SYN-QUOTE-001'"
        ).fetchone()
        assert quote["status"] == "review_required"
        assert con.execute(
            "SELECT COUNT(*) FROM ezstimate_quote_evidence WHERE quote_intake_id=?",
            (quote["id"],)).fetchone()[0] == 1
        rows = con.execute(
            "SELECT event_id,status,entity_id FROM event_ledger "
            "WHERE event_type='quote.estimate.draft_imported'"
        ).fetchall()
        assert len(rows) == 1
        event_id = rows[0]["event_id"]
        assert rows[0]["status"] == "pending_delivery"
        assert rows[0]["entity_id"] == str(quote["id"])

    # App restart invokes the existing SQL recovery path.
    create_app({"TESTING": True})
    with db() as con:
        status = con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?", (event_id,)
        ).fetchone()[0]
        assert status in ("pending_delivery", "delivered")
    # No typed consumer is required for a pending event to remain durable.
    deliver_staged(event_id)
    repeated = ezstimate_quote.import_ezstimate_quote(
        proposal, pdf_bytes=pdf, actor="synthetic-reviewer")
    assert repeated["idempotent"] is True
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM quote_intakes").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ezstimate_quote_evidence").fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='quote.estimate.draft_imported'"
        ).fetchone()[0] == 1
