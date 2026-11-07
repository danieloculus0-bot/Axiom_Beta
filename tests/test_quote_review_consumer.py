"""Synthetic end-to-end regression for quote review consumer and operator queue."""
from superforge.db import db
from superforge import event_bus
from superforge.integrations.ezstimate_quote import import_ezstimate_quote
from test_sql_quote_atomic_event import _proposal


def test_import_creates_one_operator_visible_review_action(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "quote-review"))
    from superforge.app import create_app
    app = create_app({"TESTING": True})
    proposal, pdf = _proposal()
    result = import_ezstimate_quote(proposal, pdf_bytes=pdf, actor="fictional-reviewer")
    assert result["status"] == "review_required"
    with db() as con:
        event = con.execute(
            "SELECT event_id,status FROM event_ledger WHERE event_type=?",
            ("quote.estimate.draft_imported",),
        ).fetchone()
        action = con.execute(
            "SELECT * FROM workflow_actions WHERE event_id=? AND target_module='quoting'",
            (event["event_id"],),
        ).fetchone()
        assert action["entity_type"] == "quote_intake"
        assert action["entity_id"] == str(result["quote_id"])
        assert action["workflow_key"] == "quote-draft-review"
        assert action["status"] == "open"
        assert event["status"] == "delivered"
        assert con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event["event_id"], event_bus._handler_key(event_bus._quote_draft_imported)),
        ).fetchone()[0] == "delivered"
    page = app.test_client().get("/quoting")
    assert page.status_code == 200
    assert b"Quote review actions" in page.data
    assert b"review-estimate-and-drawing" in page.data
    assert import_ezstimate_quote(proposal, pdf_bytes=pdf, actor="fictional-reviewer")["idempotent"]
    event_bus.deliver_staged(event["event_id"])
    create_app({"TESTING": True})
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND target_module='quoting'",
            (event["event_id"],),
        ).fetchone()[0] == 1


def test_lost_receipt_replays_without_duplicate_action(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "lost-receipt"))
    from superforge.app import create_app
    create_app({"TESTING": True})
    proposal, pdf = _proposal()
    original = event_bus._record_delivery
    failed = [False]

    def lose_quote_receipt(event, handler, status, error_text=""):
        if (not failed[0] and handler is event_bus._quote_draft_imported
                and status == "delivered"):
            failed[0] = True
            return False
        return original(event, handler, status, error_text)

    with monkeypatch.context() as patch:
        patch.setattr(event_bus, "_record_delivery", lose_quote_receipt)
        import_ezstimate_quote(proposal, pdf_bytes=pdf, actor="fictional-reviewer")
    assert failed[0]
    with db() as con:
        event = con.execute(
            "SELECT event_id,status FROM event_ledger WHERE event_type='quote.estimate.draft_imported'"
        ).fetchone()
        assert event["status"] == "partial_failure"
    event_bus.recover_undelivered()
    with db() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM workflow_actions WHERE event_id=? AND target_module='quoting'",
            (event["event_id"],),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT status FROM event_delivery_receipts WHERE event_id=? AND handler_key=?",
            (event["event_id"], event_bus._handler_key(event_bus._quote_draft_imported)),
        ).fetchone()[0] == "delivered"
