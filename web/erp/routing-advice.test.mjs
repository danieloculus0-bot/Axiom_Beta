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

test("insert/remove do not flag untouched steps as REORDERED",()=>{
 const j=job(),p=candidate(j),extra={step:"15",name:"Synthetic step",center:"DEMO-CUT",instructions:["Synthetic"],check:"Example"};
 p.operations.splice(1,0,extra);p.evidence=[{step:"15",sourceRef:"SYN-ADD"}];
 let v=reviewRoutingCandidate(j,p);
 assert.equal(v.status,"REVIEW_REQUIRED");assert.deepEqual(v.changes.map(x=>[x.step,x.kind]),[["15","ADDED"]]);
 j.routing.operations.splice(1,0,extra);
 const removal=candidate(j);removal.operations.splice(1,1);removal.evidence=[{step:"15",sourceRef:"SYN-REMOVE"}];
 v=reviewRoutingCandidate(j,removal);
 assert.equal(v.status,"REVIEW_REQUIRED");assert.deepEqual(v.changes.map(x=>[x.step,x.kind]),[["15","REMOVED"]]);
});
test("true swap remains a reorder requiring step-specific evidence",()=>{
 const j=job(),p=candidate(j);p.operations.reverse();
 p.evidence=[{step:"10",sourceRef:"SYN-10"},{step:"20",sourceRef:"SYN-20"}];
 const v=reviewRoutingCandidate(j,p);
 assert.equal(v.status,"REVIEW_REQUIRED");
 assert.deepEqual(v.changes.map(x=>[x.step,x.kind]),[["20","REORDERED"],["10","REORDERED"]]);
});
test("unchanged operation program cannot support a different changed operation",()=>{
 const j=job(),p=candidate(j);p.operations[0].center="LASER-01";
 p.evidence=[{step:"10",sourceRef:"SYN-CHANGE"}];
 p.programLinks=[{step:"20",partNumber:j.partNumber,revision:"A",center:"DEMO-QC",programId:"SYN-PROG-20",sourceRef:"SYN-REF-20"}];
 let v=reviewRoutingCandidate(j,p);
 assert.equal(v.programAssociations[0].status,"MISMATCH_OR_INCOMPLETE");
 assert.match(v.issues.join(" "),/do not match/);
 p.programLinks=[{step:"10",partNumber:j.partNumber,revision:"A",center:"LASER-01",programId:"SYN-PROG-10",sourceRef:"SYN-REF-10"}];
 v=reviewRoutingCandidate(j,p);
 assert.equal(v.programAssociations[0].status,"ASSERTED_REFERENCE_ONLY");
 assert.equal(v.canAutoApply,false);
});
