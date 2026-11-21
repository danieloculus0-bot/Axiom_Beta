/* Synthetic BEAN-facing nesting decision environment.
 * No live BEAN, manufacturing data, controller, or automatic job approval.
 * Actions constrain permitted rotations; the existing geometry engine independently
 * searches placements and verifies collisions. Agent-reported scores are ignored.
 */
import {solveNest,verifyNest} from "./autonest-engine.mjs";

const invalid=reason=>({schema:"axiom.autonest.challenge.v1",status:"INVALID_ACTION",
  accepted:false,reason,beanConnected:false});
const score=result=>({placed:result.placed,requested:result.requested,
  sheets:result.sheets.length,unplaced:result.unplaced.length,
  utilization:result.utilization,verified:verifyNest(result).ok});
/** Evaluate an agent's rotation policy against an unmodified synthetic baseline.
 * Each action must explicitly name every part and choose a nonempty subset of
 * the original allowed rotations. No geometry, stock, or scoring can be changed.
 */
export function evaluateNestDecision(challenge,action){
  if(!challenge||!Array.isArray(challenge.parts)||!challenge.parts.length)
    return invalid("A challenge with parts is required.");
  if(!action||typeof action!=="object"||Array.isArray(action)||
     !action.rotations||typeof action.rotations!=="object"||
     Array.isArray(action.rotations))
    return invalid("A rotations map is required.");
  const ids=challenge.parts.map(p=>p.id);
  if(ids.some(id=>typeof id!=="string")||new Set(ids).size!==ids.length||
     Object.keys(action.rotations).length!==ids.length||
     Object.keys(action.rotations).some(id=>!ids.includes(id)))
    return invalid("Rotation policy must name each original part exactly once.");
  const parts=[];
  for(const part of challenge.parts){
    const permitted=part.rotations??[0,90,180,270];
    const chosen=action.rotations[part.id];
    if(!Array.isArray(chosen)||chosen.length===0||chosen.length>24||
       !chosen.every(a=>typeof a==="number"&&Number.isFinite(a)&&permitted.includes(a))||
       new Set(chosen).size!==chosen.length)
      return invalid("Rotation choices must be unique and within the original policy for "+part.id+".");
    parts.push({...part,rotations:[...chosen]});
  }
  try{
    const baseline=solveNest(challenge);
    const candidate=solveNest({...challenge,parts});
    const baselineReview=verifyNest(baseline),candidateReview=verifyNest(candidate);
    if(!baselineReview.ok||!candidateReview.ok)
      return invalid("Independent geometry verification failed.");
    const before=score(baseline),after=score(candidate);
    return {schema:"axiom.autonest.challenge.v1",status:"EVALUATED",
      accepted:true,beanConnected:false,action:{rotations:Object.fromEntries(parts.map(p=>[p.id,p.rotations]))},
      baseline:before,candidate:after,
      delta:{placed:after.placed-before.placed,sheets:after.sheets-before.sheets,
        utilization:Math.round((after.utilization-before.utilization)*1e6)/1e6},
      improved:after.placed>before.placed||
        (after.placed===before.placed&&after.sheets<before.sheets),
      evidence:{baselineStrategy:baseline.strategy,candidateStrategy:candidate.strategy,
        baselineVerification:baselineReview,candidateVerification:candidateReview},
      limitations:["Synthetic geometric nesting only; no live BEAN model, machine verification or production approval."]};
  }catch(error){
    return invalid("Invalid challenge geometry or configuration: "+String(error.message));
  }
}
