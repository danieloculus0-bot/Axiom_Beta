from __future__ import annotations
import hashlib,json,uuid
from pathlib import Path
from typing import Any
from ..audit import record_event
from ..db import db
from ..event_bus import publish
from .flatfile import FlatFileAdapter
from .mapping import map_record
from .rest import RESTAdapter
from .sql import SQLReportAdapter

ADAPTERS={"flatfile":FlatFileAdapter,"rest":RESTAdapter,"sql":SQLReportAdapter}
ENTITY_TABLES={
 "job":("jobs","job_number"),
 "purchase_order":("purchase_orders","po_number"),
 "inventory_item":("inventory_items","item_number"),
 "customer":("customers","name"),
 "supplier":("suppliers","name"),
 "part":("parts","part_number"),
 "machine":("machines","machine_number"),
 "clocking_error":("clocking_errors","id"),
}

def _hash(payload:dict)->str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode("utf-8")).hexdigest()

class IntegrationService:
    def __init__(self,credential_loader=None):
        self.credential_loader=credential_loader or (lambda ref:{})
    def connection(self,connection_id:int):
        with db() as con:
            row=con.execute("SELECT * FROM erp_connections WHERE id=?",(connection_id,)).fetchone()
            return dict(row) if row else None
    def mappings(self,connection_id:int,entity_type:str,direction:str)->list[dict]:
        with db() as con:
            return [dict(r) for r in con.execute("SELECT * FROM erp_mappings WHERE connection_id=? AND entity_type=? AND direction=? ORDER BY id",(connection_id,entity_type,direction))]
    def adapter(self,connection:dict):
        cls=ADAPTERS.get(connection["adapter_type"])
        if cls is None: raise ValueError(f"adapter not installed: {connection['adapter_type']}")
        config=json.loads(connection.get("config_json") or "{}")
        credentials=self.credential_loader(connection.get("credentials_ref") or "")
        return cls(config,credentials)
    def pull(self,connection_id:int,entity_type:str,*,actor:str="integration")->dict:
        connection=self.connection(connection_id)
        if not connection or not connection["enabled"]: raise ValueError("ERP connection unavailable or disabled")
        run_id=f"sync_{uuid.uuid4().hex}"
        with db() as con:
            con.execute("INSERT INTO integration_runs(connection_id,run_id,direction,entity_type,status) VALUES(?,?, 'in',?,'running')",(connection_id,run_id,entity_type))
        adapter=self.adapter(connection)
        mappings=self.mappings(connection_id,entity_type,"in")
        table,key_field=ENTITY_TABLES.get(entity_type,(None,None))
        if not table: raise ValueError(f"entity type not yet mapped to a SuperForge table: {entity_type}")
        read=applied=skipped=errors=0
        for external in adapter.pull(entity_type):
            read+=1
            try:
                mapped=map_record(external.payload,mappings,"in") if mappings else dict(external.payload)
                if key_field not in mapped or mapped.get(key_field) in (None,""):
                    raise ValueError(f"mapped record lacks key field {key_field}")
                columns=[k for k in mapped.keys() if k.replace("_","").isalnum()]
                with db() as con:
                    existing=con.execute(f"SELECT * FROM {table} WHERE {key_field}=?",(mapped[key_field],)).fetchone()
                    before=dict(existing) if existing else None
                    if existing:
                        updates=[c for c in columns if c not in {"id","created_at"}]
                        if updates:
                            con.execute(f"UPDATE {table} SET "+",".join(f"{c}=?" for c in updates)+",updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                        tuple(mapped[c] for c in updates)+(existing["id"],))
                            internal_id=str(existing["id"])
                    else:
                        inserts=[c for c in columns if c!="id"]
                        cur=con.execute(f"INSERT INTO {table}("+",".join(inserts)+") VALUES("+",".join("?" for _ in inserts)+")",
                                        tuple(mapped[c] for c in inserts))
                        internal_id=str(cur.lastrowid)
                    con.execute("""INSERT INTO external_refs(connection_id,entity_type,internal_id,external_id,last_seen_at,last_payload_hash)
                                   VALUES(?,?,?,?,CURRENT_TIMESTAMP,?)
                                   ON CONFLICT(connection_id,entity_type,external_id) DO UPDATE SET internal_id=excluded.internal_id,last_seen_at=CURRENT_TIMESTAMP,last_payload_hash=excluded.last_payload_hash""",
                                (connection_id,entity_type,internal_id,external.external_id,_hash(external.payload)))
                applied+=1
                record_event(event_type="ERP_IMPORT_ROW",action="APPLIED",module="integrations",source_module=connection["name"],target_module=entity_type,
                             entity_type=entity_type,entity_id=internal_id,actor=actor,before=before,after=mapped,data={"external_id":external.external_id,"run_id":run_id})
            except Exception as exc:
                errors+=1
                record_event(event_type="ERP_IMPORT_ROW",action="ERROR",module="integrations",source_module=connection["name"],target_module=entity_type,
                             entity_type=entity_type,entity_id=external.external_id,actor=actor,reason=str(exc),data={"run_id":run_id})
        status="completed" if errors==0 else "completed_with_errors"
        with db() as con:
            con.execute("""UPDATE integration_runs SET status=?,read_count=?,applied_count=?,skipped_count=?,error_count=?,completed_at=CURRENT_TIMESTAMP,
                           summary_json=? WHERE run_id=?""",(status,read,applied,skipped,errors,json.dumps({"connection":connection["name"]}),run_id))
        publish("erp.sync.completed",source_module="integrations",entity_type="integration_run",entity_id=run_id,actor=actor,
                payload={"connection_id":connection_id,"entity_type":entity_type,"read":read,"applied":applied,"skipped":skipped,"errors":errors})
        return {"run_id":run_id,"status":status,"read":read,"applied":applied,"skipped":skipped,"errors":errors}
    def queue_push(self,connection_id:int,entity_type:str,entity_id:str,operation:str,payload:dict,*,event_id:str="",actor:str="integration")->int:
        with db() as con:
            cur=con.execute("""INSERT INTO integration_outbox(connection_id,event_id,entity_type,entity_id,operation,payload_json,status)
                               VALUES(?,?,?,?,?,?,'queued')""",(connection_id,event_id,entity_type,str(entity_id),operation,json.dumps(payload,sort_keys=True,default=str)))
            row_id=int(cur.lastrowid)
        record_event(event_type="ERP_OUTBOX",action="QUEUED",module="integrations",entity_type=entity_type,entity_id=entity_id,actor=actor,data={"outbox_id":row_id,"connection_id":connection_id,"operation":operation},event_id=event_id or None)
        return row_id
    def flush_outbox(self,connection_id:int,*,actor:str="integration")->dict:
        connection=self.connection(connection_id)
        if not connection or not connection["enabled"]: raise ValueError("ERP connection unavailable or disabled")
        adapter=self.adapter(connection)
        sent=failed=0
        with db() as con:
            rows=[dict(r) for r in con.execute("SELECT * FROM integration_outbox WHERE connection_id=? AND status IN ('queued','retry') ORDER BY id",(connection_id,))]
        for row in rows:
            payload=json.loads(row["payload_json"])
            receipt=adapter.push(row["entity_type"],row["operation"],payload)
            with db() as con:
                if receipt.ok:
                    con.execute("UPDATE integration_outbox SET status='sent',attempts=attempts+1,sent_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=?",(row["id"],)); sent+=1
                else:
                    con.execute("UPDATE integration_outbox SET status='retry',attempts=attempts+1,last_error=? WHERE id=?",(receipt.message[:2000],row["id"])); failed+=1
            record_event(event_type="ERP_OUTBOX",action="SENT" if receipt.ok else "FAILED",module="integrations",source_module="SuperForge",target_module=connection["name"],
                         entity_type=row["entity_type"],entity_id=row["entity_id"],actor=actor,reason=receipt.message,data={"outbox_id":row["id"],"receipt":receipt.raw})
        return {"sent":sent,"failed":failed}
