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
    html = create_app({"TESTING": True}).test_client().get("/ez-fair")
    assert html.status_code == 200
    assert b"Vault Record" in html.data and b"Release Package" in html.data
    assert source["record_id"].encode() in html.data
    assert source["release_package_number"].encode() in html.data
    assert source["sha256"][:16].encode() in html.data
    with pytest.raises(ValueError, match="checksum"):
        import_controlled_fai(proposal, content+b"changed", fai_number="FAI-OTHER", actor="tester")
    # The next independent engine reuses the exact controlled drawing identity.
    from superforge.modules.ez_methods import create_method_plan
    from superforge.integrations.controlled_methods import link_controlled_drawing_to_method
    plan_id = create_method_plan({
        "job_number": "J-METHOD-001", "part_number": source["customer_part_number"],
        "revision": source["customer_revision"], "required_date": "2026-11-01",
        "quantity": 4,
    }, actor="tester")
    result_source = link_controlled_drawing_to_method(plan_id, source, actor="tester")
    assert not result_source["idempotent"]
    assert link_controlled_drawing_to_method(plan_id, source, actor="tester")["idempotent"]
    with db() as con:
        method_source = con.execute("SELECT * FROM ezm_sources WHERE plan_id=?", (plan_id,)).fetchone()
        assert method_source["location"].endswith(source["file_version_id"])
        assert method_source["revision"] == source["customer_revision"]
        assert source["sha256"] in method_source["note"]
    with pytest.raises(ValueError, match="no verified FAI import"):
        link_controlled_drawing_to_method(
            plan_id, dict(source, file_version_id="changed-version-id"), actor="tester"
        )
    with pytest.raises(ValueError, match="part/revision"):
        wrong_plan = create_method_plan({
            "job_number": "J-WRONG", "part_number": source["customer_part_number"],
            "revision": "WRONG", "required_date": "2026-11-01",
        }, actor="tester")
        link_controlled_drawing_to_method(wrong_plan, source, actor="tester")

