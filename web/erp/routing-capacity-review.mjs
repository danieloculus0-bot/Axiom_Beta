/* Read-only capacity evidence preflight for the selected fictional Axiom job.
 * Reuses the existing advisor and PM snapshot. No invented hours, machine
 * qualification, live BEAN service, draft mutation, or production release.
 */
import {getJob} from "./engine.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";
import {assessAlternateCenters} from "./routing-capacity-advice.mjs";

const h = value => String(value ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const localStamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const fail = message => {throw Error(message);};

/** No supplied capacity/capability evidence means UNKNOWN, not an idle machine.
 * Browser datetime-local values are interpreted in the user's local timezone.
 * Results are ephemeral and never saved to job, PM, or ERP event records.
 */
export function inspectRoutingCapacityEvidence(state, jobId, step, centerId, startLocal, endLocal) {
  const job = getJob(state,jobId);
  if (!job || !state.jobs.some(item => item.id === jobId))
    fail("Select an existing fictional job.");
  const operation = job.routing?.operations?.find(item => item.step === step);
  if (!operation || job.routing.revision !== job.revision)
    fail("Select a routed operation matching the current fictional job revision.");
  if (!DEMO_CENTER_OPTIONS.includes(centerId) || centerId === operation.center)
    fail("Select a different registered fictional work center.");
  if (!localStamp.test(startLocal) || !localStamp.test(endLocal))
    fail("Enter a start and end time for the planning window.");
  const start = new Date(startLocal), end = new Date(endLocal);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) ||
      end.getTime() <= start.getTime())
    fail("The planning window must end after it starts.");
  const result = assessAlternateCenters(job,step,{
    window:{start:start.toISOString(),end:end.toISOString()},
    // Deliberately omit all capability, capacity and readiness assertions.
    // A browser-local PM record is evidence to review, not a clearance.
    centers:[{id:centerId}],
    pmContext:{state:state.pm}
  });
  return {jobId,partNumber:job.partNumber,revision:job.revision,step,centerId,
    startLocal,endLocal,result,assessment:result.assessments[0] || null};
}

export function routingCapacityEvidenceHtml(job, review = null) {
  const operations = job.routing?.operations || [];
  const step = review?.jobId === job.id ? review.step : operations[0]?.step;
  const operation = operations.find(item => item.step === step) || operations[0];
  const centerId = review?.jobId === job.id ? review.centerId :
    DEMO_CENTER_OPTIONS.find(id => id !== operation?.center);
  const option = (id,label,selected) =>
    '<option value="'+h(id)+'"'+(id === selected?' selected':'')+'>'+h(label)+'</option>';
  let html = '<section class="panel" id="routing-capacity-review">'+
    '<div class="panel-head"><h2>Alternate work-center evidence</h2>'+
    '<span class="tag warn">REVIEW ONLY</span></div>'+
    '<p class="small">Check a fictional alternate against the saved job routing and existing browser-local PM records. '+
    'No live schedule, capability, machine hours, or BEAN service is connected. '+
    'Missing information stays UNKNOWN; this never changes a routing.</p>'+
    '<form class="controls" data-form="routing-capacity-review">'+
    '<label>Routed operation<select name="step" required>'+
    operations.map(item => option(item.step,item.step+' / '+item.name,item.step === step)).join('')+
    '</select></label>'+
    '<label>Potential alternate center<select name="center" required>'+
    DEMO_CENTER_OPTIONS.map(id => option(id,id,id === centerId)).join('')+
    '</select></label>'+
    '<label>Planning start (local)<input type="datetime-local" name="window-start" required value="'+
    h(review?.startLocal || '')+'"></label>'+
    '<label>Planning end (local)<input type="datetime-local" name="window-end" required value="'+
    h(review?.endLocal || '')+'"></label>'+
    '<button class="action secondary" type="submit">Review evidence gaps</button></form>';
  if (review?.jobId === job.id) {
    const a = review.assessment;
    const messages = [...(a?.blocked || []),...(a?.unknown || [])];
    html += '<div id="routing-capacity-result" class="receipt" role="status">'+
      '<h3>Read-only assessment: '+h(review.step)+' / '+h(review.centerId)+'</h3>'+
      '<p><b>Result:</b> '+h(a?.status || review.result.status)+
      ' · <b>PM association:</b> '+h(a?.pmEvidence?.status || 'UNKNOWN')+'</p>'+
      '<p><b>Capacity and qualification:</b> UNKNOWN. No capacity figures were supplied or inferred.</p>'+
      (messages.length?'<ul>'+messages.map(message=>'<li>'+h(message)+'</li>').join('')+'</ul>':'')+
      '<p class="small">No alternate routing proposed or saved. Source evidence, scheduled load, '+
      'tooling, material, maintenance clearance and human review are required before a recommendation.</p></div>';
  }
  return html+'</section>';
}
