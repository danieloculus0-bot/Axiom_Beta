/* Quality Forge browser-case increment. Fictional, browser-local and advisory.
 * Reuses the canonical ERP quality record and event ledger, not a second case store.
 */
import {change,closeQuality} from "./engine.mjs";

export const QUALITY_DISPOSITIONS=[
  {id:"REWORK",label:"Rework (fictional)"},
  {id:"SCRAP",label:"Scrap (fictional)"},
  {id:"RETURN_FOR_REVIEW",label:"Return for review (fictional)"}
];
const recordFor=(state,id)=>state.quality.find(q=>q.id===id);
const noteText=value=>{
  const note=String(value??"").trim();
  if(note.length<5||note.length>500)throw Error("Enter a fictional case note of 5 to 500 characters");
  return note;
};
const timestamp=at=>{
  if(typeof at!=="string"||!Number.isFinite(Date.parse(at)))throw Error("Invalid case timestamp");
  return at;
};
export const QUALITY_INSPECTION_STAGES=[
  {id:"FIRST_PIECE",label:"First-piece check"},
  {id:"IN_PROCESS",label:"In-process check"},
  {id:"FINAL_REVIEW",label:"Final review"}
];
export const QUALITY_INSPECTION_RESULTS=["PASS","FAIL","REVIEW_REQUIRED"];
/* Records a fictional observation against the existing NCR, job and routed step.
 * It is evidence only, never a production inspection approval or automatic release.
 */
export function recordQualityInspection(state,id,stage,step,result,observation,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  const job=state.jobs.find(j=>j.id===record.jobId);
  if(!job)throw Error("Linked fictional work order is missing");
  if(!QUALITY_INSPECTION_STAGES.some(item=>item.id===stage))throw Error("Choose a listed fictional inspection stage");
  const operation=job.routing?.operations?.find(op=>String(op.step)===String(step));
  if(!operation)throw Error("Choose a routed operation on this fictional job");
  if(!QUALITY_INSPECTION_RESULTS.includes(result))throw Error("Choose a listed fictional inspection result");
  const detail=noteText(observation),time=timestamp(at);
  return change(state,"quality.inspection.recorded",record.number+" / "+stage+" / "+result,n=>{
    const q=n.quality.find(item=>item.id===id);
    if(!Array.isArray(q.inspections))q.inspections=[];
    q.inspections.push({
      id:id+"-inspection-"+(q.inspections.length+1),stage,step:String(operation.step),
      operation:operation.name,center:operation.center,result,observation:detail,
      jobRevision:job.revision,drawingRevision:job.drawing?.revision??null,at:time
    });
  },time);
}
export function recordQualityDisposition(state,id,decision,note,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  if(!QUALITY_DISPOSITIONS.some(item=>item.id===decision))throw Error("Choose a listed fictional disposition");
  const detail=noteText(note),time=timestamp(at);
  return change(state,"quality.disposition.recorded",record.number+" / "+decision,n=>{
    n.quality.find(q=>q.id===id).disposition={decision,note:detail,recordedAt:time};
  },time);
}
export function recordQualityFollowup(state,id,note,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record)throw Error("Fictional quality case not found");
  const detail=noteText(note),time=timestamp(at);
  return change(state,"quality.followup.recorded",record.number+" / case follow-up",n=>{
    const q=n.quality.find(item=>item.id===id);
    if(!Array.isArray(q.followUps))q.followUps=[];
    q.followUps.push({id:id+"-followup-"+(q.followUps.length+1),note:detail,at:time});
  },time);
}
export function closeReviewedQuality(state,id,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  if(!record.disposition||!QUALITY_DISPOSITIONS.some(item=>item.id===record.disposition.decision))
    throw Error("Record a fictional disposition before closing this case");
  if(record.disposition.decision==="RETURN_FOR_REVIEW")
    throw Error("Return for review keeps this fictional quality case open");
  return closeQuality(state,id,timestamp(at));
}
