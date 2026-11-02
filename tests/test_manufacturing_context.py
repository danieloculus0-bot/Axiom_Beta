"""Read-only SQL-to-module contract tests, using invented manufacturing data."""
from __future__ import annotations


def test_shared_job_context_tracks_canonical_part_revision_and_operations(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    from superforge.db import db
    from superforge.modules.job_passport import get_job_passport

    client = create_app({"TESTING": True}).test_client()
    with db() as con:
        part = con.execute(
            "INSERT INTO parts(part_number,revision,description) VALUES('SYN-PLATE-99','A','Fictional plate')"
        ).lastrowid
        job = con.execute(
            "INSERT INTO jobs(job_number,part_id,status,quantity) VALUES('SYN-WO-909',?,'open',12)",
            (part,),
        ).lastrowid

    path = f"/api/v1/jobs/{job}/manufacturing-context"
    missing_plan = client.get(path)
    assert missing_plan.status_code == 200
    state = missing_plan.get_json()
    assert state["job"]["part_number"] == "SYN-PLATE-99"
    assert state["method_status"] == "no_method_plan"
    assert state["method_operations"] == []
    assert state["cam"]["machine_program_ready"] is False
    assert client.get("/api/v1/jobs/999999/manufacturing-context").status_code == 404

    with db() as con:
        plan = con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,quantity,required_date,status)
               VALUES(?,?,?,?,?,?,?,'DRAFT')""",
            (job, part, "SYN-WO-909", "SYN-PLATE-99", "A", 12, "2026-11-30"),
        ).lastrowid
        op = con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction,inspection_requirement)
               VALUES(?,10,'MILL','Face fictional plate','2026-11-15','Review stock before setup','Check surface')""",
            (plan,),
        ).lastrowid
        con.execute(
            """INSERT INTO ewi_routes(job_id,step,operation,work_center,part_number,pulled_at)
               VALUES(?, '10','Inspect fictional plate','QC','SYN-PLATE-99','2026-11-01T00:00:00Z')""",
            (job,),
        )
        con.execute(
            """INSERT INTO documents(document_number,title,revision,document_type,status,job_id,part_id,sha256)
               VALUES('SYN-DWG-909','Fictional drawing','A','drawing','released',?,?,?)""",
            (job,part,"a"*64),
        )

    response = client.get(path)
    assert response.status_code == 200
    ctx = response.get_json()
    assert ctx["schema"] == "axiom.manufacturing-context.v1"
    assert ctx["method_status"] == "ready_for_review"
    assert ctx["method_plan"]["id"] == plan
    assert ctx["method_plan"]["revision"] == "A"
    assert len(ctx["method_operations"]) == 1
    assert ctx["method_operations"][0]["id"] == op
    assert ctx["method_operations"][0]["work_center"] == "MILL"
    assert ctx["method_operations"][0]["operation"] == "Face fictional plate"
    assert ctx["ewi_status"] == "separate_source_unverified"
    assert ctx["ewi_operations"][0]["operation"] == "Inspect fictional plate"
    assert ctx["drawing_status"] == "released_record_present_unverified_file"
    assert ctx["cam"] == {
        "machine_program_ready": False, "job_geometry_loaded": False,
        "operation_must_be_selected": True,
    }
    assert get_job_passport(job)["job"]["part_number"] == ctx["job"]["part_number"]

    # The client sees SQL changes without resyncing a browser-local synthetic copy.
    with db() as con:
        con.execute("UPDATE parts SET revision='B' WHERE id=?", (part,))
    stale = client.get(path).get_json()
    assert stale["job"]["part_revision"] == "B"
    assert stale["method_status"] == "revision_mismatch"
    assert stale["method_operations"] == []
    assert stale["method_plan"] is None
    assert stale["drawing_status"] == "drawing_revision_mismatch"
    assert stale["cam"]["machine_program_ready"] is False
    with db() as con:
        con.execute("UPDATE ezm_method_plans SET revision='B' WHERE id=?", (plan,))
    refreshed = client.get(path).get_json()
    assert refreshed["method_status"] == "ready_for_review"
    assert refreshed["method_operations"][0]["id"] == op
    assert refreshed["drawing_status"] == "drawing_revision_mismatch"

    # Multiple plans require a human to choose; no implicit highest-ID fallback.
    with db() as con:
        con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,quantity,required_date,status)
               VALUES(?,?,?,?,?,?,?,'DRAFT')""",
            (job,part,"SYN-WO-909","SYN-PLATE-99","B",12,"2026-11-30"),
        )
    ambiguous = client.get(path).get_json()
    assert ambiguous["method_status"] == "ambiguous_method_plans"
    assert ambiguous["method_plan_candidates"] == 2
    assert ambiguous["method_operations"] == []
    assert ambiguous["method_plan"] is None


def test_context_read_only_missing_canonical_part_does_not_guess(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    from superforge.app import create_app
    from superforge.db import db

    client = create_app({"TESTING":True}).test_client()
    with db() as con:
        job = con.execute("INSERT INTO jobs(job_number,status) VALUES('SYN-NO-PART-1','open')").lastrowid
    path = f"/api/v1/jobs/{job}/manufacturing-context"
    first = client.get(path).get_json()
    assert first["method_status"] == "missing_canonical_part"
    assert first["method_operations"] == []
    assert first["cam"]["job_geometry_loaded"] is False
    with db() as con:
        before = con.execute("SELECT COUNT(*) FROM event_ledger").fetchone()[0]
    second = client.get(path).get_json()
    with db() as con:
        after = con.execute("SELECT COUNT(*) FROM event_ledger").fetchone()[0]
    assert first == second
    assert before == after  # GET must not invent data or broadcast a sync event
