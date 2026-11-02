import test from "node:test";
import assert from "node:assert/strict";
import {seedWorkforce} from "./workforce.mjs";
import {submitDemoPto,reviewDemoPto,previewDemoPay,renderPto,renderPayroll} from "./people-workflows.mjs";
import {MODULE_CATALOG,renderModuleDirectory,camFacingEnvelope,renderCam} from "./portfolio-view.mjs";
import {seedState} from "./engine.mjs";
test("PTO uses existing fictional employee codes, review guards and immutable state",()=>{
 const w=seedWorkforce();
 const a=submitDemoPto(w,{personId:"DEMO-01",startDate:"2026-11-02",endDate:"2026-11-03"});
 assert.equal(w.ptoRequests.length,0);assert.equal(a.ptoRequests[0].days,2);
 assert.throws(()=>submitDemoPto(a,{personId:"DEMO-01",startDate:"2026-11-03",endDate:"2026-11-04"}),/overlapping/);
 assert.throws(()=>submitDemoPto(w,{personId:"UNKNOWN",startDate:"2026-11-02",endDate:"2026-11-03"}),/existing/);
 const b=reviewDemoPto(a,"PTO-1","APPROVED_SIMULATION");
 assert.equal(b.ptoRequests[0].status,"APPROVED_SIMULATION");
 assert.throws(()=>reviewDemoPto(b,"PTO-1","DECLINED"),/not found/);
});
test("pay preview is exact arithmetic with no payments or tax inference",()=>{
 const w=seedWorkforce();
 const p=previewDemoPay(w,{personId:"DEMO-01",payType:"hourly",rate:"25",hours:"40",overtime:"5",bonus:"100",tax:"200",deductions:"50"});
 assert.equal(p.gross,1287.5);assert.equal(p.net,1037.5);
 assert.throws(()=>previewDemoPay(w,{personId:"DEMO-01",payType:"salary",rate:2000,hours:0,overtime:5,bonus:0,tax:0,deductions:0}),/Salary overtime/);
 assert.ok(renderPayroll(w,p).includes("not an actual pay stub"));
 assert.ok(renderPto(w).includes('data-form="pto-submit"'));
});
test("CAM facing exercise validates bounds and does not invent production authority",()=>{
 const r=camFacingEnvelope({width:120,height:80,diameter:16,stepover:55,depth:.5,stepdown:.5});
 assert.ok(r.passCount>0);
 assert.throws(()=>camFacingEnvelope({width:120,height:80,diameter:16,stepover:0,depth:.5,stepdown:.5}),/Stepover/);
 const out=renderCam(seedState().jobs[0],r);
 assert.ok(out.includes("NOT a dimension")&&out.includes('href="#routing"')&&out.includes("No CNC code"));
});
test("CAM page embeds the full EZ CAM browser app with a direct launch fallback and preserves job context",()=>{
 const html=renderCam(seedState().jobs[0]);
 assert.match(html,/<iframe[^>]+class="cam-embed"[^>]+src="https:\/\/danieloculus0-bot\.github\.io\/EZ-CAM\/"/);
 assert.ok(html.includes("Open full-size CAM demo"));
 assert.ok(html.includes('href="#routing"'));
 assert.ok(html.includes("independent browser state"));
});
test("module directory includes audited local-only and independent modules without fake routes",()=>{
 const html=renderModuleDirectory();
 for(const name of ["EZ CAM","Payroll","PTO requests","EZ-FAIR","Supplier intelligence","Accounting & journal","BEAN reasoning"])
  assert.ok(MODULE_CATALOG.some(([,items])=>items.some(x=>x[0].startsWith(name))),name);
 assert.ok(MODULE_CATALOG.every(([,items])=>items.every(x=>x[2]===null||/^(jobs|routing|ewi|cam|documents|quality|inventory|purchasing|requests|pm|cost|qcdsm|hr|pto|payroll|morale|reports|audit)$/.test(x[2]))));
 assert.ok(html.includes("No public in-app screen"));
});