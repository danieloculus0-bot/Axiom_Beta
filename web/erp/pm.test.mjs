import test from "node:test";
import assert from "node:assert/strict";
import {
  seedPm,validatePm,localDay,dayAdd,dayDiff,taskDue,machineSummary,pmOverview,
  createMachine,addPmTask,completePmTask,requestMaintenance,closeMaintenanceRequest,
  completionsCsv,MACHINE_TYPES,PM_TEMPLATES
} from "./pm.mjs";
import {seedState,validateState,change} from "./engine.mjs";

const day="2026-10-30";
const at="2026-10-30T12:00:00.000Z";
const later="2026-10-31T12:00:00.000Z";
test("public PM fixtures contain only generic fictional equipment",()=>{
 const pm=seedPm(day);
 assert.equal(pm.synthetic,true);
 assert.equal(pm.machines.length,4);
 assert.equal(pm.tasks.length,5);
 assert.ok(pm.machines.every(m=>/^DEMO-M-\d{3}$/.test(m.id)&&m.location.startsWith("Demo Zone")));
 assert.ok(pm.tasks.every(t=>/^DEMO-PM-\d{3}$/.test(t.id)&&t.machineId.startsWith("DEMO-M-")));
 assert.deepEqual(pm.completions,[]);
 assert.deepEqual(pm.requests,[]);
});
test("PM scheduling reproduces standalone tracker overdue today soon and clear statuses",()=>{
 const pm=seedPm(day);
 assert.deepEqual(pm.tasks.map(t=>taskDue(pm,t.id,day).kind),
   ["overdue","today","soon","clear","soon"]);
 assert.equal(pmOverview(pm,day).overdue,1);
 assert.equal(pmOverview(pm,day).dueToday,1);
 assert.equal(pmOverview(pm,day).dueSoon,2);
 assert.equal(machineSummary(pm,"DEMO-M-001",day).kind,"overdue");
 assert.equal(machineSummary(pm,"DEMO-M-002",day).kind,"today");
 assert.equal(machineSummary(pm,"DEMO-M-003",day).kind,"soon");
 assert.equal(machineSummary(pm,"DEMO-M-004",day).kind,"clear");
});
test("local date arithmetic is deterministic and timezone independent",()=>{
 assert.equal(dayAdd("2026-10-30",7),"2026-11-06");
 assert.equal(dayAdd("2026-12-31",1),"2027-01-01");
 assert.equal(dayDiff("2026-11-06","2026-10-30"),7);
 assert.throws(()=>dayAdd("2026-02-30",1),/Invalid calendar/);
 assert.throws(()=>dayAdd("2026-10-30",0.5),/Invalid/);
});
test("PM PASS completion recalculates due and writes a fictional history entry",()=>{
 let pm=seedPm(day);
 const result=completePmTask(pm,"DEMO-PM-001",{
   operator:"DEMO-01",result:"PASS",notes:"Example checklist satisfied",checklistConfirmed:true,at
 });
 assert.equal(pm.completions.length,0);
 pm=result.pm;
 assert.equal(pm.completions.length,1);
 assert.equal(pm.completions[0].operator,"DEMO-01");
 assert.equal(pm.completions[0].result,"PASS");
 assert.equal(pmOverview(pm,day).completedToday,1);
 assert.equal(taskDue(pm,"DEMO-PM-001",day).due,"2026-11-06");
 assert.equal(taskDue(pm,"DEMO-PM-001",day).kind,"soon");
 assert.equal(pm.requests.length,0);
 assert.match(completionsCsv(pm),/DEMO-COMP-0001/);
});
test("completion flagged needs attention raises a separate fictional maintenance request",()=>{
 let pm=seedPm(day);
 const result=completePmTask(pm,"DEMO-PM-001",{
   operator:"DEMO-02",result:"NEEDS ATTENTION",
   notes:"Example condition needs further evaluation",checklistConfirmed:true,at
 });
 pm=result.pm;
 assert.equal(result.raisedRequest,true);
 assert.equal(pm.requests.length,1);
 assert.equal(pm.requests[0].status,"OPEN");
 assert.equal(pm.requests[0].machineId,"DEMO-M-001");
 assert.equal(taskDue(pm,"DEMO-PM-001",day).kind,"overdue","attention record does not auto-clear due PM");
 pm=closeMaintenanceRequest(pm,pm.requests[0].id,undefined,later);
 assert.equal(pm.requests[0].status,"CLOSED");
 assert.equal(pm.requests[0].closedAt,later);
 assert.throws(()=>closeMaintenanceRequest(pm,"DEMO-MWO-0001"),/not open/);
});
test("PM controls enforce synthetic-only templates and demo operator",()=>{
 const pm=seedPm(day);
 assert.throws(()=>completePmTask(pm,"DEMO-PM-001",{operator:"PERSON-123",checklistConfirmed:true,at}),/fictional/);
 assert.throws(()=>completePmTask(pm,"DEMO-PM-001",{operator:"DEMO-01",at}),/Confirm/);
 assert.throws(()=>completePmTask(pm,"DEMO-PM-001",{operator:"DEMO-01",checklistConfirmed:true,notes:"Actual shop findings",at}),/fictional completion note/);
 assert.throws(()=>createMachine(pm,"Customer machine, actual serial"),/fictional/);
 assert.throws(()=>requestMaintenance(pm,null,"Actual bearing failure","High"),/fictional/);
});
test("add fictional asset and recurring task, then record it",()=>{
 let pm=seedPm(day);
 const machine=createMachine(pm,MACHINE_TYPES[5],"Low");pm=machine.pm;
 assert.equal(pm.machines.length,5);
 const task=addPmTask(pm,machine.id,4,30,day);pm=task.pm;
 assert.equal(pm.tasks.length,6);
 assert.equal(taskDue(pm,task.id,day).due,"2026-11-29");
 assert.equal(pm.tasks[5].name,PM_TEMPLATES[4].name);
 pm=completePmTask(pm,task.id,{checklistConfirmed:true,at}).pm;
 assert.equal(pmOverview(pm,day).completedToday,1);
});
test("standalone-style maintenance requests can be opened and closed",()=>{
 let pm=seedPm(day);
 const result=requestMaintenance(pm,"DEMO-M-003","Illustrative abnormal noise","High","DEMO-01",at);
 pm=result.pm;
 assert.equal(pmOverview(pm,day).openRequests,1);
 assert.equal(pm.requests[0].priority,"High");
 pm=closeMaintenanceRequest(pm,result.id,"Example follow-up closed",later);
 assert.equal(pmOverview(pm,day).openRequests,0);
 assert.throws(()=>requestMaintenance(pm,"REAL-ASSET","Illustrative abnormal noise","High"),/Fictional/);
});
test("existing Axiom browser state upgrades with PM without losing other records",()=>{
 let prior=seedState();
 assert.equal(prior.pm.synthetic,true);
 const preservedJob=prior.jobs[0].jobNumber;
 delete prior.pm;
 prior.events.push({id:"test",at,detail:"synthetic",type:"test"});
 const updated=validateState(prior);
 assert.equal(updated.jobs[0].jobNumber,preservedJob);
 assert.equal(updated.events.length,2);
 assert.equal(updated.pm.tasks.length,5);
 const next=change(updated,"pm.task.demo","Synthetic PM",s=>{s.pm=completePmTask(s.pm,"DEMO-PM-001",
 {checklistConfirmed:true,at}).pm;},at);
 assert.equal(next.pm.completions.length,1);
 assert.equal(next.jobs.length,2);
 assert.throws(()=>validatePm({schema:1,synthetic:false}),/Invalid/);
});
