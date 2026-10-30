import test from "node:test";
import assert from "node:assert/strict";
import {seedState,makePurchaseOrder,receivePurchaseOrder,raiseQuality,createJob} from "./engine.mjs";
import {makeReport,reportCsv,REPORTS} from "./reports.mjs";
import {startSession,stopSession} from "../ewi/engine.mjs";
import {completePmTask} from "./pm.mjs";
const at="2026-10-30T12:00:00.000Z",later="2026-10-30T12:00:30.000Z";
test("all report types have functional rows, no fake network data",()=>{
 const state=seedState();
 assert.equal(REPORTS.length,9);
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
