/* Read-only, caller-supplied planning scenario for Axiom's canonical job.routing.
 * No live capacity, PM, HR, CNC, BEAN, or scheduling integration is implied.
 * All evidence references are assertions; recommendations remain human-reviewed.
 */
import {reviewRoutingCandidate} from "./routing-advice.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";
import {validatePm,getMachine,machineSummary} from "./pm.mjs";

const str = value => typeof value === "string" ? value.trim() : "";
const hours = value => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100000;
// Keep display rounding distinct from raw eligibility; normalize -0 for strict consumers.
const round = value => {
  const rounded = Math.round(value * 100) / 100;
  return Object.is(rounded, -0) ? 0 : rounded;
};
const limitations = [
  "Planning-window, capacity, readiness and evidence inputs are caller-supplied, not live or verified.",
  "Zero routed operations is not proof of free machine time, capability or qualification.",
  "Scenario hours are estimates, not measured cycle times or a released schedule.",
  "A matching program reference is optional and never proves machine qualification.",
  "Only Axiom's existing draft/review flow can handle a proposed change; no automatic apply or release.",
  "Optional PM asset links and maintenance records are asserted snapshot evidence, never proof of clearance."
];
const invalid = issue => ({status:"INVALID_SCENARIO",proposalOnly:true,canAutoApply:false,
  assessments:[],suggestions:[],issues:[issue],limitations:[...limitations]});

// Read only from the existing synthetic PM Tracker record model. The center-to-asset
// relationship must be explicitly supplied; names and IDs are never guessed.
function pmEvidenceFor(context, centerId, window) {
  const link = context.links.find(item => item.centerId === centerId);
  const base = {machineId:link?.machineId || null,linkSourceRef:str(link?.sourceRef) || null,
    openRequestIds:[],dueTaskIds:[],concerns:[]};
  if (!link) return {...base,status:"UNMAPPED",
    concerns:["PM asset relationship is UNKNOWN; no explicit center-to-machine link."]};
  let machine;
  try { machine = getMachine(context.state,link.machineId); }
  catch { return {...base,status:"UNKNOWN",
    concerns:["Linked PM machine record is invalid; clearance is UNKNOWN."]}; }
  if (!machine) return {...base,status:"UNRESOLVED",
    concerns:["Linked PM machine does not exist in the supplied snapshot."]};
  let summary;
  try { summary = machineSummary(context.state,link.machineId,window.start.slice(0,10)); }
  catch { return {...base,status:"UNKNOWN",
    concerns:["PM task evidence could not be evaluated; maintenance clearance is UNKNOWN."]}; }
  base.openRequestIds = context.state.requests
    .filter(r => r?.machineId === link.machineId && !["CLOSED","CANCELLED"].includes(r.status))
    .map(r => r.id);
  base.dueTaskIds = summary.tasks
    .filter(t => t.due && t.due <= window.end.slice(0,10)).map(t => t.id);
  if (!base.linkSourceRef) base.concerns.push("PM asset mapping evidence reference missing.");
  if (machine.active !== true) base.concerns.push("Linked PM machine is inactive or its status is UNKNOWN.");
  if (base.openRequestIds.length)
    base.concerns.push("Open PM requests require independent machine-availability review.");
  if (base.dueTaskIds.length)
    base.concerns.push("PM tasks due within the planning window require downtime review.");
  return {...base,status:base.concerns.length ? "NEEDS_REVIEW" : "NO_RECORDED_ALERTS"};
}

/**
 * Evaluate alternatives to one existing job.routing operation using an explicit
 * synthetic snapshot: {window:{start,end},centers:[{id,capability:{operation,
 * supported,sourceRef},calendarHours,bookedHours,queuedHours,maintenanceHours,
 * setupHours,runHours,capacitySourceRef,readinessSourceRef,maintenanceState,
 * tooling,fixture,material,deliveryState,routedOperationCount}]}.
 * Missing inputs stay UNKNOWN. No persistent work-center records are created.
 */
export function assessAlternateCenters(job, step, scenario) {
  if (!job || !str(job.partNumber) || !str(job.revision) ||
      job.routing?.revision !== job.revision || !Array.isArray(job.routing.operations))
    return invalid("A matching canonical job and routing revision are required.");
  const operation = job.routing.operations.find(op => op.step === step);
  if (!operation) return invalid("Selected operation is not in the existing routing.");
  const window = scenario?.window;
  const start = Date.parse(window?.start), end = Date.parse(window?.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start ||
      !/(?:Z|[+-]\d{2}:\d{2})$/.test(window?.start || "") ||
      !/(?:Z|[+-]\d{2}:\d{2})$/.test(window?.end || "") ||
      !Array.isArray(scenario?.centers) || scenario.centers.length > 100)
    return invalid("Provide a valid planning window and at most 100 work-center snapshots.");
  const ids = scenario.centers.map(c => str(c?.id));
  if (ids.some(id => !id) || new Set(ids).size !== ids.length)
    return invalid("Work-center IDs must be present and unique.");
  // This optional link reads the existing browser-local PM state, not a second
  // machine registry. Invalid or ambiguous mappings fail closed.
  const pmContext = scenario.pmContext ?? null;
  if (pmContext !== null) {
    try { validatePm(pmContext.state); }
    catch { return invalid("A valid synthetic PM Tracker snapshot is required."); }
    const links = pmContext.links;
    if (!Array.isArray(links) || links.length > 100 ||
        links.some(link => !str(link?.centerId) || !str(link?.machineId)) ||
        new Set(links.map(link => str(link.centerId))).size !== links.length ||
        new Set(links.map(link => str(link.machineId))).size !== links.length)
      return invalid("PM center-to-machine links must be explicit, unique and unambiguous.");
  }
  const assessments = [], suggestions = [];
  for (const center of scenario.centers) {
    if (center.id === operation.center) continue;
    const blocked = [], unknown = [], notes = [];
    if (!DEMO_CENTER_OPTIONS.includes(center.id))
      blocked.push("Work center is not registered in the existing browser demo.");
    const cap = center.capability;
    if (cap?.operation !== operation.name || cap?.supported !== true) {
      if (cap?.supported === false && cap.operation === operation.name)
        blocked.push("Operation capability explicitly marked incompatible.");
      else unknown.push("Matching operation capability has not been established.");
    }
    if (!str(cap?.sourceRef)) unknown.push("Capability evidence reference missing.");
    for (const key of ["tooling", "fixture", "material"]) {
      if (center[key] === "BLOCKED") blocked.push(key + " is blocked.");
      else if (center[key] !== "READY") unknown.push(key + " readiness is UNKNOWN.");
    }
    if (center.maintenanceState === "DOWN") blocked.push("Machine is down for maintenance.");
    else if (center.maintenanceState !== "CLEAR") unknown.push("Maintenance clearance is UNKNOWN.");
    const pmEvidence = pmContext ? pmEvidenceFor(pmContext,center.id,window) : null;
    if (pmEvidence) {
      unknown.push(...pmEvidence.concerns);
      notes.push("PM evidence is an asserted synthetic snapshot, not certified clearance.");
    }
    if (center.deliveryState === "LATE") blocked.push("Scenario cannot meet the required delivery window.");
    else if (center.deliveryState !== "ON_TIME") unknown.push("Delivery feasibility is UNKNOWN.");
    if (!str(center.capacitySourceRef)) unknown.push("Capacity evidence reference missing.");
    if (!str(center.readinessSourceRef)) unknown.push("Resource-readiness evidence reference missing.");
    const keys = ["calendarHours", "bookedHours", "queuedHours", "maintenanceHours", "setupHours", "runHours"];
    const complete = keys.every(key => hours(center[key]));
    let availableHours = null, requiredHours = null, utilizationPercent = null, slackHours = null;
    if (!complete) {
      if (keys.some(key => center[key] !== undefined && !hours(center[key])))
        blocked.push("Capacity input contains a negative or invalid hour value.");
      else unknown.push("Planning-window hours are UNKNOWN.");
    } else if (center.calendarHours === 0) {
      blocked.push("Calendar provides zero working hours.");
    } else if (center.calendarHours > (end - start) / 3600000 + 1e-6) {
      blocked.push("Calendar hours exceed the selected planning-window duration.");
    } else {
      const occupied = center.bookedHours + center.queuedHours + center.maintenanceHours;
      const rawRequired = center.setupHours + center.runHours;
      const rawAvailable = center.calendarHours - occupied;
      requiredHours = round(rawRequired);
      availableHours = round(rawAvailable);
      utilizationPercent = round(100 * occupied / center.calendarHours);
      slackHours = round(rawAvailable - rawRequired);
      if (occupied > center.calendarHours)
        blocked.push("Booked, queued and maintenance hours exceed calendar hours.");
      else if (rawAvailable < rawRequired)
        blocked.push("Insufficient remaining hours after booked, queued and maintenance load.");
    }
    const idleCandidate = center.routedOperationCount === 0;
    if (idleCandidate)
      notes.push("No routed operations reported; independently supplied capacity still required.");
    if (center.programLink)
      notes.push("Optional machining-program link is asserted only, not qualification evidence.");
    const status = blocked.length ? "EXCLUDED" : unknown.length ? "NEEDS_REVIEW" : "SCENARIO_ELIGIBLE";
    const evidenceRefs = [cap?.sourceRef,center.capacitySourceRef,center.readinessSourceRef]
      .concat(pmEvidence?.linkSourceRef || []).filter(v => str(v)).map(str);
    const assessment = {center:center.id,status,idleCandidate,blocked,unknown,notes,
      evidenceRefs,pmEvidence,availableHours,requiredHours,utilizationPercent,slackHours};
    assessments.push(assessment);
    if (status !== "SCENARIO_ELIGIBLE") continue;
    const operations = structuredClone(job.routing.operations);
    operations.find(op => op.step === step).center = center.id;
    const candidate = {partNumber:job.partNumber,revision:job.revision,operations,
      evidence:[{step,sourceRef:cap.sourceRef}]};
    // Preserve optional program evidence for the existing reviewer; never infer a link.
    if (center.programLink != null) candidate.programLinks = [structuredClone(center.programLink)];
    const routingReview = reviewRoutingCandidate(job,candidate);
    if (routingReview.status !== "REVIEW_REQUIRED") continue;
    suggestions.push({center:center.id,idleCandidate,availableHours,requiredHours,
      utilizationPercent,slackHours,evidenceRefs,pmEvidence,candidate,routingReview,
      canAutoApply:false,scenarioOnly:true});
  }
  suggestions.sort((a,b) => Number(b.idleCandidate) - Number(a.idleCandidate) ||
    b.slackHours - a.slackHours || a.center.localeCompare(b.center));
  suggestions.forEach((suggestion,index) => {suggestion.rank = index + 1;});
  return {status:suggestions.length ? "SCENARIO_CANDIDATES" : "NO_ELIGIBLE_ALTERNATIVES",
    proposalOnly:true,canAutoApply:false,window:{start:window.start,end:window.end},
    operation:{step:operation.step,name:operation.name,currentCenter:operation.center},
    assessments,suggestions,issues:[],limitations:[...limitations]};
}
