/* Read-only, caller-supplied planning scenario for Axiom's canonical job.routing.
 * No live capacity, PM, HR, CNC, BEAN, or scheduling integration is implied.
 * All evidence references are assertions; recommendations remain human-reviewed.
 */
import {reviewRoutingCandidate} from "./routing-advice.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";

const str = value => typeof value === "string" ? value.trim() : "";
const hours = value => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100000;
const round = value => Math.round(value * 100) / 100;
const limitations = [
  "Planning-window, capacity, readiness and evidence inputs are caller-supplied, not live or verified.",
  "Zero routed operations is not proof of free machine time, capability or qualification.",
  "Scenario hours are estimates, not measured cycle times or a released schedule.",
  "A matching program reference is optional and never proves machine qualification.",
  "Only Axiom's existing draft/review flow can handle a proposed change; no automatic apply or release."
];
const invalid = issue => ({status:"INVALID_SCENARIO",proposalOnly:true,canAutoApply:false,
  assessments:[],suggestions:[],issues:[issue],limitations:[...limitations]});

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
      .filter(v => str(v)).map(str);
    const assessment = {center:center.id,status,idleCandidate,blocked,unknown,notes,
      evidenceRefs,availableHours,requiredHours,utilizationPercent,slackHours};
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
      utilizationPercent,slackHours,evidenceRefs,candidate,routingReview,
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
