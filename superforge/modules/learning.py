from __future__ import annotations
import json,uuid
from collections import defaultdict
from ..audit import record_event
from ..db import db

def observe(signal_key:str,context:dict,*,outcome:str="",confidence:float=.5,source_event_id:str="",human_rating:float|None=None)->int:
    with db() as con:
        cur=con.execute("""INSERT INTO learning_observations(signal_key,context_json,outcome,confidence,source_event_id,human_rating)
                           VALUES(?,?,?,?,?,?)""",(signal_key,json.dumps(context,sort_keys=True,default=str),outcome,max(0,min(1,float(confidence))),source_event_id,human_rating))
        return int(cur.lastrowid)

def patterns(min_count:int=3)->list[dict]:
    with db() as con:
        rows=[dict(r) for r in con.execute("SELECT * FROM learning_observations ORDER BY id DESC LIMIT 5000")]
    groups=defaultdict(list)
    for row in rows: groups[row["signal_key"]].append(row)
    result=[]
    for key,items in groups.items():
        if len(items)<min_count: continue
        rated=[float(x["human_rating"]) for x in items if x["human_rating"] is not None]
        avg=sum(rated)/len(rated) if rated else None
        result.append({"signal_key":key,"count":len(items),"average_human_rating":avg,"latest_outcome":items[0].get("outcome")})
    return sorted(result,key=lambda x:x["count"],reverse=True)

def propose(*,title:str,problem_statement:str,proposed_change:str,target_module:str,evidence:list[dict],validation_plan:str,rollback_plan:str,risk_level:str="medium",actor:str="bean")->str:
    proposal_id=f"learn_{uuid.uuid4().hex[:16]}"
    with db() as con:
        con.execute("""INSERT INTO learning_proposals(proposal_id,title,problem_statement,proposed_change,target_module,evidence_json,validation_plan,rollback_plan,risk_level)
                       VALUES(?,?,?,?,?,?,?,?,?)""",(proposal_id,title,problem_statement,proposed_change,target_module,json.dumps(evidence,sort_keys=True,default=str),validation_plan,rollback_plan,risk_level))
    record_event(event_type="LEARNING_PROPOSAL",action="PROPOSED",module="bean",entity_type="learning_proposal",entity_id=proposal_id,actor=actor,
                 data={"title":title,"target_module":target_module,"risk_level":risk_level,"execution_permission":"proposal_only"})
    return proposal_id

def review(proposal_id:str,*,decision:str,reviewer:str,notes:str)->None:
    decisions={"approve_sandbox":("approved_for_sandbox","sandbox_only"),"approve_human":("approved_for_human_execution","human_execution_only"),
               "request_revision":("revision_requested","proposal_only"),"defer":("deferred","proposal_only"),"reject":("rejected","proposal_only")}
    if decision not in decisions: raise ValueError("invalid decision")
    if not reviewer.strip() or not notes.strip(): raise ValueError("reviewer and notes required")
    status,permission=decisions[decision]
    with db() as con:
        before=con.execute("SELECT * FROM learning_proposals WHERE proposal_id=?",(proposal_id,)).fetchone()
        if not before: raise ValueError("proposal not found")
        con.execute("""UPDATE learning_proposals SET status=?,execution_permission=?,reviewed_by=?,review_notes=?,updated_at=CURRENT_TIMESTAMP WHERE proposal_id=?""",
                    (status,permission,reviewer,notes,proposal_id))
        after=dict(con.execute("SELECT * FROM learning_proposals WHERE proposal_id=?",(proposal_id,)).fetchone())
    record_event(event_type="LEARNING_PROPOSAL",action="REVIEWED",module="bean",entity_type="learning_proposal",entity_id=proposal_id,actor=reviewer,reason=decision,before=dict(before),after=after)
