from __future__ import annotations
import csv,json
from pathlib import Path
from typing import Iterable
from .base import ERPAdapter,ExternalRecord,PushReceipt

class FlatFileAdapter(ERPAdapter):
    """CSV/JSON report-drop adapter. Excel files are handled by service optional openpyxl support."""
    def pull(self,entity_type:str,*,cursor:str="")->Iterable[ExternalRecord]:
        path=Path(self.config.get("path","")).expanduser()
        if not path.exists(): return []
        id_field=self.config.get("external_id_field","id")
        rows=[]
        if path.suffix.lower()==".csv":
            with path.open("r",encoding="utf-8-sig",newline="") as handle:
                rows=list(csv.DictReader(handle))
        elif path.suffix.lower()==".json":
            data=json.loads(path.read_text(encoding="utf-8"))
            rows=data if isinstance(data,list) else data.get("records",[])
        else:
            raise ValueError(f"unsupported flat-file source: {path.suffix}")
        return [ExternalRecord(str(row.get(id_field) or f"row-{i+1}"),entity_type,dict(row)) for i,row in enumerate(rows)]
    def push(self,entity_type:str,operation:str,payload:dict)->PushReceipt:
        out=Path(self.config.get("outbox","integration_outbox")).expanduser()
        out.mkdir(parents=True,exist_ok=True)
        name=f"{entity_type}_{operation}.jsonl"
        with (out/name).open("a",encoding="utf-8") as handle:
            handle.write(json.dumps(payload,sort_keys=True,default=str)+"\n")
        return PushReceipt(True,str(payload.get("id") or payload.get("external_id") or ""),f"queued to {out/name}")
