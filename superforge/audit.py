from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_paths import audit_journal_path

_LOCK = threading.RLock()
GENESIS = "GENESIS"
SENSITIVE = {"password","secret","token","api_key","apikey","client_secret"}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False, default=str)

def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result={}
        for key,item in value.items():
            result[key] = "[REDACTED]" if any(marker in str(key).lower() for marker in SENSITIVE) else sanitize(item)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value

def _tail(path: Path) -> tuple[int,str]:
    if not path.exists() or path.stat().st_size == 0:
        return 0,GENESIS
    last=None
    with path.open("r",encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last=line
    if not last:
        return 0,GENESIS
    row=json.loads(last)
    return int(row["sequence"]),str(row["entry_hash"])

def record_event(
    *,
    event_type: str,
    action: str,
    module: str,
    entity_type: str="",
    entity_id: str="",
    actor: str="",
    reason: str="",
    before: Any=None,
    after: Any=None,
    data: Any=None,
    event_id: str|None=None,
    parent_event_id: str="",
    correlation_id: str="",
    source_module: str|None=None,
    target_module: str|None=None,
) -> dict:
    path=audit_journal_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    with _LOCK:
        sequence,previous_hash=_tail(path)
        row={
            "sequence":sequence+1,
            "timestamp_utc":utc_now(),
            "event_id":event_id or f"evt_{uuid.uuid4().hex}",
            "parent_event_id":parent_event_id or "",
            "correlation_id":correlation_id or "",
            "event_type":str(event_type)[:120],
            "action":str(action)[:240],
            "module":str(module)[:120],
            "source_module":str(source_module or module)[:120],
            "target_module":str(target_module or module)[:120],
            "entity_type":str(entity_type)[:120],
            "entity_id":str(entity_id)[:200],
            "actor":str(actor)[:200],
            "reason":str(reason)[:4000],
            "before":sanitize(before),
            "after":sanitize(after),
            "data":sanitize(data),
            "previous_hash":previous_hash,
        }
        row["before_hash"]=digest(row["before"]) if before is not None else ""
        row["after_hash"]=digest(row["after"]) if after is not None else ""
        row["entry_hash"]=digest(row)
        with path.open("a",encoding="utf-8",newline="\n") as handle:
            handle.write(json.dumps(row,sort_keys=True,ensure_ascii=False,default=str)+"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return row

def verify_journal(path: str|Path|None=None) -> dict:
    path=Path(path or audit_journal_path())
    if not path.exists():
        return {"ok":True,"entries":0,"last_hash":GENESIS,"path":str(path)}
    previous=GENESIS
    count=0
    with path.open("r",encoding="utf-8") as handle:
        for line_number,line in enumerate(handle,start=1):
            if not line.strip():
                continue
            try:
                row=json.loads(line)
            except Exception as exc:
                return {"ok":False,"entries":count,"line":line_number,"error":f"invalid JSON: {exc}","path":str(path)}
            if row.get("previous_hash") != previous:
                return {"ok":False,"entries":count,"line":line_number,"error":"previous hash mismatch","path":str(path)}
            claimed=row.get("entry_hash")
            check=dict(row)
            check.pop("entry_hash",None)
            if digest(check) != claimed:
                return {"ok":False,"entries":count,"line":line_number,"error":"entry hash mismatch","path":str(path)}
            previous=claimed
            count+=1
    return {"ok":True,"entries":count,"last_hash":previous,"path":str(path)}

def tail_entries(limit:int=100) -> list[dict]:
    path=audit_journal_path()
    if not path.exists():
        return []
    rows=[]
    with path.open("r",encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"event_type":"JOURNAL_ERROR","action":"Unreadable audit entry"})
    return rows[-max(1,int(limit)):]
