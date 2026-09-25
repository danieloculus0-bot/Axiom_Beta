from __future__ import annotations

import json
from pathlib import Path

from ..audit import record_event
from ..db import db
from ..event_bus import publish
from .ezfair_engine import add_pdf_balloons, get_last_skipped_candidates
from .ezfair_enhancements import ExtractionSettings, extract_pdf_dimensions_enhanced
from .ezfair_writer import fill_fai_template

def create_fai_from_drawing(
    *,
    pdf_path:str|Path,
    template_path:str|Path,
    output_dir:str|Path,
    fai_number:str,
    actor:str,
    job_id:int|None=None,
    part_id:int|None=None,
    drawing_document_id:int|None=None,
    drawing_revision:str="",
    extraction_settings:ExtractionSettings|None=None,
)->dict:
    pdf_path=Path(pdf_path)
    template_path=Path(template_path)
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    characteristics=extract_pdf_dimensions_enhanced(pdf_path,extraction_settings)
    ballooned=add_pdf_balloons(pdf_path,characteristics,output_dir/f"{pdf_path.stem}_BALLOONED.pdf")
    workbook=fill_fai_template(template_path,characteristics,output_dir/f"{pdf_path.stem}_FAI{template_path.suffix.lower()}")
    with db() as con:
        cur=con.execute("""INSERT INTO fai_runs(fai_number,job_id,part_id,drawing_document_id,drawing_revision,status,characteristic_count,ballooned_pdf,fai_workbook,created_by)
                           VALUES(?,?,?,?,?,'inspection_ready',?,?,?,?)""",
                        (fai_number,job_id,part_id,drawing_document_id,drawing_revision,len(characteristics),str(ballooned),str(workbook),actor))
        fai_id=int(cur.lastrowid)
        for c in characteristics:
            con.execute("""INSERT INTO fai_characteristics(fai_run_id,char_number,reference_location,raw_text,nominal,lsl,usl,characteristic_type,tooling,notes,source_metadata)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (fai_id,c.char_number,c.reference_location,c.raw_text,c.nominal,c.lsl,c.usl,c.type,c.tooling,c.comments,json.dumps(c.metadata,sort_keys=True,default=str)))
    record_event(event_type="FAI",action="CREATED_FROM_DRAWING",module="ezfair",entity_type="fai",entity_id=fai_id,actor=actor,
                 data={"fai_number":fai_number,"characteristics":len(characteristics),"source_pdf":str(pdf_path),"ballooned_pdf":str(ballooned),"fai_workbook":str(workbook),
                       "skipped_candidates":len(get_last_skipped_candidates())})
    publish("fai.created",source_module="ezfair",entity_type="fai",entity_id=str(fai_id),actor=actor,payload={"job_id":job_id,"part_id":part_id,"characteristics":len(characteristics)})
    return {"id":fai_id,"fai_number":fai_number,"characteristics":len(characteristics),"ballooned_pdf":str(ballooned),"fai_workbook":str(workbook)}

def record_measurement(fai_id:int,char_number:int,actual:float|None,*,actor:str,notes:str="")->dict:
    with db() as con:
        row=con.execute("SELECT * FROM fai_characteristics WHERE fai_run_id=? AND char_number=?",(fai_id,char_number)).fetchone()
        if not row: raise ValueError("FAI characteristic not found")
        before=dict(row)
        lsl=row["lsl"]; usl=row["usl"]
        result="PASS"
        if actual is None: result=""
        elif lsl is not None and actual<float(lsl): result="FAIL"
        elif usl is not None and actual>float(usl): result="FAIL"
        con.execute("UPDATE fai_characteristics SET actual=?,result=?,notes=? WHERE id=?",(actual,result,notes,row["id"]))
        after=dict(con.execute("SELECT * FROM fai_characteristics WHERE id=?",(row["id"],)).fetchone())
        counts=con.execute("""SELECT COUNT(*) total,SUM(CASE WHEN result='PASS' THEN 1 ELSE 0 END) passes,SUM(CASE WHEN result='FAIL' THEN 1 ELSE 0 END) fails
                              FROM fai_characteristics WHERE fai_run_id=?""",(fai_id,)).fetchone()
        con.execute("UPDATE fai_runs SET characteristic_count=?,pass_count=?,fail_count=?,status=? WHERE id=?",
                    (counts["total"],counts["passes"] or 0,counts["fails"] or 0,"failed" if (counts["fails"] or 0)>0 else "in_progress",fai_id))
    record_event(event_type="FAI_MEASUREMENT",action="RECORDED",module="ezfair",entity_type="fai_characteristic",entity_id=f"{fai_id}:{char_number}",actor=actor,before=before,after=after)
    if result=="FAIL":
        publish("fai.failed",source_module="ezfair",entity_type="fai",entity_id=str(fai_id),actor=actor,payload={"char_number":char_number,"actual":actual,"lsl":lsl,"usl":usl})
    return after

def complete_fai(fai_id:int,*,actor:str)->dict:
    with db() as con:
        row=con.execute("SELECT * FROM fai_runs WHERE id=?",(fai_id,)).fetchone()
        if not row: raise ValueError("FAI run not found")
        pending=con.execute("SELECT COUNT(*) n FROM fai_characteristics WHERE fai_run_id=? AND (result IS NULL OR result='')",(fai_id,)).fetchone()["n"]
        fails=con.execute("SELECT COUNT(*) n FROM fai_characteristics WHERE fai_run_id=? AND result='FAIL'",(fai_id,)).fetchone()["n"]
        status="failed" if fails else ("in_progress" if pending else "complete")
        con.execute("UPDATE fai_runs SET status=?,completed_at=CASE WHEN ?='complete' THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id=?",(status,status,fai_id))
        after=dict(con.execute("SELECT * FROM fai_runs WHERE id=?",(fai_id,)).fetchone())
    record_event(event_type="FAI",action="COMPLETION_REVIEW",module="ezfair",entity_type="fai",entity_id=fai_id,actor=actor,after=after)
    publish("fai.completed" if status=="complete" else "fai.reviewed",source_module="ezfair",entity_type="fai",entity_id=str(fai_id),actor=actor,payload={"status":status,"fail_count":after.get("fail_count",0),"pass_count":after.get("pass_count",0),"part_id":after.get("part_id"),"job_id":after.get("job_id"),"drawing_revision":after.get("drawing_revision")})
    return after
