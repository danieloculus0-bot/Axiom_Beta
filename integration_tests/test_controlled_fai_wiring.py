"""Actual ForgeVault, EZ-FAIR, Axiom contract execution."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in ("forgevault-src", "ezfair-src"):
    if not (ROOT / folder).is_dir():
        raise RuntimeError("Missing checked-out source: " + folder)
    sys.path.insert(0, str(ROOT / folder))
sys.path.insert(0, str(ROOT / "forgevault-src" / "backend"))

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from forgevault.config import settings
from forgevault.database import Base
from forgevault.services.metadata import create_record
from forgevault.services.versioning import append_version_bytes
from forgevault.services.lifecycle import transition_record
from forgevault.services.fai_handoff import released_pdf_handoff
from controlled_handoff import inspect_released_pdf

def test_real_three_repository_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_vault_root", str(tmp_path / "objects"))
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "vault.db"))
    Base.metadata.create_all(engine)
    drawing = fitz.open()
    drawing.new_page().insert_text((60, 80), "WIDTH 20.00")
    pdf = drawing.tobytes()
    drawing.close()
    with Session(engine, expire_on_commit=False) as session:
        record = create_record(session, customer_part_number="BRACKET",
            customer_revision="C", internal_revision="03", metadata={}, actor="tester")
        version = append_version_bytes(session, record=record,
            filename="BRACKET.pdf", original_source_path="test/BRACKET.pdf",
            content=pdf, customer_revision="C", internal_revision="03",
            metadata={}, actor="tester", mime_type="application/pdf")
        session.flush()
        record_id, version_id = record.internal_record_id, str(version.id)
        with pytest.raises(ValueError, match="Released"):
            released_pdf_handoff(session, record_id=record_id, version_id=version_id)
        transition_record(session, record=record, to_state_name="Review", actor="tester")
        session.flush()
        session.expire(record, ["lifecycle_state"])
        transition_record(session, record=record, to_state_name="Released", actor="tester")
        session.flush()
        session.expire(record, ["lifecycle_state"])
        source, content = released_pdf_handoff(session, record_id=record_id, version_id=version_id)
        session.commit()
    engine.dispose()
    assert source["sha256"] == hashlib.sha256(pdf).hexdigest() and content == pdf
    proposal = inspect_released_pdf(source, content)
    assert proposal["status"] == "review_required" and proposal["characteristic_count"] > 0
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    from superforge.db import db
    from superforge.integrations.controlled_fai import import_controlled_fai
    create_app({"TESTING": True})
    result = import_controlled_fai(proposal, content, fai_number="FAI-BRACKET", actor="tester")
    assert result["status"] == "review_required" and not result["idempotent"]
    assert import_controlled_fai(proposal, content, fai_number="FAI-BRACKET", actor="tester")["idempotent"]
    with db() as con:
        row = con.execute("SELECT * FROM fai_runs WHERE id=?", (result["id"],)).fetchone()
        assert row["status"] == "review_required" and row["drawing_revision"] == "C"
        assert row["pass_count"] == 0 and row["fail_count"] == 0
        link = con.execute("SELECT * FROM fai_source_links WHERE fai_run_id=?", (result["id"],)).fetchone()
        assert link["pdf_sha256"] == source["sha256"]
    with pytest.raises(ValueError, match="checksum"):
        import_controlled_fai(proposal, content+b"changed", fai_number="FAI-OTHER", actor="tester")
