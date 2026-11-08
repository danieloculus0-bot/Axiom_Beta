"""Synthetic regression for the shipped quote review consumer and durable receipts."""
from __future__ import annotations

import hashlib
import json

from superforge.db import db
from superforge.integrations import ezstimate_quote


def test_real_quote_consumer_receipt_loss_restart_and_operator_action(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "real-consumer"))
    from superforge.app import create_app
    from superforge import event_bus

    create_app({"TESTING": True})
    event_type = "quote.estimate.draft_imported"
    handler = event_bus._quote_draft_imported
    assert handler in event_bus._HANDLERS[event_type]

    pdf = b"%PDF-1.4\n% fictional drawing\n%%EOF\n"
    drawing = {
        "record_id": "SYN-REPLAY-DOC", "file_version_id": "SYN-REPLAY-V1",
        "release_package_number": "SYN-REPLAY-RELEASE",
        "sha256": hashlib.sha256(pdf).hexdigest(), "byte_size": len(pdf),
        "customer_part_number": "SYN-REPLAY-PART",
        "customer_revision": "A", "internal_revision": "A",
        "lifecycle": "Released",
    }
    proposal = {
        "schema": "ezstimate.quote_proposal.v1", "source_system": "EZstimate",
        "status": "review_required", "quote_number": "SYN-REPLAY-QUOTE",
        "source_drawing": drawing,
        "documents": [{"source": "fictional controlled drawing"}],
        "lines": [{"part_number": "SYN-REPLAY-PART", "quantity": 2,
                   "material_cost_each": "10.00", "labor_hours_each": "0"}],
        "pricing": {"status": "draft_review", "approval": "not approved",
                    "issues": [], "total": "20.00", "lines": [{}]},
    }

    original = event_bus._record_delivery
    lost = [False]

    def lose_only_real_consumer_receipt(event, subscriber, status, error_text=""):
        if subscriber is handler and status == "delivered" and not lost[0]:
            lost[0] = True
            return False
        return original(event, subscriber, status, error_text)

    with monkeypatch.context() as patch:
        patch.setattr(event_bus, "_record_delivery", lose_only_real_consumer_receipt)
        result = ezstimate_quote.import_ezstimate_quote(
            proposal, pdf_bytes=pdf, actor="synthetic-reviewer")
    assert result["status"] == "review_required"
    assert lost[0]

    # Exercise the actual operator route, not only the SQL action table.
    first_page = create_app({"TESTING": True}).test_client().get("/quoting")
    assert first_page.status_code == 200
    assert b"Quote review actions" in first_page.data
    assert b"SYN-REPLAY-QUOTE" in first_page.data
    assert b"quote-draft-review" in first_page.data
    assert b"review-estimate-and-drawing" in first_page.data

    with db() as con:
        quote = con.execute(
            "SELECT id FROM quote_intakes WHERE quote_number=?",
            ("SYN-REPLAY-QUOTE",)).fetchone()
        assert quote is not None
        event = con.execute(
            "SELECT event_id,status FROM event_ledger WHERE event_type=?",
            (event_type,)).fetchone()
        assert event["status"] == "partial_failure"
        action = con.execute(
            """SELECT event_id,workflow_key,step_key,target_module,
                      entity_type,entity_id,status,input_json
               FROM workflow_actions WHERE event_id=?""",
            (event["event_id"],)).fetchone()
        assert action is not None
        assert (action["workflow_key"], action["step_key"], action["target_module"]) == (
            "quote-draft-review", "review-estimate-and-drawing", "quoting")
        assert (action["entity_type"], action["entity_id"], action["status"]) == (
            "quote_intake", str(quote["id"]), "open")
        assert json.loads(action["input_json"])["quote_intake_id"] == str(quote["id"])
        assert con.execute(
            """SELECT COUNT(*) FROM event_delivery_receipts
               WHERE event_id=? AND handler_key=?""",
            (event["event_id"], event_bus._handler_key(handler))).fetchone()[0] == 0

    # Recreate the Flask app to exercise its real startup recovery registration.
    app = create_app({"TESTING": True})
    assert app is not None
    replay = event_bus.recover_undelivered()
    assert replay["failed"] == 0
    assert event_bus.deliver_staged(event["event_id"])["skipped"] >= 1
    assert ezstimate_quote.import_ezstimate_quote(
        proposal, pdf_bytes=pdf, actor="synthetic-reviewer")["idempotent"]

    recovered_page = app.test_client().get("/quoting")
    assert recovered_page.status_code == 200
    assert recovered_page.data.count(b"review-estimate-and-drawing") == 1
    assert b"SYN-REPLAY-QUOTE" in recovered_page.data

    with db() as con:
        assert con.execute(
            """SELECT COUNT(*) FROM workflow_actions
               WHERE event_id=? AND workflow_key='quote-draft-review'
                 AND step_key='review-estimate-and-drawing'
                 AND target_module='quoting'""",
            (event["event_id"],)).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM quote_intakes").fetchone()[0] == 1
        assert con.execute(
            "SELECT status FROM event_ledger WHERE event_id=?",
            (event["event_id"],)).fetchone()[0] == "delivered"
        assert con.execute(
            """SELECT status FROM event_delivery_receipts
               WHERE event_id=? AND handler_key=?""",
            (event["event_id"], event_bus._handler_key(handler))).fetchone()[0] == "delivered"
