import test from "node:test";
import assert from "node:assert/strict";
import {assessAlternateCenters} from "./routing-capacity-advice.mjs";

const job = () => ({jobNumber:"SYN-JOB-1",partNumber:"SYN-PART-1",revision:"A",
  routing:{revision:"A",operations:[
    {step:"10",name:"Fictional cutting",center:"DEMO-CUT",instructions:["Demo only"],check:"Sample check"},
    {step:"20",name:"Fictional inspection",center:"DEMO-QC",instructions:["Inspect sample"],check:"Sample result"}
  ]}});
const center = (id="LASER-01") => ({id,routedOperationCount:0,
  capability:{operation:"Fictional cutting",supported:true,sourceRef:"SYN-CAPABILITY-1"},
  calendarHours:40,bookedHours:10,queuedHours:4,maintenanceHours:2,setupHours:1,runHours:6,
  capacitySourceRef:"SYN-CALENDAR-1",readinessSourceRef:"SYN-READINESS-1",
  maintenanceState:"CLEAR",tooling:"READY",fixture:"READY",material:"READY",deliveryState:"ON_TIME"});
const scenario = (...centers) => ({window:{start:"2026-11-02T08:00:00Z",end:"2026-11-06T16:00:00Z"},centers});
const assess = (...centers) => assessAlternateCenters(job(),"10",scenario(...centers));

test("compatible zero-routed center needs actual scenario hours and remains draft-only",()=>{
  const j=job(),original=structuredClone(j),c=center(),before=structuredClone(c);
  const r=assessAlternateCenters(j,"10",scenario(c));
  assert.equal(r.status,"SCENARIO_CANDIDATES");
  assert.equal(r.suggestions.length,1);
  assert.equal(r.suggestions[0].routingReview.status,"REVIEW_REQUIRED");
  assert.equal(r.suggestions[0].routingReview.changes[0].capabilityUnverified,true);
  assert.equal(r.suggestions[0].candidate.operations[0].center,"LASER-01");
  assert.equal(r.suggestions[0].canAutoApply,false);
  assert.equal(r.suggestions[0].utilizationPercent,40);
  assert.equal(r.suggestions[0].slackHours,17);
  assert.deepEqual(j,original);assert.deepEqual(c,before);
});
test("explicitly incompatible idle work center is excluded",()=>{
  const c=center();c.capability.supported=false;
  const r=assess(c);
  assert.equal(r.assessments[0].status,"EXCLUDED");
  assert.match(r.assessments[0].blocked.join(" "),/incompatible/);
  assert.equal(r.suggestions.length,0);
});
test("machine down for maintenance is excluded despite apparent hours",()=>{
  const c=center();c.maintenanceState="DOWN";
  assert.match(assess(c).assessments[0].blocked.join(" "),/maintenance/);
});
test("insufficient working hours excludes the candidate",()=>{
  const c=center();c.calendarHours=10;
  assert.equal(assess(c).assessments[0].status,"EXCLUDED");
});
test("queued job load is included rather than treating unscheduled work as free",()=>{
  const c=center();c.queuedHours=24;
  const a=assess(c).assessments[0];
  assert.equal(a.status,"EXCLUDED");
  assert.match(a.blocked.join(" "),/Insufficient remaining hours/);
});
test("missing calendar, readiness or evidence remains UNKNOWN without utilization",()=>{
  const c=center();delete c.calendarHours;c.material="UNKNOWN";delete c.capacitySourceRef;
  const a=assess(c).assessments[0];
  assert.equal(a.status,"NEEDS_REVIEW");
  assert.equal(a.utilizationPercent,null);
  assert.match(a.unknown.join(" "),/UNKNOWN/);
  assert.equal(assess(c).suggestions.length,0);
});
test("zero routed operations never substitutes for missing hours",()=>{
  const c=center();delete c.bookedHours;
  const r=assess(c);
  assert.equal(r.assessments[0].idleCandidate,true);
  assert.equal(r.assessments[0].status,"NEEDS_REVIEW");
  assert.equal(r.suggestions.length,0);
});
test("eligible idle work center ranks ahead of occupied alternative",()=>{
  const occupied=center("PRESS-02");occupied.routedOperationCount=3;occupied.bookedHours=0;
  const r=assess(occupied,center("LASER-01"));
  assert.deepEqual(r.suggestions.map(s=>s.center),["LASER-01","PRESS-02"]);
  assert.deepEqual(r.suggestions.map(s=>s.rank),[1,2]);
});
test("missing program is nonblocking; asserted program is not proof",()=>{
  const c=center();c.programLink={programId:"SYN-PROGRAM-1"};
  const r=assess(c);
  assert.equal(r.suggestions.length,1);
  assert.match(r.assessments[0].notes.join(" "),/asserted only/);
});
test("invalid revision, duplicate IDs and invalid planning windows are rejected",()=>{
  const j=job();j.routing.revision="B";
  assert.equal(assessAlternateCenters(j,"10",scenario(center())).status,"INVALID_SCENARIO");
  assert.equal(assess(center(),center()).status,"INVALID_SCENARIO");
  assert.equal(assessAlternateCenters(job(),"10",{window:{start:"bad",end:"bad"},centers:[center()]}).status,"INVALID_SCENARIO");
});
test("unregistered work center cannot be recommended",()=>{
  const r=assess(center("NOT-REGISTERED"));
  assert.equal(r.assessments[0].status,"EXCLUDED");
  assert.equal(r.suggestions.length,0);
});

test("fractional-hour deficit is excluded before rounded display values",()=>{
  const c=center();
  c.calendarHours=8;c.bookedHours=0;c.queuedHours=0;c.maintenanceHours=0;
  c.setupHours=1;c.runHours=7.004;
  const insufficient=assess(c);
  assert.equal(insufficient.assessments[0].status,"EXCLUDED");
  assert.equal(insufficient.assessments[0].slackHours,0);
  assert.equal(insufficient.suggestions.length,0);
  assert.match(insufficient.assessments[0].blocked.join(" "),/Insufficient remaining hours/);
  c.runHours=6.996;
  const sufficient=assess(c);
  assert.equal(sufficient.assessments[0].status,"SCENARIO_ELIGIBLE");
  assert.equal(sufficient.suggestions.length,1);
  assert.equal(sufficient.assessments[0].slackHours,0);
});
