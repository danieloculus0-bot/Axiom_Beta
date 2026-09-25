from __future__ import annotations
from datetime import date,datetime
from typing import Any

TRANSFORMS={"strip","upper","lower","int","float","date","bool","identity"}

def apply_transform(value:Any,name:str|None)->Any:
    name=(name or "identity").strip().lower()
    if name not in TRANSFORMS:
        raise ValueError(f"unsupported mapping transform: {name}")
    if name=="identity": return value
    if name=="strip": return "" if value is None else str(value).strip()
    if name=="upper": return "" if value is None else str(value).strip().upper()
    if name=="lower": return "" if value is None else str(value).strip().lower()
    if name=="int": return None if value in (None,"") else int(float(value))
    if name=="float": return None if value in (None,"") else float(value)
    if name=="bool":
        return str(value).strip().lower() in {"1","true","yes","y","on"}
    if name=="date":
        if value in (None,""): return None
        if isinstance(value,(date,datetime)): return value.date().isoformat() if isinstance(value,datetime) else value.isoformat()
        raw=str(value).strip()
        for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y","%Y/%m/%d"):
            try: return datetime.strptime(raw,fmt).date().isoformat()
            except ValueError: pass
        return raw
    return value

def map_record(payload:dict,mappings:list[dict],direction:str="in")->dict:
    result={}
    for m in mappings:
        if (m.get("direction") or "in")!=direction: continue
        src=m["external_field"] if direction=="in" else m["internal_field"]
        dst=m["internal_field"] if direction=="in" else m["external_field"]
        value=payload.get(src)
        if m.get("required") and value in (None,""):
            raise ValueError(f"required mapped field missing: {src}")
        result[dst]=apply_transform(value,m.get("transform"))
    return result
