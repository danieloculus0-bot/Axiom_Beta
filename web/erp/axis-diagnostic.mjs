/* EZ-Ladder v0 synthetic X-axis fault-tracing experiment for Axiom Maintenance.
 * Pure, deterministic, read-only analysis of caller-provided fictional signals.
 * No PLC transport, live BEAN connection, physical output or automatic repair.
 */
import {validatePm, getMachine, requestMaintenance} from './pm.mjs';

const REQUIRED = ['moveRequested','estopHealthy','guardClosed','plcMotionOutput',
  'driveReady','driveFault','stepPulsesSeen'];
const SYNREF = /^SYN-[A-Z0-9-]{1,64}$/;
const clone = value => structuredClone(value);
const finding = (code, explanation, possibleCauses, nextChecks, evidence) => ({
  code, explanation, possibleCauses, nextChecks, evidence,
  confirmedPartFailure: false
});

/** A discrete, ladder-like rung trace, not an IEC 61131 interpreter. */
export function traceAxisPermissives(signals) {
  const permissive = signals.estopHealthy && signals.guardClosed;
  const plcDemand = permissive && signals.moveRequested;
  return [
    {rungId:'SYN-RUNG-01', expression:'ESTOP_HEALTHY AND GUARD_CLOSED',
      result:permissive, observedOutput:signals.plcMotionOutput,
      mismatch:permissive !== signals.plcMotionOutput},
    {rungId:'SYN-RUNG-02', expression:'PERMISSIVE AND MOVE_REQUESTED',
      result:plcDemand, observedOutput:signals.stepPulsesSeen,
      mismatch:plcDemand !== signals.stepPulsesSeen}
  ];
}

export function diagnoseAxis(pm, {machineId,axis,scenarioId,sourceRefs,signals}={}) {
  validatePm(pm);
  if (pm.synthetic!==true) throw Error('Synthetic PM state required');
  const machine=getMachine(pm,machineId);
  if(!machine || !machine.active) throw Error('Active fictional Axiom PM machine required');
  if(axis!=='X') throw Error('This experiment supports only a fictional X axis');
  if(typeof scenarioId!=='string'||!SYNREF.test(scenarioId))
    throw Error('Fictional scenario ID must begin SYN-');
  if(!Array.isArray(sourceRefs)||!sourceRefs.length||sourceRefs.length>12||
     !sourceRefs.every(s=>typeof s==='string'&&SYNREF.test(s)))
    throw Error('Traceable fictional SYN- evidence refs required');
  if(!signals || typeof signals!=='object'||Array.isArray(signals) ||
     REQUIRED.some(k=>typeof signals[k]!=='boolean'))
    throw Error('Complete boolean motion and PLC observations required');
  if(typeof signals.axisDeltaMm!=='number'||!Number.isFinite(signals.axisDeltaMm)||
     signals.axisDeltaMm<0||signals.axisDeltaMm>100000)
    throw Error('Bounded measured axis displacement required');
  for(const name of ['motorCurrentAmps','supplyVoltage']) {
    if(signals[name]!=null&&(!Number.isFinite(signals[name])||signals[name]<0||signals[name]>1000))
      throw Error('Invalid optional electrical reading: '+name);
  }
  if(signals.shaftRotated!=null&&typeof signals.shaftRotated!=='boolean')
    throw Error('Optional shaft motion observation must be boolean or unknown');
  const evidence = [...sourceRefs];
  const rungs=traceAxisPermissives(signals);
  let f;
  if(!signals.moveRequested) {
    f=finding('NO_MOVE_REQUEST','No X-axis move was requested.',
      ['No movement was requested by the simulated operator/program.'],
      ['Verify intended command and selected program.'],evidence);
  } else if(signals.axisDeltaMm>0.05) {
    f=finding('MOTION_OBSERVED','Axis motion was observed; this snapshot does not show a stationary axis.',
      ['Movement may be incomplete; travel target and timing were not supplied.'],
      ['Compare actual movement with the commanded target.'],evidence);
  } else if(!signals.estopHealthy || !signals.guardClosed) {
    f=finding('PERMISSIVE_OPEN','A motion permissive is not satisfied in the synthetic ladder trace.',
      ['Guard or safety-permissive input state','Missing validated permission to move'],
      ['Check the recorded permissive state through approved diagnostics; do not bypass an interlock.'],evidence);
  } else if(!signals.plcMotionOutput) {
    f=finding('PLC_OUTPUT_ABSENT','The motion request exists but the observed PLC motion output is off.',
      ['Program condition or output mapping','Unobserved logic condition'],
      ['Compare the authorized controller program and output state against the fictional rung trace.'],evidence);
  } else if(signals.driveFault || !signals.driveReady) {
    f=finding('DRIVE_NOT_READY','Controller requests motion but the drive reports a fault or not-ready state.',
      ['Drive fault','Drive enable or supply problem'],
      ['Read the actual drive fault code and manufacturer diagnostic guidance.'],evidence);
  } else if(!signals.stepPulsesSeen) {
    f=finding('STEP_SIGNAL_MISSING','Motion output is active but no step pulses were observed.',
      ['Command/drive signal path','Interface configuration or wiring'],
      ['Verify command signal at designated test points using approved service procedures.'],evidence);
  } else if(signals.shaftRotated===true) {
    f=finding('AXIS_TRANSMISSION','Motor shaft motion was observed but the machine axis did not move.',
      ['Coupling or transmission fault','Motion-feedback or load-side mechanical issue'],
      ['Inspect documented coupling and load-side feedback with equipment safely isolated.'],evidence);
  } else if(signals.motorCurrentAmps!=null&&signals.motorCurrentAmps<0.05) {
    f=finding('MOTOR_POWER_PATH','Step pulses were observed but motor current was near zero.',
      ['Drive output not energizing','Motor wiring/connection open','Motor winding fault'],
      ['Review drive output state and measured phase-circuit continuity with approved procedures.'],evidence);
  } else if(signals.motorCurrentAmps!=null&&signals.motorCurrentAmps>=0.05 &&
           signals.shaftRotated===false) {
    f=finding('STALL_OR_BINDING','Pulses and motor current were observed, but neither shaft nor axis motion was observed.',
      ['Mechanical binding','Insufficient drive torque or drive tuning','Motor defect'],
      ['Compare drive alarm history, motor-shaft feedback, and load condition after safe isolation.'],evidence);
  } else {
    f=finding('FEEDBACK_INCOMPLETE','The axis did not move, but available electrical and shaft feedback cannot isolate a cause.',
      ['Motor or drive path','Mechanical load','Missing instrumentation'],
      ['Capture a current reading and independent shaft-motion measurement.'],evidence);
  }
  return {
    schema:1,kind:'axiom.maintenance.axis_diagnostic',synthetic:true,
    machineId,axis,scenarioId,sourceRefs:evidence,
    capturedSignals:clone(signals),rungs,finding:f,
    advisoryOnly:true,canAutoActuate:false,canAutoClearMaintenance:false,
    beanHandoff:{schema:1,kind:'diagnosis_candidate',reviewRequired:true,
      observations:[`X-axis displacement ${signals.axisDeltaMm} mm in synthetic observation`,
        `PLC output ${signals.plcMotionOutput}; pulses seen ${signals.stepPulsesSeen}`],
      interpretation:f.explanation,possibleCauses:[...f.possibleCauses],
      evidenceRefs:evidence,uncertainties:['No actual controller or motor telemetry was retrieved.',
        'Component failure is unconfirmed until independent measurements support it.']}
  };
}

/** Explicit fictional operator review can raise the existing Axiom PM request. */
export function fileReviewedDemoFollowup(pm,diagnosis,{reviewedBy='DEMO-01',at}={}) {
  validatePm(pm);
  if(diagnosis?.kind!=='axiom.maintenance.axis_diagnostic'||
     diagnosis.synthetic!==true||!getMachine(pm,diagnosis.machineId)||
     diagnosis.finding?.code==='NO_MOVE_REQUEST'||diagnosis.finding?.code==='MOTION_OBSERVED')
    throw Error('Eligible reviewed synthetic diagnostic required');
  if(!/^DEMO-[A-Z0-9]{1,16}$/.test(reviewedBy)||
     !at||Number.isNaN(Date.parse(at)))
    throw Error('Explicit synthetic reviewer and timestamp required');
  const outcome=requestMaintenance(pm,diagnosis.machineId,
    'Generic maintenance follow-up','High',reviewedBy,at);
  return {pm:outcome.pm,requestId:outcome.id,sourceScenarioId:diagnosis.scenarioId,
    reviewedBy,advisoryOnly:true,canAutoActuate:false};
}
