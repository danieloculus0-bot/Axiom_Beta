/* Browser-local, human-initiated demonstration association between an existing
 * PM machine and an existing Axiom work center. No real asset, approval, capacity
 * or machine qualification is implied. The PM record remains the sole store.
 */
import {validatePm,getMachine} from "./pm.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";

const fail = message => {throw Error(message);};
const clone = value => structuredClone(value);
const syntheticRef = value => typeof value === "string" && /^SYN-[A-Z0-9-]{1,60}$/.test(value);
const demoReviewer = value => typeof value === "string" && /^DEMO-[A-Z0-9-]{1,20}$/.test(value);
const validTime = value => typeof value === "string" &&
  /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));

/** Record a reviewed fictional association, or explicitly remove one with centerId:null.
 * This is a pure PM-state update, not a live ERP write or verified authorization.
 * The caller must independently establish a real user's authority in production.
 */
export function reviewPmWorkCenterAssociation(pm,{
  machineId,centerId,sourceRef,reviewedBy,at
}={}) {
  validatePm(pm);
  if (!demoReviewer(reviewedBy)) fail("A fictional reviewer code is required.");
  if (!syntheticRef(sourceRef)) fail("Use a fictional SYN- evidence reference.");
  if (!validTime(at)) fail("An explicit offset-aware review timestamp is required.");
  const machine=getMachine(pm,machineId);
  if (!machine || machine.active !== true) fail("Select an active existing fictional PM machine.");
  if (centerId !== null && !DEMO_CENTER_OPTIONS.includes(centerId))
    fail("Select an existing registered fictional work center, or null to unlink.");
  if (centerId !== null && pm.machines.some(other =>
      other?.id !== machineId && other?.workCenterLink?.centerId === centerId))
    fail("That work center is already associated with another PM machine.");
  const previous=machine.workCenterLink?.centerId ?? null;
  if (previous === centerId) fail("Association is unchanged; no review event recorded.");
  const next=clone(pm);
  const target=getMachine(next,machineId);
  if (centerId === null) delete target.workCenterLink;
  else target.workCenterLink={centerId,sourceRef,reviewedBy,reviewedAt:at,
    reviewState:"DEMO_REVIEWED"};
  next.workCenterLinkHistory=[...(next.workCenterLinkHistory||[]),{
    machineId,previousCenterId:previous,centerId,sourceRef,reviewedBy,at,
    kind:centerId===null?"DEMO_UNLINK":"DEMO_LINK_REVIEW"
  }];
  return {pm:next,change:next.workCenterLinkHistory.at(-1),canAutoRelease:false};
}
