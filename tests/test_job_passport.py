"""Evidence integrity tests for the read-only Job Passport."""
from __future__ import annotations


def test_job_passport_scopes_records_and_preserves_review_status(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.job_passport import get_job_passport

    app = create_app({"TESTING": True})
    with db() as con:
        customer = con.execute(
            "INSERT INTO customers(name) VALUES (?)", ("Sample Fabrication",)
        ).lastrowid
        part = con.execute(
            "INSERT INTO parts(part_number,revision,customer_id) VALUES (?,?,?)",
            ("PL-100", "B", customer),
        ).lastrowid
        first = con.execute(
            "INSERT INTO jobs(job_number,part_id,customer_id,quantity,status) VALUES (?,?,?,?,?)",
            ("WO-ALPHA", part, customer, 20, "open"),
        ).lastrowid
        second = con.execute(
            "INSERT INTO jobs(job_number,part_id,customer_id) VALUES (?,?,?)",
            ("WO-BETA", part, customer),
        ).lastrowid
        con.execute(
            "INSERT INTO purchase_orders(po_number,job_id,status) VALUES (?,?,?)",
            ("PO-ALPHA", first, "open"),
        )
        con.execute(
            "INSERT INTO purchase_orders(po_number,job_id,status) VALUES (?,?,?)",
            ("PO-BETA", second, "open"),
        )
        con.execute(
            """INSERT INTO quality_records(record_type,record_number,job_id,
                       description,status) VALUES (?,?,?,?,?)""",
            ("NCR", "NCR-ALPHA", first, "Needs review", "open"),
        )
        con.execute(
            "INSERT INTO documents(document_number,title,job_id,status) VALUES (?,?,?,?)",
            ("D-ALPHA", "Assigned drawing", first, "Released"),
        )
        con.execute(
            "INSERT INTO documents(document_number,title,part_id,status) VALUES (?,?,?,?)",
            ("D-PART", "Reference only", part, "Released"),
        )
        con.execute(
            """INSERT INTO ezm_method_plans(job_id,job_number,part_number,revision,
                       quantity,required_date,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
            (first, "WO-ALPHA", "PL-100", "B", 20, "2026-11-01", "DRAFT"),
        )
        fai = con.execute(
            """INSERT INTO fai_runs(fai_number,job_id,part_id,status,
                       characteristic_count) VALUES (?,?,?,?,?)""",
            ("FAI-ALPHA", first, part, "review_required", 3),
        ).lastrowid
        con.execute(
            """INSERT INTO fai_source_links(fai_run_id,vault_record_id,
                       vault_version_id,release_package_number,pdf_sha256,payload_sha256)
               VALUES (?,?,?,?,?,?)""",
            (fai, "VR-1", "VV-1", "REL-1", "a" * 64, "b" * 64),
        )
        con.execute(
            """INSERT INTO fai_runs(fai_number,job_id,part_id,status)
               VALUES (?,?,?,?)""", ("FAI-BETA", second, part, "complete"),
        )
        con.execute(
            """INSERT INTO quote_intakes(quote_number,part_id,status,estimated_value)
               VALUES (?,?,?,?)""", ("QUOTE-PART", part, "review_required", 900.0),
        )
        con.execute(
            "INSERT INTO inventory_items(item_number) VALUES (?)", ("STOCK-1",)
        )
        item = con.execute(
            "SELECT id FROM inventory_items WHERE item_number='STOCK-1'"
        ).fetchone()["id"]
        con.execute(
            """INSERT INTO inventory_transactions(item_id,job_id,txn_type,quantity)
               VALUES (?,?,?,?)""", (item, first, "issue", 4),
        )

    first_data = get_job_passport(first)
    assert first_data is not None
    assert [x["po_number"] for x in first_data["linked"]["purchase_orders"]] == ["PO-ALPHA"]
    assert [x["record_number"] for x in first_data["linked"]["quality"]] == ["NCR-ALPHA"]
    assert [x["fai_number"] for x in first_data["linked"]["inspections"]] == ["FAI-ALPHA"]
    assert first_data["linked"]["inspections"][0]["status"] == "review_required"
    assert first_data["linked"]["inspections"][0]["vault_version_id"] == "VV-1"
    assert [x["document_number"] for x in first_data["linked"]["documents"]] == ["D-ALPHA"]
    assert [x["quote_number"] for x in first_data["part_references"]["quotes"]] == ["QUOTE-PART"]
    assert [x["fai_number"] for x in first_data["part_references"]["inspections"]] == ["FAI-BETA"]

    client = app.test_client()
    passport = client.get(f"/jobs/{first}/passport")
    assert passport.status_code == 200
    html = passport.get_data(as_text=True)
    assert "Job Passport: WO-ALPHA" in html
    assert "FAI-ALPHA" in html
    assert "review_required" in html
    assert "Part-level references (not job evidence)" in html
    assert "PO-BETA" not in html
    assert client.get(f"/jobs/{second}/passport").status_code == 200
    assert client.get("/jobs/999999/passport").status_code == 404
    listing = client.get("/jobs").get_data(as_text=True)
    assert f"/jobs/{first}/passport" in listing


def test_job_passport_empty_missing_and_html_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "isolated"))
    from superforge.app import create_app
    from superforge.db import db

    app = create_app({"TESTING": True})
    with db() as con:
        job_id = con.execute(
            "INSERT INTO jobs(job_number,notes) VALUES (?,?)",
            ("WO-<script>bad</script>", "No linked evidence"),
        ).lastrowid
    client = app.test_client()
    response = client.get(f"/jobs/{job_id}/passport")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "WO-&lt;script&gt;bad&lt;/script&gt;" in text
    assert "WO-<script>bad</script>" not in text
    assert "No records directly linked to this job." in text
    assert "No part-level references." in text
    assert client.get(f"/jobs/{job_id}/passport", follow_redirects=True).status_code == 200
