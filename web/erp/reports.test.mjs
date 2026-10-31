import test from "node:test";
import assert from "node:assert/strict";
import {seedState,makePurchaseOrder,receivePurchaseOrder,raiseQuality,createJob} from "./engine.mjs";
import {makeReport,reportCsv,REPORTS} from "./reports.mjs";
import {startSession,stopSession} from "../ewi/engine.mjs";
import {completePmTask} from "./pm.mjs";
import {qualityJobSummary,recordQualityInspection,recordQualityDisposition,closeReviewedQuality,
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
 assert.ok(app.includes('selectedContext={type:"job",id}'));
 assert.ok(app.includes('selectedQualityId=(cases.find(q=>q.status==="OPEN")||cases[0]).id'));
 assert.ok(app.includes('if(view==="quality"&&selectedContext?.type==="job")'));
 assert.ok(app.includes('if(selected.id==="jobs"&&col===7&&Number(value)>0)'));
});
