import test from "node:test";
import assert from "node:assert/strict";
import {reviewRoutingCandidate} from "./routing-advice.mjs";

const job = () => ({partNumber:"SYN-PLATE-01",revision:"A",routing:{revision:"A",operations:[
  {step:"10",name:"Cut fictional blank",center:"DEMO-CUT",instructions:["Use synthetic drawing."],check:"Check outline."},
  {step:"20",name:"Inspect fictional blank",center:"DEMO-QC",instructions:["Measure sample."],check:"Record result."}
]}});
const candidate = j => ({partNumber:j.partNumber,revision:j.revision,
  operations:structuredClone(j.routing.operations),evidence:[]});

test("unchanged candidate is read-only and does not require an optional program",()=>{
  const j=job(),snapshot=structuredClone(j),p=candidate(j);
  const r=reviewRoutingCandidate(j,p);
  assert.equal(r.status,"NO_CHANGE");
  assert.equal(r.canAutoApply,false);
  assert.deepEqual(r.changes,[]);
  assert.deepEqual(r.programAssociations,[]);
  assert.deepEqual(j,snapshot);
});
test("changed operation with asserted source remains review-only",()=>{
  const j=job(),p=candidate(j);
  p.operations[0].name="Alternate fictional cut";
  p.evidence=[{step:"10",sourceRef:"SYN-DWG-01:rev-A:sheet-1"}];
  const r=reviewRoutingCandidate(j,p);
  assert.equal(r.status,"REVIEW_REQUIRED");
  assert.equal(r.changes[0].kind,"MODIFIED");
  assert.deepEqual(r.changes[0].evidenceRefs,["SYN-DWG-01:rev-A:sheet-1"]);
  assert.equal(j.routing.operations[0].name,"Cut fictional blank");
});
test("missing evidence on added, removed or reordered steps is explicit",()=>{
  const j=job(),p=candidate(j);
  p.operations.reverse();
  let r=reviewRoutingCandidate(j,p);
  assert.equal(r.status,"NEEDS_EVIDENCE");
  assert.equal(r.changes.filter(x=>x.kind==="REORDERED").length,2);
  p.operations=[{step:"30",name:"Sample",center:"DEMO-CUT",instructions:["Example"],check:"Sample"}];
  r=reviewRoutingCandidate(j,p);
  assert.equal(r.status,"NEEDS_EVIDENCE");
  assert.deepEqual(r.changes.map(x=>x.kind),["ADDED","REMOVED","REMOVED"]);
});
test("wrong part or revision and invalid operations cannot be recommended",()=>{
  const j=job(),p=candidate(j);
  p.revision="B";
  assert.equal(reviewRoutingCandidate(j,p).status,"INVALID");
  p.revision="A";p.operations[1].step="10";
  assert.equal(reviewRoutingCandidate(j,p).status,"INVALID");
  p.operations=[];
  assert.equal(reviewRoutingCandidate(j,p).status,"INVALID");
  j.routing.revision="C";
  assert.equal(reviewRoutingCandidate(j,candidate(j)).status,"INVALID");
});
test("changed work center is flagged even with a citation",()=>{
  const j=job(),p=candidate(j);
  p.operations[0].center="DEMO-MILL";
  p.evidence=[{step:"10",sourceRef:"SYN-CAPABILITY-CARD"}];
  const r=reviewRoutingCandidate(j,p);
  assert.equal(r.status,"REVIEW_REQUIRED");
  assert.equal(r.changes[0].capabilityUnverified,true);
  assert.match(r.issues.join(" "),/independent capability verification/);
});
test("optional program association never proves capacity or permits release",()=>{
  const j=job(),p=candidate(j);
  p.programLinks=[{step:"10",partNumber:j.partNumber,revision:"A",center:"DEMO-CUT",
    programId:"SYN-PROG-001",sourceRef:"SYN-REGISTER-01",cycleSeconds:12,verified:true}];
  let r=reviewRoutingCandidate(j,p);
  assert.equal(r.status,"NO_CHANGE");
  assert.equal(r.programAssociations[0].status,"ASSERTED_REFERENCE_ONLY");
  assert.equal(r.canAutoApply,false);
  p.programLinks[0].revision="Z";
  r=reviewRoutingCandidate(j,p);
  assert.equal(r.programAssociations[0].status,"MISMATCH_OR_INCOMPLETE");
  assert.match(r.issues.join(" "),/do not match/);
});
test("malformed or absent optional associations cannot crash assessment",()=>{
  const j=job(),p=candidate(j);
  p.programLinks=[null,{}, {step:"10",programId:"SYN-PROG-001"}];
  const r=reviewRoutingCandidate(j,p);
  assert.equal(r.programAssociations.length,3);
  assert.ok(r.programAssociations.every(x=>x.status==="MISMATCH_OR_INCOMPLETE"));
});
