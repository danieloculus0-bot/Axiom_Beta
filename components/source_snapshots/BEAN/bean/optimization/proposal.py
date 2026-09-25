"""Data model and vocabulary for Brain 0.14 self-optimization proposals."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

VALID_TARGET_LAYERS = {
    "memory",
    "reasoning",
    "runtime",
    "safety",
    "sensor",
    "software",
    "workflow",
    "hardware",
    "embodiment",
}

VALID_PROPOSAL_TYPES = {
    "configuration_change",
    "code_change",
    "experiment",
    "hardware_change",
    "process_change",
}

VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_STATUSES = {
    "proposed",
    "approved_for_sandbox_test",
    "approved_for_human_execution",
    "revision_requested",
    "deferred",
    "rejected",
    "implemented",
    "validated",
    "rolled_back",
    "superseded",
}
VALID_EXECUTION_PERMISSIONS = {
    "proposal_only",
    "sandbox_test_only",
    "human_execution_only",
}


@dataclass
class OptimizationProposal:
    session_uuid: str
    title: str
    problem_statement: str
    proposed_change: str
    target_layer: str
    proposal_type: str
    expected_benefit: str
    expected_cost: str
    risk_level: str
    validation_plan: str
    rollback_plan: str
    created_by: str = "bean"
    evidence_refs: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    proposal_id: str = field(default_factory=lambda: f"opt_{uuid.uuid4().hex[:12]}")
    status: str = "proposed"
    execution_permission: str = "proposal_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        required_text = {
            "session_uuid": self.session_uuid,
            "title": self.title,
            "problem_statement": self.problem_statement,
            "proposed_change": self.proposed_change,
            "expected_benefit": self.expected_benefit,
            "expected_cost": self.expected_cost,
            "validation_plan": self.validation_plan,
            "rollback_plan": self.rollback_plan,
            "created_by": self.created_by,
        }
        missing = [name for name, value in required_text.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"missing required proposal fields: {', '.join(missing)}")
        if self.target_layer not in VALID_TARGET_LAYERS:
            raise ValueError(f"invalid target_layer: {self.target_layer}")
        if self.proposal_type not in VALID_PROPOSAL_TYPES:
            raise ValueError(f"invalid proposal_type: {self.proposal_type}")
        if self.risk_level not in VALID_RISK_LEVELS:
            raise ValueError(f"invalid risk_level: {self.risk_level}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status}")
        if self.execution_permission not in VALID_EXECUTION_PERMISSIONS:
            raise ValueError(f"invalid execution_permission: {self.execution_permission}")

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        data["auto_executed"] = False
        data["motion_command_generated"] = False
        data["requires_supervisor_execution"] = True
        return data
