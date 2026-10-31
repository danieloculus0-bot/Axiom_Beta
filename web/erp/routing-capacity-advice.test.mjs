import test from "node:test";
import assert from "node:assert/strict";
import {assessAlternateCenters} from "./routing-capacity-advice.mjs";
import {seedPm,completePmTask,requestMaintenance,closeMaintenanceRequest} from "./pm.mjs";

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
  assert.equal(r.suggestions[0].routingReview.programAssociations[0].status,"MISMATCH_OR_INCOMPLETE");
});
test("complete optional program reference reaches existing reviewer without proving qualification",()=>{
  const c=center();c.programLink={step:"10",partNumber:"SYN-PART-1",revision:"A",center:"LASER-01",
    programId:"SYN-PROGRAM-1",sourceRef:"SYN-PROGRAM-METADATA-1"};
  const original=structuredClone(c);
  const r=assess(c);
  assert.equal(r.suggestions.length,1);
  assert.deepEqual(r.suggestions[0].candidate.programLinks,[c.programLink]);
  assert.equal(r.suggestions[0].routingReview.programAssociations[0].status,"ASSERTED_REFERENCE_ONLY");
  assert.equal(r.suggestions[0].routingReview.changes[0].capabilityUnverified,true);
  assert.equal(r.suggestions[0].canAutoApply,false);
  assert.deepEqual(c,original);
});
test("mismatched optional program revision stays flagged and does not block routing proposal",()=>{
  const c=center();c.programLink={step:"10",partNumber:"SYN-PART-1",revision:"B",center:"LASER-01",
    programId:"SYN-PROGRAM-2",sourceRef:"SYN-PROGRAM-METADATA-2"};
  const r=assess(c);
  assert.equal(r.suggestions.length,1);
  assert.equal(r.suggestions[0].routingReview.programAssociations[0].status,"MISMATCH_OR_INCOMPLETE");
  assert.match(r.suggestions[0].routingReview.issues.join(" "),/program associations/);
  assert.equal(r.suggestions[0].canAutoApply,false);
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

test("two-operation alternate-center suggestion rejects unrelated CNC program evidence",()=>{
 const v=center();v.programLink={step:"20",partNumber:"SYN-PART-1",revision:"A",
  center:"DEMO-QC",programId:"SYN-UNRELATED-20",sourceRef:"SYN-REF-20"};
 const result=assess(v);
 assert.equal(result.suggestions.length,1);
 assert.equal(result.suggestions[0].candidate.operations[0].center,"LASER-01");
 assert.equal(result.suggestions[0].routingReview.programAssociations[0].status,"MISMATCH_OR_INCOMPLETE");
 assert.match(result.suggestions[0].routingReview.issues.join(" "),/do not match/);
 assert.equal(result.suggestions[0].canAutoApply,false);
});

const mappedPmScenario = (pm, links=[{centerId:"LASER-01",machineId:"DEMO-M-001",sourceRef:"SYN-PM-MAPPING-1"}]) => {
  const s=scenario(center());
  s.pmContext={state:pm,links};
  return s;
};
test("optional PM snapshot without explicit asset mapping cannot assert clearance",()=>{
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(seedPm("2026-11-02"),[]));
  assert.equal(r.assessments[0].status,"NEEDS_REVIEW");
  assert.equal(r.assessments[0].pmEvidence.status,"UNMAPPED");
  assert.equal(r.suggestions.length,0);
});
test("existing PM overdue work produces a review signal, not automatic machine-down claim",()=>{
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(seedPm("2026-11-02")));
  const a=r.assessments[0];
  assert.equal(a.status,"NEEDS_REVIEW");
  assert.equal(a.pmEvidence.status,"NEEDS_REVIEW");
  assert.ok(a.pmEvidence.dueTaskIds.includes("DEMO-PM-001"));
  assert.equal(a.blocked.length,0);
  assert.equal(r.suggestions.length,0);
});
test("completed PM and no recorded alerts preserve independent scenario clearance",()=>{
  const pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T09:00:00Z"}).pm;
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  assert.equal(r.suggestions.length,1);
  assert.equal(r.assessments[0].pmEvidence.status,"NO_RECORDED_ALERTS");
  assert.ok(r.suggestions[0].evidenceRefs.includes("SYN-PM-MAPPING-1"));
  assert.equal(r.suggestions[0].canAutoApply,false);
});
test("open PM request flags uncertainty; closing it restores only scenario eligibility",()=>{
  let pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T09:00:00Z"}).pm;
  const request=requestMaintenance(pm,"DEMO-M-001","Illustrative abnormal noise","Medium","DEMO-01","2026-11-01T10:00:00Z");
  pm=request.pm;
  const before=structuredClone(pm);
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  assert.equal(r.assessments[0].status,"NEEDS_REVIEW");
  assert.ok(r.assessments[0].pmEvidence.openRequestIds.includes(request.id));
  assert.equal(r.assessments[0].blocked.length,0);
  assert.deepEqual(pm,before);
  pm=closeMaintenanceRequest(pm,request.id,"Example resolved","2026-11-01T11:00:00Z");
  const cleared=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  assert.equal(cleared.assessments[0].pmEvidence.status,"NO_RECORDED_ALERTS");
  assert.equal(cleared.suggestions.length,1);
});
test("unresolved or ambiguous PM mapping never fabricates a work-center link",()=>{
  let s=mappedPmScenario(seedPm("2026-11-02"),[{centerId:"LASER-01",machineId:"DEMO-M-999",sourceRef:"SYN-LINK"}]);
  const unresolved=assessAlternateCenters(job(),"10",s);
  assert.equal(unresolved.assessments[0].pmEvidence.status,"UNRESOLVED");
  assert.equal(unresolved.suggestions.length,0);
  s=mappedPmScenario(seedPm("2026-11-02"),[
    {centerId:"LASER-01",machineId:"DEMO-M-001",sourceRef:"SYN-1"},
    {centerId:"LASER-01",machineId:"DEMO-M-002",sourceRef:"SYN-2"}]);
  assert.equal(assessAlternateCenters(job(),"10",s).status,"INVALID_SCENARIO");
});
test("malformed PM asset record does not crash advisory review",()=>{
  const pm=seedPm("2026-11-02");pm.machines=[null];
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  assert.equal(r.assessments[0].pmEvidence.status,"UNKNOWN");
  assert.equal(r.suggestions.length,0);
});

test("canonical PM machine association resolves without a caller link",()=>{
  const pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T09:00:00Z"}).pm;
  pm.machines[0].workCenterLink={centerId:"LASER-01",sourceRef:"SYN-CANONICAL-PM-LINK",reviewedAt:"2026-11-01T08:00:00Z",reviewState:"DEMO_REVIEWED"};
  const before=structuredClone(pm),s=scenario(center());
  s.pmContext={state:pm};
  const r=assessAlternateCenters(job(),"10",s);
  assert.equal(r.assessments[0].pmEvidence.status,"NO_RECORDED_ALERTS");
  assert.equal(r.assessments[0].pmEvidence.machineId,"DEMO-M-001");
  assert.equal(r.suggestions.length,1);
  assert.ok(r.suggestions[0].evidenceRefs.includes("SYN-CANONICAL-PM-LINK"));
  assert.equal(r.suggestions[0].canAutoApply,false);
  assert.deepEqual(pm,before);
});
test("canonical PM link without source evidence cannot assert a relationship",()=>{
  const pm=seedPm("2026-11-02");
  pm.machines[0].workCenterLink={centerId:"LASER-01"};
  const s=scenario(center());s.pmContext={state:pm};
  const r=assessAlternateCenters(job(),"10",s);
  assert.equal(r.status,"INVALID_SCENARIO");
  assert.equal(r.suggestions.length,0);
});
test("canonical PM link to unregistered center is rejected",()=>{
  const pm=seedPm("2026-11-02");
  pm.machines[0].workCenterLink={centerId:"NOT-A-CENTER",sourceRef:"SYN-UNVERIFIED"};
  const s=scenario(center());s.pmContext={state:pm};
  assert.equal(assessAlternateCenters(job(),"10",s).status,"INVALID_SCENARIO");
});
test("conflicting PM machine and caller links fail rather than guessing",()=>{
  const pm=seedPm("2026-11-02");
  pm.machines[0].workCenterLink={centerId:"LASER-01",sourceRef:"SYN-CANONICAL",reviewedAt:"2026-11-01T08:00:00Z",reviewState:"DEMO_REVIEWED"};
  const s=mappedPmScenario(pm,[{centerId:"LASER-01",machineId:"DEMO-M-002",sourceRef:"SYN-LEGACY"}]);
  const r=assessAlternateCenters(job(),"10",s);
  assert.equal(r.status,"INVALID_SCENARIO");
  assert.equal(r.suggestions.length,0);
});
test("two PM machines claiming the same center are ambiguous",()=>{
  const pm=seedPm("2026-11-02");
  pm.machines[0].workCenterLink={centerId:"LASER-01",sourceRef:"SYN-LINK-1",reviewedAt:"2026-11-01T08:00:00Z",reviewState:"DEMO_REVIEWED"};
  pm.machines[1].workCenterLink={centerId:"LASER-01",sourceRef:"SYN-LINK-2",reviewedAt:"2026-11-01T08:00:00Z",reviewState:"DEMO_REVIEWED"};
  const s=scenario(center());s.pmContext={state:pm};
  assert.equal(assessAlternateCenters(job(),"10",s).status,"INVALID_SCENARIO");
});

test("post-window PM completion and request closure cannot clear an earlier window",()=>{
  let pm=seedPm("2026-11-02");
  pm=completePmTask(pm,"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-07T09:00:00Z"}).pm;
  const request=requestMaintenance(pm,"DEMO-M-001","Illustrative abnormal noise",
    "Medium","DEMO-01","2026-11-02T10:00:00Z");
  pm=closeMaintenanceRequest(request.pm,request.id,"Example resolved","2026-11-07T11:00:00Z");
  const before=structuredClone(pm);
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  const evidence=r.assessments[0].pmEvidence;
  assert.equal(evidence.status,"NEEDS_REVIEW");
  assert.ok(evidence.dueTaskIds.includes("DEMO-PM-001"));
  assert.ok(evidence.openRequestIds.includes(request.id));
  assert.equal(r.suggestions.length,0);
  assert.deepEqual(pm,before);
});
test("PM completion during the window does not rewrite readiness at window start",()=>{
  const pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-03T09:00:00Z"}).pm;
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  assert.equal(r.assessments[0].pmEvidence.status,"NEEDS_REVIEW");
  assert.ok(r.assessments[0].pmEvidence.dueTaskIds.includes("DEMO-PM-001"));
});
test("requests opened after the window do not block an earlier planning scenario",()=>{
  let pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T09:00:00Z"}).pm;
  pm=requestMaintenance(pm,"DEMO-M-001","Illustrative abnormal noise",
    "Medium","DEMO-01","2026-11-07T10:00:00Z").pm;
  const r=assessAlternateCenters(job(),"10",mappedPmScenario(pm));
  assert.equal(r.assessments[0].pmEvidence.status,"NO_RECORDED_ALERTS");
  assert.equal(r.suggestions.length,1);
});


/* Synthetic human-review contract for optional canonical PM/work-center links. */
const {reviewPmWorkCenterAssociation} = await import("./pm-work-center-link.mjs");
const reviewLink = (pm,machineId="DEMO-M-001",centerId="LASER-01",overrides={}) =>
  reviewPmWorkCenterAssociation(pm,{
    machineId,centerId,sourceRef:"SYN-REVIEW-LINK-1",
    reviewedBy:"DEMO-PLANNER",at:"2026-11-01T08:00:00Z",...overrides
  });

test("human-reviewed PM association persists only in cloned canonical PM record",()=>{
  const pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T07:00:00Z"}).pm;
  const before=structuredClone(pm);
  const result=reviewLink(pm);
  assert.deepEqual(pm,before);
  assert.equal(result.pm.machines[0].workCenterLink.centerId,"LASER-01");
  assert.equal(result.pm.machines[0].workCenterLink.reviewState,"DEMO_REVIEWED");
  assert.equal(result.pm.workCenterLinkHistory.length,1);
  assert.equal(result.pm.workCenterLinkHistory[0].previousCenterId,null);
  assert.equal(result.canAutoRelease,false);
  const s=scenario(center());s.pmContext={state:result.pm};
  const assessed=assessAlternateCenters(job(),"10",s);
  assert.equal(assessed.assessments[0].pmEvidence.machineId,"DEMO-M-001");
  assert.equal(assessed.assessments[0].pmEvidence.status,"NO_RECORDED_ALERTS");
  assert.equal(assessed.suggestions[0].canAutoApply,false);
});

test("reviewed association requires synthetic reviewer, source and explicit time",()=>{
  const pm=seedPm("2026-11-02");
  assert.throws(()=>reviewLink(pm,"DEMO-M-001","LASER-01",{reviewedBy:""}),/reviewer/);
  assert.throws(()=>reviewLink(pm,"DEMO-M-001","LASER-01",{sourceRef:""}),/SYN-/);
  assert.throws(()=>reviewLink(pm,"DEMO-M-001","LASER-01",{sourceRef:"REAL-REF"}),/SYN-/);
  assert.throws(()=>reviewLink(pm,"DEMO-M-001","LASER-01",{at:"2026-11-01"}),/timestamp/);
  assert.throws(()=>reviewLink(pm,"DEMO-M-999"),/existing fictional/);
  assert.throws(()=>reviewLink(pm,"DEMO-M-001","UNREGISTERED"),/registered/);
});

test("duplicate PM machine claims for one work center are rejected",()=>{
  const linked=reviewLink(seedPm("2026-11-02")).pm;
  assert.throws(()=>reviewLink(linked,"DEMO-M-002","LASER-01"),/already associated/);
  assert.equal(linked.machines[1].workCenterLink,undefined);
});

test("explicit reviewed unlink restores unmapped uncertainty and preserves history",()=>{
  const linked=reviewLink(seedPm("2026-11-02")).pm;
  const unlinked=reviewLink(linked,"DEMO-M-001",null,{
    sourceRef:"SYN-UNLINK-1",at:"2026-11-01T09:00:00Z"}).pm;
  assert.equal(unlinked.machines[0].workCenterLink,undefined);
  assert.equal(linked.machines[0].workCenterLink.centerId,"LASER-01");
  assert.equal(unlinked.workCenterLinkHistory.length,2);
  assert.equal(unlinked.workCenterLinkHistory[1].kind,"DEMO_UNLINK");
  const s=scenario(center());s.pmContext={state:unlinked};
  const assessed=assessAlternateCenters(job(),"10",s);
  assert.equal(assessed.assessments[0].pmEvidence.status,"UNMAPPED");
  assert.equal(assessed.suggestions.length,0);
});

test("reassociation preserves the previous center in review history",()=>{
  const first=reviewLink(seedPm("2026-11-02")).pm;
  const next=reviewLink(first,"DEMO-M-001","PRESS-02",{
    sourceRef:"SYN-REVIEW-LINK-2",at:"2026-11-01T10:00:00Z"}).pm;
  assert.equal(next.machines[0].workCenterLink.centerId,"PRESS-02");
  assert.equal(next.workCenterLinkHistory[1].previousCenterId,"LASER-01");
  assert.throws(()=>reviewLink(next,"DEMO-M-001","PRESS-02"),/unchanged/);
});

/* renderPm association UI: synthetic records, no browser or live equipment. */
const {renderPm} = await import("./pm-view.mjs");

test("renderPm association UI exposes optional center selection and explicit review",()=>{
  const pm=seedPm("2026-11-02"),before=structuredClone(pm);
  const html=renderPm(pm,"DEMO-M-001");
  assert.match(html,/data-form="pm-work-center-link"/);
  assert.match(html,/name="machine" value="DEMO-M-001"/);
  assert.match(html,/name="center"/);
  assert.match(html,/value="LASER-01"/);
  assert.match(html,/name="confirmed" required/);
  assert.match(html,/not production authorization/);
  assert.match(html,/UNMAPPED/);
  assert.deepEqual(pm,before);
});

test("renderPm association UI displays reviewed mapping and history in same PM state",()=>{
  const pm=reviewLink(seedPm("2026-11-02")).pm;
  const html=renderPm(pm,"DEMO-M-001");
  assert.match(html,/value="LASER-01" selected/);
  assert.match(html,/SYN-REVIEW-LINK-1/);
  assert.match(html,/DEMO-PLANNER/);
  assert.match(html,/Recent association history/);
  assert.match(html,/DEMO REVIEWED/);
});

test("renderPm association UI escapes untrusted legacy association history",()=>{
  const pm=reviewLink(seedPm("2026-11-02")).pm;
  pm.workCenterLinkHistory[0].sourceRef='<img src=x onerror=alert(1)>';
  pm.workCenterLinkHistory[0].reviewedBy='<script>alert(1)</script>';
  const html=renderPm(pm,"DEMO-M-001");
  assert.ok(!html.includes('<img src=x'));
  assert.ok(!html.includes('<script>'));
  assert.match(html,/&lt;img src=x/);
  assert.match(html,/&lt;script&gt;/);
});

test("future first PM association cannot clear an earlier planning window",()=>{
  let pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T07:00:00Z"}).pm;
  pm=reviewLink(pm,"DEMO-M-001","LASER-01",{at:"2026-11-07T08:00:00Z"}).pm;
  const s=scenario(center());s.pmContext={state:pm};
  const r=assessAlternateCenters(job(),"10",s);
  assert.equal(r.assessments[0].pmEvidence.status,"UNMAPPED");
  assert.equal(r.assessments[0].status,"NEEDS_REVIEW");
  assert.equal(r.suggestions.length,0);
});

test("future PM reassignment cannot replace an earlier window mapping",()=>{
  let pm=reviewLink(seedPm("2026-11-02")).pm;
  pm=reviewLink(pm,"DEMO-M-001","PRESS-02",{
    at:"2026-11-07T09:00:00Z",sourceRef:"SYN-FUTURE-REASSIGN"}).pm;
  const s=scenario(center("PRESS-02"));s.pmContext={state:pm};
  const r=assessAlternateCenters(job(),"10",s);
  assert.equal(r.assessments[0].pmEvidence.status,"UNMAPPED");
  assert.equal(r.suggestions.length,0);
  assert.equal(r.canAutoApply,false);
});

test("undated legacy PM association is unknown, not historical clearance",()=>{
  const pm=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T07:00:00Z"}).pm;
  pm.machines[0].workCenterLink={centerId:"LASER-01",sourceRef:"SYN-UNDATED-LINK"};
  const s=scenario(center());s.pmContext={state:pm};
  const r=assessAlternateCenters(job(),"10",s);
  assert.equal(r.assessments[0].pmEvidence.status,"UNMAPPED");
  assert.equal(r.suggestions.length,0);
});

test("offset-aware reviewed PM links match equivalent UTC instants without backdating",()=>{
  const base=completePmTask(seedPm("2026-11-02"),"DEMO-PM-001",
    {checklistConfirmed:true,result:"PASS",at:"2026-11-01T07:00:00Z"}).pm;
  const utc=reviewLink(base,"DEMO-M-001","LASER-01",
    {at:"2026-11-01T08:00:00Z"}).pm;
  const offset=reviewLink(base,"DEMO-M-001","LASER-01",
    {at:"2026-11-01T03:00:00-05:00"}).pm;
  const assessPm=pm=>{
    const s=scenario(center());s.pmContext={state:pm};
    return assessAlternateCenters(job(),"10",s);
  };
  const utcResult=assessPm(utc),offsetResult=assessPm(offset);
  assert.equal(offsetResult.assessments[0].pmEvidence.machineId,"DEMO-M-001");
  assert.deepEqual(offsetResult.assessments[0].pmEvidence,utcResult.assessments[0].pmEvidence);
  assert.equal(offsetResult.assessments[0].pmEvidence.status,"NO_RECORDED_ALERTS");
  assert.equal(offsetResult.suggestions.length,1);
  const future=reviewLink(base,"DEMO-M-001","LASER-01",
    {at:"2026-11-07T03:00:00-05:00"}).pm;
  assert.equal(assessPm(future).assessments[0].pmEvidence.status,"UNMAPPED");
});
