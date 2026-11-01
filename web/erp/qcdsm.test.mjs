import test from "node:test";
import assert from "node:assert/strict";
import {seedState,raiseQuality,packetIssues,makePurchaseOrder,receivePurchaseOrder} from "./engine.mjs";
import {seedWorkforce,recordDemoPulse,recordDemoIncident,recordDemoSafetySurvey,validateWorkforce} from "./workforce.mjs";
import {qcdsmEvidence,captureQualityContext,qualityContextFor} from "./qcdsm.mjs";
import {renderQcdsm,renderCost,renderDelivery,renderSafety,wheelHtml,qualityRcaHtml} from "./qcdsm-view.mjs";
import {makeReport} from "./reports.mjs";
import {getMenuItem} from "./navigation.mjs";
const today="2026-10-30",at="2026-10-30T12:00:00Z";
const pulse={department:"Assembly",scheduled_headcount:20,present_headcount:18,overtime_hours:180,
 over_50_hours_count:8,exhausted_pto_count:3,pto_absence_count:1,sick_absence_clusters:0,
 turnover_count:0,staffing_shortage_count:3,quality_risk_signal:35};
test("QCDSM uses factual ERP signals and missing baselines remain N/A",()=>{
 const s=seedState(),w=seedWorkforce();
 const e=qcdsmEvidence(s,w,"Machining",today);
 assert.equal(e.moraleRisk,null);
 assert.equal(e.safetyPriority,null);
 assert.equal(e.cost.value,null);
 assert.equal(e.delivery.value,null);
 assert.equal(e.recordables,0);
 assert.ok(e.possibleFactors.length===0);
 assert.equal(e.quality.openHolds,0);
 assert.match(wheelHtml(e),/Morale/);
 assert.match(wheelHtml(e),/Quality/);
 assert.match(wheelHtml(e),/N\/A/);
 const wheel=wheelHtml(e);
 assert.equal((wheel.match(/data-qcdsm-domain=/g)||[]).length,5);
 assert.deepEqual([...wheel.matchAll(/data-qcdsm-domain="([^"]+)"/g)].map(x=>x[1]),
  ["Quality","Cost","Delivery","Safety","Morale"]);
 assert.equal((wheel.match(/data-driver="true"/g)||[]).length,1);
 assert.match(wheel,/data-qcdsm-domain="Morale" data-driver="true"/);
 assert.equal((wheel.match(/class="wheel-sector"/g)||[]).length,5);
 for(const route of ["quality","cost","delivery","safety","morale"]){
  assert.match(wheel,new RegExp('href="#'+route+'"'));
  assert.ok(getMenuItem(route));
 }
 assert.doesNotMatch(wheel,/>QCDSM<\/text>|QCDSM wheel|QCDSM operating wheel/);
 assert.doesNotMatch(wheel,/>MORALE<\/text>/);
 assert.doesNotMatch(renderQcdsm(s,w,"Machining",today),/Morale: the five structural levers|Purpose|Mastery|Autonomy|Belonging/);
});
test("overtime and 50+ hour pressure feed RCA investigation signals, no individual rating",()=>{
 const w=recordDemoPulse(seedWorkforce(),pulse);
 const e=qcdsmEvidence(seedState(),w,"Assembly",today);
 assert.ok(e.overtimeLoad>.15);
 assert.ok(e.possibleFactors.some(x=>x.key==="OVERTIME"));
 assert.ok(e.possibleFactors.some(x=>x.key==="LONG_HOURS"));
 assert.ok(e.possibleFactors.some(x=>x.key==="STAFFING"));
 assert.ok(e.moraleRisk>0);
 assert.equal(e.survey,null);
 assert.ok(!e.possibleFactors.some(x=>x.key==="SAFETY_CONFIDENCE"));
});
test("recent recordable gives review signal without inventing unsafe employee sentiment",()=>{
 const w=recordDemoIncident(seedWorkforce(),{department:"Quality",kind:"recordable",observedOn:today},today);
 const e=qcdsmEvidence(seedState(),w,"Quality",today);
 assert.equal(e.recordables,1);
 assert.equal(e.safetyPriority,70);
 assert.ok(e.possibleFactors.some(x=>x.key==="RECORDABLE"));
 assert.equal(e.survey,null);
 assert.ok(!e.possibleFactors.some(x=>x.key==="SAFETY_CONFIDENCE"));
 const late=qcdsmEvidence(seedState(),w,"Quality","2026-12-10");
 assert.equal(late.recordables,0);
 assert.equal(late.safetyPriority,null);
 assert.throws(()=>recordDemoIncident(w,{department:"Quality",kind:"recordable",observedOn:"2026-11-01"},today),/future/);
});
test("explicit aggregate confidence input changes safety priority, with validation",()=>{
 let w=recordDemoSafetySurvey(seedWorkforce(),{department:"Maintenance",respondents:10,concerned:4},today);
 let e=qcdsmEvidence(seedState(),w,"Maintenance",today);
 assert.equal(e.safetyPriority,12);
 assert.equal(e.survey.concerned,4);
 assert.ok(e.possibleFactors.some(x=>x.key==="SAFETY_CONFIDENCE"));
 assert.throws(()=>recordDemoSafetySurvey(w,{department:"Maintenance",respondents:5,concerned:6},today),/cannot exceed/);
 assert.equal(validateWorkforce(w),w);
});
test("RCA snapshot links to actual ERP NCR and freezes referenced evidence, does not change job clock readiness",()=>{
 let erp=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 let w=recordDemoPulse(seedWorkforce(),pulse);
 w=recordDemoIncident(w,{department:"Assembly",kind:"recordable",observedOn:today},today);
 let after=captureQualityContext(erp,w,erp.quality[0].id,"Assembly",today);
 let ctx=qualityContextFor(after,erp.quality[0].id);
 assert.equal(ctx.qualityId,erp.quality[0].id);
 assert.equal(ctx.pulseId,w.pulses.at(-1).id);
 assert.equal(ctx.safetyEventIds.length,1);
 assert.equal(ctx.finding,"REVIEW_REQUIRED");
 assert.ok(ctx.possibleFactors.some(x=>x.key==="OVERTIME"));
 assert.deepEqual(packetIssues(after,"sample-1001"),packetIssues(erp,"sample-1001"));
 assert.equal(qualityContextFor(erp,erp.quality[0].id),null);
 assert.ok(after.events.some(e=>e.type==="quality.qcdsm.context_captured"));
 const changed=recordDemoPulse(w,{...pulse,overtime_hours:0,over_50_hours_count:0,staffing_shortage_count:0});
 assert.equal(qualityContextFor(after,erp.quality[0].id).pulseId,ctx.pulseId);
 assert.notEqual(changed.pulses.at(-1).id,ctx.pulseId);
 assert.throws(()=>captureQualityContext(erp,w,"missing","Assembly",today),/existing quality record/);
});
test("QCDSM report and wheel read same sources as quality and workforce modules",()=>{
 let erp=raiseQuality(seedState(),"sample-1001","Generic drawing revision conflict",at);
 let w=recordDemoPulse(seedWorkforce(),pulse);
 w=recordDemoIncident(w,{department:"Assembly",kind:"recordable",observedOn:today},today);
 const report=makeReport(erp,[],"qcdsm",today,w);
 const row=report.rows.find(x=>x[0]==="Assembly");
 const e=qcdsmEvidence(erp,w,"Assembly",today);
 assert.equal(row[1],e.moraleRisk);
 assert.equal(row[4],e.recordables);
 assert.equal(row[5],e.safetyPriority);
 assert.equal(row[6],e.quality.openHolds);
 assert.equal(row[7],"N/A");
 const ui=renderQcdsm(erp,w,"Assembly",today);
 assert.match(ui,/Select a section to open its current records/);
 assert.doesNotMatch(ui,/QCDSM wheel|QCDSM operating wheel|data-form="safety-incident"/);
 const safetyUi=renderSafety(erp,w,"Assembly",today);
 assert.match(safetyUi,/data-form="safety-incident"/);
 assert.match(safetyUi,/data-form="safety-survey"/);
 assert.match(safetyUi,/SI-1/);
 const rca=qualityRcaHtml(erp,w,"Assembly",today);
 assert.match(rca,/data-form="quality-qcdsm-review"/);
 assert.match(rca,/Capture QCDSM evidence for RCA/);
});

test("Cost opens real PO and clock evidence, without inventing monetary rates",()=>{
 let erp=seedState();
 assert.match(renderCost(erp,[]),/No purchase orders entered/);
 erp=makePurchaseOrder(erp,"MAT-BAR",15,at);
 let page=renderCost(erp,[]);
 assert.match(page,/SIM-PO-0001/);
 assert.match(page,/>15</);
 assert.match(page,/Outstanding POs<\/small><strong>1/);
 assert.match(page,/Actual cost<\/small><strong>N\/A/);
 assert.match(page,/href="#purchasing"/);
 erp=receivePurchaseOrder(erp,erp.purchaseOrders[0].id,at);
 page=renderCost(erp,[]);
 assert.match(page,/Outstanding POs<\/small><strong>0/);
 assert.match(page,/Received POs<\/small><strong>1/);
});
test("Delivery opens current ERP work-order and material readiness, not fabricated OTD",()=>{
 let erp=seedState();
 let page=renderDelivery(erp);
 assert.match(page,/On-time delivery<\/small><strong>N\/A/);
 assert.match(page,/DEMO-4102/);
 assert.match(page,/data-job="sample-1001"/);
 assert.match(page,/href="#jobs"/);
 erp=raiseQuality(erp,"sample-1001","Generic drawing revision conflict",at);
 page=renderDelivery(erp);
 assert.match(page,/Needs attention<\/small><strong>2/);
 assert.match(page,/Open quality hold/);
 assert.match(page,/Readiness does not equal on-time delivery/);
});
test("Safety opens live department incident and distinct confidence records",()=>{
 let w=seedWorkforce();
 let page=renderSafety(seedState(),w,"Maintenance",today);
 assert.match(page,/No safety events recorded/);
 assert.match(page,/Safety priority<\/small><strong>N\/A/);
 w=recordDemoIncident(w,{department:"Maintenance",kind:"near_miss",observedOn:today},today);
 w=recordDemoSafetySurvey(w,{department:"Maintenance",respondents:10,concerned:4},today);
 page=renderSafety(seedState(),w,"Maintenance",today);
 assert.match(page,/SI-1/);
 assert.match(page,/Safety priority<\/small><strong>27/);
 assert.match(page,/Surveyed concerns<\/small><strong>4 \/ 10/);
 assert.match(page,/href="#quality"/);
 assert.match(page,/href="#morale"/);
 assert.doesNotMatch(renderSafety(seedState(),w,"Assembly",today),/SI-1/);
});
