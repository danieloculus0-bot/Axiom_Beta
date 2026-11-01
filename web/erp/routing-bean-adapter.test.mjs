import test from "node:test";
import assert from "node:assert/strict";
import {reviewBeanCoreRoutingProposal as review} from "./routing-bean-adapter.mjs";
const job=()=>({jobNumber:"SYN-ORDER-01",partNumber:"SYN-PART-01",revision:"A",
 routing:{revision:"A",operations:[{step:"10",name:"Sample cut",
 center:"DEMO-CUT",instructions:["Synthetic instructions"],check:"Demo check"}]}});
const binding=j=>({jobNumber:j.jobNumber,partNumber:j.partNumber,revision:j.revision});
const bean=()=>({proposal_id:"proposal_abcdef123456",request_id:"req_abcdef123456",
 response_id:"resp_abcdef123456",proposal_type:"reasoning",status:"pending_review",
 summary:"Consider a different synthetic method.",confidence:0.45,
 observations_json:'["Fictional drawing asserted"]',
 interpretations_json:'["Process option unconfirmed"]',
 assumptions_json:'["Illustrative machine available"]',
 uncertainties_json:'["Cycle time not validated"]',
 evidence_refs_json:'["SYN-DWG-A"]',
 candidate_steps_json:'["Consider another cutting method"]',
 risk_flags_json:"[]"});
test("existing job and BEAN record stay untouched; free text remains advice",()=>{
 const j=job(),row=bean(),before=structuredClone(j);
 const out=review(j,row,binding(j));
 assert.equal(out.status,"ADVISORY_ONLY");
 assert.equal(out.canAutoApply,false);
 assert.equal(out.routingReview,null);
 assert.deepEqual(out.proposal.candidateSteps,["Consider another cutting method"]);
 assert.deepEqual(out.proposal.uncertainties,["Cycle time not validated"]);
 assert.deepEqual(j,before);
});
test("must bind exact job, part, revision",()=>{
 const j=job();
 assert.equal(review(j,bean()).status,"INVALID_SOURCE");
 assert.equal(review(j,bean(),{...binding(j),revision:"B"}).status,"INVALID_SOURCE");
 assert.equal(review({...j,jobNumber:"OTHER"},bean(),binding(j)).status,"INVALID_SOURCE");
});
test("invalid provider record or JSON never looks approved",()=>{
 const j=job(),r=bean();
 r.candidate_steps_json='{"bad":true}';
 assert.equal(review(j,r,binding(j)).status,"INVALID_SOURCE");
 r.candidate_steps_json='["valid"]';r.status="released";
 assert.equal(review(j,r,binding(j)).status,"INVALID_SOURCE");
 r.status="pending_review";r.confidence=NaN;
 assert.equal(review(j,r,binding(j)).status,"INVALID_SOURCE");
});
test("risks and absent references remain explicit",()=>{
 const j=job(),r=bean();
 r.risk_flags_json='["capability_not_checked"]';r.evidence_refs_json="[]";
 const out=review(j,r,binding(j));
 assert.deepEqual(out.proposal.riskFlags,["capability_not_checked"]);
 assert.equal(out.issues.length,2);
 assert.equal(out.status,"ADVISORY_ONLY");
});
test("explicit mapping reuses existing Axiom reviewer and cannot auto-apply",()=>{
 const j=job(),original=structuredClone(j),r=bean();
 const map={partNumber:j.partNumber,revision:j.revision,
  operations:structuredClone(j.routing.operations),
  evidence:[{step:"10",sourceRef:"SYN-DWG-A"}]};
 map.operations[0].name="Alternative fictional cut";
 const out=review(j,r,binding(j),map);
 assert.equal(out.status,"REVIEW_REQUIRED");
 assert.equal(out.routingReview.status,"REVIEW_REQUIRED");
 assert.equal(out.routingReview.changes[0].kind,"MODIFIED");
 assert.equal(out.canAutoApply,false);
 assert.deepEqual(j,original);
});
test("invalid mapping is rejected; no CNC program association required",()=>{
 const j=job(),r=bean(),mapped={partNumber:j.partNumber,
  revision:j.revision,operations:structuredClone(j.routing.operations)};
 assert.equal(review(j,r,binding(j),{...mapped,revision:"B"}).status,"INVALID_MAPPING");
 const out=review(j,r,binding(j),mapped);
 assert.equal(out.status,"REVIEW_REQUIRED");
 assert.equal(out.routingReview.status,"NO_CHANGE");
 assert.deepEqual(out.routingReview.programAssociations,[]);
});
