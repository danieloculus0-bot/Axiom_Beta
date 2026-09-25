"""Activation-trace orchestration for Brain 0.9 wisdom."""

from __future__ import annotations

import json
import uuid

from .meaning_engine import build_meaning_frame, persist_meaning_frame
from .pressure_engine import compute_pressure_delta
from .schema import PRESSURE_DIMENSIONS, init_wisdom_schema
from .trigger_engine import match_triggers, root_trigger


class WisdomActivationEngine:
    def __init__(self, conn=None):
        self.conn = init_wisdom_schema(conn)

    def process_event(self, session_uuid: str, event_summary: str, source_event_id: int | None = None, event_data: dict | None = None) -> dict:
        triggers = match_triggers(event_summary, event_data)
        root = root_trigger(triggers)
        pressure = compute_pressure_delta(triggers, [])
        frame = build_meaning_frame(event_summary, triggers, pressure, (event_data or {}).get("stated_reason"))
        frame_id = persist_meaning_frame(session_uuid, source_event_id, frame, self.conn)
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            """
            INSERT INTO wisdom_activation_traces
            (trace_id, session_uuid, source_event_id, root_trigger, activated_nodes_json,
             pressure_delta_json, meaning_frame_id, evidence_refs_json, uncertainty_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (trace_id, session_uuid, source_event_id, root, json.dumps([t.to_dict() for t in triggers]), json.dumps(pressure), frame_id, json.dumps([source_event_id] if source_event_id is not None else []), float(frame.get("uncertainty_score", 0.5))),
        )
        pressure_id = f"pressure_{uuid.uuid4().hex[:12]}"
        values = [pressure_id, session_uuid, source_event_id] + [pressure.get(name, 0.0) for name in PRESSURE_DIMENSIONS]
        self.conn.execute(
            """
            INSERT INTO wisdom_pressure_states
            (pressure_id, session_uuid, source_event_id, rejection_pressure, abandonment_pressure,
             shame_pressure, trust_damage, uncertainty_load, contradiction_load, belonging_threat,
             future_plan_threat, agency_threat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.conn.commit()
        return {"trace_id": trace_id, "meaning_frame_id": frame_id, "root_trigger": root, "pressure_delta": pressure, "meaning_frame": frame}

    def get_trace(self, trace_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM wisdom_activation_traces WHERE trace_id=?", (trace_id,)).fetchone()
        return dict(row) if row else None
