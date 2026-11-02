/* Run: node web/erp/axis-diagnostic-demo.mjs
 * All machine names, signals and records are deliberately fictional.
 */
import {seedPm} from './pm.mjs';
import {diagnoseAxis,fileReviewedDemoFollowup} from './axis-diagnostic.mjs';
const pm=seedPm('2026-11-01');
const result=diagnoseAxis(pm,{
  machineId:'DEMO-M-001',axis:'X',
  scenarioId:'SYN-X-AXIS-001',
  sourceRefs:['SYN-PLC-TRACE-01','SYN-DRIVE-TRACE-01'],
  signals:{moveRequested:true,estopHealthy:true,guardClosed:true,
    plcMotionOutput:true,driveReady:true,driveFault:false,
    stepPulsesSeen:true,supplyVoltage:24,motorCurrentAmps:2.1,
    shaftRotated:false,axisDeltaMm:0}
});
const filed=fileReviewedDemoFollowup(pm,result,{
  reviewedBy:'DEMO-01',at:'2026-11-01T22:00:00Z'
});
console.log(JSON.stringify({
  scenario:result.scenarioId,machine:pm.machines.find(x=>x.id===result.machineId).name,
  rungTrace:result.rungs,
  result:result.finding,
  originalRequests:pm.requests.length,
  reviewedDemoRequest:{id:filed.requestId,open:filed.pm.requests[0].status==='OPEN'},
  beanEvidenceCandidate:result.beanHandoff,
  advisoryOnly:result.advisoryOnly,canAutoActuate:result.canAutoActuate,
  note:'Simulated signals. No PLC connected; BEAN handoff is an envelope, not a live integration.'
},null,2));
