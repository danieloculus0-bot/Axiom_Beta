import {recordQualityDisposition,recordQualityFollowup,closeReviewedQuality,recordQualityInspection,recordQualityCorrectiveAction,reviewQualityCorrectiveAction} from "./quality-case.mjs";
import {renderQualityCase,qualityInspectionCorrectiveTarget,qualityCorrectiveReviewTarget,qualityEffectivenessInspectionTarget,qualityCorrectiveInspectionTarget,qualityInspectionCorrectiveTargets,qualityJobInspectionTarget,qualityJobCorrectiveTarget,qualityJobFollowupTarget,renderJobQualityEvidence,renderJobRegisterInspectionEvidence} from "./quality-case-view.mjs";
import {contextActions,contextRelated} from "./context-actions.mjs";
import {readFileSync} from "node:fs";
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

test("Quality Forge case review stays linked to the canonical fictional job and EWI hold",()=>{
  let state=seedState();
  state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",t);
  const id=state.quality[0].id;
  assert.equal(state.quality[0].jobId,"sample-1001");
  assert.ok(contextActions(state,"quality",id).some(action=>action.view==="quality"));
  assert.deepEqual(contextRelated(state,{type:"quality",id},"quality"),["sample-1001"]);
  assert.match(renderQualityCase(state,id),/href="#routing" data-job="sample-1001"/);
  assert.match(renderQualityCase(state,id),/data-form="quality-disposition"/);
  assert.match(renderQualityCase(state,id),/disabled>Close reviewed demo case/);
  assert.throws(()=>closeReviewedQuality(state,id,t),/disposition/);
  state=recordQualityDisposition(state,id,"RETURN_FOR_REVIEW","Further fictional review required",t);
  assert.throws(()=>closeReviewedQuality(state,id,t),/keeps this fictional quality case open/);
  assert.match(renderQualityCase(state,id),/disabled>Close reviewed demo case/);
  state=recordQualityDisposition(state,id,"REWORK","Fictional rework review needed",t);
  assert.equal(state.quality[0].disposition.decision,"REWORK");
  assert.match(packetIssues(state,"sample-1001").join(" "),/quality hold/);
  assert.doesNotMatch(renderQualityCase(state,id),/disabled>Close reviewed demo case/);
  state=recordQualityFollowup(state,id,"Sample rework check planned",u);
  state=closeReviewedQuality(state,id,u);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.equal(state.quality[0].followUps.length,1);
  assert.deepEqual(packetIssues(state,"sample-1001"),[]);
  assert.deepEqual(state.events.slice(-5).map(e=>e.type),[
    "quality.hold","quality.disposition.recorded","quality.disposition.recorded",
    "quality.followup.recorded","quality.closed"
  ]);
  state=recordQualityFollowup(state,id,"Effectiveness still requires human review","2026-10-31T12:00:00Z");
  assert.equal(state.quality[0].followUps.length,2);
  assert.throws(()=>recordQualityDisposition(state,id,"SCRAP","After closure",u),/open/);
  assert.match(renderQualityCase(state,id),/Effectiveness still requires human review/);
});
test("quality case transitions reject invalid decisions and do not change unrelated records",()=>{
  let state=seedState();
  state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",t);
  const id=state.quality[0].id;
  const original=state;
  assert.throws(()=>recordQualityDisposition(state,id,"APPROVED","Pretend release",t),/listed/);
  assert.throws(()=>recordQualityDisposition(state,id,"SCRAP","x",t),/5 to 500/);
  assert.throws(()=>recordQualityFollowup(state,"missing","A fictional note",t),/not found/);
  assert.throws(()=>recordQualityFollowup(state,id,"A fictional note","invalid"),/timestamp/);
  assert.equal(state,original);
  assert.equal(state.quality[0].disposition,undefined);
  assert.ok(!packetIssues(state,"sample-1002").some(x=>x.includes("quality hold")));
  state=recordQualityFollowup(state,id,'Fictional <img src=x onerror=alert(1)> follow-up',u);
  const html=renderQualityCase(state,id);
  assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html,/<img src=x/);
});
test("quality case is reachable through register, contextual Open with, and linked job actions",()=>{
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.match(app,/data-action="select-quality"/);
  assert.match(app,/selectedQualityId=next\.quality\.at\(-1\)\.id/);
  assert.match(app,/renderQualityCase\(state,selected\?\.id\)/);
  assert.match(app,/case "quality-disposition"/);
  assert.match(app,/case "quality-followup"/);
  assert.match(app,/case "quality-reviewed-close"/);
  assert.doesNotMatch(app,/data-action="close-ncr"/);
  const state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const actions=contextActions(state,"quality",state.quality[0].id);
  assert.ok(actions.some(a=>a.view==="quality"));
  assert.ok(actions.some(a=>a.view==="jobs"));
  assert.ok(actions.some(a=>a.view==="ewi"));
});

test("Quality Forge inspection evidence uses the existing NCR, job and routed operation",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const id=state.quality[0].id,job=state.jobs.find(j=>j.id==="sample-1001");
  const op=job.routing.operations[0],before=state;
  assert.match(renderQualityCase(state,id),/data-form="quality-inspection"/);
  assert.match(renderQualityCase(state,id),/name="step"/);
  assert.throws(()=>recordQualityInspection(state,id,"FIRST_PIECE","999","PASS","Sample check",t),/routed operation/);
  assert.throws(()=>recordQualityInspection(state,id,"INVALID",op.step,"PASS","Sample check",t),/listed fictional inspection stage/);
  assert.throws(()=>recordQualityInspection(state,id,"FIRST_PIECE",op.step,"ACCEPTED","Sample check",t),/listed fictional inspection result/);
  assert.throws(()=>recordQualityInspection(state,id,"FIRST_PIECE",op.step,"FAIL","x",t),/5 to 500/);
  assert.throws(()=>recordQualityInspection(state,id,"FIRST_PIECE",op.step,"FAIL","Sample check","invalid"),/timestamp/);
  assert.strictEqual(state,before);
  state=recordQualityInspection(state,id,"FIRST_PIECE",op.step,"FAIL",
    'Fictional <img src=x onerror=alert(1)> observation',u);
  const evidence=state.quality[0].inspections[0];
  assert.equal(evidence.id,id+"-inspection-1");
  assert.equal(evidence.step,String(op.step));
  assert.equal(evidence.operation,op.name);
  assert.equal(evidence.center,op.center);
  assert.equal(evidence.jobRevision,job.revision);
  assert.equal(evidence.drawingRevision,job.drawing.revision);
  assert.equal(state.events.at(-1).type,"quality.inspection.recorded");
  assert.match(packetIssues(state,"sample-1001").join(" "),/quality hold/);
  assert.ok(!packetIssues(state,"sample-1002").some(issue=>issue.includes("quality hold")));
  const html=renderQualityCase(state,id);
  assert.match(html,/href="#routing" data-job="sample-1001"/);
  assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html,/<img src=x/);
  assert.match(html,/drawing rev/);
  assert.match(html,/FAIL/);
  assert.match(readFileSync(new URL("./app.mjs",import.meta.url),"utf8"),/case "quality-inspection"/);
});
test("inspection observations survive case closure without claiming automatic approval",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,id,"IN_PROCESS",step,"REVIEW_REQUIRED","Further sample review needed",t);
  state=recordQualityDisposition(state,id,"SCRAP","Fictional disposition documented",u);
  assert.match(packetIssues(state,"sample-1001").join(" "),/quality hold/);
  state=closeReviewedQuality(state,id,u);
  assert.equal(state.quality[0].inspections.length,1);
  assert.equal(state.quality[0].inspections[0].result,"REVIEW_REQUIRED");
  assert.doesNotMatch(renderQualityCase(state,id),/data-form="quality-inspection"/);
  assert.match(renderQualityCase(state,id),/Further sample review needed/);
  assert.throws(()=>recordQualityInspection(state,id,"FINAL_REVIEW",step,"PASS","Late inspection",u),/open fictional quality case/);
});


test("Quality Forge corrective action links an existing NCR, optional inspection and responsible fictional role",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,id,"FIRST_PIECE",step,"FAIL","Fictional first piece failed",t);
  const inspectionId=state.quality[0].inspections[0].id,original=state;
  assert.throws(()=>recordQualityCorrectiveAction(state,id,"PERSON","Example action",inspectionId,u),/owner role/);
  assert.throws(()=>recordQualityCorrectiveAction(state,id,"QUALITY","Example action","q-2-inspection-1",u),/on this fictional case/);
  assert.throws(()=>recordQualityCorrectiveAction(state,id,"QUALITY","x",inspectionId,u),/5 to 500/);
  assert.throws(()=>recordQualityCorrectiveAction(state,"missing","Example role","Example action",inspectionId,u),/open fictional quality case/);
  assert.throws(()=>recordQualityCorrectiveAction(state,id,"QUALITY","Example action",inspectionId,"bad"),/timestamp/);
  assert.strictEqual(state,original);
  state=recordQualityCorrectiveAction(state,id,"QUALITY",
    'Review fictional <img src=x onerror=alert(1)> process check',inspectionId,u);
  const q=state.quality[0],action=q.correctiveActions[0];
  assert.equal(q.jobId,"sample-1001");
  assert.equal(action.id,id+"-action-1");
  assert.equal(action.sourceInspectionId,inspectionId);
  assert.equal(action.ownerRole,"QUALITY");
  assert.deepEqual(action.reviews,[]);
  assert.equal(state.events.at(-1).type,"quality.corrective_action.recorded");
  assert.match(packetIssues(state,"sample-1001").join(" "),/quality hold/);
  assert.ok(!packetIssues(state,"sample-1002").some(issue=>issue.includes("quality hold")));
  const html=renderQualityCase(state,id);
  assert.match(html,/data-form="quality-corrective-action"/);
  assert.match(html,/data-form="quality-effectiveness"/);
  assert.match(html,/q-1-inspection-1/);
  assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html,/<img src=x/);
  assert.ok(contextActions(state,"quality",id).some(a=>a.view==="quality"));
  assert.match(html,/href="#routing" data-job="sample-1001"/);
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.match(app,/case "quality-corrective-action"/);
  assert.match(app,/case "quality-effectiveness"/);
  assert.match(app,/data-action="select-quality"/);
});
test("effectiveness review is historical evidence, not automatic case closure or release",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const id=state.quality[0].id;
  state=recordQualityCorrectiveAction(state,id,"ENGINEERING","Update a fictional check", "",t);
  const actionId=state.quality[0].correctiveActions[0].id,original=state;
  assert.throws(()=>reviewQualityCorrectiveAction(state,id,"missing","EFFECTIVE","Sample check",u),/not found/);
  assert.throws(()=>reviewQualityCorrectiveAction(state,id,actionId,"APPROVED","Sample check",u),/effectiveness result/);
  assert.throws(()=>reviewQualityCorrectiveAction(state,id,actionId,"EFFECTIVE","x",u),/5 to 500/);
  assert.throws(()=>reviewQualityCorrectiveAction(state,id,actionId,"EFFECTIVE","Sample check","invalid"),/timestamp/);
  assert.throws(()=>reviewQualityCorrectiveAction(state,id,actionId,"EFFECTIVE","Sample check","2026-10-29T12:00:00Z"),/cannot precede/);
  assert.strictEqual(state,original);
  state=reviewQualityCorrectiveAction(state,id,actionId,"MORE_EVIDENCE","Further fictional evidence required",u);
  assert.equal(state.quality[0].status,"OPEN");
  assert.equal(state.quality[0].correctiveActions[0].reviews[0].result,"MORE_EVIDENCE");
  assert.match(packetIssues(state,"sample-1001").join(" "),/quality hold/);
  state=recordQualityDisposition(state,id,"SCRAP","Fictional disposition documented",u);
  state=closeReviewedQuality(state,id,u);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.deepEqual(packetIssues(state,"sample-1001"),[]);
  assert.doesNotMatch(renderQualityCase(state,id),/data-form="quality-corrective-action"/);
  assert.match(renderQualityCase(state,id),/data-form="quality-effectiveness"/);
  assert.throws(()=>recordQualityCorrectiveAction(state,id,"QUALITY","Late action","",u),/open fictional quality case/);
  state=reviewQualityCorrectiveAction(state,id,actionId,"NOT_EFFECTIVE",
    "Fictional sample still needs follow-up","2026-10-31T12:00:00Z");
  const reviews=state.quality[0].correctiveActions[0].reviews;
  assert.equal(reviews.length,2);
  assert.equal(reviews[1].id,actionId+"-review-2");
  assert.equal(state.quality[0].status,"CLOSED");
  assert.equal(state.events.at(-1).type,"quality.corrective_action.effectiveness_reviewed");
  assert.match(renderQualityCase(state,id),/Fictional sample still needs follow-up/);
  state=recordQualityFollowup(state,id,"Further fictional review planned","2026-10-31T12:01:00Z");
  assert.equal(state.quality[0].followUps.length,1);
});


test("inspection and chronology start one corrective-action draft only on the matching open NCR",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL","Fictional inspection needs action",u);
  const inspectionId=state.quality[0].inspections[0].id;
  assert.deepEqual(qualityInspectionCorrectiveTarget(state,caseId,inspectionId),
    {caseId,inspectionId,jobId:"sample-1001"});
  assert.equal(qualityInspectionCorrectiveTarget(state,"another-case",inspectionId),null);
  assert.equal(qualityInspectionCorrectiveTarget(state,caseId,"missing-inspection"),null);
  const html=renderQualityCase(state,caseId);
  assert.equal((html.match(/data-action="quality-inspection-corrective"/g)||[]).length,2);
  assert.match(html,/data-form="quality-corrective-action"/);
  assert.equal(state.quality[0].correctiveActions?.length??0,0);
  const otherJobMissing=structuredClone(state);
  otherJobMissing.jobs=otherJobMissing.jobs.filter(j=>j.id!=="sample-1001");
  assert.equal(qualityInspectionCorrectiveTarget(otherJobMissing,caseId,inspectionId),null);
  state=recordQualityDisposition(state,caseId,"SCRAP","Fictional disposition recorded",u);
  state=closeReviewedQuality(state,caseId,u);
  assert.equal(qualityInspectionCorrectiveTarget(state,caseId,inspectionId),null);
  assert.doesNotMatch(renderQualityCase(state,caseId),/data-action="quality-inspection-corrective"/);
});

test("corrective action receipt and chronology open one exact effectiveness review draft after closure",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id;
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY","Fictional corrective check one","",t);
  state=recordQualityCorrectiveAction(state,caseId,"ENGINEERING","Fictional corrective check two","",u);
  const actionId=state.quality[0].correctiveActions[1].id;
  assert.deepEqual(qualityCorrectiveReviewTarget(state,caseId,actionId),
    {caseId,actionId,jobId:"sample-1001"});
  assert.equal(qualityCorrectiveReviewTarget(state,"other-case",actionId),null);
  assert.equal(qualityCorrectiveReviewTarget(state,caseId,"missing-action"),null);
  assert.equal(qualityCorrectiveReviewTarget(state,caseId,undefined),null);
  const html=renderQualityCase(state,caseId);
  const button='data-action="quality-corrective-review" data-case="'+caseId+'" data-id="'+actionId+'"';
  assert.equal(html.split(button).length-1,2);
  assert.equal(state.quality[0].correctiveActions[1].reviews.length,0);
  const missingJob=structuredClone(state);
  missingJob.jobs=missingJob.jobs.filter(job=>job.id!=="sample-1001");
  assert.equal(qualityCorrectiveReviewTarget(missingJob,caseId,actionId),null);
  assert.doesNotMatch(renderQualityCase(missingJob,caseId),/data-action="quality-corrective-review"/);
  state=recordQualityDisposition(state,caseId,"SCRAP","Fictional disposition review",u);
  state=closeReviewedQuality(state,caseId,u);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.deepEqual(qualityCorrectiveReviewTarget(state,caseId,actionId),
    {caseId,actionId,jobId:"sample-1001"});
  assert.equal(renderQualityCase(state,caseId).split(button).length-1,2);
  assert.match(readFileSync(new URL("./app.mjs",import.meta.url),"utf8"),
    /if\(action==="quality-corrective-review"\)/);
});

test("effectiveness evidence traces only its own linked source inspection through two canonical entry points",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL","Synthetic source observation",t);
  const inspectionId=state.quality[0].inspections[0].id;
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY","Synthetic linked corrective action",inspectionId,u);
  state=recordQualityCorrectiveAction(state,caseId,"ENGINEERING","Synthetic case-level action","",u);
  const linkedAction=state.quality[0].correctiveActions[0].id;
  const caseAction=state.quality[0].correctiveActions[1].id;
  const v="2026-10-30T12:01:00.000Z";
  state=reviewQualityCorrectiveAction(state,caseId,linkedAction,"MORE_EVIDENCE","Synthetic linked effectiveness review",v);
  state=reviewQualityCorrectiveAction(state,caseId,caseAction,"EFFECTIVE","Synthetic case-level effectiveness review",v);
  const record=state.quality[0],reviewId=record.correctiveActions[0].reviews[0].id;
  const caseReviewId=record.correctiveActions[1].reviews[0].id;
  assert.deepEqual(qualityEffectivenessInspectionTarget(record,reviewId),{kind:"inspection",id:inspectionId});
  assert.equal(qualityEffectivenessInspectionTarget(record,caseReviewId),null);
  assert.equal(qualityEffectivenessInspectionTarget(record,"other-case-review"),null);
  const html=renderQualityCase(state,caseId);
  const link='data-action="quality-evidence-focus" data-case="'+caseId+
    '" data-kind="inspection" data-id="'+inspectionId+'">View source inspection';
  assert.equal(html.split(link).length-1,3,"review receipt and chronology plus corrective chronology share source evidence");
  assert.equal(state.quality[0].inspections.length,1,"read-only links must not duplicate evidence");
  const missing=structuredClone(record);missing.inspections=[];
  assert.equal(qualityEffectivenessInspectionTarget(missing,reviewId),null);
  const ambiguous=structuredClone(record);ambiguous.inspections.push({...ambiguous.inspections[0]});
  assert.equal(qualityEffectivenessInspectionTarget(ambiguous,reviewId),null);
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic disposition reviewed",v);
  state=closeReviewedQuality(state,caseId,v);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.equal(renderQualityCase(state,caseId).split(link).length-1,3,
    "historical inspection remains reachable after fictional case closure");
});

test("corrective receipt and chronology link only an unambiguous source inspection",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL","Synthetic observation",t);
  const inspectionId=state.quality[0].inspections[0].id;
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY","Synthetic inspection response",inspectionId,u);
  state=recordQualityCorrectiveAction(state,caseId,"ENGINEERING","Synthetic case-level response","",u);
  const record=state.quality[0],actionId=record.correctiveActions[0].id;
  assert.deepEqual(qualityCorrectiveInspectionTarget(record,actionId),{kind:"inspection",id:inspectionId});
  assert.equal(qualityCorrectiveInspectionTarget(record,record.correctiveActions[1].id),null);
  assert.equal(qualityCorrectiveInspectionTarget(record,"unrelated-action"),null);
  const link='data-action="quality-evidence-focus" data-case="'+caseId+
    '" data-kind="inspection" data-id="'+inspectionId+'">View source inspection';
  const receiptLink='data-action="quality-evidence-focus" data-case="'+caseId+
    '" data-kind="inspection" data-id="'+inspectionId+'">View observation';
  assert.equal(renderQualityCase(state,caseId).split(link).length-1,1,
    "corrective chronology navigates to the source inspection");
  assert.equal(renderQualityCase(state,caseId).split(receiptLink).length-1,1,
    "corrective receipt preserves its existing observation link");
  const missing=structuredClone(record);missing.inspections=[];
  assert.equal(qualityCorrectiveInspectionTarget(missing,actionId),null);
  const stale=structuredClone(record);stale.correctiveActions[0].sourceInspectionId="missing-inspection";
  assert.equal(qualityCorrectiveInspectionTarget(stale,actionId),null);
  const ambiguous=structuredClone(record);ambiguous.inspections.push({...ambiguous.inspections[0]});
  assert.equal(qualityCorrectiveInspectionTarget(ambiguous,actionId),null);
  assert.doesNotMatch(renderQualityCase({...state,quality:[ambiguous]},caseId),
    /View source inspection|View observation/,"ambiguous evidence must not create a misleading link");
  const duplicateAction=structuredClone(record);
  duplicateAction.correctiveActions.push({...duplicateAction.correctiveActions[0]});
  assert.equal(qualityCorrectiveInspectionTarget(duplicateAction,actionId),null);
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic disposition reviewed",u);
  state=closeReviewedQuality(state,caseId,u);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.equal(renderQualityCase(state,caseId).split(link).length-1,1,
    "closed-case chronology remains navigable without reopening the case");
  assert.equal(renderQualityCase(state,caseId).split(receiptLink).length-1,1,
    "closed-case corrective receipt remains navigable");
});

test("inspection receipt and chronology navigate to the same exact linked corrective actions",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL","Synthetic source inspection one",t);
  state=recordQualityInspection(state,caseId,"IN_PROCESS",step,"PASS","Synthetic source inspection two",u);
  const [first,second]=state.quality[0].inspections.map(item=>item.id);
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY","Synthetic linked action one",first,u);
  state=recordQualityCorrectiveAction(state,caseId,"ENGINEERING","Synthetic linked action two",first,u);
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY","Synthetic second-inspection action",second,u);
  state=recordQualityCorrectiveAction(state,caseId,"ENGINEERING","Synthetic case-level action","",u);
  const record=state.quality[0];
  const [a,b,c,d]=record.correctiveActions.map(item=>item.id);
  assert.deepEqual(qualityInspectionCorrectiveTargets(record,first),
    [{kind:"corrective",id:a},{kind:"corrective",id:b}]);
  assert.deepEqual(qualityInspectionCorrectiveTargets(record,second),[{kind:"corrective",id:c}]);
  assert.deepEqual(qualityInspectionCorrectiveTargets(record,"missing-inspection"),[]);
  assert.deepEqual(qualityInspectionCorrectiveTargets(record,undefined),[]);
  const link=id=>'data-action="quality-evidence-focus" data-case="'+caseId+
    '" data-kind="corrective" data-id="'+id+'">View corrective action';
  let html=renderQualityCase(state,caseId);
  assert.equal(html.split(link(a)).length-1,2,"receipt and chronology reach action one");
  assert.equal(html.split(link(b)).length-1,2,"receipt and chronology reach action two");
  assert.equal(html.split(link(c)).length-1,2,"second inspection reaches only its action");
  assert.equal(html.split(link(d)).length-1,0,"case-level action has no invented inspection link");
  const duplicateInspection=structuredClone(record);
  duplicateInspection.inspections.push({...duplicateInspection.inspections[0]});
  assert.deepEqual(qualityInspectionCorrectiveTargets(duplicateInspection,first),[]);
  assert.equal(renderQualityCase({...state,quality:[duplicateInspection]},caseId).split(link(a)).length-1,0);
  const duplicateAction=structuredClone(record);
  duplicateAction.correctiveActions.push({...duplicateAction.correctiveActions[0]});
  assert.deepEqual(qualityInspectionCorrectiveTargets(duplicateAction,first),[{kind:"corrective",id:b}]);
  assert.equal(renderQualityCase({...state,quality:[duplicateAction]},caseId).split(link(a)).length-1,0);
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic reviewed disposition",u);
  state=closeReviewedQuality(state,caseId,u);
  html=renderQualityCase(state,caseId);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.equal(html.split(link(a)).length-1,2,"closed-case historical evidence remains navigable");
  assert.equal(state.quality[0].correctiveActions.length,4,"links do not create actions");
});

test("job routing evidence opens only uniquely linked fictional inspections, including closed historical cases",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL","Synthetic first observation",t);
  state=recordQualityInspection(state,caseId,"IN_PROCESS",step,"PASS","Synthetic second observation",u);
  const [first,second]=state.quality[0].inspections.map(item=>item.id);
  assert.deepEqual(qualityJobInspectionTarget(state,"sample-1001",caseId,second),
    {caseId,jobId:"sample-1001",kind:"inspection",id:second});
  assert.equal(qualityJobInspectionTarget(state,"sample-1002",caseId,first),null);
  assert.equal(qualityJobInspectionTarget(state,"sample-1001","missing-case",first),null);
  assert.equal(qualityJobInspectionTarget(state,"sample-1001",caseId,"missing-inspection"),null);
  assert.equal(qualityJobInspectionTarget(state,"sample-1001",caseId,undefined),null);
  const button=id=>'data-action="job-quality-inspection" data-case="'+caseId+
    '" data-job="sample-1001" data-id="'+id+'"';
  let html=renderJobQualityEvidence(state,"sample-1001");
  assert.equal(html.split(button(first)).length-1,1);
  assert.equal(html.split(button(second)).length-1,1);
  assert.doesNotMatch(renderJobQualityEvidence(state,"sample-1002"),/job-quality-inspection/);
  const ambiguousInspection=structuredClone(state);
  ambiguousInspection.quality[0].inspections.push({...ambiguousInspection.quality[0].inspections[0]});
  assert.equal(qualityJobInspectionTarget(ambiguousInspection,"sample-1001",caseId,first),null);
  assert.doesNotMatch(renderJobQualityEvidence(ambiguousInspection,"sample-1001"),
    new RegExp('data-id="'+first+'"'));
  const ambiguousCase=structuredClone(state);
  ambiguousCase.quality.push(structuredClone(ambiguousCase.quality[0]));
  assert.equal(qualityJobInspectionTarget(ambiguousCase,"sample-1001",caseId,first),null);
  const crossJobDuplicate=structuredClone(state);
  crossJobDuplicate.quality.push({...structuredClone(state.quality[0]),jobId:"sample-1002"});
  assert.equal(qualityJobInspectionTarget(crossJobDuplicate,"sample-1001",caseId,first),null);
  const missingJob=structuredClone(state);missingJob.jobs=[];
  assert.equal(qualityJobInspectionTarget(missingJob,"sample-1001",caseId,first),null);
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic reviewed disposition",u);
  state=closeReviewedQuality(state,caseId,u);
  assert.equal(state.quality[0].status,"CLOSED");
  assert.deepEqual(qualityJobInspectionTarget(state,"sample-1001",caseId,first),
    {caseId,jobId:"sample-1001",kind:"inspection",id:first});
  html=renderJobQualityEvidence(state,"sample-1001");
  assert.equal(html.split(button(first)).length-1,1);
  assert.equal(state.quality[0].inspections.length,2,"read-only job links cannot write evidence");
  assert.match(readFileSync(new URL("./app.mjs",import.meta.url),"utf8"),
    /if\(\["job-quality-inspection","job-quality-corrective","job-quality-followup"\]\.includes\(action\)\)/);
});

test("work-order register reveals only uniquely linked inspections and reuses canonical case links",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL","Synthetic register inspection",t);
  const inspectionId=state.quality[0].inspections[0].id;
  const button='data-action="job-quality-inspection" data-case="'+caseId+
    '" data-job="sample-1001" data-id="'+inspectionId+'"';
  let html=renderJobRegisterInspectionEvidence(state,"sample-1001");
  assert.ok(html.includes('<details class="job-inspection-details"><summary>Quality evidence (1)</summary>'));
  assert.equal(html.split(button).length-1,1,"register links to exact existing inspection");
  assert.match(html,/data-action="report-quality-case"/,"case entry is the same canonical NCR");
  assert.equal(renderJobRegisterInspectionEvidence(state,"sample-1002"),"","unrelated job has no evidence");
  assert.equal(renderJobRegisterInspectionEvidence({...state,jobs:[]},"sample-1001"),"","missing job is not linked");
  const duplicate=structuredClone(state);
  duplicate.quality[0].inspections.push({...duplicate.quality[0].inspections[0]});
  assert.equal(renderJobRegisterInspectionEvidence(duplicate,"sample-1001"),"",
    "ambiguous duplicate inspection is not advertised");
  const wrongCase=structuredClone(state);
  wrongCase.quality.push({...structuredClone(state.quality[0]),jobId:"sample-1002"});
  assert.equal(renderJobRegisterInspectionEvidence(wrongCase,"sample-1001"),"",
    "duplicate case IDs across jobs do not create links");
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic reviewed disposition",u);
  state=closeReviewedQuality(state,caseId,u);
  html=renderJobRegisterInspectionEvidence(state,"sample-1001");
  assert.equal(html.split(button).length-1,1,"closed-case inspection remains readable");
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.ok(app.includes("jobQualityCell(j)+renderJobRegisterInspectionEvidence(state,j.id)"),
    "the actual job register embeds the existing evidence projection");
  assert.ok(app.includes('(view==="jobs"&&!contextSelection("jobs",state.jobs)'),
    "register navigation validates visible job identity");
});


test("canonical work-order corrective evidence is reachable without guessing or changing records",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",t);
  const caseId=state.quality[0].id;
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY","Synthetic corrective check one","",t);
  state=recordQualityCorrectiveAction(state,caseId,"ENGINEERING","Synthetic corrective check two","",u);
  const [first,second]=state.quality[0].correctiveActions.map(action=>action.id);
  const target={caseId,jobId:"sample-1001",kind:"corrective",id:second};
  assert.deepEqual(qualityJobCorrectiveTarget(state,"sample-1001",caseId,second),target);
  assert.equal(qualityJobCorrectiveTarget(state,"sample-1002",caseId,first),null);
  assert.equal(qualityJobCorrectiveTarget(state,"sample-1001",caseId,"missing"),null);
  assert.equal(qualityJobCorrectiveTarget(state,"sample-1001",caseId,undefined),null);
  const button=id=>'data-action="job-quality-corrective" data-case="'+caseId+
    '" data-job="sample-1001" data-id="'+id+'"';
  const html=renderJobQualityEvidence(state,"sample-1001");
  assert.equal(html.split(button(first)).length-1,1);
  assert.equal(html.split(button(second)).length-1,1);
  assert.doesNotMatch(renderJobQualityEvidence(state,"sample-1002"),/job-quality-corrective/);
  assert.match(renderJobRegisterInspectionEvidence(state,"sample-1001"),
    /<summary>Quality evidence \(2\)<\/summary>/);
  const ambiguousAction=structuredClone(state);
  ambiguousAction.quality[0].correctiveActions.push({...ambiguousAction.quality[0].correctiveActions[0]});
  assert.equal(qualityJobCorrectiveTarget(ambiguousAction,"sample-1001",caseId,first),null);
  assert.ok(!renderJobQualityEvidence(ambiguousAction,"sample-1001").includes(button(first)));
  const ambiguousCase=structuredClone(state);
  ambiguousCase.quality.push({...structuredClone(state.quality[0]),jobId:"sample-1002"});
  assert.equal(qualityJobCorrectiveTarget(ambiguousCase,"sample-1001",caseId,first),null);
  assert.equal(renderJobRegisterInspectionEvidence(ambiguousCase,"sample-1001"),"");
  const missingJob=structuredClone(state);missingJob.jobs=[];
  assert.equal(qualityJobCorrectiveTarget(missingJob,"sample-1001",caseId,first),null);
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic reviewed disposition",u);
  state=closeReviewedQuality(state,caseId,u);
  assert.deepEqual(qualityJobCorrectiveTarget(state,"sample-1001",caseId,second),target);
  assert.equal(renderJobQualityEvidence(state,"sample-1001").split(button(second)).length-1,1);
  assert.equal(state.quality[0].correctiveActions.length,2,"navigation is read-only");
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.match(app,/if\(\["job-quality-inspection","job-quality-corrective","job-quality-followup"\]\.includes\(action\)\)/);
  assert.match(app,/qualityJobCorrectiveTarget\(state,button.dataset.job,button.dataset.case,id\)/);
});

test("work-order follow-up links preserve exact post-closure evidence from routing and register",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic fictional case review",t);
  const caseId=state.quality[0].id;
  state=recordQualityFollowup(state,caseId,"Synthetic initial follow-up",t);
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic reviewed disposition",u);
  state=closeReviewedQuality(state,caseId,u);
  state=recordQualityFollowup(state,caseId,"Synthetic post-closure follow-up",u);
  const [first,second]=state.quality[0].followUps.map(item=>item.id);
  const expected={caseId,jobId:"sample-1001",kind:"followup",id:second};
  assert.deepEqual(qualityJobFollowupTarget(state,"sample-1001",caseId,second),expected);
  assert.equal(qualityJobFollowupTarget(state,"sample-1002",caseId,second),null);
  assert.equal(qualityJobFollowupTarget(state,"sample-1001",caseId,"missing"),null);
  assert.equal(qualityJobFollowupTarget(state,"sample-1001",caseId,undefined),null);
  const button=id=>'data-action="job-quality-followup" data-case="'+caseId+
    '" data-job="sample-1001" data-id="'+id+'"';
  const routing=renderJobQualityEvidence(state,"sample-1001");
  assert.equal(routing.split(button(first)).length-1,1);
  assert.equal(routing.split(button(second)).length-1,1);
  const register=renderJobRegisterInspectionEvidence(state,"sample-1001");
  assert.match(register,/<summary>Quality evidence \(2\)<\/summary>/);
  assert.equal(register.split(button(second)).length-1,1);
  assert.equal(renderJobRegisterInspectionEvidence(state,"sample-1002"),"");
  const duplicate=structuredClone(state);
  duplicate.quality[0].followUps.push({...duplicate.quality[0].followUps[0]});
  assert.equal(qualityJobFollowupTarget(duplicate,"sample-1001",caseId,first),null);
  assert.ok(!renderJobQualityEvidence(duplicate,"sample-1001").includes(button(first)));
  const duplicateCase=structuredClone(state);
  duplicateCase.quality.push({...structuredClone(state.quality[0]),jobId:"sample-1002"});
  assert.equal(qualityJobFollowupTarget(duplicateCase,"sample-1001",caseId,second),null);
  assert.equal(renderJobRegisterInspectionEvidence(duplicateCase,"sample-1001"),"");
  const missingJob=structuredClone(state);missingJob.jobs=[];
  assert.equal(qualityJobFollowupTarget(missingJob,"sample-1001",caseId,second),null);
  assert.equal(state.quality[0].followUps.length,2,"navigation cannot append evidence");
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.match(app,/qualityJobFollowupTarget\(state,button.dataset.job,button.dataset.case,id\)/);
});
