import test from 'node:test';
import assert from 'node:assert/strict';
import {seedPm} from './pm.mjs';
import {diagnoseAxis,fileReviewedDemoFollowup} from './axis-diagnostic.mjs';
const pm=seedPm('2026-11-01');
const defaultSignals={moveRequested:true,estopHealthy:true,guardClosed:true,
  plcMotionOutput:true,driveReady:true,driveFault:false,stepPulsesSeen:true,
  supplyVoltage:24,motorCurrentAmps:2.1,shaftRotated:false,axisDeltaMm:0};
const run=(overrides={})=>diagnoseAxis(pm,{machineId:'DEMO-M-001',axis:'X',
  scenarioId:'SYN-X-AXIS-001',sourceRefs:['SYN-PLC-TRACE-01','SYN-DRIVE-TRACE-01'],
  signals:{...defaultSignals,...overrides}});
test('synthetic stopped stepper narrows fault without claiming a broken motor',()=>{
  const d=run();
  assert.equal(d.finding.code,'STALL_OR_BINDING');
  assert.equal(d.finding.confirmedPartFailure,false);
  assert.ok(d.finding.possibleCauses.includes('Mechanical binding'));
  assert.ok(d.finding.possibleCauses.includes('Motor defect'));
  assert.equal(d.canAutoActuate,false);
  assert.equal(d.beanHandoff.reviewRequired,true);
  assert.equal(d.rungs.length,2);
  assert.equal(pm.requests.length,0);
});
test('missing permissive is not misdiagnosed as a dead motor',()=>{
  const d=run({guardClosed:false,plcMotionOutput:false,stepPulsesSeen:false,motorCurrentAmps:0});
  assert.equal(d.finding.code,'PERMISSIVE_OPEN');
  assert.equal(d.rungs[0].result,false);
});
test('missing PLC output, drive fault, step pulses, power and coupling are distinct',()=>{
  assert.equal(run({plcMotionOutput:false,stepPulsesSeen:false}).finding.code,'PLC_OUTPUT_ABSENT');
  assert.equal(run({driveFault:true,driveReady:false}).finding.code,'DRIVE_NOT_READY');
  assert.equal(run({stepPulsesSeen:false}).finding.code,'STEP_SIGNAL_MISSING');
  assert.equal(run({motorCurrentAmps:0}).finding.code,'MOTOR_POWER_PATH');
  assert.equal(run({shaftRotated:true}).finding.code,'AXIS_TRANSMISSION');
});
test('unknown current and shaft feedback result in abstention',()=>{
  assert.equal(run({motorCurrentAmps:null,shaftRotated:null}).finding.code,'FEEDBACK_INCOMPLETE');
});
test('only explicit review creates one existing Axiom PM maintenance request',()=>{
  const d=run();
  const submitted=fileReviewedDemoFollowup(pm,d,{reviewedBy:'DEMO-01',at:'2026-11-01T22:00:00Z'});
  assert.equal(submitted.pm.requests.length,1);
  assert.equal(submitted.pm.requests[0].machineId,'DEMO-M-001');
  assert.equal(submitted.pm.requests[0].status,'OPEN');
  assert.equal(submitted.pm.requests[0].priority,'High');
  assert.equal(pm.requests.length,0);
  assert.equal(submitted.canAutoActuate,false);
});
test('reject unsourced, real or malformed input',()=>{
  assert.throws(()=>diagnoseAxis({...pm,synthetic:false},{machineId:'DEMO-M-001',axis:'X'}));
  assert.throws(()=>run({axisDeltaMm:-1}));
  assert.throws(()=>run({shaftRotated:'false'}));
  assert.throws(()=>diagnoseAxis(pm,{machineId:'DEMO-M-001',axis:'X',
    scenarioId:'SYN-X-1',sourceRefs:[],signals:defaultSignals}));
});
