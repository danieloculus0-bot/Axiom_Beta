"""
bean/world/world_model.py

BEAN's structured beliefs about its environment.
Only sourced claims. Unknowns are first-class claims.
"""

from __future__ import annotations

import json
from typing import Optional

from .claim import Claim, ClaimCategory, ClaimSource, make_claim
from .model_store import ModelStore


class WorldModel:
    def __init__(self, store: Optional[ModelStore] = None):
        self._store = store or ModelStore()

    def update(self, session_uuid: str) -> list[Claim]:
        claims: list[Claim] = []
        claims.extend(self._derive_observations())
        claims.extend(self._derive_presence())
        claims.extend(self._derive_uncertainties())
        self._store.save_many(claims)
        return claims

    def get(self, key: str) -> Optional[Claim]:
        return self._store.get_active(key)

    def get_value(self, key: str, default=None):
        claim = self.get(key)
        return claim.parsed_value(default) if claim else default

    def add_supervisor_claim(self, key: str, content: str, session_uuid: str, confidence: float = 0.9, value=None, notes: str = "") -> Claim:
        from ..memory.event_logger import log_event, EventType, Source
        claim = make_claim(
            key=key,
            content=content,
            category=ClaimCategory.ENVIRONMENT,
            source_type=ClaimSource.SUPERVISOR,
            confidence=confidence,
            value=value,
            notes=notes,
        )
        self._store.save(claim)
        log_event(
            session_uuid=session_uuid,
            event_type=EventType.WORLD_MODEL_UPDATE,
            subtype="supervisor_claim",
            summary=f"World model updated by supervisor: {key}",
            source=Source.HUMAN,
            data=claim.to_dict(),
        )
        return claim

    def all_claims(self) -> list[Claim]:
        return [claim for claim in self._store.get_all_active() if not claim.key.startswith("self.")]

    def snapshot(self) -> dict:
        claims = self.all_claims()
        return {
            "claim_count": len(claims),
            "claims": {
                claim.key: {
                    "content": claim.content,
                    "confidence": claim.confidence,
                    "source": claim.source_type.value,
                    "value": claim.parsed_value(),
                }
                for claim in sorted(claims, key=lambda c: c.key)
            },
        }

    def _derive_observations(self) -> list[Claim]:
        events = self._fetchone("SELECT COUNT(*) as n FROM events WHERE event_type='sensor_reading'")["n"]
        records = self._fetchone("SELECT COUNT(*) as n FROM observations")["n"]
        sensor_rows = self._fetchall("SELECT DISTINCT subtype FROM events WHERE event_type='sensor_reading' AND subtype IS NOT NULL")
        table_rows = self._fetchall("SELECT DISTINCT sensor FROM observations")
        sensors = sorted({r["subtype"] for r in sensor_rows if r["subtype"]} | {r["sensor"] for r in table_rows if r["sensor"]})
        claims = [
            make_claim("environment.observations.total_count", f"I have logged {events} sensor reading event(s) and {records} observation record(s)." if events or records else "I have not logged any sensor readings or observations yet.", ClaimCategory.ENVIRONMENT, ClaimSource.EVENT_LOG, 1.0, {"event_count": events, "record_count": records}),
            make_claim("environment.observations.sensor_types", f"Sensors that have produced logged data: {', '.join(sensors)}." if sensors else "No sensors have produced logged data yet.", ClaimCategory.ENVIRONMENT, ClaimSource.EVENT_LOG, 1.0, sensors),
        ]
        last = self._fetchone("SELECT created_at FROM events WHERE event_type='sensor_reading' ORDER BY id DESC LIMIT 1")
        if last:
            claims.append(make_claim("environment.observations.last_at", f"My most recent sensor reading was at {last['created_at']}.", ClaimCategory.ENVIRONMENT, ClaimSource.EVENT_LOG, 1.0, last["created_at"]))
        return claims

    def _derive_presence(self) -> list[Claim]:
        interactions = self._fetchone("SELECT COUNT(*) as n FROM events WHERE source='human'")["n"]
        last = self._fetchone("SELECT created_at FROM events WHERE source='human' ORDER BY id DESC LIMIT 1")
        supervisors = [r["name"] for r in self._fetchall("SELECT name FROM supervisors WHERE active=1 ORDER BY name")]
        claims = [
            make_claim("environment.presence.interaction_count", f"I have received {interactions} human-sourced event(s)." if interactions else "I have not recorded any human interaction events yet.", ClaimCategory.RELATIONAL, ClaimSource.EVENT_LOG, 1.0, interactions),
            make_claim("environment.presence.registered_supervisors", f"My registered supervisors are: {', '.join(supervisors)}." if supervisors else "No supervisors are registered.", ClaimCategory.RELATIONAL, ClaimSource.BOOTSTRAP, 1.0, supervisors),
        ]
        if last:
            claims.append(make_claim("environment.presence.last_interaction_at", f"The most recent human interaction was at {last['created_at']}.", ClaimCategory.RELATIONAL, ClaimSource.EVENT_LOG, 1.0, last["created_at"]))
        return claims

    def _derive_uncertainties(self) -> list[Claim]:
        has_vision = self._fetchone("""
            SELECT COUNT(*) as n FROM events
            WHERE event_type='sensor_reading'
            AND (subtype LIKE '%camera%' OR subtype LIKE '%vision%' OR subtype LIKE '%image%')
        """)["n"] > 0
        has_audio = self._fetchone("""
            SELECT COUNT(*) as n FROM events
            WHERE event_type='sensor_reading'
            AND (subtype LIKE '%audio%' OR subtype LIKE '%microphone%' OR subtype LIKE '%sound%')
        """)["n"] > 0
        body_rows = self._fetchone("SELECT COUNT(*) as n FROM body_state")["n"]
        claims = [
            make_claim("environment.uncertainty.no_spatial_map", "I have no map of my physical environment. I do not know the dimensions, layout, or contents of my space.", ClaimCategory.UNCERTAINTY, ClaimSource.BOOTSTRAP, 1.0),
        ]
        if not has_vision:
            claims.append(make_claim("environment.uncertainty.no_vision", "I have no camera data in memory. I cannot make visual claims about my environment yet.", ClaimCategory.UNCERTAINTY, ClaimSource.EVENT_LOG, 1.0))
        if not has_audio:
            claims.append(make_claim("environment.uncertainty.no_audio", "I have no audio localization data in memory. I cannot locate sound sources yet.", ClaimCategory.UNCERTAINTY, ClaimSource.EVENT_LOG, 1.0))
        if body_rows:
            latest = self._fetchone("SELECT temperature_c, cpu_percent, created_at FROM body_state ORDER BY id DESC LIMIT 1")
            claims.append(make_claim("environment.sensor_status.hardware_monitor", f"My hardware health monitor has logged {body_rows} reading(s).", ClaimCategory.ENVIRONMENT, ClaimSource.EVENT_LOG, 0.9, dict(latest) if latest else None))
        else:
            claims.append(make_claim("environment.uncertainty.sensor_status", "No hardware health readings have been logged yet.", ClaimCategory.UNCERTAINTY, ClaimSource.EVENT_LOG, 1.0))
        return claims

    def _fetchone(self, sql: str, params=()):
        from ..memory.store import get_store
        return get_store().fetchone(sql, params)

    def _fetchall(self, sql: str, params=()):
        from ..memory.store import get_store
        return get_store().fetchall(sql, params)
