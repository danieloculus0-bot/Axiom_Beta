/* One job-linked fictional quality case, using existing ERP context and events. */
import {QUALITY_DISPOSITIONS} from "./quality-case.mjs";
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
  let html='<section class="panel" id="quality-case-detail"><div class="panel-head"><h2>Quality Forge case · '+h(q.number)+'</h2><span class="tag">'+h(q.status)+'</span></div>'+
    '<p class="small">Linked work order: <b>'+h(j?.jobNumber||"Missing fictional job")+'</b> · '+h(q.reason)+
    '. Browser-local demonstration only. No production disposition or release authority.</p>'+
    '<div class="controls">'+links+'</div>'+
    '<div class="receipt"><b>Recorded fictional disposition:</b> '+
    (disp?h(QUALITY_DISPOSITIONS.find(item=>item.id===disp.decision)?.label||disp.decision)+
      ' · '+h(disp.note)+' · '+h(disp.recordedAt):"Not recorded. Case remains on hold.")+'</div>';
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
  html+='<form class="controls" data-form="quality-followup">'+
    '<input type="hidden" name="id" value="'+h(q.id)+'">'+
    '<label>Case follow-up (also available after closing)<textarea name="note" minlength="5" maxlength="500" required placeholder="Record a fictional follow-up or effectiveness check."></textarea></label>'+
    '<button class="action secondary" type="submit">Record follow-up</button></form>'+
    '<h3>Case activity</h3>'+
    (notes.length?notes.map(item=>'<div class="receipt"><b>'+h(item.at)+'</b> · '+h(item.note)+'</div>').join(""):
      '<p class="small">No follow-ups recorded for this fictional case.</p>')+
    '</section>';
  return html;
}
