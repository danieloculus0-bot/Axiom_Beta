/* Editable demonstration routings using the existing EWI routing contract.
 * Mirrors EZ Methods' draft/review boundaries. No actual drawing extraction,
 * work-center capability certification, BEAN invocation, or manufacturing release.
 */
import {normalizeRouting} from "../ewi/engine.mjs";
import {change,getJob} from "./engine.mjs";

const clone=v=>structuredClone(v);
const fail=message=>{throw Error(message)};
export const DEMO_CENTER_OPTIONS=[
  "LASER-01","PRESS-02","WELD-03","QC-01","FINISH-01",
  "DEMO-CUT","DEMO-QC"
];
export function editableRouting(job){
 if(!job?.routing?.operations?.length)fail("This fictional job has no routed steps");
 return clone(job.routing.operations);
}
export function addRouteStep(operations){
 if(!Array.isArray(operations)||operations.length>=60)fail("A route supports at most 60 operations");
 const steps=operations.map(o=>Number(o.step)).filter(Number.isFinite);
 let next=Math.max(0,...steps)+10;
 if(!Number.isSafeInteger(next)||next>99990)fail("No available sample step number");
 while(operations.some(o=>o.step===String(next)))next+=10;
 return [...clone(operations),{
  step:String(next),name:"Sample operation",center:"DEMO-CUT",
  instructions:["Review the fictional drawing and verify the operation requirements."],
  check:"Record an illustrative first-piece check."
 }];
}
export function moveRouteStep(operations,index,direction){
 if(!Array.isArray(operations)||!Number.isInteger(index)||![-1,1].includes(direction))
   fail("Invalid routing movement");
 const target=index+direction;
 if(index<0||index>=operations.length||target<0||target>=operations.length)
   return clone(operations);
 const n=clone(operations);
 [n[index],n[target]]=[n[target],n[index]];
 return n;
}
export function removeRouteStep(operations,index){
 if(!Array.isArray(operations)||operations.length<=1)fail("Routing must keep at least one step");
 if(!Number.isInteger(index)||index<0||index>=operations.length)fail("Operation missing");
 return operations.filter((_,i)=>i!==index).map(clone);
}
export function validateRoutingDraft(job,operations){
 if(!job)fail("Fictional job not found");
 const packet=normalizeRouting({
  jobNumber:job.jobNumber,partNumber:job.partNumber,
  revision:job.revision,operations
 });
 for(const op of packet.operations){
  if(!DEMO_CENTER_OPTIONS.includes(op.center))
   fail("Choose a registered fictional work center");
 }
 return packet.operations;
}
export function saveRoutingDraft(state,jobId,operations,sessions=[],at=new Date().toISOString()){
 const job=getJob(state,jobId);
 if(!job)fail("Fictional work order not found");
 if(job.status!=="OPEN")fail("Only open fictional jobs can be edited");
 if(sessions.some(s=>s.jobId===jobId))
   fail("This job has recorded clocking. Create another fictional job rather than silently changing its execution history.");
 const clean=validateRoutingDraft(job,operations);
 if(!Number.isFinite(Date.parse(at)))fail("Invalid update time");
 return change(state,"routing.draft_edited",job.jobNumber+" / "+clean.length+" operations / REVIEW REQUIRED",n=>{
  const j=getJob(n,jobId);
  const old=clone(j.routing);
  j.routing={
   ...old,revision:j.revision,source:"BROWSER-LOCAL ROUTING DRAFT",
   reviewState:"REVIEW_REQUIRED",reviewedAt:null,reviewedBy:null,
   lastEditedAt:at,operations:clean,
   history:[...(old.history||[]),{
     at,kind:"DRAFT_EDIT",previous:old.operations.map(o=>({step:o.step,name:o.name,center:o.center})),
     current:clean.map(o=>({step:o.step,name:o.name,center:o.center}))
   }]
  };
 },at);
}
export function reviewRoutingDraft(state,jobId,sessions=[],at=new Date().toISOString()){
 const j=getJob(state,jobId);
 if(!j||j.routing.reviewState!=="REVIEW_REQUIRED")
   fail("No edited route is awaiting demo review");
 if(sessions.some(s=>s.jobId===jobId))fail("Clock history prevents routing modification");
 validateRoutingDraft(j,j.routing.operations);
 if(!Number.isFinite(Date.parse(at)))fail("Invalid review timestamp");
 return change(state,"routing.demo_reviewed",j.jobNumber+" / DEMO REVIEW ONLY",n=>{
  const target=getJob(n,jobId);
  target.routing.reviewState="DEMO_REVIEWED";
  target.routing.reviewedAt=at;
  target.routing.reviewedBy="DEMO-PLANNER";
  target.routing.history=[...(target.routing.history||[]),{
   at,kind:"DEMO_REVIEW",previous:[],current:[]
  }];
 },at);
}
