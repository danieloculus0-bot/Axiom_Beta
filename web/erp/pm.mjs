/* Axiom PM Tracker Pages adapter.
 * Mirrors the public PM-Tracker model and due-date conventions using ORIGINAL
 * synthetic records only. Never load local employer data or real equipment.
 * Browser-local state is a demonstration, not a site PM/safety system.
 */
const clone=x=>structuredClone(x);
const fail=message=>{throw Error(message);};
const ISO_DAY=/^\d{4}-\d{2}-\d{2}$/;
export const DEMO_OPERATOR="DEMO-01";
export const MACHINE_TYPES=[
  "Generic cutting station","Generic pump","Generic air compressor",
  "Generic test fixture","Generic conveyor demonstrator","Generic bench mill"
];
export const PM_TEMPLATES=[
  {name:"Inspect guards and visible condition",description:"Perform a visual, non-invasive example inspection.",frequencyDays:7,estimatedMinutes:10,role:"Demo technician",safety:"Follow the equipment-specific approved safety procedure. This simulation is not an authorization to service equipment."},
  {name:"Review lubrication schedule",description:"Check a fictional lubrication record against the example schedule.",frequencyDays:30,estimatedMinutes:15,role:"Demo maintenance",safety:"Follow the applicable manufacturer instructions and approved energy-control procedures."},
  {name:"Check example filter indicator",description:"Record a fictional indicator condition without opening the machine.",frequencyDays:14,estimatedMinutes:8,role:"Demo maintenance",safety:"Do not treat the browser checklist as an isolation, inspection or lockout procedure."},
  {name:"Verify example instrument status",description:"Compare the fictional instrument tag to its sample due-date record.",frequencyDays:90,estimatedMinutes:12,role:"Demo quality",safety:"No actual calibration or approval is performed."},
  {name:"Review example housekeeping condition",description:"Inspect a simulated workstation area for routine housekeeping.",frequencyDays:7,estimatedMinutes:6,role:"Demo operator",safety:"Never enter a hazardous zone based on this fictional checklist."}
];
export const REQUEST_TYPES=[
  "Illustrative abnormal noise","Simulated visual damage",
  "Generic maintenance follow-up","Fictional indicator out of range",
  "Demonstration housekeeping request"
];
export const COMPLETION_NOTES=[
  "Example checklist satisfied","Illustrative routine review completed",
  "Example condition needs further evaluation"
];
export const PRIORITIES=["Low","Medium","High"];
export function localDay(date=new Date()){
  const d=date instanceof Date?date:new Date(date);
  if(Number.isNaN(d.getTime()))throw Error("Invalid date");
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-");
}
export function dayAdd(day,delta){
  if(!ISO_DAY.test(day)||!Number.isInteger(delta))throw Error("Invalid date or day offset");
  const [year,month,date]=day.split("-").map(Number);
  const d=new Date(Date.UTC(year,month-1,date));
  if(d.toISOString().slice(0,10)!==day)throw Error("Invalid calendar date");
  d.setUTCDate(d.getUTCDate()+delta);
  return d.toISOString().slice(0,10);
}
export function dayDiff(a,b){
  const utc=day=>{const [y,m,d]=day.split("-").map(Number);return Date.UTC(y,m-1,d);};
  if(!ISO_DAY.test(a)||!ISO_DAY.test(b))throw Error("Invalid ISO day");
  return Math.round((utc(a)-utc(b))/86400000);
}
export function seedPm(today=localDay()){
  return {schema:1,synthetic:true,machines:[
    {id:"DEMO-M-001",name:"Generic cutting station",department:"Sample production",location:"Demo Zone A",criticality:"Medium",active:true},
    {id:"DEMO-M-002",name:"Generic coolant pump",department:"Sample utilities",location:"Demo Zone B",criticality:"High",active:true},
    {id:"DEMO-M-003",name:"Generic air compressor",department:"Sample utilities",location:"Demo Zone C",criticality:"High",active:true},
    {id:"DEMO-M-004",name:"Generic test fixture",department:"Sample quality",location:"Demo Zone D",criticality:"Low",active:true}
  ],tasks:[
    {id:"DEMO-PM-001",machineId:"DEMO-M-001",...clone(PM_TEMPLATES[0]),nextDueSeed:dayAdd(today,-2),active:true},
    {id:"DEMO-PM-002",machineId:"DEMO-M-002",...clone(PM_TEMPLATES[1]),nextDueSeed:today,active:true},
    {id:"DEMO-PM-003",machineId:"DEMO-M-003",...clone(PM_TEMPLATES[2]),nextDueSeed:dayAdd(today,4),active:true},
    {id:"DEMO-PM-004",machineId:"DEMO-M-004",...clone(PM_TEMPLATES[3]),nextDueSeed:dayAdd(today,25),active:true},
    {id:"DEMO-PM-005",machineId:"DEMO-M-001",...clone(PM_TEMPLATES[4]),nextDueSeed:dayAdd(today,6),active:true}
  ],completions:[],requests:[]};
}
export function validatePm(pm){
  if(!pm||pm.schema!==1||pm.synthetic!==true||!Array.isArray(pm.machines)||
     !Array.isArray(pm.tasks)||!Array.isArray(pm.completions)||!Array.isArray(pm.requests))
    throw Error("Invalid demo maintenance state");
  return pm;
}
export function getMachine(pm,id){return pm.machines.find(m=>m.id===id)||null;}
export function getTask(pm,id){return pm.tasks.find(t=>t.id===id)||null;}
export function taskDue(pm,taskId,today=localDay()){
  const task=getTask(pm,taskId);
  if(!task||!task.active)return {label:"INACTIVE",kind:"inactive",due:null,days:null};
  const passing=pm.completions.filter(c=>c.taskId===taskId&&c.result==="PASS")
    .sort((a,b)=>b.completedAt.localeCompare(a.completedAt))[0];
  const due=passing?dayAdd(passing.completedAt.slice(0,10),task.frequencyDays):task.nextDueSeed;
  if(!due)return {label:"UNSCHEDULED",kind:"unscheduled",due:null,days:null};
  const days=dayDiff(due,today);
  return {due,days,label:days<0?"OVERDUE":days===0?"DUE TODAY":days<=7?"DUE SOON":"CLEAR",
          kind:days<0?"overdue":days===0?"today":days<=7?"soon":"clear"};
}
export function machineSummary(pm,machineId,today=localDay()){
  const machine=getMachine(pm,machineId);
  if(!machine)throw Error("Fictional machine not found");
  const tasks=pm.tasks.filter(t=>t.machineId===machineId&&t.active).map(t=>({...t,...taskDue(pm,t.id,today)}));
  const kind=["overdue","today","soon","clear","unscheduled"].find(x=>tasks.some(t=>t.kind===x))||"unscheduled";
  const next=tasks.map(t=>t.due).filter(Boolean).sort()[0]||null;
  const labels={overdue:"OVERDUE",today:"DUE TODAY",soon:"DUE SOON",clear:"CLEAR",unscheduled:"NO SCHEDULE"};
  return {machine,tasks,kind,label:labels[kind],nextDue:next,
    overdue:tasks.filter(t=>t.kind==="overdue").length,today:tasks.filter(t=>t.kind==="today").length,
    soon:tasks.filter(t=>t.kind==="soon").length};
}
export function pmOverview(pm,today=localDay()){
  validatePm(pm);
  const summaries=pm.machines.filter(m=>m.active).map(m=>machineSummary(pm,m.id,today));
  const tasks=summaries.flatMap(m=>m.tasks);
  return {machines:summaries.length,tasks:tasks.length,overdue:tasks.filter(t=>t.kind==="overdue").length,
    dueToday:tasks.filter(t=>t.kind==="today").length,dueSoon:tasks.filter(t=>t.kind==="soon").length,
    completedToday:pm.completions.filter(c=>c.completedAt.slice(0,10)===today).length,
    openRequests:pm.requests.filter(r=>!["CLOSED","CANCELLED"].includes(r.status)).length,summaries};
}
const operatorCheck=operator=>{
  if(typeof operator!=="string"||!/^DEMO-[A-Z0-9]{1,16}$/.test(operator.toUpperCase()))
    fail("Use a fictional operator code such as DEMO-01");
  return operator.toUpperCase();
};
export function completePmTask(pm,taskId,{operator=DEMO_OPERATOR,result="PASS",notes=COMPLETION_NOTES[0],
  checklistConfirmed=false,at=new Date().toISOString()}={}){
  const task=getTask(pm,taskId);
  if(!task||!task.active)throw Error("Active example PM task not found");
  if(!getMachine(pm,task.machineId))throw Error("Example asset not found");
  const worker=operatorCheck(operator);
  if(!["PASS","NEEDS ATTENTION"].includes(result))throw Error("Invalid demo completion result");
  if(!COMPLETION_NOTES.includes(notes))throw Error("Choose a fictional completion note");
  if(checklistConfirmed!==true)throw Error("Confirm that the sample checklist was reviewed");
  if(!Number.isFinite(Date.parse(at)))throw Error("Invalid completion timestamp");
  const n=clone(pm),id="DEMO-COMP-"+String(n.completions.length+1).padStart(4,"0");
  n.completions.push({id,taskId,machineId:task.machineId,operator:worker,result,notes,completedAt:at});
  if(result==="NEEDS ATTENTION"){
    n.requests.push({id:"DEMO-MWO-"+String(n.requests.length+1).padStart(4,"0"),
      machineId:task.machineId,type:"Generic maintenance follow-up",priority:"Medium",
      submittedBy:worker,sourceTaskId:task.id,status:"OPEN",submittedAt:at,closedAt:null,
      assignedTo:null,resolution:null});
  }
  return {pm:n,id,raisedRequest:result==="NEEDS ATTENTION"};
}
export function createMachine(pm,type,criticality="Medium"){
  if(!MACHINE_TYPES.includes(type))throw Error("Choose a prebuilt fictional machine type");
  if(!["Low","Medium","High"].includes(criticality))throw Error("Choose demo criticality");
  const n=clone(pm),serial=n.machines.length+1,id="DEMO-M-"+String(serial).padStart(3,"0");
  n.machines.push({id,name:type,department:"Sample production",location:"Demo Zone "+String(serial),
    criticality,active:true});
  return {pm:n,id};
}
export function addPmTask(pm,machineId,templateIndex,frequencyDays,at=localDay()){
  const machine=getMachine(pm,machineId);
  const template=PM_TEMPLATES[templateIndex];
  if(!machine||!machine.active)throw Error("Select a fictional machine");
  if(!template)throw Error("Choose a built-in fictional task");
  if(!Number.isInteger(frequencyDays)||frequencyDays<1||frequencyDays>3650)
    throw Error("Frequency must be 1 to 3650 days");
  const n=clone(pm),id="DEMO-PM-"+String(n.tasks.length+1).padStart(3,"0");
  n.tasks.push({id,machineId,...clone(template),frequencyDays,nextDueSeed:dayAdd(at,frequencyDays),active:true});
  return {pm:n,id};
}
export function requestMaintenance(pm,machineId,type,priority,submittedBy=DEMO_OPERATOR,
 at=new Date().toISOString()){
  if(machineId&&!getMachine(pm,machineId))throw Error("Fictional machine not found");
  if(!REQUEST_TYPES.includes(type)||!PRIORITIES.includes(priority))throw Error("Choose a fictional issue and priority");
  if(!Number.isFinite(Date.parse(at)))throw Error("Invalid timestamp");
  const n=clone(pm),id="DEMO-MWO-"+String(n.requests.length+1).padStart(4,"0");
  n.requests.push({id,machineId:machineId||null,type,priority,submittedBy:operatorCheck(submittedBy),
    sourceTaskId:null,status:"OPEN",submittedAt:at,closedAt:null,assignedTo:null,resolution:null});
  return {pm:n,id};
}
export function closeMaintenanceRequest(pm,id,resolution="Example follow-up closed",at=new Date().toISOString()){
  const r=pm.requests.find(x=>x.id===id);
  if(!r||!["OPEN","IN PROGRESS"].includes(r.status))throw Error("Demo maintenance request is not open");
  const n=clone(pm),item=n.requests.find(x=>x.id===id);
  item.status="CLOSED";item.closedAt=at;item.assignedTo="DEMO-MAINT";item.resolution=resolution;
  return n;
}
export function completionsCsv(pm){
  const csvCell=value=>'"'+String(value??"").replace(/"/g,'""').replace(/^[=+\-@]/,"'$&")+'"';
  const cols=["Completion ID","Machine ID","Task ID","Completed By","Completion Date","Completion Time","Notes","Pass/Fail"];
  const values=pm.completions.map(c=>[c.id,c.machineId,c.taskId,c.operator,c.completedAt.slice(0,10),
    c.completedAt.slice(11,19),c.notes,c.result]);
  return [cols,...values].map(row=>row.map(csvCell).join(",")).join("\r\n")+"\r\n";
}


/* Maintenance request follow-up and verification for the fictional browser demo.
 * Existing closeMaintenanceRequest API is preserved for old PM tests.
 */
export const MAINTENANCE_FOLLOWUPS=[
 "Maintenance notified","Work status requested","Machine unavailable",
 "Replacement component pending","Work completion checked",
 "Verification scheduled","Further action required"
];
export function assignMaintenanceRequest(pm,id,owner,dueDate,at=new Date().toISOString()){
 if(!["DEMO-MAINT","DEMO-OPS","DEMO-QA"].includes(owner))throw Error("Choose a fictional assignee");
 dayAdd(dueDate,0);
 const r=pm.requests.find(r=>r.id===id);
 if(!r||["CLOSED","CANCELLED"].includes(r.status))throw Error("Maintenance request is no longer actionable");
 const next=clone(pm),item=next.requests.find(x=>x.id===id);
 item.assignedTo=owner;item.dueDate=dueDate;item.followups||=[];
 if(item.status==="OPEN")item.status="IN PROGRESS";
 item.updatedAt=at;
 return next;
}
export function followupMaintenanceRequest(pm,id,note,at=new Date().toISOString()){
 if(!MAINTENANCE_FOLLOWUPS.includes(note))throw Error("Choose an example follow-up");
 const r=pm.requests.find(x=>x.id===id);
 if(!r||r.status==="CLOSED")throw Error("Maintenance request already closed");
 const next=clone(pm),item=next.requests.find(x=>x.id===id);
 item.followups||=[];item.followups.push({at,by:"DEMO-MAINT",note});
 item.updatedAt=at;
 return next;
}
