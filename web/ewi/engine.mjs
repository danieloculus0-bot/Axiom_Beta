/* Axiom browser EWI engine. All built-in records are invented.
 * Clock events are real browser-local timestamps, never ERP time tickets.
 */
export const EXAMPLES = [
  {
    id: "sample-1001", jobNumber: "DEMO-4102", partNumber: "SYN-BRACKET-12",
    revision: "C", quantity: 36, status: "OPEN", due: "Training example",
    drawing: {number: "SYN-DWG-12", revision: "C", status: "RELEASED", source: "SYNTHETIC EXAMPLE", digest: null},
    routing: {revision: "C", source: "SYNTHETIC EXAMPLE", operations: [
      {step: "10", name: "Laser cut blank", center: "LASER-01",
       instructions: ["Verify material callout against the drawing before cutting.", "Cut outline and holes to the indicated dimensions.", "Deburr edges and identify the lot."],
       check: "Confirm cut profile, hole count, and edge condition."},
      {step: "20", name: "Form flange", center: "PRESS-02",
       instructions: ["Check tool setup against the drawing.", "Form to the noted 90° angle.", "Check the first piece before continuing."],
       check: "Record first-piece angle and flange dimension."},
      {step: "30", name: "Weld and clean", center: "WELD-03",
       instructions: ["Clean weld area and verify joint orientation.", "Apply welds at the locations indicated in the synthetic drawing.", "Inspect visible discontinuities before passing work on."],
       check: "Operator checks weld location and visual condition."},
      {step: "40", name: "Final inspection", center: "QC-01",
       instructions: ["Confirm the part identity and drawing revision.", "Measure critical dimensions shown on the drawing.", "Record inspection results in the applicable quality system."],
       check: "Inspection signoff is separate and NOT implemented in this browser demo."}
    ]}
  },
  {
    id: "sample-1002", jobNumber: "DEMO-4103", partNumber: "SYN-MOUNT-07",
    revision: "B", quantity: 12, status: "OPEN", due: "Training example",
    drawing: {number: "SYN-DWG-07", revision: "A", status: "RELEASED", source: "SYNTHETIC EXAMPLE", digest: null},
    routing: {revision: "B", source: "SYNTHETIC EXAMPLE", operations: [
      {step: "10", name: "Cut mount", center: "LASER-01",
       instructions: ["Check the approved version before cutting.", "Cut the blank."],
       check: "First-piece verification required."},
      {step: "20", name: "Finish", center: "FINISH-01",
       instructions: ["Prepare material.", "Apply finish."],
       check: "Check surface condition."}
    ]}
  }
];

export function normalizeRouting(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw Error("Routing JSON must be an object");
  const field = (v, name, max = 120) => {
    if (typeof v !== "string" || !v.trim() || v.length > max) throw Error(name + " is missing or too long");
    return v.trim();
  };
  const jobNumber = field(raw.jobNumber, "jobNumber");
  const partNumber = field(raw.partNumber, "partNumber");
  const revision = field(raw.revision, "revision", 30);
  const operations = raw.operations;
  if (!Array.isArray(operations) || operations.length < 1 || operations.length > 60) throw Error("Provide 1 to 60 routed operations");
  const seen = new Set();
  const clean = operations.map((op, i) => {
    if (!op || typeof op !== "object" || Array.isArray(op)) throw Error("Invalid operation " + (i + 1));
    const step = field(String(op.step ?? ""), "operation step", 24);
    if (seen.has(step)) throw Error("Duplicate routed step " + step);
    seen.add(step);
    const lines = op.instructions;
    if (!Array.isArray(lines) || !lines.length || lines.length > 12) throw Error("Operation instructions must have 1 to 12 lines");
    return {
      step, name: field(op.name, "operation name"),
      center: field(op.center, "work center"),
      instructions: lines.map(line => field(line, "instruction", 1000)),
      check: op.check == null ? "" : field(op.check, "inspection/check", 500)
    };
  });
  return {jobNumber, partNumber, revision, operations: clean};
}

export function evaluatePacket(job) {
  if (!job) return ["No job selected"];
  const issues = [];
  const drawing = job.drawing;
  const routing = job.routing;
  if (job.status !== "OPEN") issues.push("Job is not open for work");
  if (!drawing) issues.push("Drawing source missing");
  else {
    if (drawing.status !== "RELEASED" && drawing.status !== "ATTACHED") issues.push("No released or attached drawing source");
    if (drawing.revision !== job.revision) issues.push("Drawing revision " + drawing.revision + " does not match job revision " + job.revision);
  }
  if (!routing || !Array.isArray(routing.operations) || !routing.operations.length) issues.push("Routed instructions missing");
  else if (routing.revision !== job.revision) issues.push("Routing revision " + routing.revision + " does not match job revision " + job.revision);
  // BETA: preserve draft review metadata, but do not treat a pending demo
  // review as an operator clocking error. This is a synthetic browser-only
  // workbench; original interlock is kept here for future reinstatement.
  // if (routing?.reviewState === "REVIEW_REQUIRED") issues.push("Edited routing awaiting demo review");
  return issues;
}

export function startSession(sessions, {id, employee, job, step, timestamp}) {
  const operator = String(employee || "").trim().toUpperCase();
  if (!/^DEMO-[A-Z0-9]{1,16}$/.test(operator)) throw Error("Use a fictional demo operator code such as DEMO-01. Never enter actual employee IDs.");
  if (!job || evaluatePacket(job).length) throw Error("Drawing and routing checks must pass before clocking");
  if (!job.routing.operations.some(op => op.step === step)) throw Error("Selected operation does not exist on this job");
  if (sessions.some(s => s.employee === operator && !s.end)) throw Error(operator + " is already clocked in. Stop that session first.");
  if (sessions.some(s => s.id === id)) throw Error("Duplicate clock event ID");
  const at = new Date(timestamp);
  if (!Number.isFinite(at.getTime())) throw Error("Invalid start timestamp");
  return [...sessions, {
    id, employee: operator, jobId: job.id, jobNumber: job.jobNumber, partNumber: job.partNumber,
    step, operation: job.routing.operations.find(op => op.step === step).name,
    start: at.toISOString(), end: null
  }];
}

export function stopSession(sessions, {id, employee, timestamp}) {
  const operator = String(employee || "").trim().toUpperCase();
  const found = sessions.find(s => s.id === id && !s.end);
  if (!found) throw Error("Active session not found");
  if (found.employee !== operator) throw Error("Employee code does not match this active session");
  const at = new Date(timestamp);
  if (!Number.isFinite(at.getTime()) || at.getTime() < Date.parse(found.start)) throw Error("Stop time cannot precede start");
  return sessions.map(s => s.id === id ? {...s, end: at.toISOString()} : s);
}

export function durationSeconds(session, now = Date.now()) {
  const start = Date.parse(session.start);
  const end = session.end ? Date.parse(session.end) : now;
  return Math.max(0, Math.floor((end - start) / 1000));
}

export function summarize(sessions, now = Date.now()) {
  const stopped = sessions.filter(s => !!s.end);
  return {
    total: sessions.length, active: sessions.length - stopped.length,
    completed: stopped.length,
    completedSeconds: stopped.reduce((sum, s) => sum + durationSeconds(s, now), 0)
  };
}

export function sessionsCsv(sessions) {
  const heads = ["session_id","employee_code","job_number","part_number","operation_step","operation","start_utc","end_utc","duration_seconds","sync_status"];
  const escapeCell = value => {
    const string = String(value ?? "");
    // Guard against spreadsheet formula execution when a user opens the CSV.
    const safe = /^[=+@\-\t\r]/.test(string) ? "'" + string : string;
    return '"' + safe.replace(/"/g, '""') + '"';
  };
  const rows = sessions.map(s => [
    s.id, s.employee, s.jobNumber, s.partNumber, s.step, s.operation, s.start,
    s.end || "", s.end ? durationSeconds(s) : "", "LOCAL_ONLY_NOT_ERP_SYNCED"
  ]);
  return [heads, ...rows].map(row => row.map(escapeCell).join(",")).join("\r\n") + "\r\n";
}
