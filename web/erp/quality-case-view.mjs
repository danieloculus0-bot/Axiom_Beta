/* One job-linked fictional quality case, using existing ERP context and events. */
import {QUALITY_DISPOSITIONS,QUALITY_INSPECTION_STAGES,QUALITY_INSPECTION_RESULTS,QUALITY_ACTION_ROLES,QUALITY_EFFECTIVENESS_RESULTS} from "./quality-case.mjs";
const h=value=>String(value??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
})[c]);
export function renderQualityCase(state,id){
  const q=state.quality.find(record=>record.id===id);
  if(!q)return '<section class="panel" id="quality-case-detail"><h2>Case review</h2><p class="small">Select a fictional nonconformance above to review its linked record.</p></section>';
  const j=state.jobs.find(job=>job.id===q.jobId);
  const links=j?'<a class="action secondary" href="#routing" data-job="'+h(j.id)+'">Routing</a> '+
    '<a class="action secondary" href="#documents" data-job="'+h(j.id)+'">Drawing</a> '+
    '<a class="action secondary" href="#ewi" data-job="'+h(j.id)+'">EWI / hold</a>':"";
  const disp=q.disposition;
  const notes=Array.isArray(q.followUps)?q.followUps:[];
  const inspections=Array.isArray(q.inspections)?q.inspections:[];
  const actions=Array.isArray(q.correctiveActions)?q.correctiveActions:[];
  const operations=Array.isArray(j?.routing?.operations)?j.routing.operations:[];
  let html='<section class="panel" id="quality-case-detail"><div class="panel-head"><h2>Quality Forge case · '+h(q.number)+'</h2><span class="tag">'+h(q.status)+'</span></div>'+
    '<p class="small">Linked work order: <b>'+h(j?.jobNumber||"Missing fictional job")+'</b> · '+h(q.reason)+
    '. Browser-local demonstration only. No production disposition or release authority.</p>'+
    '<div class="controls">'+links+'</div>'+
    '<div class="receipt"><b>Recorded fictional disposition:</b> '+
    (disp?h(QUALITY_DISPOSITIONS.find(item=>item.id===disp.decision)?.label||disp.decision)+
      ' · '+h(disp.note)+' · '+h(disp.recordedAt):"Not recorded. Case remains on hold.")+'</div>';
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
      return '<div class="receipt"><b>'+h(action.id)+'</b> · '+
        h(QUALITY_ACTION_ROLES.find(role=>role.id===action.ownerRole)?.label||action.ownerRole)+
        ' · '+h(action.createdAt)+
        '<div>'+h(action.description)+'</div>'+
        '<div class="small">Linked observation: '+h(action.sourceInspectionId?(linked?
          linked.stage+' / step '+linked.step+' / '+linked.result:'Missing fictional observation'):'None (case-level)')+'</div>'+
        (reviews.length?reviews.map(review=>
          '<div class="receipt"><b>Effectiveness review:</b> '+h(review.result)+' · '+h(review.at)+
          '<div>'+h(review.note)+'</div></div>').join(""):
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
    '<h3>Inspection observations</h3>'+
    (inspections.length?inspections.map(item=>'<div class="receipt"><b>'+h(item.at)+'</b> · '+
      h(QUALITY_INSPECTION_STAGES.find(stage=>stage.id===item.stage)?.label||item.stage)+' · '+
      h(item.result)+' · step '+h(item.step)+' / '+h(item.operation)+' ('+h(item.center)+')'+
      '<div class="small">Job rev '+h(item.jobRevision)+' · drawing rev '+h(item.drawingRevision??"unknown")+'</div>'+
      '<div>'+h(item.observation)+'</div></div>').join(""):
      '<p class="small">No fictional inspection observations recorded for this case.</p>')+
    '<h3>Case activity</h3>'+
    (notes.length?notes.map(item=>'<div class="receipt"><b>'+h(item.at)+'</b> · '+h(item.note)+'</div>').join(""):
      '<p class="small">No follow-ups recorded for this fictional case.</p>')+
    '</section>';
  return html;
}
