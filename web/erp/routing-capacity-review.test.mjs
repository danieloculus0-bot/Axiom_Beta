import test from "node:test";
import assert from "node:assert/strict";
import {seedState} from "./engine.mjs";
import {reviewPmWorkCenterAssociation} from "./pm-work-center-link.mjs";
import {inspectRoutingCapacityEvidence,routingCapacityEvidenceHtml} from "./routing-capacity-review.mjs";

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
