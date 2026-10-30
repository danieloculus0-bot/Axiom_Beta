import {EXAMPLES, evaluatePacket, startSession, stopSession, durationSeconds, summarize, sessionsCsv} from "./engine.mjs";

const $ = id => document.getElementById(id);
const STORE = "axiom_ewi_public_demo_sessions_v1";
const jobs = EXAMPLES.map(record => structuredClone(record));
let job = jobs[0];
let selectedStep = job.routing.operations[0].step;
let zoom = 100;
let sessions = [];
let storageEnabled = false;
let lastMessage = "";

function readStorage() {
  try {
    const raw = localStorage.getItem(STORE);
    // No real staff data or confidential records should ever be entered here.
    if (raw && raw.length < 2500000) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        sessions = parsed.filter(s =>
          s && typeof s === "object" &&
          typeof s.id === "string" && s.id.length < 100 &&
          typeof s.employee === "string" && s.employee.length <= 32 &&
          typeof s.jobId === "string" && typeof s.step === "string" &&
          typeof s.jobNumber === "string" && typeof s.partNumber === "string" &&
          typeof s.operation === "string" && typeof s.start === "string" &&
          Number.isFinite(Date.parse(s.start)) &&
          (s.end === null || (typeof s.end === "string" &&
            Number.isFinite(Date.parse(s.end)) && Date.parse(s.end) >= Date.parse(s.start)))
        ).slice(-2000);
      }
    }
    const probe = STORE + "_probe";
    localStorage.setItem(probe, "ok");
    localStorage.removeItem(probe);
    storageEnabled = true;
  } catch {
    storageEnabled = false;
    sessions = [];
  }
}

function persist() {
  if (!storageEnabled) return;
  try { localStorage.setItem(STORE, JSON.stringify(sessions)); }
  catch {
    storageEnabled = false;
    showMessage("Browser storage unavailable. This session will not survive a refresh.", true);
  }
}

function formatClock(totalSeconds) {
  const n = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  return [Math.floor(n/3600), Math.floor(n%3600/60), n%60].map(v=>String(v).padStart(2,"0")).join(":");
}
function localTime(iso) {
  if (!iso) return "RUNNING";
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d.toLocaleString(undefined,{dateStyle:"medium",timeStyle:"medium"}) : "INVALID";
}
function activeOperator() {
  const operator = $("employee").value.trim().toUpperCase();
  return sessions.find(s=>s.employee===operator&&!s.end) ?? null;
}
function showMessage(message, error=false) {
  lastMessage = message;
  const target = $("clock-message");
  target.textContent = message;
  target.className = error ? "message error" : "message";
}

function renderJob() {
  const issues = evaluatePacket(job);
  $("job-number").textContent = job.jobNumber;
  $("part-number").textContent = job.partNumber + " / " + job.revision;
  $("part-desc").textContent = "Fictional training example";
  $("order-qty").textContent = job.quantity;
  $("drawing-id").textContent = job.drawing.number;
  $("drawing-rev").textContent = job.drawing.revision;
  $("drawing-state").textContent = "Synthetic / illustrative";
  $("operation-count").textContent = job.routing.operations.length + " operations";
  $("routing-source").textContent = "Fictional routing / " + job.routing.revision;
  $("packet-status").className = "pill " + (issues.length ? "warning" : "positive");
  $("packet-status").textContent = issues.length ? "REVIEW REQUIRED / CLOCK BLOCKED" : "Demo checks passed";
  const alerts = $("alerts");
  alerts.replaceChildren();
  if (issues.length) {
    const headline = document.createElement("strong");
    headline.textContent = "STOP / SOURCE CONFLICT";
    alerts.append(headline);
    for (const issue of issues) {
      const p = document.createElement("div");
      p.textContent = "• " + issue;
      alerts.append(p);
    }
    alerts.classList.add("visible");
  } else alerts.classList.remove("visible");
  const template = $("drawing-" + job.id);
  $("drawing-content").replaceChildren(template.content.cloneNode(true));
  zoom = 100;
  updateZoom();
  renderRouting();
  updateClock();
}

function renderRouting() {
  const parent = $("route-list");
  parent.replaceChildren();
  for (const op of job.routing.operations) {
    const selected = selectedStep === op.step;
    const card = document.createElement("div");
    card.className = "route-item" + (selected ? " selected" : "");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "route-button";
    btn.setAttribute("aria-expanded", String(selected));
    const left = document.createElement("span");
    const step = document.createElement("span");
    step.className = "step";
    step.textContent = op.step;
    const name = document.createElement("b");
    name.textContent = op.name;
    left.append(step, name);
    const center = document.createElement("span");
    center.className = "op-center";
    center.textContent = op.center;
    btn.append(left,center);
    btn.addEventListener("click", () => {
      selectedStep = op.step;
      renderRouting();
      updateClock();
    });
    card.append(btn);
    const detail = document.createElement("div");
    detail.className = "route-detail";
    const label = document.createElement("div");
    label.className = "route-tag";
    label.textContent = "SYNTHETIC ROUTING / STEP " + op.step + " / " + op.center;
    const list = document.createElement("ol");
    for (const line of op.instructions) {
      const li = document.createElement("li");
      li.textContent = line;
      list.append(li);
    }
    const inspection = document.createElement("div");
    inspection.className = "inspection";
    inspection.textContent = "Required check (example): " + op.check;
    detail.append(label,list,inspection);
    card.append(detail);
    parent.append(card);
  }
  const selected = job.routing.operations.find(op => op.step === selectedStep);
  $("selected-operation").textContent = selected ? selected.step + " · " + selected.name : "No operation selected";
  $("selected-check").textContent = selected ? selected.check : "Select a routing operation.";
}

function updateZoom() {
  $("zoom-label").textContent = zoom + "%";
  $("drawing-content").style.width = zoom + "%";
  $("zoom-out").disabled = zoom <= 75;
  $("zoom-in").disabled = zoom >= 200;
}

function updateClock() {
  const now = Date.now();
  const operatorActive = activeOperator();
  const issues = evaluatePacket(job);
  const thisJob = sessions.filter(s=>s.jobId===job.id);
  const running = thisJob.filter(s=>!s.end);
  const selected = job.routing.operations.find(op=>op.step===selectedStep);
  const jobSeconds = thisJob.reduce((sum,s)=>sum+durationSeconds(s,now),0);
  $("clock-total").textContent = formatClock(jobSeconds);
  $("active-label").textContent = running.length ? running.length + " active local session(s)" : "No active clocks on this job";
  $("session-timer").textContent = operatorActive ? formatClock(durationSeconds(operatorActive,now)) : "00:00:00";
  $("session-indicator").textContent = operatorActive ?
    "CLOCKED IN · " + operatorActive.jobNumber + " · STEP " + operatorActive.step : "READY TO CLOCK IN";
  $("clock-start").disabled = !!operatorActive || issues.length>0 || !selected;
  $("clock-stop").disabled = !operatorActive;
  $("clock-stop").textContent = operatorActive ? "Clock OUT · " + operatorActive.step : "Clock OUT";
  return operatorActive;
}

function download(content,mime,filename) {
  const blob = new Blob([content],{type:mime});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function renderHistory() {
  const totals = summarize(sessions);
  $("stat-sessions").textContent = totals.total;
  $("stat-active").textContent = totals.active;
  $("stat-complete").textContent = totals.completed;
  $("stat-hours").textContent = formatClock(totals.completedSeconds);
  const body = $("history-body");
  body.replaceChildren();
  if (!sessions.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan=7;
    td.textContent = "No clock events yet. Return to the operator workbench and clock into a sample operation.";
    tr.append(td);
    body.append(tr);
  }
  for (const s of [...sessions].reverse()) {
    const tr = document.createElement("tr");
    const cols = [s.employee, s.jobNumber, s.step + " · " + s.operation,
                  localTime(s.start), s.end ? localTime(s.end) : "RUNNING",
                  formatClock(durationSeconds(s)), s.end ? "STOPPED · LOCAL" : "ACTIVE · LOCAL"];
    for (const value of cols) {
      const cell=document.createElement("td");
      cell.textContent=value;
      tr.append(cell);
    }
    body.append(tr);
  }
  $("storage-status").textContent = storageEnabled ?
    "Saved only to this browser's localStorage. No server or ERP transmission. Private/shared browsing can remove these records." :
    "Browser storage is disabled. Clock events work during this tab session only; exporting is recommended.";
}

function navigate() {
  const view = location.hash === "#sessions" ? "sessions" : location.hash === "#about" ? "about" : "workbench";
  for (const name of ["workbench","sessions","about"]) {
    $(name+"-view").classList.toggle("active",name===view);
    $("nav-"+name).classList.toggle("active",name===view);
  }
  if (view==="sessions") renderHistory();
}

function install() {
  readStorage();
  $("job-select").addEventListener("change", e=>{
    job = jobs.find(j=>j.id===e.target.value) || jobs[0];
    selectedStep = job.routing.operations[0].step;
    renderJob();
    showMessage("");
  });
  $("employee").addEventListener("input",()=>{updateClock();showMessage("");});
  $("zoom-out").addEventListener("click",()=>{zoom=Math.max(75,zoom-25);updateZoom();});
  $("zoom-in").addEventListener("click",()=>{zoom=Math.min(200,zoom+25);updateZoom();});
  $("zoom-reset").addEventListener("click",()=>{zoom=100;updateZoom();});
  $("print-drawing").addEventListener("click",()=>window.print());

  $("clock-start").addEventListener("click",()=>{
    try {
      const updated = startSession(sessions,{
        id:crypto.randomUUID(),employee:$("employee").value,job,
        step:selectedStep,timestamp:new Date().toISOString()
      });
      sessions = updated;
      persist();
      showMessage("Clock IN saved locally for " + $("employee").value.trim().toUpperCase() + ". Not sent to JobBOSS².");
    } catch (err) {showMessage(err.message,true);}
    updateClock();
  });
  $("clock-stop").addEventListener("click",()=>{
    try {
      const current = activeOperator();
      if (!current) throw Error("No active session for this operator code");
      sessions = stopSession(sessions,{
        id:current.id,employee:$("employee").value,timestamp:new Date().toISOString()
      });
      persist();
      showMessage("Clock OUT saved locally. Time ticket NOT posted to ERP.");
    } catch (err) {showMessage(err.message,true);}
    updateClock();
  });
  $("export-csv").addEventListener("click",()=>download(
    sessionsCsv(sessions),"text/csv;charset=utf-8","axiom-ewi-demo-clocking.csv"
  ));
  $("export-json").addEventListener("click",()=>download(
    JSON.stringify({schema:"axiom.ewi.browser.demo.v1",demo_only:true,erp_connected:false,
      exported_utc:new Date().toISOString(),sessions},null,2),
    "application/json","axiom-ewi-demo-clocking.json"
  ));
  $("clear-history").addEventListener("click",()=>{
    if (!confirm("Erase all local EWI demo clock records from this browser? This cannot be undone.")) return;
    sessions=[];
    persist();
    renderHistory();
    updateClock();
  });
  window.addEventListener("hashchange",navigate);
  window.addEventListener("storage",event=>{
    if (event.key===STORE) {readStorage();updateClock();renderHistory();}
  });
  setInterval(()=>{updateClock();if(location.hash==="#sessions")renderHistory();},1000);
  renderJob();
  navigate();
}
install();
