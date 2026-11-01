/* Read-only capacity evidence preflight for the selected fictional Axiom job.
 * Reuses the existing advisor and PM snapshot. Optional labeled placeholders are
 * planning assumptions, never verified machine load. No actual hours, machine
 * qualification, live BEAN service, draft mutation, or production release.
 */
import {getJob,packetIssues,reservedTotal} from "./engine.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";
import {assessAlternateCenters} from "./routing-capacity-advice.mjs";

const h = value => String(value ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const localStamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const fail = message => {throw Error(message);};
const syntheticRef = x => typeof x === "string" && /^SYN-[A-Z0-9-]{1,60}$/.test(x);
const roundHours = n => Math.round(n * 100) / 100;
/** One fictional shift maximum. An editable interruption allowance is taken
 * once from nominal capacity; booked/queued assumptions are separate.
 */
export function conservativeCapacityPlaceholders(startLocal,endLocal,bufferPercent=25) {
  if(!localStamp.test(startLocal)||!localStamp.test(endLocal))fail("Enter a valid fictional planning window.");
  if(typeof bufferPercent!=="number"||!Number.isFinite(bufferPercent)||
     bufferPercent<0||bufferPercent>90)
    fail("Fictional interruption allowance must be between 0 and 90 percent.");
  const duration=(new Date(endLocal)-new Date(startLocal))/3600000;
  if(!Number.isFinite(duration)||duration<=0)fail("Planning window must have positive duration.");
  const nominalHours=Math.min(8,duration);
  const calendarHours=roundHours(nominalHours*(1-bufferPercent/100));
  if(calendarHours<=0)fail("Planning window is too short for rounded scenario hours.");
  return {nominalHours:roundHours(nominalHours),calendarHours,
    bookedHours:roundHours(calendarHours*0.25),
    queuedHours:roundHours(calendarHours*0.125),
    bufferPercent,
    basis:"FICTIONAL one-shift estimate: "+bufferPercent+"% interruption allowance; 25% booked and 12.5% queued of effective hours."};
}
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
    "deliveryState","routedOperationCount","capacityEstimateType","capacityHourSources",
     "placeholderBufferPercent"];
  if(!c || typeof c!=="object" || Array.isArray(c) ||
      Object.keys(c).some(k=>!allowed.includes(k)))
    fail("Scenario center contains unsupported or missing evidence fields.");
  if(c.capacityEstimateType!==undefined && !["MANUAL","PLACEHOLDER_ASSISTED"].includes(c.capacityEstimateType))
    fail("Capacity estimate type must identify manual or placeholder-assisted scenario values.");
  // A placeholder claim without field-level origins bypasses the arithmetic
  // gate below. Legacy untagged and explicitly MANUAL scenarios stay valid.
  if(c.capacityEstimateType==="PLACEHOLDER_ASSISTED" && c.capacityHourSources===undefined)
    fail("Placeholder-assisted scenario requires per-field capacity hour provenance.");
  // Per-field origins describe estimates, not independently verified scheduling.
  // The metadata is optional to preserve existing scenario callers.
  if(c.capacityHourSources!==undefined){
    const sources=c.capacityHourSources,keys=["calendarHours","bookedHours","queuedHours"];
    if(!sources || typeof sources!=="object" || Array.isArray(sources) ||
       Object.keys(sources).length!==3 ||
       keys.some(k=>!["MANUAL","PLACEHOLDER","UNKNOWN"].includes(sources[k])) ||
       keys.some(k=>sources[k]==="UNKNOWN" ? c[k]!==undefined : c[k]===undefined) ||
       keys.some(k=>sources[k]!=="UNKNOWN" && c[k]===undefined) ||
       (keys.some(k=>sources[k]==="PLACEHOLDER") !==
        (c.capacityEstimateType==="PLACEHOLDER_ASSISTED")))
      fail("Capacity hour provenance must match supplied values and estimate type.");
  }
  if(c.placeholderBufferPercent!==undefined &&
     (c.capacityHourSources?.calendarHours!=="PLACEHOLDER" ||
      typeof c.placeholderBufferPercent!=="number" ||
      !Number.isFinite(c.placeholderBufferPercent) ||
      c.placeholderBufferPercent<0 || c.placeholderBufferPercent>90))
    fail("Placeholder interruption allowance must be 0 to 90 percent and apply only to placeholder calendar hours.");
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
  // Provenance must describe actual scenario arithmetic, not merely a
  // caller-supplied label. Manual values remain editable and unverified.
  if(c.capacityHourSources){
    const sources=c.capacityHourSources;
    if(sources.calendarHours==="PLACEHOLDER"){
      const expected=conservativeCapacityPlaceholders(
        startLocal,endLocal,c.placeholderBufferPercent??25).calendarHours;
      if(c.calendarHours!==expected)
        fail("Placeholder calendar hours must match the fictional planning window and interruption allowance.");
    }
    for(const [key,rate] of [["bookedHours",0.25],["queuedHours",0.125]]){
      if(sources[key]==="PLACEHOLDER" && c[key]!==roundHours(c.calendarHours*rate))
        fail("Placeholder booked and queued hours must match the stated effective calendar hours.");
    }
  }
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
  const hour=(k,optional=false)=>{
    const raw=get(k);
    // Blank booked/queued load is UNKNOWN, never assumed to be zero.
    if(optional && raw==="")return null;
    if(!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw))
      fail("Calendar, maintenance, setup and run hours must be explicitly supplied; booked/queued hours may be blank for UNKNOWN.");
    const n=Number(raw);
    if(!Number.isFinite(n)||n<0||n>100000)
      fail("Scenario hours must be finite, nonnegative estimates.");
    return n;
  };
  const placeholderMode=fields.has("scenario-placeholder");
  const bufferRaw=get("bufferPercent");
  const bufferPercent=bufferRaw===""?25:Number(bufferRaw);
  if(placeholderMode &&
     (bufferRaw!==""&&!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(bufferRaw) ||
      !Number.isFinite(bufferPercent)||bufferPercent<0||bufferPercent>90))
    fail("Fictional interruption allowance must be between 0 and 90 percent.");
  const suggested=placeholderMode?conservativeCapacityPlaceholders(startLocal,endLocal,bufferPercent):null;
  const calendarInput=hour("calendarHours",placeholderMode);
  const calendarHours=calendarInput??suggested?.calendarHours;
  const bookedInput=hour("bookedHours",true),queuedInput=hour("queuedHours",true);
  const bookedHours=bookedInput??(placeholderMode?roundHours(calendarHours*0.25):null);
  const queuedHours=queuedInput??(placeholderMode?roundHours(calendarHours*0.125):null);
  const capacityHourSources={
    calendarHours:calendarInput===null?"PLACEHOLDER":"MANUAL",
    bookedHours:bookedInput===null?(placeholderMode?"PLACEHOLDER":"UNKNOWN"):"MANUAL",
    queuedHours:queuedInput===null?(placeholderMode?"PLACEHOLDER":"UNKNOWN"):"MANUAL"
  };
  const usedPlaceholder=Object.values(capacityHourSources).includes("PLACEHOLDER");
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
    calendarHours,
    ...(bookedHours===null?{}:{bookedHours}),
    ...(queuedHours===null?{}:{queuedHours}),
    maintenanceHours:hour("maintenanceHours"),
    setupHours:hour("setupHours"),runHours:hour("runHours"),
    capacitySourceRef:usedPlaceholder && !get("capacity-ref")?
      "SYN-PLACEHOLDER-ONE-SHIFT":source("capacity-ref"),
    capacityEstimateType:usedPlaceholder?"PLACEHOLDER_ASSISTED":"MANUAL",
    capacityHourSources,
    ...(capacityHourSources.calendarHours==="PLACEHOLDER"?{placeholderBufferPercent:bufferPercent}:{}),
    readinessSourceRef:source("readiness-ref"),...readiness
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
  const clockHistoryUnknown = sessions === null;
  const clockHistoryCount = clockHistoryUnknown ? null :
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
  // Provenance is review-only; placeholders never certify a dated schedule.
  const capacityAssessment=result.assessments.find(item=>item.center===centerId);
  if(capacityAssessment && center.capacityEstimateType){
    capacityAssessment.capacityEstimateType=center.capacityEstimateType;
    if(center.capacityEstimateType==="PLACEHOLDER_ASSISTED") {
      const calendarBasis=center.capacityHourSources?.calendarHours==="PLACEHOLDER" ?
        "one fictional shift, "+(center.placeholderBufferPercent??25)+"% interruption allowance; " :
        "manually entered effective calendar hours (no added interruption buffer); ";
      capacityAssessment.notes.push("PLACEHOLDER-ASSISTED: "+calendarBasis+
        "25% booked and 12.5% queued estimates only when blank; review actual load.");
    }
    else capacityAssessment.notes.push("MANUAL scenario hours; not independently verified.");
    for(const suggestion of result.suggestions)
      if(suggestion.center===centerId)suggestion.capacityEstimateType=center.capacityEstimateType;
  }
  // Browser-local reservations can contradict a claimed material READY state,
  // but even full reservation does not prove material is physically at the center.
  // There is no canonical dated production schedule in this ERP demo.
  const materialItem = state.items.find(item => item.id === job.materialId);
  const materialKnown = !!materialItem &&
    Number.isSafeInteger(job.quantity) && job.quantity > 0 &&
    Number.isSafeInteger(job.reserved) && job.reserved >= 0 &&
    job.reserved <= job.quantity;
  const materialConflict = center.material === "READY" &&
    (!materialKnown || job.reserved < job.quantity);
  // Reuse the ERP's aggregate reservation calculation. A fully reserved job
  // can still conflict with stock promised to other fictional jobs. Neither
  // an on-hand number nor a reservation proves physical material readiness.
  const stockKnown = materialKnown &&
    typeof materialItem.onHand === "number" &&
    Number.isFinite(materialItem.onHand) && materialItem.onHand >= 0 &&
    state.jobs.filter(item => item.materialId === job.materialId)
      .every(item => Number.isSafeInteger(item.reserved) && item.reserved >= 0);
  const stockConflict = center.material === "READY" && materialKnown &&
    (!stockKnown || reservedTotal(state,job.materialId) > materialItem.onHand);
  // Reuse the canonical EWI/job packet checks. Scenario assertions cannot
  // override drawing, quality holds or job status. BETA: the existing
  // REVIEW_REQUIRED routing flag is advisory for synthetic operator clocking;
  // preserve the former draft-review restriction for later restoration only.
  const packetConcerns = packetIssues(state,jobId);
  if (clockHistoryUnknown || contradictedZero || materialConflict || stockConflict || packetConcerns.length || clockHistoryConflict) {
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
      if (stockConflict) {
        assessment.unknown.push(stockKnown ?
          "Scenario material READY conflicts with aggregate fictional reservations exceeding recorded on-hand stock; stock readiness is UNKNOWN." :
          "Scenario material READY lacks valid fictional on-hand or aggregate reservation quantities; stock readiness is UNKNOWN.");
        assessment.notes.push("Browser-local stock and reservations do not prove physical material availability or operation-level readiness.");
      }
      if (clockHistoryUnknown) {
        assessment.unknown.push("Browser-local EWI clock history was not supplied; routing edit eligibility is UNKNOWN.");
        assessment.notes.push("An absent session snapshot cannot establish that a job has no clock history.");
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
  const hourSources=scenario?.capacityHourSources;
  const num=(k,label)=>'<label>'+h(label)+'<input type="number" min="0" max="100000" step="any" name="scenario-'+k+'" value="'+h(scenario?.capacityHourSources?.[k]==="PLACEHOLDER"?"":scenario?.[k]??"")+'"></label>';
  const ref=(k,label,value)=>'<label>'+h(label)+'<input name="scenario-'+k+'" maxlength="64" pattern="SYN-[A-Z0-9-]{1,60}" placeholder="SYN-EXAMPLE-001" value="'+h(value??"")+'"></label>';
  const pick=(k,label,choices,value)=>'<label>'+h(label)+'<select name="scenario-'+k+'">'+choices.map(x=>option(x,x,x===value)).join('')+'</select></label>';
  const scenarioFields='<details'+(scenario?' open':'')+'><summary>Optional fictional capacity scenario</summary>'+
    '<p class="small">Manually asserted estimates only. No live machine, schedule, BEAN, or qualification connection. Leave unchecked for UNKNOWN. Nothing saved.</p>'+
    '<label><input type="checkbox" name="scenario-enabled" value="yes"'+(scenario?' checked':'')+'> Evaluate fictional estimates</label>'+
    '<label><input type="checkbox" name="scenario-placeholder" value="yes"'+
      (scenario?.capacityEstimateType==="PLACEHOLDER_ASSISTED"?' checked':'')+
      '> Use conservative placeholders for blank capacity/booked/queued hours</label>'+
    '<p class="small">Optional fictional one-shift assumption: at most 8 nominal hours, editable interruption allowance (25% default), then hypothetical booked 25% and queued 12.5% of effective hours. Allowance applies only to a blank calendar-hour field; manual calendar hours are already effective hours. PM downtime and setup/run time still require explicit input. NOT actual scheduled hours.</p>'+
    '<div class="controls">'+
    pick("capability","Operation capability",["","supported","unsupported"],
      scenario?.capability?.supported===true?"supported":scenario?.capability?.supported===false?"unsupported":"")+
    ref("capability-ref","Capability source",scenario?.capability?.sourceRef)+
    '<label>Interruption allowance % (blank calendar only)<input type="number" min="0" max="90" step="any" name="scenario-bufferPercent" value="'+h(scenario?.placeholderBufferPercent??25)+'"></label>'+
    num("calendarHours","Effective planning hours")+num("bookedHours","Booked hours (blank = UNKNOWN)")+
    num("queuedHours","Queued hours (blank = UNKNOWN)")+num("maintenanceHours","PM downtime hours")+
    num("setupHours","Setup hours")+num("runHours","Run hours")+
    ref("capacity-ref","Capacity source",scenario?.capacitySourceRef)+
    ref("readiness-ref","Readiness source",scenario?.readinessSourceRef)+
    pick("maintenanceState","Maintenance",["UNKNOWN","CLEAR","DOWN"],scenario?.maintenanceState??"UNKNOWN")+
    pick("tooling","Tooling",["UNKNOWN","READY","BLOCKED"],scenario?.tooling??"UNKNOWN")+
    pick("fixture","Fixture",["UNKNOWN","READY","BLOCKED"],scenario?.fixture??"UNKNOWN")+
    pick("material","Material",["UNKNOWN","READY","BLOCKED"],scenario?.material??"UNKNOWN")+
    pick("deliveryState","Delivery",["UNKNOWN","ON_TIME","LATE"],scenario?.deliveryState??"UNKNOWN")+
    num("routedOperationCount","Routed operations (blank = UNKNOWN)")+
    '</div><p class="small">Booked and queued hours may be blank when UNKNOWN. Enter 0 only with an explicit estimate. Other four hour fields are required. SYN- references are unverified. Zero routed operations does not establish availability or suitability.</p></details>';
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
      '<p><b>Capacity basis:</b> '+h(a?.capacityEstimateType || 'UNKNOWN')+'</p>'+
      (hourSources?'<p class="small"><b>Hour inputs:</b> '+
        ["calendarHours","bookedHours","queuedHours"].map(k=>
          h(k)+': '+h(hourSources[k]??"UNKNOWN")).join('; ')+'</p>':'')+
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
      (a?.notes?.length?'<p class="small">'+a.notes.map(h).join(' ')+'</p>':'')+
      (messages.length?'<ul>'+messages.map(message=>'<li>'+h(message)+'</li>').join('')+'</ul>':'')+
      (review.result.suggestions.length ?
        '<p class="small">Scenario-only alternate identified for human draft review. No routing saved, approved or released.</p>' :
        '<p class="small">No alternate routing proposed or saved. Source evidence, scheduled load, '+
        'tooling, material, maintenance clearance and human review are required before a recommendation.</p>')+
      '</div>';
  }
  return html+'</section>';
}
