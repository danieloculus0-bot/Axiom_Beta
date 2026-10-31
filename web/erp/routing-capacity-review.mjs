/* Read-only capacity evidence preflight for the selected fictional Axiom job.
 * Reuses the existing advisor and PM snapshot. No invented hours, machine
 * qualification, live BEAN service, draft mutation, or production release.
 */
import {getJob,packetIssues} from "./engine.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";
import {assessAlternateCenters} from "./routing-capacity-advice.mjs";

const h = value => String(value ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const localStamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const fail = message => {throw Error(message);};
const syntheticRef = x => typeof x === "string" && /^SYN-[A-Z0-9-]{1,60}$/.test(x);
// Caller-supplied scenario assertions are never verified, persisted or auto-applied.
function scopedScenarioCenter(e,job,op,id,startLocal,endLocal){
  if(e === null)return {id};
  if(!e || typeof e !== "object" || Array.isArray(e) ||
      Object.keys(e).some(k=>!["scope","center"].includes(k)))
    fail("Scenario evidence must be a scoped synthetic object.");
  const expected={jobId:job.id,partNumber:job.partNumber,revision:job.revision,
    step:op.step,centerId:id,startLocal,endLocal};
  if(!e.scope || typeof e.scope !== "object" || Array.isArray(e.scope) ||
      Object.keys(e.scope).length!==Object.keys(expected).length ||
      Object.entries(expected).some(([k,v])=>e.scope[k]!==v))
    fail("Scenario evidence must match the selected job, revision, step, center and window.");
  const c=e.center;
  const allowed=["capability","calendarHours","bookedHours","queuedHours",
    "maintenanceHours","setupHours","runHours","capacitySourceRef",
    "readinessSourceRef","maintenanceState","tooling","fixture","material",
    "deliveryState","routedOperationCount"];
  if(!c || typeof c!=="object" || Array.isArray(c) ||
      Object.keys(c).some(k=>!allowed.includes(k)))
    fail("Scenario center contains unsupported or missing evidence fields.");
  const cap=c.capability;
  if(!cap || typeof cap!=="object" || Array.isArray(cap) ||
      Object.keys(cap).some(k=>!["operation","supported","sourceRef"].includes(k)) ||
      cap.operation!==op.name || typeof cap.supported!=="boolean")
    fail("Capability assertion must identify the exact selected operation.");
  if(![cap.sourceRef,c.capacitySourceRef,c.readinessSourceRef].every(syntheticRef))
    fail("Capability, capacity and readiness require fictional SYN- evidence references.");
  const states={maintenanceState:["CLEAR","DOWN","UNKNOWN"],
    tooling:["READY","BLOCKED","UNKNOWN"],fixture:["READY","BLOCKED","UNKNOWN"],
    material:["READY","BLOCKED","UNKNOWN"],deliveryState:["ON_TIME","LATE","UNKNOWN"]};
  if(Object.entries(states).some(([k,values])=>c[k]!==undefined&&!values.includes(c[k])))
    fail("Scenario readiness values must use explicit supported states.");
  const hours=["calendarHours","bookedHours","queuedHours","maintenanceHours","setupHours","runHours"];
  if(hours.some(k=>c[k]!==undefined &&
      (typeof c[k]!=="number"||!Number.isFinite(c[k])||c[k]<0||c[k]>100000)))
    fail("Scenario hours must be finite, nonnegative estimates.");
  if(c.routedOperationCount!==undefined &&
      (!Number.isSafeInteger(c.routedOperationCount)||c.routedOperationCount<0))
    fail("Scenario routed-operation count must be a nonnegative integer.");
  return {id,...structuredClone(c)};
}


/** Only explicitly opted-in fictional scenario values are evaluated. */
export function readRoutingCapacityScenario(fields,job,step,centerId,startLocal,endLocal){
  if(!fields.has("scenario-enabled"))return null;
  const operation=job?.routing?.operations?.find(op=>op.step===step);
  if(!operation)fail("Select a routed operation before scenario review.");
  const get=k=>String(fields.get("scenario-"+k)??"").trim();
  const source=k=>{
    const s=get(k);
    if(!syntheticRef(s))fail("Scenario sources require fictional SYN- references.");
    return s;
  };
  const hour=k=>{
    const raw=get(k);
    if(!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw))
      fail("All six scenario hour estimates must be explicitly supplied.");
    const n=Number(raw);
    if(!Number.isFinite(n)||n<0||n>100000)
      fail("Scenario hours must be finite, nonnegative estimates.");
    return n;
  };
  const capability=get("capability");
  if(!["supported","unsupported"].includes(capability))
    fail("Select supported or unsupported fictional capability.");
  const choices={maintenanceState:["UNKNOWN","CLEAR","DOWN"],
    tooling:["UNKNOWN","READY","BLOCKED"],fixture:["UNKNOWN","READY","BLOCKED"],
    material:["UNKNOWN","READY","BLOCKED"],deliveryState:["UNKNOWN","ON_TIME","LATE"]};
  const readiness={};
  for(const [k,options] of Object.entries(choices)){
    if(!options.includes(get(k)))fail("Choose explicit scenario readiness states.");
    readiness[k]=get(k);
  }
  const count=get("routedOperationCount");
  if(count!==""&&(!/^\d+$/.test(count)||!Number.isSafeInteger(Number(count))))
    fail("Routed-operation count must be nonnegative or UNKNOWN.");
  const center={
    capability:{operation:operation.name,supported:capability==="supported",sourceRef:source("capability-ref")},
    calendarHours:hour("calendarHours"),bookedHours:hour("bookedHours"),
    queuedHours:hour("queuedHours"),maintenanceHours:hour("maintenanceHours"),
    setupHours:hour("setupHours"),runHours:hour("runHours"),
    capacitySourceRef:source("capacity-ref"),readinessSourceRef:source("readiness-ref"),...readiness
  };
  if(count!=="")center.routedOperationCount=Number(count);
  return {scope:{jobId:job.id,partNumber:job.partNumber,revision:job.revision,
    step,centerId,startLocal,endLocal},center};
}

/** No supplied capacity/capability evidence means UNKNOWN, not an idle machine.
 * Browser datetime-local values are interpreted in the user's local timezone.
 * Results are ephemeral and never saved to job, PM, or ERP event records.
 */
export function inspectRoutingCapacityEvidence(state, jobId, step, centerId, startLocal, endLocal, scenarioEvidence = null, sessions = null) {
  // The caller must supply its browser-local EWI session snapshot to check
  // whether the existing routing editor permits changes to this job.
  if (sessions !== null && !Array.isArray(sessions))
    fail("Browser-local EWI sessions must be an array when provided.");
  const clockHistoryCount = sessions === null ? null :
    sessions.filter(session => session && typeof session === "object" && session.jobId === jobId).length;
  const clockHistoryConflict = clockHistoryCount > 0;
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
  const center = scopedScenarioCenter(scenarioEvidence,job,operation,centerId,startLocal,endLocal);
  // The existing canonical browser jobs can disprove an asserted zero count,
  // but their routes have no scheduling dates and cannot prove occupied hours.
  const knownRoutedCount = state.jobs.reduce((count,item) =>
    count + (Array.isArray(item.routing?.operations) ?
      item.routing.operations.filter(op => op?.center === centerId).length : 0),0);
  const contradictedZero = center.routedOperationCount === 0 && knownRoutedCount > 0;
  if (contradictedZero) delete center.routedOperationCount;
  const result = assessAlternateCenters(job,step,{
    window:{start:start.toISOString(),end:end.toISOString()},
    // Deliberately omit unverified capability, capacity and readiness facts.
    centers:[center],pmContext:{state:state.pm}
  });
  // Browser-local reservations can contradict a claimed material READY state,
  // but even full reservation does not prove material is physically at the center.
  // There is no canonical dated production schedule in this ERP demo.
  const materialKnown = state.items.some(item => item.id === job.materialId) &&
    Number.isSafeInteger(job.quantity) && job.quantity > 0 &&
    Number.isSafeInteger(job.reserved) && job.reserved >= 0 &&
    job.reserved <= job.quantity;
  const materialConflict = center.material === "READY" &&
    (!materialKnown || job.reserved < job.quantity);
  // Reuse the canonical EWI/job packet checks that gate clocking. Scenario
  // assertions cannot override drawing, quality, job status or draft review.
  const packetConcerns = packetIssues(state,jobId);
  if (contradictedZero || materialConflict || packetConcerns.length || clockHistoryConflict) {
    const assessment = result.assessments.find(item => item.center === centerId);
    if (assessment) {
      if (contradictedZero) {
        assessment.idleCandidate = false;
        assessment.unknown.push("Asserted zero routed operations conflicts with " +
          knownRoutedCount + " existing fictional routing assignment(s); planning-window load is UNKNOWN.");
        assessment.notes.push("Existing routing assignments do not prove scheduled hours or machine availability.");
      }
      if (materialConflict) {
        assessment.unknown.push("Scenario material READY conflicts with missing or incomplete canonical job material reservation; readiness is UNKNOWN.");
        assessment.notes.push("Browser-local reservation is not proof of physical material availability or operation-level readiness.");
      }
      if (clockHistoryConflict) {
        assessment.unknown.push("This fictional job has browser-local EWI clock history; the existing routing editor blocks changes after any clock session.");
        assessment.notes.push("Browser-local EWI sessions are not a production schedule, machine load measurement or official timeclock record.");
      }
      if (packetConcerns.length) {
        assessment.unknown.push(...packetConcerns.map(issue =>
          "Canonical job packet requires review: " + issue));
        assessment.notes.push("Existing EWI/job checks do not prove machine capacity or qualification.");
      }
      if (assessment.status !== "EXCLUDED") assessment.status = "NEEDS_REVIEW";
    }
    result.suggestions = result.suggestions.filter(item => item.center !== centerId);
    result.status = result.suggestions.length ? "SCENARIO_CANDIDATES" : "NO_ELIGIBLE_ALTERNATIVES";
  }
  return {knownRoutedCount,clockHistoryCount,jobId,partNumber:job.partNumber,revision:job.revision,step,centerId,
    startLocal,endLocal,evidenceSupplied:scenarioEvidence !== null,
    scenarioEvidence:scenarioEvidence===null?null:structuredClone(scenarioEvidence),
    result,assessment:result.assessments[0] || null};
}

export function routingCapacityEvidenceHtml(job, review = null) {
  const operations = job.routing?.operations || [];
  const step = review?.jobId === job.id ? review.step : operations[0]?.step;
  const operation = operations.find(item => item.step === step) || operations[0];
  const centerId = review?.jobId === job.id ? review.centerId :
    DEMO_CENTER_OPTIONS.find(id => id !== operation?.center);
  const option = (id,label,selected) =>
    '<option value="'+h(id)+'"'+(selected?' selected':'')+'>'+h(label)+'</option>';

  const scenario=review?.jobId===job.id?review.scenarioEvidence?.center:null;
  const num=(k,label)=>'<label>'+h(label)+'<input type="number" min="0" max="100000" step="any" name="scenario-'+k+'" value="'+h(scenario?.[k]??"")+'"></label>';
  const ref=(k,label,value)=>'<label>'+h(label)+'<input name="scenario-'+k+'" maxlength="64" pattern="SYN-[A-Z0-9-]{1,60}" placeholder="SYN-EXAMPLE-001" value="'+h(value??"")+'"></label>';
  const pick=(k,label,choices,value)=>'<label>'+h(label)+'<select name="scenario-'+k+'">'+choices.map(x=>option(x,x,x===value)).join('')+'</select></label>';
  const scenarioFields='<details'+(scenario?' open':'')+'><summary>Optional fictional capacity scenario</summary>'+
    '<p class="small">Manually asserted estimates only. No live machine, schedule, BEAN, or qualification connection. Leave unchecked for UNKNOWN. Nothing saved.</p>'+
    '<label><input type="checkbox" name="scenario-enabled" value="yes"'+(scenario?' checked':'')+'> Evaluate fictional estimates</label>'+
    '<div class="controls">'+
    pick("capability","Operation capability",["","supported","unsupported"],
      scenario?.capability?.supported===true?"supported":scenario?.capability?.supported===false?"unsupported":"")+
    ref("capability-ref","Capability source",scenario?.capability?.sourceRef)+
    num("calendarHours","Calendar hours")+num("bookedHours","Booked hours")+
    num("queuedHours","Queued hours")+num("maintenanceHours","PM downtime hours")+
    num("setupHours","Setup hours")+num("runHours","Run hours")+
    ref("capacity-ref","Capacity source",scenario?.capacitySourceRef)+
    ref("readiness-ref","Readiness source",scenario?.readinessSourceRef)+
    pick("maintenanceState","Maintenance",["UNKNOWN","CLEAR","DOWN"],scenario?.maintenanceState??"UNKNOWN")+
    pick("tooling","Tooling",["UNKNOWN","READY","BLOCKED"],scenario?.tooling??"UNKNOWN")+
    pick("fixture","Fixture",["UNKNOWN","READY","BLOCKED"],scenario?.fixture??"UNKNOWN")+
    pick("material","Material",["UNKNOWN","READY","BLOCKED"],scenario?.material??"UNKNOWN")+
    pick("deliveryState","Delivery",["UNKNOWN","ON_TIME","LATE"],scenario?.deliveryState??"UNKNOWN")+
    num("routedOperationCount","Routed operations (blank = UNKNOWN)")+
    '</div><p class="small">SYN- references are unverified. Zero routed operations does not establish availability or suitability.</p></details>';
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
    scenarioFields+
    '<button class="action secondary" type="submit">Review scenario evidence</button></form>';
  if (review?.jobId === job.id) {
    const a = review.assessment;
    const messages = [...(a?.blocked || []),...(a?.unknown || [])];
    html += '<div id="routing-capacity-result" class="receipt" role="status">'+
      '<h3>Read-only assessment: '+h(review.step)+' / '+h(review.centerId)+'</h3>'+
      '<p><b>Result:</b> '+h(a?.status || review.result.status)+
      ' · <b>PM association:</b> '+h(a?.pmEvidence?.status || 'UNKNOWN')+'</p>'+
      '<p class="small">Existing fictional job routing references to this center: '+
      h(review.knownRoutedCount ?? 'UNKNOWN')+
      '. This is not a scheduled-load or machine-availability measurement.</p>'+
      '<p class="small">Browser-local EWI clock sessions on this job: '+
      h(review.clockHistoryCount ?? 'NOT CHECKED')+
      '. These are not a production schedule or verified machine load.</p>'+
      (review.evidenceSupplied ?
        '<p><b>Scenario estimates, not verified:</b> available '+h(a?.availableHours ?? "UNKNOWN")+
        ' hours; required '+h(a?.requiredHours ?? "UNKNOWN")+
        ' hours; utilization '+h(a?.utilizationPercent ?? "UNKNOWN")+
        '%. Capability and availability still require independent review.</p>'+
        '<p class="small"><b>Asserted evidence:</b> '+(a?.evidenceRefs || []).map(h).join(', ')+'</p>' :
        '<p><b>Capacity and qualification:</b> UNKNOWN. No capacity figures were supplied or inferred.</p>')+
      (messages.length?'<ul>'+messages.map(message=>'<li>'+h(message)+'</li>').join('')+'</ul>':'')+
      (review.result.suggestions.length ?
        '<p class="small">Scenario-only alternate identified for human draft review. No routing saved, approved or released.</p>' :
        '<p class="small">No alternate routing proposed or saved. Source evidence, scheduled load, '+
        'tooling, material, maintenance clearance and human review are required before a recommendation.</p>')+
      '</div>';
  }
  return html+'</section>';
}
