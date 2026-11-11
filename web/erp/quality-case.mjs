/* Quality Forge browser-case increment. Fictional, browser-local and advisory.
 * Reuses the canonical ERP quality record and event ledger, not a second case store.
 */
import {change,closeQuality} from "./engine.mjs";

export const QUALITY_DISPOSITIONS=[
  {id:"REWORK",label:"Rework (fictional)"},
  {id:"SCRAP",label:"Scrap (fictional)"},
  {id:"RETURN_FOR_REVIEW",label:"Return for review (fictional)"}
];
/* Canonical NCR IDs must resolve to exactly one case and one work order.
 * Legacy duplicate IDs or orphaned records cannot authorize a mutation or
 * navigate to whichever record Array.find happens to return first.
 */
export function uniqueQualityCase(state,id){
  if(typeof id!=="string"||!id||!Array.isArray(state?.quality)||!Array.isArray(state?.jobs))return null;
  const matches=state.quality.filter(q=>q?.id===id);
  if(matches.length!==1||!["OPEN","CLOSED"].includes(matches[0].status))return null;
  return state.jobs.filter(job=>job?.id===matches[0].jobId).length===1?matches[0]:null;
}
const recordFor=uniqueQualityCase;
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
/* Existing browser-local inspections may have sparse or manually restored IDs.
 * Allocate beyond the highest valid suffix rather than using array length,
 * so a new observation cannot silently reuse historical evidence identity.
 */
const nextInspectionEvidenceId=record=>{
  const prefix=record.id+"-inspection-";
  const inspections=Array.isArray(record.inspections)?record.inspections:[];
  let sequence=inspections.length+1;
  for(const item of inspections){
    const existing=item?.id;
    if(typeof existing!=="string"||!existing.startsWith(prefix))continue;
    const suffix=existing.slice(prefix.length);
    if(!/^[1-9][0-9]*$/.test(suffix))continue;
    const number=Number(suffix);
    if(Number.isSafeInteger(number))sequence=Math.max(sequence,number+1);
  }
  if(!Number.isSafeInteger(sequence))
    throw Error("Fictional inspection evidence ID range exhausted");
  return prefix+sequence;
};
/* Records a fictional observation against the existing NCR, job and routed step.
 * It is evidence only, never a production inspection approval or automatic release.
 */
export function recordQualityInspection(state,id,stage,step,result,observation,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  const job=state.jobs.find(j=>j.id===record.jobId);
  if(!job)throw Error("Linked fictional work order is missing");
  if(!QUALITY_INSPECTION_STAGES.some(item=>item.id===stage))throw Error("Choose a listed fictional inspection stage");
  // A legacy browser-local route can contain colliding step numbers. Never
  // attach a new observation to whichever operation Array.find sees first.
  const operations=Array.isArray(job.routing?.operations)?job.routing.operations:[];
  const stepId=(typeof step==="string"||typeof step==="number")?String(step).trim():"";
  const matches=stepId?operations.filter(op=>op?.step!==undefined&&
    String(op.step)===stepId):[];
  if(matches.length!==1)
    throw Error("Choose one unambiguous routed operation on this fictional job");
  const operation=matches[0];
  if(!QUALITY_INSPECTION_RESULTS.includes(result))throw Error("Choose a listed fictional inspection result");
  const detail=noteText(observation),time=timestamp(at),inspectionId=nextInspectionEvidenceId(record);
  return change(state,"quality.inspection.recorded",record.number+" / "+stage+" / "+result,n=>{
    const q=n.quality.find(item=>item.id===id);
    if(!Array.isArray(q.inspections))q.inspections=[];
    q.inspections.push({
      id:inspectionId,stage,step:String(operation.step),
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

export const QUALITY_ACTION_ROLES=[
  {id:"QUALITY",label:"Quality (fictional role)"},
  {id:"PRODUCTION",label:"Production (fictional role)"},
  {id:"ENGINEERING",label:"Engineering (fictional role)"},
  {id:"MATERIALS",label:"Materials (fictional role)"},
  {id:"MAINTENANCE",label:"Maintenance (fictional role)"}
];
export const QUALITY_EFFECTIVENESS_RESULTS=[
  {id:"EFFECTIVE",label:"Effective (illustrative)"},
  {id:"NOT_EFFECTIVE",label:"Not effective / further action needed"},
  {id:"MORE_EVIDENCE",label:"More evidence needed"}
];
/* Corrective actions live on the existing fictional NCR and may optionally cite
 * an inspection on that same case. No approval, release or automatic rerouting.
 */
export function recordQualityCorrectiveAction(state,id,ownerRole,description,inspectionId="",at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  if(!state.jobs.some(j=>j.id===record.jobId))throw Error("Linked fictional work order is missing");
  if(!QUALITY_ACTION_ROLES.some(role=>role.id===ownerRole))throw Error("Choose a listed fictional owner role");
  const sourceId=String(inspectionId??"").trim();
  const sourceMatches=sourceId?(Array.isArray(record.inspections)?record.inspections:[])
    .filter(item=>item?.id===sourceId):[];
  if(sourceId&&sourceMatches.length!==1)
    throw Error("Choose one unambiguous inspection observation on this fictional case");
  const detail=noteText(description),time=timestamp(at);
  return change(state,"quality.corrective_action.recorded",record.number+" / "+ownerRole,n=>{
    const q=n.quality.find(item=>item.id===id);
    if(!Array.isArray(q.correctiveActions))q.correctiveActions=[];
    q.correctiveActions.push({
      id:id+"-action-"+(q.correctiveActions.length+1),ownerRole,description:detail,
      sourceInspectionId:sourceId||null,createdAt:time,reviews:[]
    });
  },time);
}
/* Effectiveness reviews are append-only observations, including after case
 * closure. An ineffective result never silently reopens or releases work.
 */
export function reviewQualityCorrectiveAction(state,id,actionId,result,note,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record)throw Error("Fictional quality case not found");
  const actions=Array.isArray(record.correctiveActions)?record.correctiveActions:[];
  const matches=typeof actionId==="string"&&actionId?
    actions.filter(item=>item?.id===actionId):[];
  if(matches.length===0)
    throw Error("Corrective action not found on this fictional quality case");
  if(matches.length>1)
    throw Error("Corrective action identity is ambiguous on this fictional quality case");
  const action=matches[0];
  if(!QUALITY_EFFECTIVENESS_RESULTS.some(item=>item.id===result))
    throw Error("Choose a listed fictional effectiveness result");
  const detail=noteText(note),time=timestamp(at);
  if(Date.parse(time)<Date.parse(action.createdAt))
    throw Error("Effectiveness review cannot precede the fictional action");
  return change(state,"quality.corrective_action.effectiveness_reviewed",record.number+" / "+actionId+" / "+result,n=>{
    const target=n.quality.find(item=>item.id===id).correctiveActions.find(item=>item.id===actionId);
    if(!Array.isArray(target.reviews))target.reviews=[];
    target.reviews.push({
      id:actionId+"-review-"+(target.reviews.length+1),result,note:detail,at:time
    });
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

/* Read-only job-level view over canonical NCR records. No second quality store. */
export function qualityJobSummary(state,jobId){
  const cases=state.quality.filter(q=>q.jobId===jobId);
  const actions=cases.flatMap(q=>Array.isArray(q.correctiveActions)?q.correctiveActions:[]);
  const reviews=actions.flatMap(action=>Array.isArray(action.reviews)?action.reviews:[])
    .filter(review=>review&&typeof review.at==="string"&&typeof review.result==="string")
    .sort((a,b)=>b.at.localeCompare(a.at));
  return {
    cases,total:cases.length,open:cases.filter(q=>q.status==="OPEN").length,
    inspections:cases.reduce((count,q)=>count+(Array.isArray(q.inspections)?q.inspections.length:0),0),
    correctiveActions:actions.length,
    latestEffectiveness:reviews[0]?.result||(actions.length?"NOT REVIEWED":"NO ACTION")
  };
}
/* Resolve a real job-linked case for any dashboard, register or report entry. */
export function jobQualityTarget(state,jobId){
  if(!Array.isArray(state?.jobs)||state.jobs.filter(job=>job?.id===jobId).length!==1)return null;
  const cases=qualityJobSummary(state,jobId).cases
    .filter(q=>uniqueQualityCase(state,q.id)===q);
  const selected=cases.find(q=>q.status==="OPEN")||cases[0];
  return selected?{jobId,caseId:selected.id}:null;
}
