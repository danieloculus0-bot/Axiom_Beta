import test from "node:test";
import assert from "node:assert/strict";
import {seedState,makePurchaseOrder,receivePurchaseOrder,raiseQuality,createJob} from "./engine.mjs";
import {makeReport,reportCsv,REPORTS} from "./reports.mjs";
import {qualityCaseTimeline} from "./quality-timeline.mjs";
import {renderQualityCase,renderJobQualityEvidence,qualityCaseEvidenceSummary,qualityEvidenceTarget,qualityInspectionRoutingTarget,qualityInspectionRoutingStatus,qualityEvidenceWorkOrderTarget,qualityEvidenceReturnTarget,qualityEvidenceReturnAction} from "./quality-case-view.mjs";
import {startSession,stopSession} from "../ewi/engine.mjs";
import {completePmTask} from "./pm.mjs";
import {qualityJobSummary,jobQualityTarget,recordQualityInspection,recordQualityDisposition,closeReviewedQuality,
  recordQualityCorrectiveAction,reviewQualityCorrectiveAction,recordQualityFollowup} from "./quality-case.mjs";
import {contextActions,contextRelated} from "./context-actions.mjs";
import {readFileSync} from "node:fs";
const at="2026-10-30T12:00:00.000Z",later="2026-10-30T12:00:30.000Z";
test("all report types have functional rows, no fake network data",()=>{
 const state=seedState();
 assert.equal(REPORTS.length,10);
 for(const report of REPORTS){
  const data=makeReport(state,[],report.id,"2026-10-30");
  assert.equal(data.id,report.id);
  assert.equal(data.columns.length>0,true);
  assert.ok(data.rows.every(row=>row.length===data.columns.length));
  assert.equal(data.fictional,true);
 }
 assert.throws(()=>makeReport(state,[],"wrong"),/Unknown/);
});
test("reports reflect live synthetic manufacturing transactions",()=>{
 let state=seedState();
 const first=makeReport(state,[],"jobs");
 assert.equal(first.rows.length,2);
 state=createJob(state,"SYN-TAB-03",10,at).state;
 assert.equal(makeReport(state,[],"jobs").rows.length,3);
 state=makePurchaseOrder(state,"MAT-BAR",20,at);
 assert.equal(makeReport(state,[],"purchasing").rows.length,1);
 state=receivePurchaseOrder(state,state.purchaseOrders[0].id,later);
 const stock=makeReport(state,[],"inventory");
 assert.equal(stock.rows.find(row=>row[0]==="MAT-BAR")[3],60);
 state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",at);
 assert.equal(makeReport(state,[],"quality").rows[0][3],"OPEN");
 assert.match(makeReport(state,[],"jobs").rows[0][6],/quality hold/);
});
test("clock and PM reports use real locally recorded fictional events",()=>{
 let s=seedState();
 let clocks=startSession([],{id:"a1",employee:"DEMO-01",job:s.jobs[0],step:"10",timestamp:at});
 clocks=stopSession(clocks,{id:"a1",employee:"DEMO-01",timestamp:later});
 assert.equal(makeReport(s,clocks,"labor").rows[0][5],30);
 assert.equal(makeReport(s,clocks,"labor").rows[0][6],"STOPPED / LOCAL");
 s.pm=completePmTask(s.pm,"DEMO-PM-001",{operator:"DEMO-01",checklistConfirmed:true,at}).pm;
 const pm=makeReport(s,clocks,"pm","2026-10-30");
 assert.equal(pm.rows[0][4],"2026-11-06");
 assert.ok(makeReport(s,[],"events").rows.length>0);
});
test("report CSV quotes cells and neutralizes spreadsheet formulas",()=>{
 const csv=reportCsv({columns:["A","B"],rows:[["=SUM(1,1)","Text, with comma"],["@cmd","line\nbreak"]]});
 assert.match(csv,/"'=SUM\(1,1\)"/);
 assert.match(csv,/"'@cmd"/);
 assert.match(csv,/"Text, with comma"/);
 assert.throws(()=>reportCsv({columns:null,rows:[]}),/Invalid/);
});

test("quality register reports canonical NCR inspection, disposition and corrective-action history",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
 let report=makeReport(state,[],"quality");
 assert.equal(report.rows.length,1);
 assert.deepEqual(report.rows[0].slice(6),["NOT RECORDED",0,0,"NO ACTION",0]);
 state=recordQualityInspection(state,id,"FIRST_PIECE",step,"FAIL","Fictional first-piece observation",later);
 const inspectionId=state.quality[0].inspections[0].id;
 state=recordQualityCorrectiveAction(state,id,"QUALITY","Review fictional sample process",inspectionId,"2026-10-30T12:01:00.000Z");
 const actionId=state.quality[0].correctiveActions[0].id;
 report=makeReport(state,[],"quality");
 assert.deepEqual(report.rows[0].slice(6),["NOT RECORDED",1,1,"NOT REVIEWED",0]);
 state=reviewQualityCorrectiveAction(state,id,actionId,"MORE_EVIDENCE","More fictional evidence needed","2026-10-30T12:02:00.000Z");
 state=recordQualityFollowup(state,id,"Sample follow-up planned","2026-10-30T12:03:00.000Z");
 state=recordQualityDisposition(state,id,"SCRAP","Fictional scrap disposition","2026-10-30T12:04:00.000Z");
 state=closeReviewedQuality(state,id,"2026-10-30T12:05:00.000Z");
 state=reviewQualityCorrectiveAction(state,id,actionId,"NOT_EFFECTIVE","Further fictional review required","2026-10-30T12:06:00.000Z");
 report=makeReport(state,[],"quality");
 assert.equal(report.rows[0][3],"CLOSED");
 assert.deepEqual(report.rows[0].slice(6),["SCRAP",1,1,"NOT_EFFECTIVE",1]);
 assert.equal(state.quality[0].status,"CLOSED");
 assert.equal(report.rows[0][1],state.jobs[0].jobNumber);
 assert.equal(makeReport(state,[],"jobs").rows[0][6],"Example checks passed");
 assert.match(reportCsv(report),/NOT_EFFECTIVE/);
 assert.ok(contextActions(state,"quality",id).some(action=>action.view==="quality"));
 assert.deepEqual(contextRelated(state,{type:"quality",id},"quality"),["sample-1001"]);
 const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
 assert.ok(app.includes('data-action="report-quality-case"'));
 assert.match(app,/openContext\(\{type:"quality",id\},\{view:"quality",intent:"quality"\}\)/);
});
test("quality report retains legacy case records and chooses latest timestamped effectiveness evidence",()=>{
 const state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 const q=state.quality[0];
 q.correctiveActions=[{id:"sample-action",reviews:[
   {result:"NOT_EFFECTIVE",at:"2026-10-30T12:05:00Z"},
   {result:"EFFECTIVE",at:"2026-10-30T12:02:00Z"}]}];
 const report=makeReport(state,[],"quality");
 assert.equal(report.rows[0][9],"NOT_EFFECTIVE");
 assert.equal(report.rows[0][7],0);
 assert.equal(report.rows[0][10],0);
 assert.equal(report.columns.length,report.rows[0].length);
});

test("work order readiness derives NCR and effectiveness status from the same canonical cases",()=>{
 let state=seedState();
 let summary=qualityJobSummary(state,"sample-1001");
 assert.deepEqual([summary.total,summary.open,summary.correctiveActions,summary.latestEffectiveness],
   [0,0,0,"NO ACTION"]);
 state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",at);
 state=raiseQuality(state,"sample-1002","Generic drawing revision conflict",at);
 const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,id,"FIRST_PIECE",step,"FAIL","Fictional sample observation",later);
 state=recordQualityCorrectiveAction(state,id,"QUALITY","Review fictional example process",
   state.quality[0].inspections[0].id,"2026-10-30T12:01:00.000Z");
 const actionId=state.quality[0].correctiveActions[0].id;
 state=reviewQualityCorrectiveAction(state,id,actionId,"EFFECTIVE","Initial fictional check",
   "2026-10-30T12:02:00.000Z");
 state=recordQualityDisposition(state,id,"SCRAP","Fictional disposition evidence",
   "2026-10-30T12:03:00.000Z");
 state=closeReviewedQuality(state,id,"2026-10-30T12:04:00.000Z");
 state=reviewQualityCorrectiveAction(state,id,actionId,"NOT_EFFECTIVE","Fictional later review",
   "2026-10-30T12:05:00.000Z");
 summary=qualityJobSummary(state,"sample-1001");
 assert.deepEqual([summary.total,summary.open,summary.inspections,summary.correctiveActions,summary.latestEffectiveness],
   [1,0,1,1,"NOT_EFFECTIVE"]);
 assert.equal(summary.cases[0].id,id);
 const report=makeReport(state,[],"jobs");
 assert.deepEqual(report.rows[0].slice(7),[1,0,1,"NOT_EFFECTIVE"]);
 assert.deepEqual(report.rows[1].slice(7),[1,1,0,"NO ACTION"]);
 assert.equal(report.rows[0][6],"Example checks passed");
 assert.match(report.rows[1][6],/quality hold/);
 assert.equal(report.columns.length,report.rows[0].length);
 assert.match(reportCsv(report),/NOT_EFFECTIVE/);
});
test("job-linked NCR entry points preserve job and case identity and hide empty links",()=>{
 const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
 assert.ok(app.includes('function jobQualityCell(j)'));
 assert.ok(app.includes('if(!summary.total)return'));
 assert.ok(app.split("jobQualityCell(j)").length-1>=4);
 assert.ok(app.includes('if(action==="job-quality-cases")'));
 assert.ok(app.includes('selectedContext={type:"job",id:target.jobId}'));
 assert.ok(app.includes('selectedQualityId=target.caseId'));
 assert.ok(app.includes('if(view==="quality"&&selectedContext?.type==="job")'));
 assert.ok(app.includes('if(selected.id==="jobs"&&col===7&&Number(value)>0)'));
});

test("job quality navigation target selects a real open case before closed history",()=>{
 let state=seedState();
 assert.equal(jobQualityTarget(state,"sample-1001"),null);
 assert.equal(jobQualityTarget(state,"not-a-job"),null);
 state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",at);
 state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",later);
 const first=state.quality[0].id,second=state.quality[1].id;
 assert.deepEqual(jobQualityTarget(state,"sample-1001"),{jobId:"sample-1001",caseId:first});
 state=recordQualityDisposition(state,first,"SCRAP","Fictional disposition",later);
 state=closeReviewedQuality(state,first,"2026-10-30T12:01:00.000Z");
 assert.equal(jobQualityTarget(state,"sample-1001").caseId,second);
 state=recordQualityDisposition(state,second,"SCRAP","Fictional disposition","2026-10-30T12:02:00.000Z");
 state=closeReviewedQuality(state,second,"2026-10-30T12:03:00.000Z");
 assert.equal(jobQualityTarget(state,"sample-1001").caseId,first);
 assert.equal(jobQualityTarget(state,"sample-1002"),null);
});

test("Quality Forge case chronology follows canonical evidence through post-closure review",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict","2026-10-30T12:00:00Z");
 const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,id,"FIRST_PIECE",step,"FAIL","Fictional first piece deviation","2026-10-30T12:01:00Z");
 state=recordQualityCorrectiveAction(state,id,"QUALITY","Review fictional sample setup",
   state.quality[0].inspections[0].id,"2026-10-30T12:02:00Z");
 const actionId=state.quality[0].correctiveActions[0].id;
 state=recordQualityFollowup(state,id,"Fictional follow-up requested","2026-10-30T12:03:00Z");
 state=recordQualityDisposition(state,id,"SCRAP","Fictional disposition rationale","2026-10-30T12:04:00Z");
 state=closeReviewedQuality(state,id,"2026-10-30T12:05:00Z");
 state=reviewQualityCorrectiveAction(state,id,actionId,"NOT_EFFECTIVE","Fictional later review","2026-10-30T12:06:00Z");
 const before=JSON.stringify(state),timeline=qualityCaseTimeline(state.quality[0]);
 assert.deepEqual(timeline.map(entry=>entry.kind),
   ["opened","inspection","corrective","followup","disposition","closed","effectiveness"]);
 assert.equal(timeline[1].sourceId,state.quality[0].inspections[0].id);
 assert.equal(timeline.at(-1).sourceId,state.quality[0].correctiveActions[0].reviews[0].id);
 assert.equal(JSON.stringify(state),before);
 assert.equal(state.quality[0].status,"CLOSED");
 const html=renderQualityCase(state,id);
 const chronology=html.slice(html.indexOf("<h3>Case chronology</h3>"));
 assert.ok(chronology.includes("Effectiveness: NOT_EFFECTIVE"));
 assert.ok(chronology.indexOf("NCR closed")<chronology.indexOf("Effectiveness: NOT_EFFECTIVE"));
 assert.ok(chronology.includes(state.jobs[0].jobNumber)===false); // Timeline is scoped to the already-selected case.
});
test("Quality Forge chronology handles legacy records and escapes fictional user text",()=>{
 assert.deepEqual(qualityCaseTimeline(null),[]);
 assert.deepEqual(qualityCaseTimeline({id:"legacy",status:"OPEN"}),[]);
 const legacy={id:"legacy",reason:"Example",openedAt:"not a date",followUps:[
   {id:"first",note:"A",at:"2026-10-30T12:00:00Z"},
   {id:"second",note:"B",at:"2026-10-30T12:00:00Z"}]};
 const rows=qualityCaseTimeline(legacy);
 assert.deepEqual(rows.map(entry=>entry.sourceId),["first","second","legacy"]);
 assert.equal(rows.at(-1).at,null);
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict","2026-10-30T12:00:00Z");
 state=recordQualityFollowup(state,state.quality[0].id,"<script>alert(1)</script>","2026-10-30T12:01:00Z");
 const html=renderQualityCase(state,state.quality[0].id);
 assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
 assert.ok(!html.includes("<script>"));
});

test("job routing evidence index links exact canonical cases and keeps closed reviews visible",()=>{
 let state=seedState();
 assert.ok(!renderJobQualityEvidence(state,"sample-1001").includes('data-action='));
 state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",at);
 state=raiseQuality(state,"sample-1001","Generic drawing revision conflict",later);
 state=raiseQuality(state,"sample-1002","Generic drawing revision conflict",later);
 const [first,second,unrelated]=state.quality.map(q=>q.id);
 const step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,first,"FIRST_PIECE",step,"FAIL",
   "Fictional check requires review","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 state=recordQualityCorrectiveAction(state,first,"QUALITY","Review sample setup",
   inspectionId,"2026-10-30T12:02:00Z");
 const actionId=state.quality[0].correctiveActions[0].id;
 state=recordQualityDisposition(state,first,"SCRAP","Fictional disposition","2026-10-30T12:03:00Z");
 state=closeReviewedQuality(state,first,"2026-10-30T12:04:00Z");
 state=reviewQualityCorrectiveAction(state,first,actionId,"NOT_EFFECTIVE",
   "Further fictional action needed","2026-10-30T12:05:00Z");
 const before=JSON.stringify(state),html=renderJobQualityEvidence(state,"sample-1001");
 assert.deepEqual(qualityCaseEvidenceSummary(state.quality[0]),
   {inspections:1,correctiveActions:1,latestEffectiveness:"NOT_EFFECTIVE"});
 assert.match(html,new RegExp('data-action="report-quality-case" data-id="'+first+'"'));
 assert.match(html,new RegExp('data-action="report-quality-case" data-id="'+second+'"'));
 assert.ok(!html.includes('data-id="'+unrelated+'"'));
 assert.match(html,/NOT_EFFECTIVE/);
 assert.match(html,/CLOSED/);
 assert.equal(JSON.stringify(state),before);
 assert.equal(state.quality[0].status,"CLOSED");
});
test("quality evidence links escape legacy text and use existing record-aware navigation",()=>{
 const state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 state.quality[0].number='<script>alert(1)</script>';
 const html=renderJobQualityEvidence(state,"sample-1001");
 assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
 assert.ok(!html.includes("<script>"));
 assert.deepEqual(qualityCaseEvidenceSummary({id:"legacy"}),{
   inspections:0,correctiveActions:0,latestEffectiveness:"NO ACTION"});
 const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
 assert.ok(app.includes("renderJobQualityEvidence(state,j.id)"));
 assert.ok(app.includes("qualityCaseEvidenceSummary(q)"));
 assert.ok(app.includes('if(action==="report-quality-case")'));
 assert.ok(app.includes('openContext({type:"quality",id},{view:"quality",intent:"quality"})'));
});

test("quality evidence links resolve exact inspection, corrective action and effectiveness receipts",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 state=raiseQuality(state,"sample-1002","Generic drawing revision conflict",later);
 const [q,other]=state.quality,step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,q.id,"FIRST_PIECE",step,"FAIL","Fictional inspection evidence","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 state=recordQualityCorrectiveAction(state,q.id,"QUALITY","Review fictional setup",inspectionId,"2026-10-30T12:02:00Z");
 const actionId=state.quality[0].correctiveActions[0].id;
 state=reviewQualityCorrectiveAction(state,q.id,actionId,"MORE_EVIDENCE","More fictional checking needed","2026-10-30T12:03:00Z");
 const reviewId=state.quality[0].correctiveActions[0].reviews[0].id;
 const record=state.quality[0],before=JSON.stringify(state);
 for(const [kind,id] of [["inspection",inspectionId],["corrective",actionId],["effectiveness",reviewId]]){
   assert.deepEqual(qualityEvidenceTarget(record,kind,id),{kind,id});
   assert.equal(qualityEvidenceTarget(other,kind,id),null);
 }
 assert.equal(qualityEvidenceTarget(record,"inspection","missing"),null);
 assert.equal(qualityEvidenceTarget(record,"followup",inspectionId),null);
 assert.equal(qualityEvidenceTarget(record,"corrective",inspectionId),null);
 const html=renderQualityCase(state,q.id);
 assert.ok(html.includes('data-case-id="'+q.id+'"'));
 for(const [kind,id] of [["inspection",inspectionId],["corrective",actionId],["effectiveness",reviewId]]){
   assert.ok(html.includes('data-evidence-kind="'+kind+'" data-evidence-id="'+id+'"'));
   assert.ok(html.includes('data-case="'+q.id+'" data-kind="'+kind+'" data-id="'+id+'"'));
 }
 assert.match(html,/View observation/);
 assert.match(html,/View corrective action/);
 assert.match(html,/View evidence/);
 assert.ok(!html.includes('data-case="'+other.id+'"'));
 assert.equal(JSON.stringify(state),before);
 const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
 assert.ok(app.includes('if(action==="quality-evidence-focus")'));
 assert.ok(app.includes('panel?.dataset.caseId!==caseId'));
 assert.ok(app.includes('!qualityEvidenceTarget(record,kind,id)'));
 assert.ok(app.includes('target.focus({preventScroll:true})'));
});
test("legacy evidence without stable IDs offers no dead-end links and escapes text",()=>{
 const record={id:"legacy",inspections:[{observation:"<script>bad</script>",at:"2026-10-30T12:00:00Z"}],
   correctiveActions:[{description:"Legacy action",reviews:[{result:"EFFECTIVE",at:"2026-10-30T12:01:00Z"}]}]};
 assert.equal(qualityEvidenceTarget(record,"inspection",""),null);
 assert.equal(qualityEvidenceTarget(record,"effectiveness","missing"),null);
 assert.equal(qualityEvidenceTarget(record,"inspection",null),null);
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 state.quality[0].inspections=record.inspections;
 state.quality[0].correctiveActions=record.correctiveActions;
 const html=renderQualityCase(state,state.quality[0].id);
 assert.ok(html.includes("&lt;script&gt;bad&lt;/script&gt;"));
 assert.ok(!html.includes("<script>"));
 assert.ok(!html.includes('data-action="quality-evidence-focus"'));
});


test("inspection and linked corrective evidence navigate to the exact current job operation",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 const q=state.quality[0],job=state.jobs.find(j=>j.id===q.jobId);
 const step=job.routing.operations[0].step;
 state=recordQualityInspection(state,q.id,"FIRST_PIECE",step,"FAIL",
   "Fictional operation check needs review","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 state=recordQualityCorrectiveAction(state,q.id,"QUALITY","Review sample setup",
   inspectionId,"2026-10-30T12:02:00Z");
 const before=JSON.stringify(state);
 const target=qualityInspectionRoutingTarget(state,q.id,inspectionId);
 assert.deepEqual(target,{caseId:q.id,inspectionId,jobId:job.id,step:String(step)});
 const html=renderQualityCase(state,q.id);
 // Three genuine entry points: observation, linked corrective action, chronology.
 assert.equal((html.match(/data-action="quality-routing-step"/g)||[]).length,3);
 assert.ok(html.includes('data-case="'+q.id+'" data-id="'+inspectionId+'"'));
 assert.ok(html.includes('href="#jobs" data-job="'+job.id+'"'));
 assert.equal(JSON.stringify(state),before);
 const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
 assert.ok(app.includes('if(action==="quality-routing-step")'));
 assert.ok(app.includes('panel?.dataset.caseId!==target.caseId'));
 assert.ok(app.includes('pendingRoutingStep={jobId:target.jobId,step:target.step}'));
 assert.ok(app.includes('data-route-step='));
 assert.ok(app.includes('card.focus({preventScroll:true})'));
});

test("inspection routing navigation rejects changed revisions, operations, missing or cross-case evidence",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 state=raiseQuality(state,"sample-1002","Generic drawing revision conflict",later);
 const q=state.quality[0],other=state.quality[1];
 const step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,q.id,"IN_PROCESS",step,"REVIEW_REQUIRED",
   "Generic sample operation observation","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 assert.equal(qualityInspectionRoutingTarget(state,other.id,inspectionId),null);
 assert.equal(qualityInspectionRoutingTarget(state,q.id,"missing"),null);
 assert.equal(qualityInspectionRoutingTarget(state,q.id,null),null);
 assert.equal(qualityInspectionRoutingTarget(null,q.id,inspectionId),null);
 const cases=[
   s=>{s.jobs[0].revision="CHANGED";},
   s=>{s.jobs[0].drawing.revision="CHANGED";},
   s=>{s.jobs[0].routing.operations[0].name="Different operation";},
   s=>{s.jobs[0].routing.operations[0].center="DIFFERENT";},
   s=>{s.jobs[0].routing.operations[0].step="NOT-THE-STEP";},
   s=>{s.quality[0].jobId="missing-job";},
   s=>{delete s.quality[0].inspections[0].drawingRevision;}
 ];
 for(const change of cases){
   const stale=structuredClone(state);
   change(stale);
   assert.equal(qualityInspectionRoutingTarget(stale,q.id,inspectionId),null);
   assert.ok(!renderQualityCase(stale,q.id).includes('data-action="quality-routing-step"'));
 }
});

test("closed fictional NCR retains read-only routing link without changing case status",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,id,"FINAL_REVIEW",step,"FAIL",
   "Fictional final check evidence","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 state=recordQualityDisposition(state,id,"SCRAP","Fictional disposition","2026-10-30T12:02:00Z");
 state=closeReviewedQuality(state,id,"2026-10-30T12:03:00Z");
 const before=JSON.stringify(state);
 assert.equal(state.quality[0].status,"CLOSED");
 assert.equal(qualityInspectionRoutingTarget(state,id,inspectionId)?.jobId,"sample-1001");
 assert.match(renderQualityCase(state,id),/data-action="quality-routing-step"/);
 assert.equal(JSON.stringify(state),before);
});


test("historical routing hints explain stale evidence without offering a misleading current-step link",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 const q=state.quality[0],job=state.jobs[0],step=job.routing.operations[0].step;
 state=recordQualityInspection(state,q.id,"IN_PROCESS",step,"REVIEW_REQUIRED",
   "Fictional historical inspection observation","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 assert.deepEqual(qualityInspectionRoutingStatus(state,q.id,inspectionId),{
   target:{caseId:q.id,inspectionId,jobId:job.id,step:String(step)},reason:null
 });
 assert.equal(qualityInspectionRoutingStatus(state,q.id,"unknown"),null);
 assert.equal(qualityInspectionRoutingStatus(state,"other-case",inspectionId),null);
 assert.ok(!renderQualityCase(state,q.id).includes("Historical route:"));
 const cases=[
   [s=>{s.jobs[0].revision="B";},"Recorded job revision differs from the current work order."],
   [s=>{s.jobs[0].drawing.revision="B";},"Recorded drawing revision differs from the current drawing."],
   [s=>{s.jobs[0].routing.operations[0].step="99";},"Recorded step is absent from the current routing."],
   [s=>{s.jobs[0].routing.operations[0].name="Changed operation";},"Recorded operation or work center differs from the current routing."],
   [s=>{s.jobs[0].routing.operations[0].center="OTHER";},"Recorded operation or work center differs from the current routing."],
   [s=>{delete s.quality[0].inspections[0].drawingRevision;},"Recorded revision evidence is incomplete."],
   [s=>{delete s.quality[0].inspections[0].operation;},"Recorded operation details are incomplete."],
   [s=>{s.quality[0].jobId="missing-job";},"Linked fictional work order is unavailable."]
 ];
 for(const [mutate,reason] of cases){
   const stale=structuredClone(state);
   mutate(stale);
   const before=JSON.stringify(stale);
   assert.deepEqual(qualityInspectionRoutingStatus(stale,q.id,inspectionId),{target:null,reason});
   assert.equal(qualityInspectionRoutingTarget(stale,q.id,inspectionId),null);
   const html=renderQualityCase(stale,q.id);
   assert.ok(html.includes("Historical route: "+reason+" Current step link unavailable."));
   assert.ok(html.includes("Fictional historical inspection observation"));
   assert.ok(!html.includes('data-action="quality-routing-step"'));
   assert.equal(JSON.stringify(stale),before);
 }
});

test("closed NCR keeps historical inspection, linked corrective and chronology hints read-only",()=>{
 let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 const id=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
 state=recordQualityInspection(state,id,"FINAL_REVIEW",step,"FAIL",
   "Fictional final check evidence","2026-10-30T12:01:00Z");
 const inspectionId=state.quality[0].inspections[0].id;
 state=recordQualityCorrectiveAction(state,id,"QUALITY","Review sample setup",
   inspectionId,"2026-10-30T12:02:00Z");
 state=recordQualityDisposition(state,id,"SCRAP","Fictional disposition","2026-10-30T12:03:00Z");
 state=closeReviewedQuality(state,id,"2026-10-30T12:04:00Z");
 state.jobs[0].routing.operations[0].center="OTHER";
 const before=JSON.stringify(state),html=renderQualityCase(state,id);
 assert.equal(state.quality[0].status,"CLOSED");
 assert.equal((html.match(/Historical route:/g)||[]).length,3);
 assert.equal((html.match(/Current step link unavailable\./g)||[]).length,3);
 assert.ok(html.includes("Fictional final check evidence"));
 assert.ok(html.includes("Case chronology"));
 assert.ok(html.includes('href="#jobs" data-job="sample-1001"'));
 assert.ok(!html.includes('data-action="quality-routing-step"'));
 assert.equal(JSON.stringify(state),before);
});

test("NCR inspection, corrective action and effectiveness evidence open only their actual work order",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
  state=raiseQuality(state,"sample-1002","Generic drawing revision conflict",later);
  const q=state.quality[0],other=state.quality[1];
  const step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,q.id,"FIRST_PIECE",step,"FAIL",
    "Generic fictional inspection evidence","2026-10-30T12:01:00Z");
  const inspectionId=state.quality[0].inspections[0].id;
  state=recordQualityCorrectiveAction(state,q.id,"QUALITY",
    "Generic fictional corrective action",inspectionId,"2026-10-30T12:02:00Z");
  const actionId=state.quality[0].correctiveActions[0].id;
  state=reviewQualityCorrectiveAction(state,q.id,actionId,"EFFECTIVE",
    "Fictional effectiveness observation","2026-10-30T12:03:00Z");
  const reviewId=state.quality[0].correctiveActions[0].reviews[0].id;
  const before=JSON.stringify(state);
  for(const [kind,id] of [["inspection",inspectionId],["corrective",actionId],["effectiveness",reviewId]]){
    assert.deepEqual(qualityEvidenceWorkOrderTarget(state,q.id,kind,id),
      {caseId:q.id,kind,id,jobId:"sample-1001"});
    assert.equal(qualityEvidenceWorkOrderTarget(state,other.id,kind,id),null);
    assert.equal(qualityEvidenceWorkOrderTarget(state,q.id,kind,"unrelated-evidence"),null);
  }
  const html=renderQualityCase(state,q.id);
  assert.equal((html.match(/data-action="quality-evidence-work-order"/g)||[]).length,3);
  for(const [kind,id] of [["inspection",inspectionId],["corrective",actionId],["effectiveness",reviewId]])
    assert.ok(html.includes('data-case="'+q.id+'" data-kind="'+kind+'" data-id="'+id+'"'));
  assert.ok(html.includes('href="#jobs" data-job="sample-1001"'));
  assert.equal(JSON.stringify(state),before);
});

test("NCR evidence work-order actions are guarded for legacy, missing and unrelated records",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
  const q=state.quality[0],step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,q.id,"FINAL_REVIEW",step,"PASS",
    "Fictional final observation",later);
  const id=state.quality[0].inspections[0].id;
  assert.equal(qualityEvidenceWorkOrderTarget(state,q.id,"inspection",null),null);
  assert.equal(qualityEvidenceWorkOrderTarget(state,q.id,"corrective",id),null);
  assert.equal(qualityEvidenceWorkOrderTarget(null,q.id,"inspection",id),null);
  const orphan=structuredClone(state);
  orphan.jobs=[];
  assert.equal(qualityEvidenceWorkOrderTarget(orphan,q.id,"inspection",id),null);
  assert.ok(!renderQualityCase(orphan,q.id).includes('data-action="quality-evidence-work-order"'));
  const legacy=structuredClone(state);
  legacy.quality[0].inspections=[{stage:"FINAL",observation:"Legacy fictional evidence"}];
  assert.ok(!renderQualityCase(legacy,q.id).includes('data-action="quality-evidence-work-order"'));
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.ok(app.includes('if(action==="quality-evidence-work-order")'));
  assert.ok(app.includes('qualityEvidenceWorkOrderTarget(state,caseId,kind,id)'));
  assert.ok(app.includes('panel?.dataset.caseId!==target.caseId'));
  assert.ok(app.includes('selectedContext={type:"quality",id:target.caseId}'));
  assert.ok(app.includes('selectedQualityId=target.caseId'));
  assert.ok(app.includes('rememberJob(target.jobId)'));
  assert.ok(app.includes('if(action==="quality-routing-step")'));
});

test("NCR evidence return keeps exact inspection, corrective and effectiveness identity on the same work order",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
  const caseId=state.quality[0].id,step=state.jobs[0].routing.operations[0].step;
  state=recordQualityInspection(state,caseId,"FIRST_PIECE",step,"FAIL",
    "Synthetic first-piece evidence","2026-10-30T12:01:00Z");
  const inspectionId=state.quality[0].inspections[0].id;
  state=recordQualityCorrectiveAction(state,caseId,"QUALITY",
    "Synthetic corrective action",inspectionId,"2026-10-30T12:02:00Z");
  const actionId=state.quality[0].correctiveActions[0].id;
  state=reviewQualityCorrectiveAction(state,caseId,actionId,"EFFECTIVE",
    "Synthetic effectiveness review","2026-10-30T12:03:00Z");
  const reviewId=state.quality[0].correctiveActions[0].reviews[0].id;
  state=recordQualityDisposition(state,caseId,"SCRAP","Synthetic disposition","2026-10-30T12:04:00Z");
  state=closeReviewedQuality(state,caseId,"2026-10-30T12:05:00Z");
  const before=JSON.stringify(state);
  for(const [kind,id] of [["inspection",inspectionId],["corrective",actionId],["effectiveness",reviewId]]){
    const selection={caseId,kind,id};
    assert.deepEqual(qualityEvidenceReturnTarget(state,selection,"sample-1001"),
      {caseId,kind,id,jobId:"sample-1001"});
    assert.equal(qualityEvidenceReturnTarget(state,selection,"sample-1002"),null);
    const html=qualityEvidenceReturnAction(state,selection,"sample-1001");
    assert.ok(html.includes('data-action="quality-evidence-return"'));
    assert.ok(html.includes('data-case="'+caseId+'" data-kind="'+kind+'" data-id="'+id+'"'));
    assert.ok(html.includes("Return to NCR evidence"));
    assert.equal(qualityEvidenceReturnAction(state,selection,"sample-1002"),"");
  }
  assert.equal(state.quality[0].status,"CLOSED");
  assert.equal(JSON.stringify(state),before);
});

test("NCR return suppresses stale, cross-case, orphaned and legacy evidence",()=>{
  let state=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
  state=raiseQuality(state,"sample-1002","Generic drawing revision conflict",later);
  const caseId=state.quality[0].id,otherId=state.quality[1].id;
  state=recordQualityInspection(state,caseId,"FINAL_REVIEW",
    state.jobs[0].routing.operations[0].step,"PASS",
    "Synthetic observation","2026-10-30T12:01:00Z");
  const id=state.quality[0].inspections[0].id;
  const selection={caseId,kind:"inspection",id};
  for(const invalid of [null,{}, {...selection,caseId:otherId},
    {...selection,kind:"corrective"},{...selection,id:"unknown"}]){
    assert.equal(qualityEvidenceReturnTarget(state,invalid,"sample-1001"),null);
    assert.equal(qualityEvidenceReturnAction(state,invalid,"sample-1001"),"");
  }
  const orphan=structuredClone(state);
  orphan.jobs=orphan.jobs.filter(job=>job.id!=="sample-1001");
  assert.equal(qualityEvidenceReturnAction(orphan,selection,"sample-1001"),"");
  const legacy=structuredClone(state);
  legacy.quality[0].inspections=[{observation:"Synthetic legacy note"}];
  assert.equal(qualityEvidenceReturnAction(legacy,selection,"sample-1001"),"");
  const changed=structuredClone(state);
  changed.jobs[0].routing.operations[0].center="CHANGED";
  assert.ok(qualityEvidenceReturnAction(changed,selection,"sample-1001").includes("Return to NCR evidence"),
    "Historical inspection remains readable even when current routing changes");
});

test("work-order return action is scoped and focuses original NCR evidence after navigation",()=>{
  const app=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
  assert.ok(app.includes('selectedQualityEvidence={caseId:target.caseId,kind:target.kind,id:target.id}'));
  assert.ok(app.includes('qualityEvidenceReturnAction(state,selectedQualityEvidence,selectedJobId)'));
  assert.ok(app.includes('if(action==="quality-evidence-return")'));
  assert.ok(app.includes('selectedQualityEvidence?.id!==selection.id'));
  assert.ok(app.includes('selectedQualityId=target.caseId'));
  assert.ok(app.includes('pendingQualityFocus={caseId:target.caseId,kind:target.kind,id:target.id}'));
  assert.ok(app.includes('panel?.dataset.caseId===focus.caseId'));
  assert.ok(app.includes('element.dataset.evidenceKind===focus.kind&&element.dataset.evidenceId===focus.id'));
  assert.ok(app.includes('target.focus({preventScroll:true})'));
});
