import test from "node:test";
import assert from "node:assert/strict";
import {EXAMPLES, normalizeRouting, evaluatePacket, startSession, stopSession, durationSeconds, summarize, sessionsCsv} from "./engine.mjs";

test("all built-in jobs are explicitly fictional examples",()=>{
  assert.equal(EXAMPLES.length,2);
  for(const j of EXAMPLES) {
    assert.match(j.jobNumber,/^DEMO-/);
    assert.match(j.partNumber,/^SYN-/);
    assert.match(j.drawing.number,/^SYN-/);
    assert.equal(j.drawing.source,"SYNTHETIC EXAMPLE");
    assert.equal(j.routing.source,"SYNTHETIC EXAMPLE");
  }
});

test("matching fictional drawing and routing allow clocking; mismatched revision blocks",()=>{
  assert.deepEqual(evaluatePacket(EXAMPLES[0]),[]);
  assert.match(evaluatePacket(EXAMPLES[1]).join(" "),/revision/i);
  const conflict=EXAMPLES[1];
  assert.throws(()=>startSession([],{
    id:"a",employee:"DEMO-01",job:conflict,step:"10",timestamp:"2026-01-01T08:00:00Z"
  }),/checks must pass/);
});

test("one running time session per operator, including on a different job",()=>{
  const t1="2026-01-01T08:00:00Z";
  const sessions=startSession([],{
    id:"s1",employee:"DEMO-01",job:EXAMPLES[0],step:"10",timestamp:t1
  });
  assert.equal(sessions.length,1);
  assert.equal(sessions[0].employee,"DEMO-01");
  assert.equal(sessions[0].end,null);
  assert.throws(()=>startSession(sessions,{
    id:"s2",employee:"demo-01",job:EXAMPLES[0],step:"20",timestamp:t1
  }),/already clocked in/);
  assert.throws(()=>startSession(sessions,{
    id:"s1",employee:"DEMO-02",job:EXAMPLES[0],step:"20",timestamp:t1
  }),/Duplicate clock/);
  assert.throws(()=>startSession(sessions,{
    id:"s3",employee:"DEMO-02",job:EXAMPLES[0],step:"99",timestamp:t1
  }),/does not exist/);
  assert.deepEqual(summarize(sessions,Date.parse("2026-01-01T09:00:00Z")),{
    total:1,active:1,completed:0,completedSeconds:0
  });
});

test("clock out validates operator, creates duration, and allows next operation",()=>{
  const a=startSession([],{
    id:"s1",employee:"DEMO-01",job:EXAMPLES[0],step:"10",timestamp:"2026-01-01T08:00:00Z"
  });
  assert.throws(()=>stopSession(a,{
    id:"s1",employee:"OTHER",timestamp:"2026-01-01T08:30:00Z"
  }),/does not match/);
  assert.throws(()=>stopSession(a,{
    id:"s1",employee:"DEMO-01",timestamp:"2026-01-01T07:59:59Z"
  }),/cannot precede/);
  const ended=stopSession(a,{
    id:"s1",employee:"DEMO-01",timestamp:"2026-01-01T08:30:03Z"
  });
  assert.equal(durationSeconds(ended[0]),1803);
  assert.equal(summarize(ended).completedSeconds,1803);
  assert.throws(()=>stopSession(ended,{
    id:"s1",employee:"DEMO-01",timestamp:"2026-01-01T08:33:00Z"
  }),/not found/);
  const next=startSession(ended,{
    id:"s2",employee:"DEMO-01",job:EXAMPLES[0],step:"20",timestamp:"2026-01-01T08:31:00Z"
  });
  assert.equal(next.length,2);
  assert.equal(summarize(next).active,1);
});

test("CSV contains true timestamps and explicit no-ERP status",()=>{
  const sessions=stopSession(startSession([],{
    id:"s1",employee:"DEMO-01",job:EXAMPLES[0],step:"10",timestamp:"2026-01-01T08:00:00Z"
  }),{id:"s1",employee:"DEMO-01",timestamp:"2026-01-01T08:00:35Z"});
  const csv=sessionsCsv(sessions);
  assert.match(csv,/s1/);
  assert.match(csv,/2026-01-01T08:00:00.000Z/);
  assert.match(csv,/2026-01-01T08:00:35.000Z/);
  assert.match(csv,/35/);
  assert.match(csv,/LOCAL_ONLY_NOT_ERP_SYNCED/);
});

test("route parser rejects missing steps, duplicate steps and empty instructions",()=>{
  const good={
    jobNumber:"DEMO-100",partNumber:"SYN-1",revision:"A",
    operations:[{step:10,name:"Cut",center:"WC-1",instructions:["Inspect first piece"]}]
  };
  const parsed=normalizeRouting(good);
  assert.equal(parsed.operations[0].step,"10");
  assert.throws(()=>normalizeRouting({...good,operations:[good.operations[0],good.operations[0]]}),/Duplicate routed step/);
  assert.throws(()=>normalizeRouting({...good,operations:[]}),/1 to 60/);
  assert.throws(()=>normalizeRouting({...good,operations:[{...good.operations[0],instructions:[]}]}),/instructions must have/);
});
