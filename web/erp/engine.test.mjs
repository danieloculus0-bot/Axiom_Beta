import test from "node:test";
import assert from "node:assert/strict";
import {
  seedState,createJob,getJob,available,reservedTotal,reserve,makePurchaseOrder,
  receivePurchaseOrder,raiseQuality,closeQuality,setDrawingRevision,packetIssues,
  syncEmulatorJob,emulatorFetchJobs,emulatorFetchRouting,postEmulatorTicket,
  validateState,EXTERNAL_FIXTURES
} from "./engine.mjs";
import {startSession,stopSession} from "../ewi/engine.mjs";

const t="2026-10-30T12:00:00.000Z";
const u="2026-10-30T12:00:30.000Z";
test("all built-in records are clearly fictional",()=>{
  const s=seedState();
  assert.ok(s.demo);
  assert.ok(s.jobs.every(j=>j.jobNumber.startsWith("DEMO-")));
  assert.ok(s.items.every(x=>x.id.startsWith("MAT-")));
  assert.ok(EXTERNAL_FIXTURES.every(x=>x.jobNumber.startsWith("SIM-")));
  assert.ok(s.quality.length===0 && s.receipts.length===0);
});
test("standalone EWI starter job and ERP suite have matching identities",()=>{
  const s=seedState();const j=s.jobs[0];
  assert.equal(j.id,"sample-1001");
  assert.equal(j.jobNumber,"DEMO-4102");
  assert.deepEqual(packetIssues(s,j.id),[]);
  assert.equal(reservedTotal(s,"MAT-PLATE"),48);
  assert.equal(available(s,"MAT-PLATE"),22);
});
test("work order creation, material shortage and purchasing receiving are connected",()=>{
  let s=seedState();
  const created=createJob(s,"SYN-TAB-03",60,t);s=created.state;
  assert.equal(getJob(s,created.jobId).reserved,0);
  assert.match(packetIssues(s,created.jobId).join(" "),/reserved/);
  assert.throws(()=>reserve(s,created.jobId,t),/Insufficient/);
  s=makePurchaseOrder(s,"MAT-BAR",40,t);
  const po=s.purchaseOrders[0];assert.equal(po.status,"ORDERED");
  s=receivePurchaseOrder(s,po.id,u);
  assert.equal(s.items.find(i=>i.id==="MAT-BAR").onHand,80);
  s=reserve(s,created.jobId,u);
  assert.equal(getJob(s,created.jobId).reserved,60);
  assert.equal(available(s,"MAT-BAR"),20);
  assert.deepEqual(packetIssues(s,created.jobId),[]);
  assert.throws(()=>receivePurchaseOrder(s,po.id,u),/not open/);
});
test("quality record blocks only its job, then closing unblocks it",()=>{
  let s=seedState();
  s=raiseQuality(s,"sample-1001","Generic drawing revision conflict",t);
  assert.match(packetIssues(s,"sample-1001").join(" "),/quality hold/);
  assert.ok(!packetIssues(s,"sample-1002").some(x=>x.includes("quality hold")));
  s=closeQuality(s,s.quality[0].id,u);
  assert.deepEqual(packetIssues(s,"sample-1001"),[]);
  assert.throws(()=>closeQuality(s,s.quality[0].id,u),/not open/);
});
test("drawing revision conflict blocks, changing illustrative revision clears mismatch",()=>{
  let s=seedState();
  assert.match(packetIssues(s,"sample-1002").join(" "),/Drawing revision A/);
  s=setDrawingRevision(s,"sample-1002","B",t);
  assert.deepEqual(packetIssues(s,"sample-1002"),[]);
  assert.equal(s.jobs[1].drawing.revision,"B");
  assert.throws(()=>setDrawingRevision(s,"sample-1002","Z"),/illustrative/);
});
test("simulated external API is isolated and import is idempotent",()=>{
  let s=seedState();
  const first=emulatorFetchJobs()[0];
  assert.equal(first.jobNumber,"SIM-5101");
  const routing=emulatorFetchRouting(first.jobNumber);
  assert.equal(routing.operations.length,2);
  let result=syncEmulatorJob(s,first.jobNumber,t);
  assert.equal(result.imported,true);
  s=result.state;
  assert.equal(getJob(s,result.jobId).origin,"SIMULATED ERP IMPORT");
  assert.equal(getJob(s,result.jobId).reserved,0);
  const eventCount=s.events.length;
  result=syncEmulatorJob(s,first.jobNumber,t);
  assert.equal(result.imported,false);
  assert.equal(result.state.events.length,eventCount);
  assert.throws(()=>emulatorFetchRouting("REAL-CUSTOMER"),/not found/);
});
test("clocking is a real local event, emulator receipt is an explicit separate action",()=>{
  let s=seedState();
  let clocks=[];
  clocks=startSession(clocks,{id:"clock-1",employee:"DEMO-01",job:s.jobs[0],step:"10",timestamp:t});
  assert.throws(()=>postEmulatorTicket(s,clocks[0],u),/completed/);
  clocks=stopSession(clocks,{id:"clock-1",employee:"DEMO-01",timestamp:u});
  assert.equal(s.receipts.length,0);
  s=postEmulatorTicket(s,clocks[0],u);
  assert.equal(s.receipts[0].status,"SIMULATED ACCEPTED");
  assert.equal(s.receipts[0].seconds,30);
  assert.throws(()=>postEmulatorTicket(s,clocks[0],u),/already/);
});
test("malformed persisted ERP state is not trusted",()=>{
  assert.throws(()=>validateState(null),/Invalid/);
  assert.throws(()=>validateState({schema:1,demo:false,jobs:[]}),/Invalid/);
  const s=seedState();assert.equal(validateState(s),s);
});
test("synthetic purchasing and drawing updates create audit events",()=>{
  let s=seedState();
  s=makePurchaseOrder(s,"MAT-FIX",10,t);
  s=receivePurchaseOrder(s,s.purchaseOrders[0].id,u);
  s=setDrawingRevision(s,"sample-1002","B",u);
  assert.deepEqual(s.events.slice(-3).map(e=>e.type),
    ["po.issued","inventory.received","drawing.example_revision_changed"]);
});
