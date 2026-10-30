/* Axiom connected browser ERP. Entirely synthetic, in-browser, no network/backend.
 * The "external" ERP is a deterministic local emulator, not ECI JobBOSS software.
 */
import {EXAMPLES, evaluatePacket, startSession, stopSession, durationSeconds} from "../ewi/engine.mjs";
import {seedPm,validatePm} from "./pm.mjs";

export const ERP_KEY = "axiom_public_erp_suite_v1";
export const CLOCK_KEY = "axiom_ewi_public_demo_sessions_v1";
export const CATALOG = [
  {partNumber:"SYN-BRACKET-12", revision:"C", drawing:"GEN-PLATE-12", materialId:"MAT-PLATE", operations:EXAMPLES[0].routing.operations},
  {partNumber:"SYN-MOUNT-07", revision:"B", drawing:"GEN-MOUNT-07", materialId:"MAT-PLATE", operations:EXAMPLES[1].routing.operations},
  {partNumber:"SYN-TAB-03", revision:"A", drawing:"GEN-TAB-03", materialId:"MAT-BAR",
   operations:[
    {step:"10",name:"Cut generic blank",center:"DEMO-CUT",instructions:["Verify material and sample drawing.","Cut illustrative shape."],check:"Visual first-piece check"},
    {step:"20",name:"Inspect generic blank",center:"DEMO-QC",instructions:["Confirm sample part identity.","Compare to generic dimensions."],check:"Illustrative inspection only"}
   ]}
];
export const EXTERNAL_FIXTURES = [
  {id:"sim-ext-5101",jobNumber:"SIM-5101",partNumber:"SYN-TAB-03",revision:"A",quantity:20,status:"OPEN",
   drawing:{number:"GEN-TAB-03",revision:"A",status:"RELEASED",source:"SIMULATED EXTERNAL RECORD"},
   routing:{revision:"A",source:"IN-BROWSER ERP EMULATOR",operations:CATALOG[2].operations},materialId:"MAT-BAR"},
  {id:"sim-ext-5102",jobNumber:"SIM-5102",partNumber:"SYN-BRACKET-12",revision:"C",quantity:8,status:"OPEN",
   drawing:{number:"GEN-PLATE-12",revision:"C",status:"RELEASED",source:"SIMULATED EXTERNAL RECORD"},
   routing:{revision:"C",source:"IN-BROWSER ERP EMULATOR",operations:CATALOG[0].operations},materialId:"MAT-PLATE"}
];
export const EMULATOR_CONTRACT = [
  {method:"GET",endpoint:"/demo-api/v1/jobs",description:"Return synthetic work orders"},
  {method:"GET",endpoint:"/demo-api/v1/jobs/{jobNumber}/routing",description:"Return the selected fictional routing"},
  {method:"POST",endpoint:"/demo-api/v1/time-tickets",description:"Store one completed demo clock session and return a simulated receipt"}
];

const now = () => new Date().toISOString();
const clone = value => structuredClone(value);
const err = m => {throw Error(m);};
export function seedState() {
  const jobs=EXAMPLES.map((job,i)=>({...clone(job),materialId:"MAT-PLATE",reserved:i===0?36:12,
    origin:"SYNTHETIC STARTER",createdAt:"DEMO SEED",status:"OPEN"}));
  return {schema:1,demo:true,jobs,items:[
    {id:"MAT-PLATE",name:"Generic sheet stock",unit:"blank",onHand:70,reorder:30},
    {id:"MAT-BAR",name:"Generic bar stock",unit:"length",onHand:40,reorder:20},
    {id:"MAT-FIX",name:"Generic hardware",unit:"unit",onHand:160,reorder:60}
  ],purchaseOrders:[],quality:[],receipts:[],pm:seedPm(),events:[
    {id:"evt-seed",at:"DEMO SEED",type:"scenario.initialized",detail:"Entirely invented records, browser only"}
  ]};
}
export function validateState(raw) {
  if(!raw || raw.schema!==1 || raw.demo!==true || !Array.isArray(raw.jobs) || !Array.isArray(raw.items) ||
     !Array.isArray(raw.purchaseOrders) || !Array.isArray(raw.quality) ||
     !Array.isArray(raw.receipts) || !Array.isArray(raw.events)) throw Error("Invalid demo state");
  if (!raw.pm) raw.pm = seedPm(); // Upgrade existing users without resetting their browser ERP data.
  validatePm(raw.pm);
  return raw;
}
export function getJob(state,id) {return state.jobs.find(j=>j.id===id)??null;}
export function reservedTotal(state,itemId) {
  return state.jobs.reduce((sum,j)=>sum+(j.materialId===itemId?(j.reserved||0):0),0);
}
export function available(state,itemId) {
  const item=state.items.find(i=>i.id===itemId);
  if(!item) throw Error("Material not found");
  return item.onHand-reservedTotal(state,itemId);
}
export function openQuality(state,jobId) {
  return state.quality.filter(q=>q.jobId===jobId && q.status==="OPEN");
}
export function packetIssues(state,jobId) {
  const job=getJob(state,jobId);
  if(!job) return ["Work order not found"];
  const issues=evaluatePacket(job);
  if(openQuality(state,jobId).length) issues.push("Open quality hold(s) on this job");
  if(job.reserved<job.quantity) issues.push("Material is not fully reserved for this job");
  return issues;
}
export function change(state,type,detail,action,at=now()) {
  const next=clone(state);
  action(next);
  next.events.push({id:"evt-"+(next.events.length+1),at,type,detail});
  return next;
}
export function createJob(state,partNumber,quantity,at=now()) {
  const c=CATALOG.find(p=>p.partNumber===partNumber);
  if(!c) throw Error("Select a fictional catalog part");
  if(!Number.isInteger(quantity)||quantity<1||quantity>1000) throw Error("Quantity must be 1 to 1000");
  const existing=state.jobs.filter(j=>/^DEMO-6\d{3}$/.test(j.jobNumber)).map(j=>Number(j.jobNumber.slice(-3)));
  const index=Math.max(0,...existing)+1;
  if(index>999) throw Error("Demo job number range exhausted");
  const jobNumber="DEMO-"+String(6000+index), id="created-"+index;
  const next=change(state,"job.created",jobNumber+" / "+c.partNumber,n=>{
    n.jobs.push({id,jobNumber,partNumber:c.partNumber,revision:c.revision,quantity,status:"OPEN",
      materialId:c.materialId,reserved:0,origin:"LOCAL SYNTHETIC",createdAt:at,
      drawing:{number:c.drawing,revision:c.revision,status:"RELEASED",source:"ILLUSTRATIVE ONLY"},
      routing:{revision:c.revision,source:"SYNTHETIC CATALOG",operations:clone(c.operations)}});
  },at);
  return {state:next,jobId:id};
}
export function reserve(state,jobId,at=now()) {
  const j=getJob(state,jobId);
  if(!j) throw Error("Work order not found");
  if(j.status!=="OPEN") throw Error("Job must be OPEN to reserve");
  const need=j.quantity-j.reserved;
  if(need<=0) throw Error("Material already reserved");
  if(available(state,j.materialId)<need) throw Error("Insufficient available material. Receive a synthetic purchase order.");
  return change(state,"material.reserved",j.jobNumber+" / "+need+" units",n=>{
    getJob(n,jobId).reserved=j.quantity;
  },at);
}
export function makePurchaseOrder(state,itemId,quantity,at=now()) {
  if(!state.items.some(i=>i.id===itemId)) throw Error("Material not found");
  if(!Number.isSafeInteger(quantity)||quantity<1||quantity>10000) throw Error("Quantity must be 1 to 10000");
  const id="po-"+(state.purchaseOrders.length+1),number="SIM-PO-"+String(state.purchaseOrders.length+1).padStart(4,"0");
  return change(state,"po.issued",number+" / "+quantity+" units",n=>{
    n.purchaseOrders.push({id,number,itemId,quantity,status:"ORDERED",supplier:"FICTIONAL SUPPLIER",issuedAt:at,receivedAt:null});
  },at);
}
export function receivePurchaseOrder(state,poId,at=now()) {
  const po=state.purchaseOrders.find(p=>p.id===poId);
  if(!po||po.status!=="ORDERED") throw Error("PO not open for receiving");
  return change(state,"inventory.received",po.number+" / "+po.quantity+" units",n=>{
    const p=n.purchaseOrders.find(x=>x.id===poId);
    p.status="RECEIVED";p.receivedAt=at;
    n.items.find(x=>x.id===po.itemId).onHand+=po.quantity;
  },at);
}
export const QUALITY_REASONS=[
  "First-piece dimension outside illustrative tolerance",
  "Generic drawing revision conflict",
  "Demonstration material identification discrepancy",
  "Illustrative visual inspection nonconformance"
];
export function raiseQuality(state,jobId,reason,at=now()) {
  const j=getJob(state,jobId);
  if(!j) throw Error("Work order not found");
  if(!QUALITY_REASONS.includes(reason)) throw Error("Choose a synthetic quality reason");
  const number="SIM-NCR-"+String(state.quality.length+1).padStart(4,"0");
  return change(state,"quality.hold",number+" / "+j.jobNumber,n=>{
    n.quality.push({id:"q-"+(n.quality.length+1),number,jobId,reason,status:"OPEN",openedAt:at,closedAt:null});
  },at);
}
export function closeQuality(state,qId,at=now()) {
  const q=state.quality.find(x=>x.id===qId);
  if(!q||q.status!=="OPEN") throw Error("Quality record not open");
  return change(state,"quality.closed",q.number+" / demo disposition only",n=>{
    const record=n.quality.find(x=>x.id===qId);record.status="CLOSED";record.closedAt=at;
  },at);
}
export function setDrawingRevision(state,jobId,revision,at=now()) {
  const j=getJob(state,jobId);
  if(!j) throw Error("Work order not found");
  if(!["A","B","C","D"].includes(revision)) throw Error("Choose an illustrative A-D revision");
  return change(state,"drawing.example_revision_changed",j.jobNumber+" / revision "+revision,n=>{
    getJob(n,jobId).drawing.revision=revision;
  },at);
}
export function emulatorFetchJobs() {return clone(EXTERNAL_FIXTURES).map(j=>({
  jobNumber:j.jobNumber,partNumber:j.partNumber,revision:j.revision,quantity:j.quantity
}));}
export function emulatorFetchRouting(jobNumber) {
  const job=EXTERNAL_FIXTURES.find(j=>j.jobNumber===jobNumber);
  if(!job) throw Error("Simulated external job not found");
  return clone(job.routing);
}
export function syncEmulatorJob(state,jobNumber,at=now()) {
  const external=EXTERNAL_FIXTURES.find(j=>j.jobNumber===jobNumber);
  if(!external) throw Error("Emulator job not found");
  if(state.jobs.some(j=>j.jobNumber===jobNumber)) return {state,imported:false,jobId:external.id};
  return {state:change(state,"bridge.simulated_job_import",jobNumber+" / in-browser fixture",n=>{
    n.jobs.push({...clone(external),reserved:0,origin:"SIMULATED ERP IMPORT",createdAt:at});
  },at),imported:true,jobId:external.id};
}
export function postEmulatorTicket(state,session,at=now()) {
  if(!session || !session.end) throw Error("Only completed clock sessions may be submitted");
  if(!/^DEMO-[A-Z0-9]{1,16}$/.test(session.employee)) throw Error("Only fictional demo operators are accepted");
  if(!state.jobs.some(j=>j.id===session.jobId)) throw Error("Session job missing from simulated ERP");
  if(state.receipts.some(r=>r.sessionId===session.id)) throw Error("This session already has a simulated receipt");
  const ticket="SIM-TICKET-"+String(state.receipts.length+1).padStart(5,"0");
  return change(state,"bridge.simulated_time_ticket",ticket+" / NOT AN ERP POSTING",n=>{
    n.receipts.push({ticket,sessionId:session.id,jobNumber:session.jobNumber,employee:session.employee,
      seconds:durationSeconds(session),status:"SIMULATED ACCEPTED",receivedAt:at});
  },at);
}
