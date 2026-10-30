import test from "node:test";
import assert from "node:assert/strict";
import {
 seedWorkforce,validateWorkforce,calculateMoraleRisk,addDemoPerson,assignDemoRole,
 recordDemoPulse,completeDemoTraining,nominateDemoRecognition,reviewDemoNomination,
 closeDemoAction,demoBalance,ROLES,DEPARTMENTS
} from "./workforce.mjs";
import {renderHr,renderMorale} from "./workforce-view.mjs";

test("morale risk retains existing SuperForge aggregate weighting and bounding",()=>{
 assert.equal(calculateMoraleRisk({}),0);
 const example={scheduled_headcount:20,present_headcount:16,overtime_hours:160,
  over_50_hours_count:6,exhausted_pto_count:4,pto_absence_count:3,
  sick_absence_clusters:4,turnover_count:2,staffing_shortage_count:4,quality_risk_signal:70};
 assert.equal(calculateMoraleRisk(example),98.5);
 assert.equal(calculateMoraleRisk({...example,pto_absence_count:15}),98.5);
 assert.equal(calculateMoraleRisk({scheduled_headcount:10,present_headcount:0,
  overtime_hours:10000,turnover_count:100,staffing_shortage_count:100,quality_risk_signal:500}),70);
});
test("seeded workforce uses only demo codes and generic roles",()=>{
 const s=seedWorkforce();
 assert.equal(validateWorkforce(s),s);
 assert.equal(s.demo,true);
 assert.ok(s.people.every(p=>/^DEMO-\d+$/.test(p.id)));
 assert.ok(s.people.every(p=>ROLES.some(r=>r.id===p.role)));
 assert.ok(DEPARTMENTS.includes(s.pulses[0].department));
 assert.throws(()=>validateWorkforce({}),/Invalid/);
});
test("HR roster and role changes are functional and nonmutating",()=>{
 const initial=seedWorkforce();
 const added=addDemoPerson(initial,"machinist");
 assert.equal(added.people.length,initial.people.length+1);
 assert.equal(added.people.at(-1).id,"DEMO-06");
 const changed=assignDemoRole(added,"DEMO-06","inspector");
 assert.equal(changed.people.at(-1).role,"inspector");
 assert.equal(added.people.at(-1).role,"machinist");
 assert.throws(()=>addDemoPerson(initial,"invented-admin"),/role/);
});
test("verified demo training generates a one-time positive ledger credit",()=>{
 const initial=seedWorkforce();
 const next=completeDemoTraining(initial,"DEMO-01","TR-01");
 assert.equal(next.completions.length,1);
 assert.equal(demoBalance(next,"DEMO-01"),10);
 assert.equal(demoBalance(initial,"DEMO-01"),0);
 assert.throws(()=>completeDemoTraining(next,"DEMO-01","TR-01"),/already recorded/);
});
test("recognition requires explicit review and rejects duplicate approvals",()=>{
 const initial=seedWorkforce();
 const nominated=nominateDemoRecognition(initial,"DEMO-02","quality","First-pass quality",5);
 assert.equal(demoBalance(nominated,"DEMO-02"),0);
 const approved=reviewDemoNomination(nominated,"N-1","APPROVED");
 assert.equal(demoBalance(approved,"DEMO-02"),5);
 assert.throws(()=>reviewDemoNomination(approved,"N-1","APPROVED"),/not pending/);
 const other=nominateDemoRecognition(approved,"DEMO-02","safety","Safety improvement",7);
 const rejected=reviewDemoNomination(other,"N-2","REJECTED");
 assert.equal(demoBalance(rejected,"DEMO-02"),5);
 assert.throws(()=>nominateDemoRecognition(initial,"DEMO-02","quality","Random user text",5),/options/);
});
test("high aggregate pulse opens a review action that can be closed",()=>{
 const raw={department:"Machining",scheduled_headcount:20,present_headcount:16,
  overtime_hours:160,over_50_hours_count:6,exhausted_pto_count:4,
  pto_absence_count:3,sick_absence_clusters:4,turnover_count:2,
  staffing_shortage_count:4,quality_risk_signal:70};
 const initial=seedWorkforce();
 const result=recordDemoPulse(initial,raw);
 assert.equal(result.pulses.at(-1).risk_score,98.5);
 assert.equal(result.actions.length,1);
 assert.equal(result.actions[0].status,"OPEN");
 const reviewed=closeDemoAction(result,result.actions[0].id);
 assert.equal(reviewed.actions[0].status,"COMPLETED");
 assert.throws(()=>closeDemoAction(reviewed,result.actions[0].id),/not found/);
 assert.throws(()=>recordDemoPulse(initial,{...raw,present_headcount:21}),/cannot exceed/);
 assert.throws(()=>recordDemoPulse(initial,{...raw,department:"REAL COMPANY"}),/generic department/);
});
test("both public screens render usable forms with clear non-production boundaries",()=>{
 const s=seedWorkforce();
 const hr=renderHr(s),morale=renderMorale(s);
 for(const token of ['data-form="hr-person"','data-form="hr-role"','data-form="hr-training"','No names, emails'])
  assert.ok(hr.includes(token),token);
 for(const token of ['data-form="morale-pulse"','data-form="morale-nominate"','No real identities','No monetary conversion'])
  assert.ok(morale.includes(token),token);
 assert.ok(!hr.includes("EZ Fabricating")&&!morale.includes("WMF"));
});
