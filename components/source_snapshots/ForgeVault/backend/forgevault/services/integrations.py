from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from ..config import settings
from ..models import IntegrationEvent, ReleasePackage, utcnow
from .audit import audit


def export_release_package_to_jobboss2(session: Session, *, release_package_id: UUID, actor: str, mode: str = "outbox") -> IntegrationEvent:
    package = session.get(ReleasePackage, release_package_id)
    if package is None:
        raise ValueError("release package not found")
    payload = {
        "source_system": "ForgeVault",
        "target_system": "JobBOSS2",
        "event": "release_package.ready",
        "package_number": package.package_number,
        "record_id": str(package.record_id),
        "internal_revision": package.internal_revision,
        "customer_revision": package.customer_revision,
        "manifest": package.manifest,
    }
    event = IntegrationEvent(
        external_system="jobboss2",
        event_type="release_package.ready",
        entity_type="release_packages",
        entity_id=str(package.id),
        status="queued",
        payload=payload,
        response={},
        created_by=actor,
    )
    session.add(event)
    session.flush()

    response: dict
    if mode == "webhook" and settings.jobboss2_webhook_url:
        request = urllib.request.Request(
            settings.jobboss2_webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {settings.jobboss2_api_key}"} if settings.jobboss2_api_key else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as result:
            response = {"mode": "webhook", "status_code": result.status, "body": result.read().decode("utf-8", errors="replace")[:2000]}
    else:
        outbox = Path(settings.jobboss2_outbox_root)
        outbox.mkdir(parents=True, exist_ok=True)
        target = outbox / f"{package.package_number}.json"
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        response = {"mode": "outbox", "path": str(target)}

    event.status = "completed"
    event.response = response
    event.completed_at = utcnow()
    audit(session, actor=actor, action="integration.jobboss2.exported", entity_type="integration_events", entity_id=str(event.id), details=response)
    return event
