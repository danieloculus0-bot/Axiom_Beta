import test from "node:test";
import assert from "node:assert/strict";
import {seedState} from "./engine.mjs";
import {reviewPmWorkCenterAssociation} from "./pm-work-center-link.mjs";
import {inspectRoutingCapacityEvidence,routingCapacityEvidenceHtml,readRoutingCapacityScenario} from "./routing-capacity-review.mjs";

const START="2026-11-02T08:00", END="2026-11-02T16:00";
test("canonical routing and PM snapshot produce review-only UNKNOWN evidence without mutations",()=>{
  const state=seedState(),job=state.jobs[0],before=structuredClone(state);
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END);
  assert.equal(review.result.canAutoApply,false);
  assert.equal(review.result.suggestions.length,0);
  assert.equal(review.assessment.status,"NEEDS_REVIEW");
  assert.equal(review.assessment.pmEvidence.status,"UNMAPPED");
  assert.equal(review.assessment.availableHours,null);
  assert.equal(review.assessment.utilizationPercent,null);
  assert.ok(review.assessment.unknown.some(s=>/Planning-window hours are UNKNOWN/.test(s)));
  assert.deepEqual(state,before);
  const html=routingCapacityEvidenceHtml(job,review);
  assert.match(html,/routing-capacity-review/);
  assert.match(html,/NEEDS_REVIEW/);
  assert.match(html,/UNMAPPED/);
  assert.match(html,/No alternate routing proposed or saved/);
});
test("invalid, stale, current-center and reversed-window requests are rejected",()=>{
  const state=seedState(),job=state.jobs[0];
  const run=(step,center,start=START,end=END,id=job.id)=>
    inspectRoutingCapacityEvidence(state,id,step,center,start,end);
  assert.throws(()=>run("99","PRESS-02"),/routed operation/);
  assert.throws(()=>run("10","LASER-01"),/different registered/);
  assert.throws(()=>run("10","PRIVATE-MACHINE"),/different registered/);
  assert.throws(()=>run("10","PRESS-02",END,START),/end after/);
  assert.throws(()=>run("10","PRESS-02","not-a-time",END),/start and end/);
  assert.throws(()=>run("10","PRESS-02",START,END,"missing-job"),/existing fictional job/);
});
test("reviewed PM association is still not proof of capacity or qualification",()=>{
  const state=seedState(),job=state.jobs[0],machine=state.pm.machines[0];
  const linked=reviewPmWorkCenterAssociation(state.pm,{
    machineId:machine.id,centerId:"PRESS-02",sourceRef:"SYN-PREFLIGHT-001",
    reviewedBy:"DEMO-PLANNER",at:"2026-11-01T08:00:00Z"
  });
  state.pm=linked.pm;
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END);
  assert.equal(review.assessment.pmEvidence.machineId,machine.id);
  assert.equal(review.assessment.status,"NEEDS_REVIEW");
  assert.equal(review.result.suggestions.length,0);
  assert.equal(review.result.canAutoApply,false);
});
test("review HTML escapes operation labels and untrusted evidence messages",()=>{
  const state=seedState(),job=structuredClone(state.jobs[0]);
  job.routing.operations[0].name='<img src=x onerror=alert(1)>';
  const html=routingCapacityEvidenceHtml(job);
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!html.includes('<img src=x'));
});

const scopedEvidence = job => ({
  scope:{jobId:job.id,partNumber:job.partNumber,revision:job.revision,
    step:"10",centerId:"PRESS-02",startLocal:START,endLocal:END},
  center:{capability:{operation:job.routing.operations[0].name,supported:true,sourceRef:"SYN-CAP-001"},
    calendarHours:8,bookedHours:1,queuedHours:1,maintenanceHours:0,setupHours:1,runHours:2,
    capacitySourceRef:"SYN-CALENDAR-001",readinessSourceRef:"SYN-READY-001",
    maintenanceState:"CLEAR",tooling:"READY",fixture:"READY",material:"READY",
    deliveryState:"ON_TIME",routedOperationCount:0}
});
test("scoped fictional hours reach advisor but PM remains unverified and nothing persists",()=>{
  const state=seedState(),job=state.jobs[0],before=structuredClone(state),e=scopedEvidence(job);
  const copy=structuredClone(e);
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  assert.equal(review.assessment.availableHours,6);
  assert.equal(review.assessment.requiredHours,3);
  assert.equal(review.assessment.utilizationPercent,25);
  assert.equal(review.assessment.pmEvidence.status,"UNMAPPED");
  assert.equal(review.assessment.status,"NEEDS_REVIEW");
  assert.equal(review.result.suggestions.length,0);
  assert.equal(review.result.canAutoApply,false);
  assert.match(routingCapacityEvidenceHtml(job,review),/Scenario estimates, not verified/);
  assert.deepEqual(state,before);assert.deepEqual(e,copy);
});
test("scenario evidence is bound to exact job, part, revision, step, center and window",()=>{
  const state=seedState(),job=state.jobs[0],e=scopedEvidence(job);
  const run=()=>inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  for(const k of Object.keys(e.scope)){
    const prior=e.scope[k];e.scope[k]="SYN-WRONG";
    assert.throws(run,/must match the selected job/);e.scope[k]=prior;
  }
  e.center.capability.operation="Unrelated operation";
  assert.throws(run,/exact selected operation/);
});
test("unsourced, invalid and unsupported scenario fields fail closed",()=>{
  const state=seedState(),job=state.jobs[0],e=scopedEvidence(job);
  const run=()=>inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  e.center.capacitySourceRef="private-asset";
  assert.throws(run,/fictional SYN-/);e.center.capacitySourceRef="SYN-CALENDAR-001";
  e.center.calendarHours=-1;
  assert.throws(run,/finite, nonnegative/);e.center.calendarHours=8;
  e.center.maintenanceState="CERTIFIED";
  assert.throws(run,/supported states/);e.center.maintenanceState="CLEAR";
  e.center.programLink={programId:"SYN-OTHER"};
  assert.throws(run,/unsupported or missing evidence/);
});

const browserScenarioFields=()=>{
  const f=new FormData();
  for(const [k,v] of Object.entries({
    capability:"supported","capability-ref":"SYN-UI-CAP-001",
    calendarHours:"8",bookedHours:"1",queuedHours:"1",maintenanceHours:"0",
    setupHours:"1",runHours:"2","capacity-ref":"SYN-UI-CAL-001",
    "readiness-ref":"SYN-UI-READY-001",maintenanceState:"CLEAR",
    tooling:"READY",fixture:"READY",material:"READY",
    deliveryState:"ON_TIME",routedOperationCount:"0"
  }))f.set("scenario-"+k,v);
  return f;
};
test("browser scenario opt-in rejects missing or unsourced values",()=>{
  const state=seedState(),job=state.jobs[0],f=browserScenarioFields();
  assert.equal(readRoutingCapacityScenario(f,job,"10","PRESS-02",START,END),null);
  f.set("scenario-enabled","yes");f.delete("scenario-calendarHours");
  assert.throws(()=>readRoutingCapacityScenario(f,job,"10","PRESS-02",START,END),/six scenario hour/);
  f.set("scenario-calendarHours","8");f.set("scenario-capacity-ref","REAL-ASSET");
  assert.throws(()=>readRoutingCapacityScenario(f,job,"10","PRESS-02",START,END),/fictional SYN-/);
});
test("browser scenario produces traceable estimates but no clearance or writes",()=>{
  const state=seedState(),job=state.jobs[0],before=structuredClone(state),f=browserScenarioFields();
  f.set("scenario-enabled","yes");
  const e=readRoutingCapacityScenario(f,job,"10","PRESS-02",START,END);
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  assert.equal(review.assessment.availableHours,6);
  assert.equal(review.assessment.utilizationPercent,25);
  assert.equal(review.assessment.pmEvidence.status,"UNMAPPED");
  assert.equal(review.assessment.status,"NEEDS_REVIEW");
  assert.equal(review.result.canAutoApply,false);
  assert.deepEqual(state,before);
  const html=routingCapacityEvidenceHtml(job,review);
  assert.match(html,/scenario-enabled" value="yes" checked/);
  assert.match(html,/SYN-UI-CAL-001/);
  assert.match(html,/Scenario estimates, not verified/);
  // Reviewed controls must retain their exact values after DOM re-render.
  assert.match(html,/<option value="10" selected>/);
  assert.match(html,/<option value="PRESS-02" selected>/);
  assert.match(html,/<option value="supported" selected>/);
  assert.match(html,/<option value="CLEAR" selected>/);
  assert.match(html,/<option value="READY" selected>/);
  assert.match(html,/<option value="ON_TIME" selected>/);
});
test("unsupported fictional capability is excluded",()=>{
  const state=seedState(),job=state.jobs[0],f=browserScenarioFields();
  f.set("scenario-enabled","yes");f.set("scenario-capability","unsupported");
  const e=readRoutingCapacityScenario(f,job,"10","PRESS-02",START,END);
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  assert.equal(review.assessment.status,"EXCLUDED");
  assert.equal(review.result.suggestions.length,0);
  assert.equal(review.result.canAutoApply,false);
});

test("a claimed idle center cannot contradict existing canonical routing assignments",()=>{
  const state=seedState(),job=state.jobs[0],before=structuredClone(state),e=scopedEvidence(job);
  // PRESS-02 is already assigned to step 20 of the existing fictional job.
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  assert.equal(review.knownRoutedCount,1);
  assert.equal(review.assessment.idleCandidate,false);
  assert.equal(review.assessment.status,"NEEDS_REVIEW");
  assert.match(review.assessment.unknown.join(" "),/zero routed operations conflicts/);
  assert.match(review.assessment.unknown.join(" "),/planning-window load is UNKNOWN/);
  assert.equal(review.result.suggestions.length,0);
  assert.match(routingCapacityEvidenceHtml(job,review),/not a scheduled-load/);
  assert.deepEqual(state,before);
  assert.equal(e.center.routedOperationCount,0); // no caller mutation
});
test("zero existing route references is only an idle candidate, not verified free hours",()=>{
  const state=seedState(),job=state.jobs[0],e=scopedEvidence(job);
  e.scope.centerId="DEMO-CUT";
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","DEMO-CUT",START,END,e);
  assert.equal(review.knownRoutedCount,0);
  assert.equal(review.assessment.idleCandidate,true);
  assert.equal(review.assessment.status,"NEEDS_REVIEW"); // PM mapping is still UNKNOWN
  assert.equal(review.result.suggestions.length,0);
});
test("nonzero asserted routed count remains reviewable without inferring a schedule",()=>{
  const state=seedState(),job=state.jobs[0],e=scopedEvidence(job);
  e.center.routedOperationCount=1;
  const review=inspectRoutingCapacityEvidence(state,job.id,"10","PRESS-02",START,END,e);
  assert.equal(review.knownRoutedCount,1);
  assert.equal(review.assessment.idleCandidate,false);
  assert.ok(!review.assessment.unknown.some(x=>x.includes("zero routed operations conflicts")));
  assert.equal(review.result.canAutoApply,false);
});
