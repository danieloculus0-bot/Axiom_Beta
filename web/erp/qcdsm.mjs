/* QCDSM evidence, linked to Axiom's existing ERP, quality and workforce records.
 * Not a causal inference engine. Missing baselines are N/A, not zero.
 */
import {change} from "./engine.mjs";
import {calculateMoraleRisk,DEPARTMENTS} from "./workforce.mjs";
const within30=(date,today)=>{
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(date||"")))return false;
 const delta=Date.parse(today+"T12:00:00Z")-Date.parse(date+"T12:00:00Z");
 return Number.isFinite(delta)&&delta>=0&&delta<31*86400000;
};
export function qcdsmEvidence(erp,workforce,department="Assembly",today=new Date().toISOString().slice(0,10)){
 if(!DEPARTMENTS.includes(department))throw Error("Unknown demo department");
 const pulse=workforce.pulses.filter(p=>p.department===department).at(-1)||null;
 const incidents=(workforce.incidents||[]).filter(x=>x.department===department&&within30(x.observedOn,today));
 const survey=(workforce.safetySurveys||[]).filter(x=>x.department===department).at(-1)||null;
 const recordables=incidents.filter(x=>x.kind==="recordable");
 const nearMisses=incidents.filter(x=>x.kind==="near_miss");
 const firstAid=incidents.filter(x=>x.kind==="first_aid");
 // A bounded ACTION-PRIORITY heuristic, not a regulatory safety rate, sentiment measure or causal finding.
 // Recordable = 70 priority points; near miss = 15; first aid = 10; reported concern fraction = up to 30.
 // Missing event data and missing survey evidence are treated as unknown, not proof of zero risk.
 const safetyPriority=(incidents.length||survey)?
  Math.min(100,recordables.length*70+nearMisses.length*15+firstAid.length*10+
  (survey?30*survey.concerned/survey.respondents:0)):null;
 const overtime=pulse?Number(pulse.overtime_hours||0):null;
 const overtimeLoad=pulse?overtime/Math.max(Number(pulse.scheduled_headcount||0)*40,1):null;
 const possibleFactors=[];
 if(pulse&&overtimeLoad>=.15)possibleFactors.push({key:"OVERTIME",label:"Elevated overtime burden",
  evidence:"Pulse "+pulse.id+" · "+overtime+" OT h / "+pulse.scheduled_headcount+" scheduled"});
 if(pulse&&Number(pulse.over_50_hours_count||0)>0)possibleFactors.push({key:"LONG_HOURS",label:"50+ hour workweeks reported",
  evidence:"Pulse "+pulse.id+" · "+pulse.over_50_hours_count+" aggregate workers"});
 if(pulse&&Number(pulse.staffing_shortage_count||0)>0)possibleFactors.push({key:"STAFFING",label:"Staffing shortages reported",
  evidence:"Pulse "+pulse.id+" · "+pulse.staffing_shortage_count+" shortages"});
 if(recordables.length)possibleFactors.push({key:"RECORDABLE",label:"Recent incident requires safety review",
  evidence:"Synthetic recordable event(s): "+recordables.map(x=>x.id).join(", ")});
 if(survey&&survey.concerned>0)possibleFactors.push({key:"SAFETY_CONFIDENCE",label:"Reported aggregate safety concern",
  evidence:"Survey "+survey.id+" · "+survey.concerned+" of "+survey.respondents+" respondents"});
 const openQuality=erp.quality.filter(q=>q.status==="OPEN").length;
 return {department,pulse,incidents,survey,recordables:recordables.length,nearMisses:nearMisses.length,
  firstAid:firstAid.length,safetyPriority:safetyPriority===null?null:Math.round(safetyPriority*10)/10,
  moraleRisk:pulse?calculateMoraleRisk(pulse):null,overtimeLoad,possibleFactors,
  quality:{openHolds:openQuality,scope:"Plant-wide job-linked NCRs; no department mapping"},
  cost:{value:null,reason:"COPQ baseline not recorded"},delivery:{value:null,reason:"OTD baseline not recorded"}};
}
export function captureQualityContext(erp,workforce,qualityId,department,today=new Date().toISOString().slice(0,10)){
 const record=erp.quality.find(q=>q.id===qualityId);
 if(!record)throw Error("Select an existing quality record");
 const signals=qcdsmEvidence(erp,workforce,department,today);
 const review={
  id:"QCTX-"+((erp.qualityReviews||[]).length+1),
  qualityId,department,recordedOn:today,jobId:record.jobId,
  pulseId:signals.pulse?.id||null,
  safetyEventIds:signals.incidents.map(i=>i.id),safetySurveyId:signals.survey?.id||null,
  moraleRisk:signals.moraleRisk,safetyPriority:signals.safetyPriority,
  possibleFactors:signals.possibleFactors.map(x=>({...x})),
  finding:"REVIEW_REQUIRED",
  note:"Observed indicators are candidate investigation factors only. No cause or employee sentiment inferred."
 };
 return change(erp,"quality.qcdsm.context_captured",record.number+" / "+review.id,n=>{
  if(!Array.isArray(n.qualityReviews))n.qualityReviews=[];
  n.qualityReviews.push(review);
 });
}
export function qualityContextFor(erp,qualityId){
 return (erp.qualityReviews||[]).filter(x=>x.qualityId===qualityId).at(-1)||null;
}
