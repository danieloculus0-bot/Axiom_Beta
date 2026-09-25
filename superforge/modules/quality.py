from __future__ import annotations
from typing import Any
from ..audit import record_event
from ..db import db
from ..event_bus import publish

RECORD_TYPES=("NCR","DMR","RMA","CAR","CAPA","DEVIATION","INSPECTION_REJECT","CUSTOMER_COMPLAINT","SUPPLIER_NCR")

def create_quality_record(data:dict[str,Any],*,actor:str)->int:
    record_type=str(data.get("record_type") or "NCR").upper()
    if record_type not in RECORD_TYPES:
        raise ValueError(f"unsupported quality record type: {record_type}")
    required={"record_number","description"}
    missing=[k for k in required if not str(data.get(k) or "").strip()]
    if missing: raise ValueError("missing required fields: "+", ".join(missing))
    fields=["record_type","record_number","customer_id","supplier_id","part_id","job_id","po_id","machine_id","severity","status","quantity_affected","quantity_shipped","description","containment","disposition","root_cause","corrective_action","preventive_action","effectiveness","owner","due_date"]
    values={k:data.get(k) for k in fields}
    values["record_type"]=record_type
    values["severity"]=values.get("severity") or "unassigned"
    values["status"]=values.get("status") or "open"
    values["quantity_affected"]=int(values.get("quantity_affected") or 0)
    values["quantity_shipped"]=int(values.get("quantity_shipped") or 0)
    with db() as con:
        cur=con.execute("INSERT INTO quality_records("+",".join(fields)+") VALUES("+",".join("?" for _ in fields)+")",tuple(values[k] for k in fields))
        record_id=int(cur.lastrowid)
        after=dict(con.execute("SELECT * FROM quality_records WHERE id=?",(record_id,)).fetchone())
    record_event(event_type="QUALITY_MUTATION",action="CREATE",module="quality",entity_type="quality_record",entity_id=record_id,actor=actor,after=after,reason=record_type)
    publish("quality.created",source_module="quality",entity_type="quality_record",entity_id=str(record_id),actor=actor,reason=record_type,
            payload={k:after.get(k) for k in ("record_type","record_number","customer_id","supplier_id","part_id","job_id","po_id","machine_id","quantity_affected","quantity_shipped","severity")})
    return record_id

def update_quality_record(record_id:int,changes:dict[str,Any],*,actor:str,reason:str)->None:
    allowed={"severity","status","quantity_affected","quantity_shipped","description","containment","disposition","root_cause","corrective_action","preventive_action","effectiveness","owner","due_date","customer_id","supplier_id","part_id","job_id","po_id","machine_id"}
    updates={k:v for k,v in changes.items() if k in allowed}
    if not updates: return
    with db() as con:
        row=con.execute("SELECT * FROM quality_records WHERE id=?",(record_id,)).fetchone()
        if not row: raise ValueError("quality record not found")
        before=dict(row)
        con.execute("UPDATE quality_records SET "+",".join(f"{k}=?" for k in updates)+",updated_at=CURRENT_TIMESTAMP WHERE id=?",tuple(updates.values())+(record_id,))
        after=dict(con.execute("SELECT * FROM quality_records WHERE id=?",(record_id,)).fetchone())
    record_event(event_type="QUALITY_MUTATION",action="UPDATE",module="quality",entity_type="quality_record",entity_id=record_id,actor=actor,reason=reason,before=before,after=after)
    if before.get("status")!="closed" and after.get("status")=="closed":
        publish("quality.closed",source_module="quality",entity_type="quality_record",entity_id=str(record_id),actor=actor,reason=reason,payload=after)

def create_car(*,quality_record_id:int,car_number:str,problem_statement:str,owner:str="",root_cause_due:str="",action_due:str="",actor:str)->int:
    with db() as con:
        source=con.execute("SELECT * FROM quality_records WHERE id=?",(quality_record_id,)).fetchone()
        if not source: raise ValueError("source quality record not found")
        cur=con.execute("""INSERT INTO corrective_actions(car_number,quality_record_id,problem_statement,owner,root_cause_due,action_due)
                           VALUES(?,?,?,?,?,?)""",(car_number,quality_record_id,problem_statement,owner,root_cause_due,action_due))
        car_id=int(cur.lastrowid)
        after=dict(con.execute("SELECT * FROM corrective_actions WHERE id=?",(car_id,)).fetchone())
    record_event(event_type="CAR_MUTATION",action="CREATE",module="quality",entity_type="corrective_action",entity_id=car_id,actor=actor,after=after,
                 data={"quality_record_id":quality_record_id})
    publish("car.created",source_module="quality",entity_type="corrective_action",entity_id=str(car_id),actor=actor,payload=after)
    return car_id

def save_five_why(car_id:int,whys:list[str],root_cause:str,corrective_action:str,preventive_action:str,*,actor:str)->None:
    whys=(whys+["","","","",""])[:5]
    with db() as con:
        row=con.execute("SELECT * FROM corrective_actions WHERE id=?",(car_id,)).fetchone()
        if not row: raise ValueError("CAR not found")
        before=dict(row)
        con.execute("""UPDATE corrective_actions SET why1=?,why2=?,why3=?,why4=?,why5=?,root_cause=?,corrective_action=?,preventive_action=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    tuple(whys)+(root_cause,corrective_action,preventive_action,car_id))
        after=dict(con.execute("SELECT * FROM corrective_actions WHERE id=?",(car_id,)).fetchone())
    record_event(event_type="CAR_MUTATION",action="FIVE_WHY_UPDATED",module="quality",entity_type="corrective_action",entity_id=car_id,actor=actor,before=before,after=after)

def ppm_summary(days:int=30)->dict:
    with db() as con:
        row=con.execute("""SELECT COALESCE(SUM(quantity_affected),0) defects,COALESCE(SUM(quantity_shipped),0) shipped,COUNT(*) records
                           FROM quality_records WHERE created_at>=datetime('now',?)""",(f"-{int(days)} days",)).fetchone()
    defects=int(row["defects"] or 0); shipped=int(row["shipped"] or 0)
    return {"days":days,"defects":defects,"shipped":shipped,"records":int(row["records"] or 0),"ppm":(defects/shipped*1_000_000 if shipped else None)}

def quality_pulse()->dict:
    with db() as con:
        open_count=con.execute("SELECT COUNT(*) n FROM quality_records WHERE status!='closed'").fetchone()["n"]
        overdue=con.execute("SELECT COUNT(*) n FROM quality_records WHERE status!='closed' AND due_date IS NOT NULL AND date(due_date)<date('now')").fetchone()["n"]
        cars=con.execute("SELECT COUNT(*) n FROM corrective_actions WHERE status!='closed'").fetchone()["n"]
        fails=con.execute("SELECT COUNT(*) n FROM fai_runs WHERE fail_count>0").fetchone()["n"]
    return {"open_quality":open_count,"overdue":overdue,"open_cars":cars,"failed_fai":fails,"ppm":ppm_summary()}
