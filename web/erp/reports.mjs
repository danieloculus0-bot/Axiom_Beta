/* Reports derived from synthetic Axiom ERP state only. No external data feeds. */
import {packetIssues,available,reservedTotal} from "./engine.mjs";
import {taskDue,getMachine,localDay} from "./pm.mjs";
import {durationSeconds} from "../ewi/engine.mjs";

export const REPORTS=[
 {id:"jobs",label:"Work order readiness",description:"Job revision, reservations and example hold reasons"},
 {id:"inventory",label:"Inventory position",description:"On hand, reserved and available by stock item"},
 {id:"purchasing",label:"Purchase order status",description:"Synthetic PO lifecycle and receiving"},
 {id:"quality",label:"Quality hold register",description:"Nonconformance status and job association"},
 {id:"labor",label:"Operation clock sessions",description:"Genuine elapsed browser-local time events, not payroll"},
 {id:"pm",label:"PM schedule status",description:"Task due dates based on fictional machines"},
 {id:"requests",label:"Maintenance request queue",description:"Fictional corrective maintenance requests"},
 {id:"events",label:"Browser transaction events",description:"Append-order local activity only"}
];
export function makeReport(state,sessions,id,today=localDay()){
 if(!REPORTS.some(x=>x.id===id))throw Error("Unknown report");
 let columns=[],rows=[];
 switch(id){
 case "jobs":
  columns=["Work order","Part","Revision","Quantity","Reserved","State","Demo checks"];
  rows=state.jobs.map(j=>[j.jobNumber,j.partNumber,j.revision,j.quantity,j.reserved||0,j.status,
    packetIssues(state,j.id).join("; ")||"Example checks passed"]);break;
 case "inventory":
  columns=["Stock item","Description","Unit","On hand","Reserved","Available"];
  rows=state.items.map(i=>[i.id,i.name,i.unit,i.onHand,reservedTotal(state,i.id),available(state,i.id)]);break;
 case "purchasing":
  columns=["PO","Material","Quantity","Supplier","Status","Issued","Received"];
  rows=state.purchaseOrders.map(p=>[p.number,p.itemId,p.quantity,p.supplier,p.status,p.issuedAt,p.receivedAt||""]);break;
 case "quality":
  columns=["NCR","Work order","Reason","Status","Opened","Closed"];
  rows=state.quality.map(q=>[q.number,state.jobs.find(j=>j.id===q.jobId)?.jobNumber||"Unknown",
    q.reason,q.status,q.openedAt,q.closedAt||""]);break;
 case "labor":
  columns=["Operator","Work order","Operation","Clock in","Clock out","Elapsed seconds","Status"];
  rows=sessions.map(s=>[s.employee,s.jobNumber,s.step+" · "+s.operation,s.start,s.end||"",
    durationSeconds(s),s.end?"STOPPED / LOCAL":"ACTIVE / LOCAL"]);break;
 case "pm":
  columns=["Machine","Asset","PM task","Frequency days","Next due","Status"];
  rows=state.pm.tasks.filter(t=>t.active).map(t=>{
   const d=taskDue(state.pm,t.id,today);
   return [getMachine(state.pm,t.machineId)?.name||"Unknown",t.machineId,t.name,t.frequencyDays,
     d.due||"",d.label];
  });break;
 case "requests":
  columns=["Request","Machine","Issue","Priority","Status","Opened","Closed"];
  rows=state.pm.requests.map(r=>[r.id,r.machineId||"General",r.type,r.priority,r.status,
    r.submittedAt,r.closedAt||""]);break;
 case "events":
  columns=["Timestamp","Event","Description"];
  rows=state.events.map(e=>[e.at,e.type,e.detail]);break;
 }
 return {id,title:REPORTS.find(x=>x.id===id).label,columns,rows,fictional:true};
}
export function reportCsv(report){
 if(!report||!Array.isArray(report.columns)||!Array.isArray(report.rows))throw Error("Invalid report");
 const cell=value=>{
  const raw=String(value??"");
  const safe=/^[=+\-@\t\r\n]/.test(raw)?"'"+raw:raw;
  return '"'+safe.replace(/"/g,'""')+'"';
 };
 return [report.columns,...report.rows].map(row=>row.map(cell).join(",")).join("\r\n")+"\r\n";
}
