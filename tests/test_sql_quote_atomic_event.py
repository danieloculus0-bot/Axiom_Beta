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


def test_typed_quote_consumer_failure_and_replay_receipt(tmp_path, monkeypatch):
    """Failed typed consumer replays exactly once after a committed quote."""
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "typed-replay"))
    from superforge.app import create_app
    from superforge import event_bus
    create_app({"TESTING": True})
    proposal, pdf = _proposal()
    event_type = "quote.estimate.draft_imported"
    attempts = []
    def typed_quote_consumer(event):
        attempts.append(event.event_id)
        assert event.entity_type == "quote_intake"
        assert event.payload["status"] == "review_required"
        if len(attempts) == 1:
            raise RuntimeError("synthetic consumer failure")

    # Other default and wildcard observers also receive events; inspect this consumer's receipt.
    monkeypatch.setitem(event_bus._HANDLERS, event_type, [typed_quote_consumer])
    result = ezstimate_quote.import_ezstimate_quote(
        proposal, pdf_bytes=pdf, actor="synthetic-reviewer")
    assert result["status"] == "review_required"
    with db() as con:
        row = con.execute(
            "SELECT event_id,status FROM event_ledger WHERE event_type=?",
            (event_type,)).fetchone()
        assert row["status"] == "partial_failure"
        receipt = con.execute(
            "SELECT status,error_text FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (row["event_id"], event_bus._handler_key(typed_quote_consumer))).fetchone()
        assert receipt["status"] == "failed"
        assert "synthetic consumer failure" in receipt["error_text"]

    replay = event_bus.recover_undelivered()
    assert replay["delivered"] == 1
    assert replay["failed"] == 0
    assert attempts == [row["event_id"], row["event_id"]]
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?",
            (row["event_id"],)).fetchone()[0] == "delivered"
        assert con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (row["event_id"], event_bus._handler_key(typed_quote_consumer))).fetchone()[0] == "delivered"
    again = event_bus.deliver_staged(row["event_id"])
    assert again["skipped"] >= 1
    assert len(attempts) == 2
    assert ezstimate_quote.import_ezstimate_quote(
        proposal, pdf_bytes=pdf, actor="synthetic-reviewer")["idempotent"]
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM quote_intakes").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM event_ledger WHERE event_type=?",
                           (event_type,)).fetchone()[0] == 1


def test_quote_receipt_write_failure_replays_idempotent_consumer(tmp_path, monkeypatch):
    """A handler success without a durable receipt must remain retryable."""
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "receipt-replay"))
    from superforge.app import create_app
    from superforge import event_bus
    create_app({"TESTING": True})
    proposal, pdf = _proposal()
    event_type = "quote.estimate.draft_imported"
    observed = set()
    calls = []
    def idempotent_quote_consumer(event):
        calls.append(event.event_id)
        observed.add(event.event_id)

    monkeypatch.setitem(event_bus._HANDLERS, event_type, [idempotent_quote_consumer])
    original = event_bus._record_delivery
    failures = [True]
    def fail_first_success_receipt(event, handler, status, error_text=""):
        if status == "delivered" and failures[0]:
            failures[0] = False
            return False
        return original(event, handler, status, error_text)
    with monkeypatch.context() as patch:
        patch.setattr(event_bus, "_record_delivery", fail_first_success_receipt)
        ezstimate_quote.import_ezstimate_quote(
            proposal, pdf_bytes=pdf, actor="synthetic-reviewer")

    with db() as con:
        row = con.execute(
            "SELECT event_id,status FROM event_ledger WHERE event_type=?",
            (event_type,)).fetchone()
        assert row["status"] == "partial_failure"
        assert con.execute(
            "SELECT COUNT(*) FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (row["event_id"], event_bus._handler_key(idempotent_quote_consumer))).fetchone()[0] == 0
    replay = event_bus.recover_undelivered()
    assert replay["delivered"] == 1
    assert len(calls) == 2
    assert observed == {row["event_id"]}
    with db() as con:
        assert con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (row["event_id"], event_bus._handler_key(idempotent_quote_consumer))).fetchone()[0] == "delivered"
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?",
            (row["event_id"],)).fetchone()[0] == "delivered"
    assert event_bus.deliver_staged(row["event_id"])["skipped"] >= 1
    assert len(calls) == 2
