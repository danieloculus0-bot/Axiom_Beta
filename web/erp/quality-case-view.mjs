/* One job-linked fictional quality case, using existing ERP context and events. */
import {QUALITY_DISPOSITIONS,QUALITY_INSPECTION_STAGES,QUALITY_INSPECTION_RESULTS,QUALITY_ACTION_ROLES,QUALITY_EFFECTIVENESS_RESULTS} from "./quality-case.mjs";
import {qualityCaseTimeline} from "./quality-timeline.mjs";
const h=value=>String(value??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
})[c]);
/* Resolve evidence from this canonical fictional NCR before offering a jump. */
export function qualityEvidenceTarget(record,kind,id){
  if(!record||typeof record!=="object"||typeof id!=="string"||!id)return null;
  const inspections=Array.isArray(record.inspections)?record.inspections:[];
  const actions=Array.isArray(record.correctiveActions)?record.correctiveActions:[];
  if(kind==="disposition"&&id===record.id&&typeof record.disposition?.decision==="string"&&
     record.disposition.decision)return {kind,id};
  if(kind==="inspection"&&inspections.some(item=>item?.id===id))return {kind,id};
  if(kind==="followup"&&Array.isArray(record.followUps)&&
     record.followUps.some(item=>item?.id===id))return {kind,id};
  if(kind==="corrective"&&actions.some(item=>item?.id===id))return {kind,id};
  if(kind==="effectiveness"&&actions.some(action=>
    Array.isArray(action?.reviews)&&action.reviews.some(review=>review?.id===id)))return {kind,id};
  return null;
}
/* A work-order jump must originate from evidence on this exact canonical NCR.
 * Never offer a generic or unrelated job when the evidence/job is missing.
 */
export function qualityEvidenceWorkOrderTarget(state,caseId,kind,id){
  if(!Array.isArray(state?.quality)||!Array.isArray(state?.jobs))return null;
  const record=state.quality.find(item=>item?.id===caseId);
  if(!qualityEvidenceTarget(record,kind,id))return null;
  const job=state.jobs.find(item=>item?.id===record.jobId);
  return job?{caseId:record.id,kind,id,jobId:job.id}:null;
}
/* Return navigation is valid only for the original evidence and its canonical job.
 * This is an in-memory UI route, not a second NCR or work-order record.
 */
export function qualityEvidenceReturnTarget(state,selection,jobId){
  if(!selection||typeof selection!=="object")return null;
  const target=qualityEvidenceWorkOrderTarget(state,selection.caseId,selection.kind,selection.id);
  return target?.jobId===jobId?target:null;
}
export function qualityEvidenceReturnAction(state,selection,jobId){
  const target=qualityEvidenceReturnTarget(state,selection,jobId);
  return target?'<div class="notice">This fictional work order was opened from linked NCR evidence. '+
    '<button type="button" class="action secondary" data-action="quality-evidence-return" data-case="'+
    h(target.caseId)+'" data-kind="'+h(target.kind)+'" data-id="'+h(target.id)+
    '">Return to NCR evidence</button></div>':"";
}
/* Link only to the current, matching routed operation for this inspection.
 * Historical evidence remains readable when a routing or revision has changed.
 */
/* Explain why a historical observation cannot open a CURRENT routing step.
 * This is a read-only projection, not an inference about why a route changed.
 */
export function qualityInspectionRoutingStatus(state,caseId,inspectionId){
  if(!Array.isArray(state?.quality)||!Array.isArray(state?.jobs))return null;
  const record=state.quality.find(item=>item?.id===caseId);
  const inspection=(Array.isArray(record?.inspections)?record.inspections:[])
    .find(item=>item?.id===inspectionId&&typeof inspectionId==="string"&&inspectionId.length>0);
  if(!inspection)return null;
  const unavailable=reason=>({target:null,reason});
  const job=state.jobs.find(item=>item?.id===record?.jobId);
  if(!job)return unavailable("Linked fictional work order is unavailable.");
  if(typeof inspection.jobRevision!=="string"||!inspection.jobRevision||
     typeof inspection.drawingRevision!=="string"||!inspection.drawingRevision)
    return unavailable("Recorded revision evidence is incomplete.");
  if(inspection.jobRevision!==job.revision)
    return unavailable("Recorded job revision differs from the current work order.");
  if(inspection.drawingRevision!==job.drawing?.revision)
    return unavailable("Recorded drawing revision differs from the current drawing.");
  const operation=job.routing?.operations?.find(op=>String(op.step)===String(inspection.step));
  if(!operation)return unavailable("Recorded step is absent from the current routing.");
  if(!inspection.operation||!inspection.center)
    return unavailable("Recorded operation details are incomplete.");
  if(inspection.operation!==operation.name||inspection.center!==operation.center)
    return unavailable("Recorded operation or work center differs from the current routing.");
  return {target:{caseId:record.id,inspectionId:inspection.id,jobId:job.id,step:String(operation.step)},reason:null};
}
export function qualityInspectionRoutingTarget(state,caseId,inspectionId){
  return qualityInspectionRoutingStatus(state,caseId,inspectionId)?.target??null;
}
const evidenceAttrs=(kind,id)=>typeof id==="string"&&id?
  ' data-evidence-kind="'+h(kind)+'" data-evidence-id="'+h(id)+'"':"";
const evidenceButton=(record,kind,id,label)=>{
  const target=qualityEvidenceTarget(record,kind,id);
  return target?'<button type="button" class="action secondary" data-action="quality-evidence-focus" data-case="'+
    h(record.id)+'" data-kind="'+h(target.kind)+'" data-id="'+h(target.id)+'">'+h(label)+'</button>':"";
};
const evidenceWorkOrderButton=(state,record,kind,id)=>{
  const target=qualityEvidenceWorkOrderTarget(state,record?.id,kind,id);
  return target?'<button type="button" class="action secondary" data-action="quality-evidence-work-order" data-case="'+
    h(target.caseId)+'" data-kind="'+h(target.kind)+'" data-id="'+h(target.id)+'">Open linked work order</button>':"";
};
const routingStepButton=(state,record,inspection)=>{
  const status=qualityInspectionRoutingStatus(state,record?.id,inspection?.id);
  const target=status?.target;
  if(target)return '<button type="button" class="action secondary" data-action="quality-routing-step" data-case="'+
    h(target.caseId)+'" data-id="'+h(target.inspectionId)+'">Open routed step '+h(target.step)+'</button>';
  return status?.reason?'<span class="small" role="note">Historical route: '+
    h(status.reason)+' Current step link unavailable.</span>':"";
};
/* Compact, read-only evidence projection for a real fictional NCR.
 * Reuses the same chronology shown in the case itself, not a second store.
 */
export function qualityCaseEvidenceSummary(record){
  const entries=qualityCaseTimeline(record);
  const inspections=entries.filter(entry=>entry.kind==="inspection").length;
  const correctiveActions=entries.filter(entry=>entry.kind==="corrective").length;
  const effectiveness=entries.filter(entry=>entry.kind==="effectiveness").at(-1);
  return {inspections,correctiveActions,
    latestEffectiveness:effectiveness?effectiveness.title.replace(/^Effectiveness: /,""):
      (correctiveActions?"NOT REVIEWED":"NO ACTION")};
}
/* Direct links preserve the exact NCR identity, including closed cases.
 * No links are offered for a job without linked quality records.
 */
export function renderJobQualityEvidence(state,jobId){
  const cases=state.quality.filter(record=>record.jobId===jobId);
  if(!cases.length)return '<p class="small muted">No fictional NCR evidence for this work order.</p>';
  return '<div class="quality-evidence-index">'+cases.map(record=>{
    const evidence=qualityCaseEvidenceSummary(record);
    return '<div class="receipt"><button type="button" class="action secondary" '+
      'data-action="report-quality-case" data-id="'+h(record.id)+'">Open '+h(record.number)+'</button> '+
      '<span class="small">'+h(record.status)+' · '+h(evidence.inspections)+' inspections · '+
      h(evidence.correctiveActions)+' corrective actions · effectiveness: '+
      h(evidence.latestEffectiveness)+'</span></div>';
  }).join("")+'</div>';
}
export function renderQualityCase(state,id){
  const q=state.quality.find(record=>record.id===id);
  if(!q)return '<section class="panel" id="quality-case-detail"><h2>Case review</h2><p class="small">Select a fictional nonconformance above to review its linked record.</p></section>';
  const j=state.jobs.find(job=>job.id===q.jobId);
  const links=j?'<a class="action secondary" href="#jobs" data-job="'+h(j.id)+'">Work order</a> '+
    '<a class="action secondary" href="#routing" data-job="'+h(j.id)+'">Routing</a> '+
    '<a class="action secondary" href="#documents" data-job="'+h(j.id)+'">Drawing</a> '+
    '<a class="action secondary" href="#ewi" data-job="'+h(j.id)+'">EWI / hold</a>':"";
  const disp=q.disposition;
  const timeline=qualityCaseTimeline(q);
  const inspections=Array.isArray(q.inspections)?q.inspections:[];
  const actions=Array.isArray(q.correctiveActions)?q.correctiveActions:[];
  const followups=Array.isArray(q.followUps)?q.followUps:[];
  const operations=Array.isArray(j?.routing?.operations)?j.routing.operations:[];
  let html='<section class="panel" id="quality-case-detail" data-case-id="'+h(q.id)+'"><div class="panel-head"><h2 class="context-record" data-ctx-type="quality" data-ctx-id="'+h(q.id)+'" tabindex="0" title="Right-click for Open with">Quality Forge case · '+h(q.number)+'</h2><span class="tag">'+h(q.status)+'</span></div>'+
    '<p class="small">Linked work order: <b>'+h(j?.jobNumber||"Missing fictional job")+'</b> · '+h(q.reason)+
    '. Browser-local demonstration only. No production disposition or release authority.</p>'+
    '<div class="controls">'+links+'</div>'+
    '<div class="receipt"'+(disp?evidenceAttrs("disposition",q.id):"")+'> <b>Recorded fictional disposition:</b> '+
    (disp?h(QUALITY_DISPOSITIONS.find(item=>item.id===disp.decision)?.label||disp.decision)+
      ' · '+h(disp.note)+' · '+h(disp.recordedAt):"Not recorded. Case remains on hold.")+
    (disp?evidenceWorkOrderButton(state,q,"disposition",q.id):"")+'</div>';
  if(q.status==="OPEN"&&operations.length){
    html+='<h3>Fictional inspection observation</h3>'+
      '<p class="small">Record an illustrative check on a routed operation. PASS does not release a job, close a case or certify inspection.</p>'+
      '<form class="controls" data-form="quality-inspection">'+
      '<input type="hidden" name="id" value="'+h(q.id)+'">'+
      '<label>Check stage<select name="stage">'+QUALITY_INSPECTION_STAGES.map(item=>
        '<option value="'+h(item.id)+'">'+h(item.label)+'</option>').join("")+'</select></label>'+
      '<label>Routed operation<select name="step">'+operations.map(op=>
        '<option value="'+h(op.step)+'">'+h(op.step)+' · '+h(op.name)+' ('+h(op.center)+')</option>').join("")+'</select></label>'+
      '<label>Observation result<select name="result">'+QUALITY_INSPECTION_RESULTS.map(result=>
        '<option value="'+h(result)+'">'+h(result.replaceAll("_"," "))+'</option>').join("")+'</select></label>'+
      '<label>Fictional observation<textarea name="observation" minlength="5" maxlength="500" required placeholder="Describe a generic sample observation."></textarea></label>'+
      '<button class="action secondary" type="submit">Record sample inspection</button></form>';
  }
  if(q.status==="OPEN"){
    html+='<form class="controls" data-form="quality-disposition">'+
      '<input type="hidden" name="id" value="'+h(q.id)+'">'+
      '<label>Disposition for review<select name="decision">'+QUALITY_DISPOSITIONS.map(item=>
        '<option value="'+h(item.id)+'" '+(disp?.decision===item.id?"selected":"")+'>'+h(item.label)+'</option>'
      ).join("")+'</select></label>'+
      '<label>Fictional rationale<textarea name="note" minlength="5" maxlength="500" required placeholder="Describe the sample decision and evidence.">'+h(disp?.note||"")+'</textarea></label>'+
      '<button class="action secondary" type="submit">Record demo disposition</button></form>'+
      '<form class="controls" data-form="quality-reviewed-close">'+
      '<input type="hidden" name="id" value="'+h(q.id)+'">'+
      '<button class="action" type="submit" '+(!disp||disp.decision==="RETURN_FOR_REVIEW"?"disabled":"")+'>Close reviewed demo case</button>'+
      '<span class="small">Closing removes this fictional job hold; it is not a real approval.</span></form>';
  }

  if(q.status==="OPEN"){
    html+='<h3>Fictional corrective action</h3>'+
      '<p class="small">Describe a proposed corrective action for this NCR. A role is a fictional responsibility, not an assigned employee or approved action.</p>'+
      '<form class="controls" data-form="quality-corrective-action">'+
      '<input type="hidden" name="id" value="'+h(q.id)+'">'+
      '<label>Responsible role<select name="ownerRole">'+QUALITY_ACTION_ROLES.map(role=>
        '<option value="'+h(role.id)+'">'+h(role.label)+'</option>').join("")+'</select></label>'+
      '<label>Related inspection (optional)<select name="inspectionId"><option value="">Case-level action</option>'+
        inspections.map(item=>'<option value="'+h(item.id)+'">'+h(item.stage)+' · step '+h(item.step)+' · '+h(item.result)+'</option>').join("")+
      '</select></label>'+
      '<label>Proposed fictional action<textarea name="description" minlength="5" maxlength="500" required placeholder="Describe a generic corrective action."></textarea></label>'+
      '<button class="action secondary" type="submit">Record sample corrective action</button></form>';
  }
  html+='<h3>Corrective actions and effectiveness</h3>'+
    (actions.length?actions.map(action=>{
      const linked=inspections.find(item=>item.id===action.sourceInspectionId);
      const reviews=Array.isArray(action.reviews)?action.reviews:[];
      return '<div class="receipt"'+evidenceAttrs("corrective",action.id)+'><b>'+h(action.id)+'</b> · '+
        h(QUALITY_ACTION_ROLES.find(role=>role.id===action.ownerRole)?.label||action.ownerRole)+
        ' · '+h(action.createdAt)+
        '<div>'+h(action.description)+'</div>'+
        '<div class="small">Linked observation: '+h(action.sourceInspectionId?(linked?
          linked.stage+' / step '+linked.step+' / '+linked.result:'Missing fictional observation'):'None (case-level)')+'</div>'+(linked?evidenceButton(q,"inspection",linked.id,"View observation"):"")+
        (linked?routingStepButton(state,q,linked):"")+evidenceWorkOrderButton(state,q,"corrective",action.id)+
        (reviews.length?reviews.map(review=>
          '<div class="receipt"'+evidenceAttrs("effectiveness",review.id)+'><b>Effectiveness review:</b> '+h(review.result)+' · '+h(review.at)+
          '<div>'+h(review.note)+'</div>'+evidenceWorkOrderButton(state,q,"effectiveness",review.id)+'</div>').join(""):
          '<p class="small">Effectiveness not yet reviewed.</p>')+
        '<form class="controls" data-form="quality-effectiveness">'+
        '<input type="hidden" name="id" value="'+h(q.id)+'">'+
        '<input type="hidden" name="actionId" value="'+h(action.id)+'">'+
        '<label>Review result<select name="result">'+QUALITY_EFFECTIVENESS_RESULTS.map(item=>
          '<option value="'+h(item.id)+'">'+h(item.label)+'</option>').join("")+'</select></label>'+
        '<label>Fictional effectiveness evidence<textarea name="note" minlength="5" maxlength="500" required placeholder="Describe a generic follow-up check."></textarea></label>'+
        '<button class="action secondary" type="submit">Record effectiveness review</button>'+
        '<span class="small">A review does not automatically change case closure or job readiness.</span></form></div>';
    }).join(""):'<p class="small">No fictional corrective actions recorded for this case.</p>');
  html+='<form class="controls" data-form="quality-followup">'+
    '<input type="hidden" name="id" value="'+h(q.id)+'">'+
    '<label>Case follow-up (also available after closing)<textarea name="note" minlength="5" maxlength="500" required placeholder="Record a fictional follow-up or effectiveness check."></textarea></label>'+
    '<button class="action secondary" type="submit">Record follow-up</button></form>'+
    '<h3>Case follow-ups</h3>'+
    (followups.length?followups.map(item=>'<div class="receipt"'+evidenceAttrs("followup",item.id)+
      '><b>'+h(item.at||"Date unknown")+'</b> · '+h(item.note)+
      evidenceWorkOrderButton(state,q,"followup",item.id)+'</div>').join(""):
      '<p class="small">No fictional follow-ups recorded for this case.</p>')+
    '<h3>Inspection observations</h3>'+
    (inspections.length?inspections.map(item=>'<div class="receipt"'+evidenceAttrs("inspection",item.id)+'><b>'+h(item.at)+'</b> · '+
      h(QUALITY_INSPECTION_STAGES.find(stage=>stage.id===item.stage)?.label||item.stage)+' · '+
      h(item.result)+' · step '+h(item.step)+' / '+h(item.operation)+' ('+h(item.center)+')'+
      '<div class="small">Job rev '+h(item.jobRevision)+' · drawing rev '+h(item.drawingRevision??"unknown")+'</div>'+
      '<div>'+h(item.observation)+'</div>'+routingStepButton(state,q,item)+evidenceWorkOrderButton(state,q,"inspection",item.id)+actions.filter(action=>action.sourceInspectionId===item.id).map(action=>
        evidenceButton(q,"corrective",action.id,"View corrective action")).join(" ")+'</div>').join(""):
      '<p class="small">No fictional inspection observations recorded for this case.</p>')+
    '<h3>Case chronology</h3><p class="small">One read-only timeline of this NCR, its inspection evidence, dispositions, corrective actions, effectiveness reviews and follow-ups. Post-closure reviews do not reopen a case.</p>'+
    (timeline.length?timeline.map(entry=>'<div class="receipt"><b>'+h(entry.at||"Date unknown")+'</b> · '+h(entry.title)+
      (entry.sourceId?'<span class="small"> · '+h(entry.sourceId)+'</span>':"")+
      evidenceButton(q,entry.kind,entry.sourceId,"View evidence")+
      (entry.kind==="inspection"?routingStepButton(state,q,inspections.find(item=>item.id===entry.sourceId)):"")+
      '<div>'+h(entry.detail)+'</div></div>').join(""):
      '<p class="small">No dated case evidence recorded for this fictional case.</p>')+
    '</section>';
  return html;
}
