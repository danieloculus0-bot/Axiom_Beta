"""Synthetic SQL job to EZ Methods operation evidence; no route release."""
from __future__ import annotations

import csv
import json

from superforge import event_bus
from superforge.db import db


def _feed(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Job", "PartId", "Op", "Status"])
        writer.writeheader()
        writer.writerows(rows)


def _connection(con, path):
    cid = int(con.execute(
        """INSERT INTO erp_connections(name,erp_type,adapter_type,direction,config_json)
           VALUES('SYN-METHOD-IMPORT','generic','flatfile','in',?)""",
        (json.dumps({"path": str(path), "external_id_field": "Job"}),),
    ).lastrowid)
    for external, internal, transform, required in (
        ("Job", "job_number", "strip", 1),
        ("PartId", "part_id", "int", 0),
        ("Op", "current_operation", "strip", 0),
        ("Status", "status", "lower", 0),
    ):
        con.execute(
            """INSERT INTO erp_mappings
               (connection_id,entity_type,external_field,internal_field,transform,direction,required)
               VALUES(?,'job',?,?,?,'in',?)""",
            (cid, external, internal, transform, required),
        )
    return cid


def _history(con, job_number):
    rows = con.execute(
        """SELECT e.event_id,e.status,e.payload_json,a.id AS action_id,
                  a.input_json,s.evidence_json
           FROM jobs j JOIN event_ledger e ON e.entity_type='job'
              AND e.entity_id=CAST(j.id AS TEXT) AND e.event_type='job.changed'
           JOIN workflow_actions a ON a.event_id=e.event_id
              AND a.workflow_key='job-change' AND a.target_module='planning'
           JOIN module_suggestions s ON s.source_event_id=e.event_id
              AND s.target_module='ez_methods' AND s.suggestion_key='job-method-readiness'
           WHERE j.job_number=? ORDER BY e.id""", (job_number,),
    ).fetchall()
    assert rows
    result = []
    for row in rows:
        identity = json.loads(row["payload_json"])["identity"]
        assert json.loads(row["input_json"])["identity"] == identity
        assert json.loads(row["evidence_json"])["identity"] == identity
        result.append((row, identity))
    return result


def test_thousand_exact_candidates_replay_and_conflicts(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    from superforge.integrations.service import IntegrationService

    create_app({"TESTING": True})
    monkeypatch.setattr(event_bus, "_HANDLERS",
                        {kind: list(handlers) for kind, handlers in event_bus._HANDLERS.items()})
    calls = {"count": 0}

    def flaky(event):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("synthetic delivery interruption")

    event_bus.subscribe("job.changed", flaky)
    path = tmp_path / "fictional_methods.csv"
    records, ids = [], []
    with db() as con:
        connection_id = _connection(con, path)
        for i in range(1000):
            part_number = f"SYN-METHOD-PART-{i:04d}"
            job_number = f"SYN-METHOD-WO-{i:04d}"
            part_id = int(con.execute(
                "INSERT INTO parts(part_number,revision) VALUES(?,'A')", (part_number,),
            ).lastrowid)
            job_id = int(con.execute(
                """INSERT INTO jobs(job_number,part_id,status,current_operation)
                   VALUES(?,?,'seed','SYN-OP-10')""", (job_number, part_id),
            ).lastrowid)
            plan_id = int(con.execute(
                """INSERT INTO ezm_method_plans
                   (job_id,part_id,job_number,part_number,revision,required_date,status)
                   VALUES(?,?,?,?,?,'2099-01-01','DRAFT')""",
                (job_id, part_id, job_number, part_number, "A"),
            ).lastrowid)
            operation_id = int(con.execute(
                """INSERT INTO ezm_operations
                   (plan_id,sequence,work_center,operation,scheduled_date,instruction)
                   VALUES(?,10,'SYN-WC','SYN-OP-10','2099-01-01','Synthetic review')""",
                (plan_id,),
            ).lastrowid)
            ids.append((job_id, part_id, plan_id, operation_id))
            records.append({"Job": job_number, "PartId": str(part_id),
                            "Op": "SYN-OP-10", "Status": "open"})

    _feed(path, records)
    service = IntegrationService()
    first = service.pull(connection_id, "job", actor="synthetic-method-test")
    assert (first["read"], first["applied"], first["skipped"], first["errors"]) == (1000, 1000, 0, 0), first
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed'").fetchone()[0] == 1000
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='job-change'").fetchone()[0] == 1000
        assert con.execute("SELECT COUNT(*) FROM module_suggestions WHERE suggestion_key='job-method-readiness'").fetchone()[0] == 1000
        assert con.execute("SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed' AND status='partial_failure'").fetchone()[0] == 1
        for i, record in enumerate(records):
            row, identity = _history(con, record["Job"])[0]
            assert (identity["job_id"], identity["part_id"], identity["method_plan_id"], identity["operation_id"]) == ids[i]
            assert identity["method_match_status"] == "unique_exact_candidate_review_required"
            assert identity["method_plan_status"] == "DRAFT"
            assert identity["operation_status"] == "matched_methods_candidate_review_required"
            assert identity["operation_sequence"] == 10
            assert identity["human_review_required"] is True

    create_app({"TESTING": True})  # restart recovers the failed receipt
    assert calls["count"] == 1001
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed' AND status='delivered'").fetchone()[0] == 1000
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='job-change'").fetchone()[0] == 1000
        assert con.execute("SELECT COUNT(*) FROM event_delivery_receipts WHERE event_type='job.changed' AND status='delivered'").fetchone()[0] >= 2000

    repeat = service.pull(connection_id, "job", actor="synthetic-method-test")
    assert (repeat["read"], repeat["applied"], repeat["skipped"], repeat["errors"]) == (1000, 0, 1000, 0), repeat
    with db() as con:
        assert con.execute("SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed'").fetchone()[0] == 1000
        second_op = int(con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,20,'SYN-WC','SYN-OP-20','2099-01-01','Synthetic review')""",
            (ids[407][2],),
        ).lastrowid)
    records[407]["Op"] = "SYN-OP-20"
    _feed(path, records)
    changed = service.pull(connection_id, "job", actor="synthetic-method-test")
    assert (changed["read"], changed["applied"], changed["skipped"], changed["errors"]) == (1000, 1, 999, 0), changed
    with db() as con:
        history = _history(con, records[407]["Job"])
        assert len(history) == 2
        assert history[0][1]["operation_id"] == ids[407][3]
        assert history[1][1]["operation_id"] == second_op
        assert history[1][1]["operation_sequence"] == 20
        con.execute("UPDATE parts SET revision='B' WHERE id=?", (ids[407][1],))

    records[407]["Op"] = "SYN-OP-10"
    _feed(path, records)
    stale = service.pull(connection_id, "job", actor="synthetic-method-test")
    assert (stale["applied"], stale["skipped"], stale["errors"]) == (1, 999, 0), stale
    with db() as con:
        history = _history(con, records[407]["Job"])
        assert len(history) == 3
        assert history[-1][1]["part_revision"] == "B"
        assert history[-1][1]["method_match_status"] == "stale_part_revision"
        assert history[-1][1]["operation_id"] is None
        assert history[0][1]["operation_id"] == ids[407][3]
        con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,required_date,status)
               VALUES(?,?,?,?,?,'2099-01-01','DRAFT')""",
            (ids[408][0], ids[408][1], records[408]["Job"], "SYN-METHOD-PART-0408", "A"),
        )
        con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,20,'SYN-WC','SYN-OP-10','2099-01-01','Synthetic duplicate')""",
            (ids[409][2],),
        )
    records[408]["Status"] = "review"
    records[409]["Status"] = "review"
    _feed(path, records)
    conflicts = service.pull(connection_id, "job", actor="synthetic-method-test")
    assert (conflicts["applied"], conflicts["skipped"], conflicts["errors"]) == (2, 998, 0), conflicts
    with db() as con:
        for i, expected in ((408, "ambiguous_method_plans"), (409, "ambiguous_operation_label")):
            identity = _history(con, records[i]["Job"])[-1][1]
            assert identity["method_match_status"] == expected
            assert identity["operation_id"] is None
            assert identity["human_review_required"] is True
        assert con.execute("SELECT COUNT(*) FROM event_ledger WHERE event_type='job.changed'").fetchone()[0] == 1004
        assert con.execute("SELECT COUNT(*) FROM workflow_actions WHERE workflow_key='job-change'").fetchone()[0] == 1004
        assert con.execute("SELECT COUNT(*) FROM ezm_method_plans WHERE status='DRAFT'").fetchone()[0] == 1001


def test_wrong_part_and_unknown_operation_never_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom"))
    monkeypatch.setenv("AXIOM_ACCESS_MODE", "local")
    from superforge.app import create_app
    from superforge.integrations.service import IntegrationService

    create_app({"TESTING": True})
    path = tmp_path / "scope.csv"
    with db() as con:
        connection_id = _connection(con, path)
        part_id = int(con.execute("INSERT INTO parts(part_number,revision) VALUES('SYN-SCOPE-PART','A')").lastrowid)
        other_part_id = int(con.execute("INSERT INTO parts(part_number,revision) VALUES('SYN-OTHER-PART','A')").lastrowid)
        job_id = int(con.execute(
            "INSERT INTO jobs(job_number,part_id,status) VALUES('SYN-SCOPE-WO',?,'seed')", (part_id,),
        ).lastrowid)
        plan_id = int(con.execute(
            """INSERT INTO ezm_method_plans
               (job_id,part_id,job_number,part_number,revision,required_date)
               VALUES(?,?,'SYN-SCOPE-WO','SYN-SCOPE-PART','A','2099-01-01')""",
            (job_id, other_part_id),
        ).lastrowid)
        con.execute(
            """INSERT INTO ezm_operations
               (plan_id,sequence,work_center,operation,scheduled_date,instruction)
               VALUES(?,10,'SYN-WC','SYN-OP-10','2099-01-01','Synthetic')""",
            (plan_id,),
        )
    records = [{"Job": "SYN-SCOPE-WO", "PartId": str(part_id),
                "Op": "SYN-OP-10", "Status": "open"}]
    _feed(path, records)
    result = IntegrationService().pull(connection_id, "job", actor="synthetic-scope-test")
    assert result["applied"] == 1 and result["errors"] == 0, result
    with db() as con:
        identity = _history(con, "SYN-SCOPE-WO")[-1][1]
        assert identity["method_match_status"] == "method_identity_mismatch"
        assert identity["operation_id"] is None
        con.execute("UPDATE ezm_method_plans SET part_id=? WHERE id=?", (part_id, plan_id))
    records[0]["Op"] = "SYN-NOT-IN-METHODS"
    _feed(path, records)
    result = IntegrationService().pull(connection_id, "job", actor="synthetic-scope-test")
    assert result["applied"] == 1 and result["errors"] == 0, result
    with db() as con:
        identity = _history(con, "SYN-SCOPE-WO")[-1][1]
        assert identity["method_match_status"] == "operation_label_not_found"
        assert identity["operation_id"] is None
