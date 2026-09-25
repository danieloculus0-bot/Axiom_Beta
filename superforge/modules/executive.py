from __future__ import annotations

import json
from typing import Any

from ..audit import record_event
from ..db import db
from ..event_bus import DomainEvent, subscribe
from .collaboration import accept_suggestion, create_suggestion
from .learning import observe

_REGISTERED = False


def _clamp(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return max(0.0, min(1.0, float(default)))


def _priority_score(value: str) -> float:
    return {
        "critical": 1.0,
        "high": 0.82,
        "normal": 0.55,
        "low": 0.30,
    }.get((value or "").strip().lower(), 0.55)


def _severity_score(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return {
        "critical": 1.0,
        "severe": 0.95,
        "high": 0.82,
        "major": 0.78,
        "medium": 0.58,
        "moderate": 0.55,
        "normal": 0.50,
        "low": 0.30,
        "minor": 0.25,
    }.get(text)


def _event_scores(event: DomainEvent, protocol: dict[str, Any]) -> tuple[float, float, float, float]:
    payload = event.payload or {}
    impact = _clamp(payload.get("impact_score"), float(protocol["default_impact"] or 0.5))
    urgency = _clamp(payload.get("urgency_score"), float(protocol["default_urgency"] or 0.5))
    confidence = _clamp(payload.get("confidence"), float(protocol["confidence_floor"] or 0.5))

    severity = _severity_score(payload.get("severity") or payload.get("risk_level") or payload.get("priority"))
    if severity is not None:
        impact = max(impact, severity)

    try:
        days_late = float(payload.get("days_late") or payload.get("days_overdue") or 0)
    except (TypeError, ValueError):
        days_late = 0
    if days_late > 0:
        urgency = max(urgency, min(1.0, 0.55 + min(days_late, 30) * 0.015))

    priority_component = _priority_score(protocol.get("priority") or "normal")
    impact = max(impact, priority_component * 0.75)
    score = round(100.0 * impact * urgency * confidence, 2)
    return impact, urgency, confidence, score


def resolve_role_assignee(role_key: str) -> dict[str, Any] | None:
    role_key = (role_key or "").strip()
    if not role_key:
        return None
    with db() as con:
        row = con.execute(
            """SELECT p.id person_id,p.person_key,p.display_name,p.email,
                      r.id role_id,r.role_key,r.title,r.authority_level
               FROM org_roles r
               JOIN org_assignments a ON a.role_id=r.id AND a.active=1
               JOIN org_people p ON p.id=a.person_id AND p.active=1
               WHERE r.role_key=? AND r.active=1
               ORDER BY a.is_primary DESC,a.id
               LIMIT 1""",
            (role_key,),
        ).fetchone()
    return dict(row) if row else None


def _format(template: str, event: DomainEvent) -> str:
    mapping = {
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "source_module": event.source_module,
        **{str(k): v for k, v in (event.payload or {}).items()},
    }

    class Safe(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    try:
        return str(template or "").format_map(Safe(mapping))
    except Exception:
        return str(template or "")


def _protocols_for(event: DomainEvent) -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute(
            """SELECT * FROM decision_protocols
               WHERE active=1
                 AND event_type=?
                 AND (COALESCE(source_module,'')='' OR source_module=?)
               ORDER BY id""",
            (event.event_type, event.source_module),
        ).fetchall()
    return [dict(row) for row in rows]


def _executive_handler(event: DomainEvent) -> None:
    if event.source_module == "executive" or event.event_type.startswith("executive."):
        return
    for protocol in _protocols_for(event):
        impact, urgency, confidence, score = _event_scores(event, protocol)
        assignee = resolve_role_assignee(protocol.get("target_role_key") or "")
        evidence = {
            "executive_protocol_id": int(protocol["id"]),
            "protocol_name": protocol["name"],
            "signal_type": protocol["signal_type"],
            "target_role_key": protocol.get("target_role_key") or "",
            "resolved_person_key": "" if assignee is None else assignee.get("person_key") or "",
            "resolved_person": "" if assignee is None else assignee.get("display_name") or "",
            "impact": impact,
            "urgency": urgency,
            "confidence": confidence,
            "weighted_impact_score": score,
            "escalation_hours": int(protocol["escalation_hours"] or 0),
            "source_payload": event.payload or {},
        }
        create_suggestion(
            event,
            target_module=protocol["target_module"],
            suggestion_key=f"exec:{protocol['id']}",
            title=_format(protocol["title_template"], event),
            rationale=_format(protocol["rationale_template"], event),
            recommended_action=_format(protocol["action_template"], event),
            priority=protocol["priority"],
            evidence=evidence,
        )


def register_executive_logic() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe("*", _executive_handler)
    _REGISTERED = True


def upsert_person(
    person_key: str,
    display_name: str,
    *,
    email: str = "",
    actor: str = "local",
) -> int:
    person_key = (person_key or "").strip()
    display_name = (display_name or "").strip()
    if not person_key or not display_name:
        raise ValueError("person key and display name are required")
    with db() as con:
        con.execute(
            """INSERT INTO org_people(person_key,display_name,email,active)
               VALUES(?,?,?,1)
               ON CONFLICT(person_key) DO UPDATE SET
                 display_name=excluded.display_name,email=excluded.email,
                 active=1,updated_at=CURRENT_TIMESTAMP""",
            (person_key, display_name, email or ""),
        )
        person_id = int(
            con.execute("SELECT id FROM org_people WHERE person_key=?", (person_key,)).fetchone()["id"]
        )
    record_event(
        event_type="ORG_PERSON",
        action="UPSERT",
        module="executive",
        entity_type="org_person",
        entity_id=person_id,
        actor=actor,
        data={"person_key": person_key, "display_name": display_name, "email": email},
    )
    return person_id


def assign_person_to_role(
    person_key: str,
    role_key: str,
    *,
    primary: bool = True,
    actor: str = "local",
) -> int:
    with db() as con:
        person = con.execute("SELECT id FROM org_people WHERE person_key=? AND active=1", (person_key,)).fetchone()
        role = con.execute("SELECT id FROM org_roles WHERE role_key=? AND active=1", (role_key,)).fetchone()
        if not person:
            raise ValueError("person not found")
        if not role:
            raise ValueError("role not found")
        if primary:
            con.execute("UPDATE org_assignments SET is_primary=0 WHERE role_id=? AND active=1", (int(role["id"]),))
        con.execute(
            """INSERT INTO org_assignments(person_id,role_id,is_primary,active)
               VALUES(?,?,?,1)
               ON CONFLICT(person_id,role_id) DO UPDATE SET
                 is_primary=excluded.is_primary,active=1""",
            (int(person["id"]), int(role["id"]), 1 if primary else 0),
        )
        assignment_id = int(
            con.execute(
                "SELECT id FROM org_assignments WHERE person_id=? AND role_id=?",
                (int(person["id"]), int(role["id"])),
            ).fetchone()["id"]
        )
    record_event(
        event_type="ORG_ASSIGNMENT",
        action="ASSIGN",
        module="executive",
        entity_type="org_assignment",
        entity_id=assignment_id,
        actor=actor,
        data={"person_key": person_key, "role_key": role_key, "primary": bool(primary)},
    )
    return assignment_id


def create_decision_protocol(data: dict[str, Any], *, actor: str = "local") -> int:
    name = (data.get("name") or "").strip()
    event_type = (data.get("event_type") or "").strip()
    if not name or not event_type:
        raise ValueError("protocol name and event type are required")
    with db() as con:
        cur = con.execute(
            """INSERT INTO decision_protocols(
                 name,event_type,source_module,target_module,target_role_key,signal_type,
                 title_template,rationale_template,action_template,priority,default_impact,
                 default_urgency,confidence_floor,escalation_hours,active,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (
                name,
                event_type,
                (data.get("source_module") or "").strip(),
                (data.get("target_module") or "leadership").strip(),
                (data.get("target_role_key") or "").strip(),
                (data.get("signal_type") or "operational").strip(),
                (data.get("title_template") or "Executive review required").strip(),
                (data.get("rationale_template") or "The event crossed a configured decision protocol.").strip(),
                (data.get("action_template") or "Review the event and assign a controlled response.").strip(),
                (data.get("priority") or "normal").strip().lower(),
                _clamp(data.get("default_impact"), 0.5),
                _clamp(data.get("default_urgency"), 0.5),
                _clamp(data.get("confidence_floor"), 0.5),
                max(0, int(data.get("escalation_hours") or 24)),
                data.get("notes") or "",
            ),
        )
        protocol_id = int(cur.lastrowid)
    record_event(
        event_type="DECISION_PROTOCOL",
        action="CREATE",
        module="executive",
        entity_type="decision_protocol",
        entity_id=protocol_id,
        actor=actor,
        data={"name": name, "event_type": event_type, "target_role_key": data.get("target_role_key") or ""},
    )
    return protocol_id


def executive_suggestions() -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute(
            """SELECT * FROM module_suggestions
               WHERE status='open' AND suggestion_key LIKE 'exec:%'
               ORDER BY id DESC"""
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        try:
            evidence = json.loads(d.get("evidence_json") or "{}")
        except Exception:
            evidence = {}
        d["evidence"] = evidence
        d["weighted_impact_score"] = float(evidence.get("weighted_impact_score") or 0)
        d["target_role_key"] = evidence.get("target_role_key") or ""
        result.append(d)
    return sorted(result, key=lambda x: (x["weighted_impact_score"], x["id"]), reverse=True)


def pareto_queue() -> dict[str, Any]:
    rows = executive_suggestions()
    total = sum(max(0.0, float(row["weighted_impact_score"])) for row in rows)
    selected: list[dict[str, Any]] = []
    cumulative = 0.0
    if rows and total <= 0:
        selected = rows[:1]
    else:
        for row in rows:
            selected.append(row)
            cumulative += max(0.0, float(row["weighted_impact_score"]))
            if total and cumulative / total >= 0.80:
                break
    return {
        "open_count": len(rows),
        "pareto_count": len(selected),
        "total_weighted_impact": round(total, 2),
        "pareto_weighted_impact": round(cumulative, 2),
        "pareto_impact_share": 0 if total <= 0 else round(cumulative / total, 4),
        "pareto_signal_share": 0 if not rows else round(len(selected) / len(rows), 4),
        "signals": selected,
    }


def accept_executive_suggestion(suggestion_id: int, *, actor: str = "local") -> int:
    with db() as con:
        row = con.execute("SELECT evidence_json FROM module_suggestions WHERE id=?", (int(suggestion_id),)).fetchone()
    if not row:
        raise ValueError("suggestion not found")
    try:
        evidence = json.loads(row["evidence_json"] or "{}")
    except Exception:
        evidence = {}
    assignee = resolve_role_assignee(evidence.get("target_role_key") or "")
    assigned_to = ""
    if assignee:
        assigned_to = assignee.get("email") or assignee.get("display_name") or assignee.get("person_key") or ""
    action_id = accept_suggestion(int(suggestion_id), actor=actor, assigned_to=assigned_to)
    record_event(
        event_type="EXECUTIVE_RECOMMENDATION",
        action="ACCEPTED",
        module="executive",
        entity_type="module_suggestion",
        entity_id=suggestion_id,
        actor=actor,
        data={"workflow_action_id": action_id, "assigned_to": assigned_to, "target_role_key": evidence.get("target_role_key") or ""},
    )
    return action_id


def capture_executive_outcome(
    suggestion_id: int,
    *,
    outcome: str,
    human_rating: float | None = None,
    actor: str = "local",
) -> int:
    with db() as con:
        row = con.execute("SELECT * FROM module_suggestions WHERE id=?", (int(suggestion_id),)).fetchone()
    if not row:
        raise ValueError("suggestion not found")
    try:
        evidence = json.loads(row["evidence_json"] or "{}")
    except Exception:
        evidence = {}
    observation_id = observe(
        f"executive:{evidence.get('executive_protocol_id') or 'unknown'}",
        {
            "suggestion_id": int(suggestion_id),
            "source_event_id": row["source_event_id"],
            "source_module": row["source_module"],
            "target_module": row["target_module"],
            "priority": row["priority"],
            "weighted_impact_score": evidence.get("weighted_impact_score"),
            "protocol_name": evidence.get("protocol_name"),
            "target_role_key": evidence.get("target_role_key"),
        },
        outcome=outcome,
        confidence=float(evidence.get("confidence") or 0.5),
        source_event_id=row["source_event_id"],
        human_rating=human_rating,
    )
    record_event(
        event_type="EXECUTIVE_OUTCOME",
        action="CAPTURE",
        module="executive",
        entity_type="module_suggestion",
        entity_id=suggestion_id,
        actor=actor,
        reason=outcome,
        data={"learning_observation_id": observation_id, "human_rating": human_rating},
    )
    return observation_id


def organization_snapshot() -> dict[str, Any]:
    with db() as con:
        units = [dict(r) for r in con.execute(
            """SELECT u.*,p.unit_key parent_unit_key
               FROM org_units u LEFT JOIN org_units p ON p.id=u.parent_unit_id
               WHERE u.active=1 ORDER BY COALESCE(p.name,''),u.name"""
        )]
        roles = [dict(r) for r in con.execute(
            """SELECT r.*,u.unit_key,u.name unit_name,pr.role_key parent_role_key,
                      p.person_key,p.display_name,p.email
               FROM org_roles r
               LEFT JOIN org_units u ON u.id=r.unit_id
               LEFT JOIN org_roles pr ON pr.id=r.parent_role_id
               LEFT JOIN org_assignments a ON a.role_id=r.id AND a.active=1 AND a.is_primary=1
               LEFT JOIN org_people p ON p.id=a.person_id AND p.active=1
               WHERE r.active=1 ORDER BY r.authority_level DESC,r.title"""
        )]
        protocols = [dict(r) for r in con.execute(
            "SELECT * FROM decision_protocols WHERE active=1 ORDER BY priority DESC,event_type,name"
        )]
    return {"units": units, "roles": roles, "protocols": protocols, "pareto": pareto_queue()}
