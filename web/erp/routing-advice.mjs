/* Read-only assessment of a proposed change to the existing Axiom routing.
 * Input can be a BEAN-generated proposal, but this module NEVER invokes BEAN,
 * edits a job, verifies a drawing/program, or authorizes manufacturing release.
 * The existing EWI routing validator remains authoritative for draft saves.
 */
const text = value => typeof value === "string" ? value.trim() : "";
const signature = op => JSON.stringify([
  text(op.step), text(op.name), text(op.center), text(op.check), op.instructions
]);
const empty = (status, issues) => ({
  status, proposalOnly: true, canAutoApply: false, changes: [],
  issues, programAssociations: [],
  limitations: ["Candidate evidence is caller-supplied, not independently verified.",
    "Work-center capacity and program compatibility are not connected or certified.",
    "Draft saving, EWI validation, and explicit human review remain separate."]
});

/** Compare a proposed operation list against the job's canonical routing.
 * evidence: [{step,sourceRef}] is an asserted citation, not a verified drawing.
 * programLinks: optional [{step,partNumber,revision,center,programId,sourceRef}].
 */
export function reviewRoutingCandidate(job, candidate) {
  if (!job || !Array.isArray(job.routing?.operations))
    return empty("INVALID", ["Existing job routing is unavailable."]);
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate) ||
      !Array.isArray(candidate.operations) || candidate.operations.length < 1 ||
      candidate.operations.length > 60)
    return empty("INVALID", ["Candidate must contain 1 to 60 operations."]);
  if (candidate.partNumber !== job.partNumber || candidate.revision !== job.revision)
    return empty("INVALID", ["Candidate part number or revision differs from the selected job."]);
  if (job.routing.revision !== job.revision)
    return empty("INVALID", ["Existing routing revision differs from the job revision."]);
  const original = job.routing.operations;
  const steps = new Set();
  for (const op of candidate.operations) {
    if (!op || typeof op !== "object" || Array.isArray(op) || !text(op.step) ||
        !text(op.name) || !text(op.center) || !Array.isArray(op.instructions) ||
        steps.has(text(op.step)))
      return empty("INVALID", ["Candidate contains incomplete or duplicate operations."]);
    steps.add(text(op.step));
  }
  const previous = new Map(original.map((op, i) => [text(op.step), {op, index:i}]));
  const current = new Map(candidate.operations.map((op, i) => [text(op.step), {op, index:i}]));
  const refs = new Map();
  for (const item of Array.isArray(candidate.evidence) ? candidate.evidence : []) {
    if (!item || !text(item.step) || !text(item.sourceRef)) continue;
    const key = text(item.step);
    refs.set(key, [...(refs.get(key) || []), text(item.sourceRef)]);
  }
  const changes = [];
  for (const [step, {op, index}] of current) {
    const before = previous.get(step);
    const kind = !before ? "ADDED" : signature(op) !== signature(before.op) ? "MODIFIED" :
      index !== before.index ? "REORDERED" : null;
    if (kind) changes.push({step, kind, evidenceRefs: refs.get(step) || [],
      capabilityUnverified: !before || text(op.center) !== text(before.op.center)});
  }
  for (const [step] of previous) {
    if (!current.has(step)) changes.push({step, kind:"REMOVED", evidenceRefs:refs.get(step) || [],
      capabilityUnverified:false});
  }
  const issues = changes.filter(x => !x.evidenceRefs.length)
    .map(x => `Operation ${x.step} (${x.kind}) lacks a source reference.`);
  if (changes.some(x => x.capabilityUnverified))
    issues.push("New or changed work-center assignments require independent capability verification.");
  const programAssociations = (Array.isArray(candidate.programLinks) ? candidate.programLinks : [])
    .map(link => {
      const op = current.get(text(link?.step))?.op;
      const matches = !!op && text(link?.partNumber) === job.partNumber &&
        text(link?.revision) === job.revision && text(link?.center) === text(op.center) &&
        !!text(link?.programId) && !!text(link?.sourceRef);
      return {step:text(link?.step), programId:text(link?.programId),
        status:matches ? "ASSERTED_REFERENCE_ONLY" : "MISMATCH_OR_INCOMPLETE"};
    });
  if (programAssociations.some(x => x.status !== "ASSERTED_REFERENCE_ONLY"))
    issues.push("One or more optional machining-program associations do not match this candidate.");
  const result = empty(changes.length ? (changes.some(x => !x.evidenceRefs.length) ?
    "NEEDS_EVIDENCE" : "REVIEW_REQUIRED") : "NO_CHANGE", issues);
  result.changes = changes;
  result.programAssociations = programAssociations;
  return result;
}
