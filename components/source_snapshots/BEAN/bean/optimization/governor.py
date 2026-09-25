"""Persistent supervised self-optimization governor for Brain 0.14.

This module can create, review, and summarize improvement proposals. It has no
execution path. Approved records remain instructions for a supervisor or a
separately controlled sandbox runner.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from .proposal import OptimizationProposal

SCHEMA = """
CREATE TABLE IF NOT EXISTS optimization_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL UNIQUE,
    session_uuid TEXT NOT NULL,
    title TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    proposed_change TEXT NOT NULL,
    target_layer TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    expected_benefit TEXT NOT NULL,
    expected_cost TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    validation_plan TEXT NOT NULL,
    rollback_plan TEXT NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    execution_permission TEXT NOT NULL DEFAULT 'proposal_only',
    reviewed_by TEXT,
    review_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','utc'))
);

CREATE TABLE IF NOT EXISTS optimization_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT NOT NULL UNIQUE,
    proposal_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    decision TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    previous_execution_permission TEXT NOT NULL,
    new_execution_permission TEXT NOT NULL,
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
    FOREIGN KEY(proposal_id) REFERENCES optimization_proposals(proposal_id)
);
"""

REVIEW_DECISIONS = {
    "approve_sandbox": ("approved_for_sandbox_test", "sandbox_test_only"),
    "approve_human": ("approved_for_human_execution", "human_execution_only"),
    "request_revision": ("revision_requested", "proposal_only"),
    "defer": ("deferred", "proposal_only"),
    "reject": ("rejected", "proposal_only"),
}


def init_self_optimization_schema(conn=None):
    if conn is None:
        from ..memory.store import get_store

        conn = get_store()._conn()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _decode_row(row) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    data["evidence_refs"] = json.loads(data.pop("evidence_refs_json"))
    data["alternatives"] = json.loads(data.pop("alternatives_json"))
    data["auto_executed"] = False
    data["motion_command_generated"] = False
    data["requires_supervisor_execution"] = True
    return data


class SelfOptimizationGovernor:
    """Stores improvement proposals and supervisor decisions without executing them."""

    def __init__(self, conn=None):
        self.conn = init_self_optimization_schema(conn)

    def create_proposal(
        self,
        *,
        session_uuid: str,
        title: str,
        problem_statement: str,
        proposed_change: str,
        target_layer: str,
        proposal_type: str,
        expected_benefit: str,
        expected_cost: str,
        risk_level: str,
        validation_plan: str,
        rollback_plan: str,
        created_by: str = "bean",
        evidence_refs: Optional[list[str]] = None,
        alternatives: Optional[list[str]] = None,
    ) -> dict:
        proposal = OptimizationProposal(
            session_uuid=session_uuid,
            title=title,
            problem_statement=problem_statement,
            proposed_change=proposed_change,
            target_layer=target_layer,
            proposal_type=proposal_type,
            expected_benefit=expected_benefit,
            expected_cost=expected_cost,
            risk_level=risk_level,
            validation_plan=validation_plan,
            rollback_plan=rollback_plan,
            created_by=created_by,
            evidence_refs=list(evidence_refs or []),
            alternatives=list(alternatives or []),
        )
        self.conn.execute(
            """
            INSERT INTO optimization_proposals (
                proposal_id, session_uuid, title, problem_statement,
                proposed_change, target_layer, proposal_type,
                expected_benefit, expected_cost, risk_level,
                evidence_refs_json, alternatives_json, validation_plan,
                rollback_plan, created_by, status, execution_permission,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.proposal_id,
                proposal.session_uuid,
                proposal.title,
                proposal.problem_statement,
                proposal.proposed_change,
                proposal.target_layer,
                proposal.proposal_type,
                proposal.expected_benefit,
                proposal.expected_cost,
                proposal.risk_level,
                json.dumps(proposal.evidence_refs),
                json.dumps(proposal.alternatives),
                proposal.validation_plan,
                proposal.rollback_plan,
                proposal.created_by,
                proposal.status,
                proposal.execution_permission,
                proposal.created_at,
            ),
        )
        self.conn.commit()
        return self.get_proposal(proposal.proposal_id)

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM optimization_proposals WHERE proposal_id=?",
            (proposal_id,),
        ).fetchone()
        return _decode_row(row)

    def list_proposals(self, *, status: str | None = None, limit: int = 25) -> list[dict]:
        bounded_limit = max(1, min(int(limit), 250))
        if status:
            rows = self.conn.execute(
                "SELECT * FROM optimization_proposals WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, bounded_limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM optimization_proposals ORDER BY id DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [_decode_row(row) for row in rows]

    def review_proposal(
        self,
        proposal_id: str,
        *,
        decision: str,
        reviewer: str,
        notes: str,
    ) -> dict:
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"invalid review decision: {decision}")
        if not str(reviewer).strip():
            raise ValueError("reviewer is required")
        if not str(notes).strip():
            raise ValueError("review notes are required")

        current = self.get_proposal(proposal_id)
        if current is None:
            raise ValueError(f"proposal not found: {proposal_id}")

        new_status, new_permission = REVIEW_DECISIONS[decision]
        review_id = f"optrev_{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            """
            INSERT INTO optimization_reviews (
                review_id, proposal_id, reviewer, decision,
                previous_status, new_status,
                previous_execution_permission, new_execution_permission,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                proposal_id,
                reviewer,
                decision,
                current["status"],
                new_status,
                current["execution_permission"],
                new_permission,
                notes,
            ),
        )
        self.conn.execute(
            """
            UPDATE optimization_proposals
            SET status=?, execution_permission=?, reviewed_by=?,
                review_notes=?, updated_at=datetime('now','utc')
            WHERE proposal_id=?
            """,
            (new_status, new_permission, reviewer, notes, proposal_id),
        )
        self.conn.commit()
        result = self.get_proposal(proposal_id)
        result["review_id"] = review_id
        result["decision"] = decision
        return result

    def mark_outcome(
        self,
        proposal_id: str,
        *,
        outcome: str,
        reviewer: str,
        notes: str,
    ) -> dict:
        outcome_to_status = {
            "implemented": "implemented",
            "validated": "validated",
            "rolled_back": "rolled_back",
            "superseded": "superseded",
        }
        if outcome not in outcome_to_status:
            raise ValueError(f"invalid outcome: {outcome}")
        current = self.get_proposal(proposal_id)
        if current is None:
            raise ValueError(f"proposal not found: {proposal_id}")
        if current["status"] not in {
            "approved_for_sandbox_test",
            "approved_for_human_execution",
            "implemented",
            "validated",
        }:
            raise ValueError("proposal must be approved before an outcome can be recorded")
        return self._record_outcome(
            proposal_id,
            new_status=outcome_to_status[outcome],
            reviewer=reviewer,
            notes=notes,
            previous=current,
        )

    def _record_outcome(self, proposal_id: str, *, new_status: str, reviewer: str, notes: str, previous: dict) -> dict:
        if not str(reviewer).strip() or not str(notes).strip():
            raise ValueError("reviewer and notes are required")
        review_id = f"optrev_{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            """
            INSERT INTO optimization_reviews (
                review_id, proposal_id, reviewer, decision,
                previous_status, new_status,
                previous_execution_permission, new_execution_permission,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                proposal_id,
                reviewer,
                f"record_{new_status}",
                previous["status"],
                new_status,
                previous["execution_permission"],
                previous["execution_permission"],
                notes,
            ),
        )
        self.conn.execute(
            """
            UPDATE optimization_proposals
            SET status=?, reviewed_by=?, review_notes=?, updated_at=datetime('now','utc')
            WHERE proposal_id=?
            """,
            (new_status, reviewer, notes, proposal_id),
        )
        self.conn.commit()
        result = self.get_proposal(proposal_id)
        result["review_id"] = review_id
        return result

    def build_summary(self) -> dict:
        status_rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM optimization_proposals GROUP BY status"
        ).fetchall()
        risk_rows = self.conn.execute(
            "SELECT risk_level, COUNT(*) AS n FROM optimization_proposals GROUP BY risk_level"
        ).fetchall()
        return {
            "proposal_count": sum(int(row["n"]) for row in status_rows),
            "by_status": {row["status"]: int(row["n"]) for row in status_rows},
            "by_risk": {row["risk_level"]: int(row["n"]) for row in risk_rows},
            "auto_execution_available": False,
            "motion_enabled": False,
        }
