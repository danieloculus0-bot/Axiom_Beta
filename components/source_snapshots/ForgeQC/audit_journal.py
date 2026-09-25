from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import audit_journal_path


_LOCK = threading.RLock()
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SENSITIVE_NAMES = {"password", "secret", "token", "api_key", "apikey"}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_record(record):
    return hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()


def _safe_request_context():
    try:
        from flask import has_request_context, request
        if not has_request_context():
            return {}
        return {
            "request_id": getattr(request, "_forgeqc_audit_request_id", ""),
            "method": request.method,
            "path": request.path,
            "remote_addr": request.remote_addr or "",
            "user_agent": (request.user_agent.string or "")[:500],
            "actor_header": (request.headers.get("X-ForgeQC-User") or "")[:160],
        }
    except Exception:
        return {}


def _tail_state(path: Path):
    if not path.exists() or path.stat().st_size == 0:
        return 0, "GENESIS"
    last = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = line
    if not last:
        return 0, "GENESIS"
    try:
        record = json.loads(last)
        return int(record.get("sequence", 0)), str(record.get("entry_hash") or "GENESIS")
    except Exception:
        return 0, "CORRUPT_TAIL"


def record_event(
    event_type,
    action,
    *,
    entity_type="",
    entity_id="",
    detail="",
    data=None,
    actor="",
):
    path = audit_journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        sequence, previous_hash = _tail_state(path)
        request_context = _safe_request_context()
        actor_value = str(actor or request_context.get("actor_header") or "").strip()
        record = {
            "sequence": sequence + 1,
            "timestamp_utc": _utc_now(),
            "event_type": str(event_type or "EVENT")[:120],
            "action": str(action or "")[:240],
            "entity_type": str(entity_type or "")[:120],
            "entity_id": str(entity_id or "")[:160],
            "actor": actor_value[:160],
            "detail": str(detail or "")[:4000],
            "data": data if isinstance(data, (dict, list, str, int, float, bool, type(None))) else str(data),
            "request": request_context,
            "previous_hash": previous_hash,
        }
        record["entry_hash"] = _hash_record(record)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record


def model_snapshot(row):
    snapshot = {}
    table = getattr(row, "__table__", None)
    if table is None:
        return snapshot
    for column in table.columns:
        value = getattr(row, column.name, None)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        snapshot[column.name] = value
    return snapshot


def verify_journal(path=None):
    path = Path(path or audit_journal_path())
    if not path.exists():
        return {"ok": True, "entries": 0, "last_hash": "GENESIS", "path": str(path)}
    previous_hash = "GENESIS"
    entries = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception as exc:
                return {"ok": False, "entries": entries, "line": line_number, "error": f"Invalid JSON: {exc}", "path": str(path)}
            claimed = record.get("entry_hash")
            stored_previous = record.get("previous_hash")
            if stored_previous != previous_hash:
                return {"ok": False, "entries": entries, "line": line_number, "error": "Previous hash mismatch", "path": str(path)}
            check_record = dict(record)
            check_record.pop("entry_hash", None)
            calculated = _hash_record(check_record)
            if calculated != claimed:
                return {"ok": False, "entries": entries, "line": line_number, "error": "Entry hash mismatch", "path": str(path)}
            previous_hash = claimed
            entries += 1
    return {"ok": True, "entries": entries, "last_hash": previous_hash, "path": str(path)}


def tail_entries(limit=50):
    path = audit_journal_path()
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"event_type": "JOURNAL ERROR", "detail": "Unreadable journal entry"})
    return rows[-max(1, int(limit)):]


def _sanitized_form(request):
    result = {}
    for key in request.form.keys():
        lower = key.lower()
        if any(marker in lower for marker in _SENSITIVE_NAMES):
            result[key] = "[REDACTED]"
        else:
            values = request.form.getlist(key)
            result[key] = values if len(values) > 1 else (values[0] if values else "")
    if request.files:
        result["_files"] = {name: (f.filename or "") for name, f in request.files.items()}
    return result


def register_request_audit(app):
    from flask import request

    @app.before_request
    def _forgeqc_assign_request_id():
        request._forgeqc_audit_request_id = uuid.uuid4().hex

    @app.after_request
    def _forgeqc_audit_mutation(response):
        if request.method in _MUTATING_METHODS:
            try:
                record_event(
                    "HTTP_MUTATION",
                    request.method,
                    entity_type="ROUTE",
                    entity_id=request.path,
                    detail=f"HTTP {response.status_code}",
                    data={"status": response.status_code, "form": _sanitized_form(request)},
                )
            except Exception:
                pass
        return response
