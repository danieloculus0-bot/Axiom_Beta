import {
  ERP_KEY,CLOCK_KEY,CATALOG,EXTERNAL_FIXTURES,EMULATOR_CONTRACT,QUALITY_REASONS,
  seedState,validateState,getJob,available,reservedTotal,openQuality,packetIssues,change,
  createJob,reserve,makePurchaseOrder,receivePurchaseOrder,raiseQuality,closeQuality,
  setDrawingRevision,emulatorFetchJobs,emulatorFetchRouting,syncEmulatorJob,postEmulatorTicket
} from "./engine.mjs";
import {startSession,stopSession,durationSeconds,sessionsCsv} from "../ewi/engine.mjs";
import {renderPm} from "./pm-view.mjs";
import {renderRequestDesk} from "./request-view.mjs";
import {WORKFORCE_KEY,seedWorkforce,validateWorkforce,addDemoPerson,assignDemoRole,recordDemoPulse,completeDemoTraining,nominateDemoRecognition,reviewDemoNomination,closeDemoAction} from "./workforce.mjs";
import {renderHr,renderMorale} from "./workforce-view.mjs";
import {recordDemoIncident,recordDemoSafetySurvey} from "./workforce.mjs";
import {captureQualityContext,qcdsmEvidence} from "./qcdsm.mjs";
import {renderQcdsm,qualityRcaHtml} from "./qcdsm-view.mjs";
import {recordQualityDisposition,recordQualityFollowup,closeReviewedQuality,recordQualityInspection} from "./quality-case.mjs";
import {renderQualityCase} from "./quality-case-view.mjs";
import {routingEditorHtml,readRoutingEditor} from "./routing-view.mjs";
import {editableRouting,addRouteStep,moveRouteStep,removeRouteStep,saveRoutingDraft,reviewRoutingDraft} from "./routing-edit.mjs";
import {requestMetrics,createPurchaseRequest,assignPurchaseRequest,approvePurchaseRequest,
 issueRequestPO,syncReceivedRequests,verifyPurchaseRequest,followupPurchaseRequest} from "./requests.mjs";
import {installContextMenu} from "./context-ui.mjs";
import {resolveContext,contextRelated} from "./context-actions.mjs";
import {installMenu} from "./navigation-ui.mjs";
import {REPORTS,makeReport,reportCsv} from "./reports.mjs";
import {getMachine,getTask,pmOverview,createMachine,addPmTask,completePmTask,requestMaintenance,
  closeMaintenanceRequest,completionsCsv,localDay,dayAdd,
  assignMaintenanceRequest,followupMaintenanceRequest} from "./pm.mjs";

const $=id=>document.getElementById(id);
const h=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const deep=v=>structuredClone(v);
const stateViews={
 dashboard:"Command Center",jobs:"Work Orders",routing:"Routing & Planning",
 ewi:"EWI & Clocking",inventory:"Inventory",purchasing:"Purchasing",
 quality:"Quality Control",documents:"Drawing Control",pm:"PM Tracker",requests:"Request Desk",hr:"Human Resources",morale:"Morale & Recognition",qcdsm:"QCDSM Wheel",reports:"Report Center",bridge:"ERP Emulator",audit:"Event History"
};
let workforce=seedWorkforce();
let qcdsmDepartment="Assembly";
let state=seedState(),sessions=[],stored=false,selectedJobId="",selectedStep="10",operator="DEMO-01",flash="",selectedPmMachineId="",selectedReport="jobs",menu=null,selectedContext=null,selectedIntent="",selectedRequest={kind:"",id:""},routeDraft=null,selectedQualityId="";
function load(){
  try{
    const raw=localStorage.getItem(ERP_KEY);
    if(raw && raw.length<1800000) state=validateState(JSON.parse(raw));
    const clocks=localStorage.getItem(CLOCK_KEY);
    if(clocks && clocks.length<2500000){
      const data=JSON.parse(clocks);
      if(Array.isArray(data)) sessions=data.filter(s=>s&&typeof s==="object" &&
        typeof s.id==="string" && typeof s.jobId==="string" && typeof s.step==="string" &&
        typeof s.employee==="string" && /^DEMO-[A-Z0-9]{1,16}$/.test(s.employee) &&
        typeof s.jobNumber==="string" && typeof s.partNumber==="string" &&
        typeof s.operation==="string" && Number.isFinite(Date.parse(s.start)) &&
        (s.end==null || (typeof s.end==="string" && Date.parse(s.end)>=Date.parse(s.start)))
      ).slice(-2000);
    }
    const k=ERP_KEY+"_test";localStorage.setItem(k,"ok");localStorage.removeItem(k);
    stored=true;
  }catch{stored=false;state=seedState();sessions=[];}
  try{
    const raw=localStorage.getItem(WORKFORCE_KEY);
    workforce=raw&&raw.length<800000?validateWorkforce(JSON.parse(raw)):seedWorkforce();
  }catch{workforce=seedWorkforce();}
}
function persist(){
  if(!stored) return;
  try{localStorage.setItem(ERP_KEY,JSON.stringify(state));localStorage.setItem(CLOCK_KEY,JSON.stringify(sessions));localStorage.setItem(WORKFORCE_KEY,JSON.stringify(workforce));}
  catch{stored=false;flash="Local storage unavailable. Export records before refreshing.";}
}
function transact(next,message){state=next;flash=message;persist();render();}
function workforceTransact(next,type,detail,message){
  workforce=next;
  state=change(state,type,detail,()=>{});
  flash=message;persist();render();
}
function pmTransact(nextPm,type,detail,message){
  transact(change(state,type,detail,n=>{n.pm=nextPm;}),message);
}
function job(){return getJob(state,selectedJobId)||state.jobs[0];}
function stamp(t){if(!t)return "RUNNING";if(t==="DEMO SEED")return "Sample";const d=new Date(t);return Number.isFinite(d.getTime())?d.toLocaleString():"Sample";}
function hours(seconds){const s=Math.floor(seconds);return [Math.floor(s/3600),Math.floor(s%3600/60),s%60].map(v=>String(v).padStart(2,"0")).join(":");}
function currentView(){const view=location.hash.slice(1);return Object.hasOwn(stateViews,view)?view:"dashboard";}
function status(s){
  const str=String(s||"");
  const kind=/^(OPEN|ORDERED|RELEASED|RECEIVED|CLOSED|SIMULATED ACCEPTED)$/.test(str)?"ok":/^(BLOCKED|HOLD|ERROR)$/.test(str)?"bad":"warn";
  return '<span class="tag '+kind+'">'+h(str)+'</span>';
}
function heading(eyebrow,title,sub,action=""){
  return '<div class="lead"><div><div class="eyebrow">'+h(eyebrow)+'</div><h1>'+h(title)+'</h1><p class="subtitle">'+h(sub)+'</p></div>'+action+'</div>';
}
function metric(label,val,detail=""){return '<div class="metric"><small>'+h(label)+'</small><strong>'+h(val)+'</strong><em>'+h(detail)+'</em></div>';}
function moduleLink(view,label,detail){
  return '<a href="#'+view+'"><b>'+h(label)+'</b><span>'+h(detail)+'</span></a>';
}
function contextAttrs(type,id){return '"data-ctx-type="'+h(type)+'" data-ctx-id="'+h(id)+'" tabindex="0" title="Right-click for Open with"';}
function ctxSpan(type,id,text){return '<span class="context-record" data-ctx-type="'+h(type)+'" data-ctx-id="'+h(id)+'" tabindex="0" title="Right-click for Open with">'+h(text)+'</span>';}
function table(headers,rows,empty="No synthetic records yet.",contexts=[]){
  if(!rows.length)return '<div class="empty">'+h(empty)+'</div>';
  return '<div class="tablewrap"><table><thead><tr>'+headers.map(x=>'<th>'+h(x)+'</th>').join("")+'</tr></thead><tbody>'+rows.map((r,i)=>{
    const record=contexts[i],attr=record?contextAttrs(record.type,record.id):"";
    return '<tr class="'+(record?"context-record-row":"")+'" '+attr+'>'+r.map(x=>'<td>'+x+'</td>').join("")+'</tr>';
  }).join("")+'</tbody></table></div>';
}
function jobLink(j,view="routing"){return '<a class="cell-link" href="#'+view+'" data-job="'+h(j.id)+'">'+h(j.jobNumber)+'</a>';}
function jobState(j){return packetIssues(state,j.id).length?'<span class="tag warn">REVIEW</span>':'<span class="tag ok">READY</span>';}
function contextBanner(){
  if(!selectedContext)return "";
  const info=resolveContext(state,selectedContext.type,selectedContext.id);
  if(!info){selectedContext=null;selectedIntent="";return "";}
  return '<div class="context-trail"><span class="context-trail-icon">⌕</span><b>Open with:</b> '+h(info.label)+
    '<span class="small muted">'+h(info.type.replace(/_/g," "))+', fictional browser record</span>'+
    '<button class="action secondary" type="button" data-action="clear-record-context">Clear context</button></div>';
}
function contextSelection(view,rows){
  const ids=contextRelated(state,selectedContext,view);
  if(!ids)return rows;
  if(view==="jobs")return rows.filter(row=>ids.includes(row.id));
  if(view==="inventory")return rows.filter(row=>ids.includes(row.id));
  if(view==="purchasing")return rows.filter(row=>ids.includes(row.itemId)&&(!selectedContext||selectedContext.type!=="po"||row.id===selectedContext.id));
  if(view==="quality")return rows.filter(row=>ids.includes(row.jobId)&&(!selectedContext||selectedContext.type!=="quality"||row.id===selectedContext.id));
  return rows;
}
function openContext(record,action){
  const c=resolveContext(state,record.type,record.id);
  if(!c)return;
  selectedContext=record;selectedIntent=action.intent;
  if(c.jobId)rememberJob(c.jobId);
  else if(c.relatedJobs.length&&["routing","ewi","documents","quality"].includes(action.view))rememberJob(c.relatedJobs[0]);
  if(c.machineId)selectedPmMachineId=c.machineId;
  if(record.type==="purchase_request")selectedRequest={kind:"purchase",id:record.id};
  if(record.type==="pm_request")selectedRequest={kind:"maintenance",id:record.id};
  if(action.intent==="pm-report")selectedReport="pm";
  if(action.intent==="request-report")selectedReport="requests";
  if(location.hash==="#"+action.view){render();applyContextFocus();}
  else location.hash="#"+action.view;
}
function applyContextFocus(){
  if(!selectedContext)return;
  const c=resolveContext(state,selectedContext.type,selectedContext.id);
  if(!c)return;
  let selector="";
  if(selectedIntent==="new-job"&&c.part){const select=document.querySelector('[data-form="new-job"] select[name="part"]');if(select){select.value=c.part;selector='[data-form="new-job"] input[name="quantity"]';}}
  if(selectedIntent==="new-po"&&c.itemId){const select=document.querySelector('[data-form="new-po"] select[name="item"]');if(select){select.value=c.itemId;selector='[data-form="new-po"] input[name="quantity"]';}}
  if(selectedContext.type==="pm_task"&&selectedIntent==="machine"){
    const select=document.getElementById("pm-completion-task");if(select)select.value=selectedContext.id;
  }
  if(selectedIntent==="requests")selector="#pm-request-queue";
  if(selector){const el=document.querySelector(selector);el?.scrollIntoView?.({block:"center"});if(el?.matches?.("input"))el.focus({preventScroll:true});}
}
function dashboard(){
  const active=sessions.filter(s=>!s.end).length,blocked=state.jobs.filter(j=>packetIssues(state,j.id).length).length;
  const ordered=state.purchaseOrders.filter(p=>p.status==="ORDERED").length;
  const pm=pmOverview(state.pm),req=requestMetrics(state),qcdsm=qcdsmEvidence(state,workforce,qcdsmDepartment);
  let s=heading("Overview / connected shop workflow","Manufacturing command center",
    "One fictional dataset drives the job tracker, material transactions, quality holds, routed work instructions and clocking.");
  s+='<div class="metrics">'+metric("Work orders",state.jobs.length,"Synthetic orders")+
     metric("Ready to clock",state.jobs.length-blocked,"Passes example checks")+
     metric("Active clocks",active,"Browser-local sessions")+
     metric("Open POs",ordered,"Simulated purchasing")+'</div>';
  s+='<div class="columns"><section class="panel"><div class="panel-head"><h2>Recent work orders</h2><a href="#jobs" class="action secondary">All work orders</a></div>';
  const recentJobs=state.jobs.slice().reverse().slice(0,7);
  s+=table(["Job","Part","Revision","Readiness","EWI"],recentJobs.map(j=>[
    jobLink(j),ctxSpan("part",j.partNumber,j.partNumber),h(j.revision),jobState(j),
    '<a href="#ewi" data-job="'+h(j.id)+'" class="action secondary">Open EWI</a>'
  ]),"No fictional jobs yet.",recentJobs.map(j=>({type:"job",id:j.id})));
  s+='</section><section class="panel"><h2>Production modules</h2><div class="feature">'+
    moduleLink("jobs","Jobs","Create and select orders")+
    moduleLink("ewi","Clocking","Live local timers")+
    moduleLink("routing","Routing","Work centers and steps")+
    moduleLink("quality","Quality","Create and close holds")+
    moduleLink("pm","PM Tracker","Maintenance schedules & requests")+
    moduleLink("requests","Request Desk","Track assignments and follow-ups")+
    moduleLink("hr","Human Resources","Demo roles and training")+
    moduleLink("morale","Morale","Company pulse and recognition")+
    moduleLink("qcdsm","QCDSM Wheel","Quality, Cost, Delivery, Safety & Morale")+
    moduleLink("reports","Reports","Live synthetic operational reports")+
    moduleLink("purchasing","Purchasing","Receive demo inventory")+
    moduleLink("bridge","ERP Bridge","Emulated import and time receipt")+
    '</div></section></div>';
  s+='<section class="panel"><div class="panel-head"><h2>QCDSM operating signals</h2><a class="action secondary" href="#qcdsm">Open wheel</a></div>'+
    '<div class="pills">'+status("MORALE "+(qcdsm.moraleRisk===null?"N/A":qcdsm.moraleRisk+"/100"))+
    status("SAFETY "+(qcdsm.safetyPriority===null?"N/A":qcdsm.safetyPriority+" priority"))+
    status("QUALITY "+qcdsm.quality.openHolds+" OPEN NCR")+
    '</div><p class="small">Aggregate synthetic inputs; Cost and Delivery remain N/A without reliable source baselines. Safety and overtime indicators should be reviewed during quality RCA, not assumed causal.</p></section>';
  s+='<section class="panel"><div class="panel-head"><h2>Request follow-up</h2><a href="#requests" class="action secondary">Open Request Desk</a></div>'+
    '<div class="pills">'+status(req.openPurchases+" PURCHASE REQUESTS")+
    status(req.openMaintenance+" MAINTENANCE REQUESTS")+status(req.overdue+" OVERDUE")+
    '</div><p class="small">Real browser-local request workflows use fictional records. Purchasing needs a received PO before completion.</p></section>';
  s+='<section class="panel"><div class="panel-head"><h2>Maintenance snapshot</h2><a href="#pm" class="action secondary">Open PM Tracker</a></div>'+
    '<div class="pills">'+status(pm.overdue+" OVERDUE TASKS")+' '+status(pm.dueToday+" DUE TODAY")+' '+status(pm.openRequests+" OPEN REQUESTS")+'</div>'+
    '<p class="small">'+h(pm.machines)+' generic machines · '+h(pm.tasks)+' recurring tasks. These are fictional maintenance records, not live equipment conditions.</p></section>';
  s+='<section class="panel"><div class="panel-head"><h2>Recent simulated transactions</h2><a href="#audit">Full event history</a></div>'+
    state.events.slice(-5).reverse().map(e=>'<div class="receipt"><b>'+h(e.type)+'</b> · '+h(e.detail)+' <span class="muted">('+h(stamp(e.at))+')</span></div>').join("")+'</section>';
  return s;
}
function jobsView(){
  let s=heading("Production / job management","Work orders",
    "Add a fictional work order from the prebuilt catalog, or import separate emulator jobs. No private file upload or real job data.");
  s+='<section class="panel"><h2>Create a synthetic work order</h2><form class="controls" data-form="new-job">'+
    '<label>Generic catalog item<select name="part">'+CATALOG.map(c=>'<option value="'+h(c.partNumber)+'">'+h(c.partNumber)+' · Rev '+h(c.revision)+'</option>').join("")+'</select></label>'+
    '<label>Order quantity<input type="number" name="quantity" min="1" max="1000" value="12" required></label>'+
    '<button class="action" type="submit">Create work order</button></form></section>';
  const shownJobs=contextSelection("jobs",state.jobs);
  s+='<section class="panel"><div class="panel-head"><h2>Shop order register</h2><a class="action secondary" href="#bridge">Import simulator job</a></div>'+
    table(["Work order","Part","Rev","Qty","Reserved","Source","Readiness","EWI"],shownJobs.map(j=>[
      jobLink(j,"routing"),ctxSpan("part",j.partNumber,j.partNumber),h(j.revision),h(j.quantity),h(j.reserved||0),
      h(j.origin),jobState(j),
      '<a class="action secondary" href="#ewi" data-job="'+h(j.id)+'">Open</a>'
    ]),"No related fictional jobs for this record.",shownJobs.map(j=>({type:"job",id:j.id})))+'</section>';
  return s;
}
function routingView(){
  const j=job(),issues=packetIssues(state,j.id);
  let s=heading("Production engineering / routing","Routing & work centers",
    "Operation records are connected to the selected work order, drawing revision, material reservation and EWI clock.",'<a href="#ewi" class="action">Operator workbench</a>');
  s+='<div class="metrics">'+metric("Selected job",j.jobNumber,j.partNumber)+metric("Operations",j.routing.operations.length,"Fictional work centers")+
    metric("Job revision",j.revision,"Synthetic drawing control")+metric("Material reserved",j.reserved+" / "+j.quantity,"Units")+'</div>';
  if(issues.length)s+='<div class="alert"><b>Work packet is not ready:</b> '+issues.map(h).join("; ")+'</div>';
  else s+='<div class="success"><b>Sample source checks passed.</b> This does not constitute manufacturing approval.</div>';
  s+='<div class="columns"><section class="panel"><h2>Routed operations</h2><div class="steps">'+j.routing.operations.map(op=>
    '<div class="step-card"><div class="panel-head"><h3>STEP '+h(op.step)+' · '+h(op.name)+'</h3>'+status(op.center)+'</div>'+
    '<ol>'+op.instructions.map(x=>'<li>'+h(x)+'</li>').join("")+'</ol><small>EXAMPLE CHECK: '+h(op.check)+'</small></div>'
  ).join("")+'</div></section><section class="panel"><h2>Work order links</h2><p>All modules use the same selected job context.</p>'+
    '<div class="feature">'+moduleLink("documents","Drawing","View / change sample revision")+
    moduleLink("inventory","Materials","Reserve generic stock")+
    moduleLink("quality","Quality","Review holds")+
    moduleLink("ewi","EWI","Clock operation")+'</div>'+
    '<h3 style="margin-top:20px">Source labels</h3><p>Routing: '+h(j.routing.source)+'<br>Drawing: '+h(j.drawing.number)+' / Rev '+h(j.drawing.revision)+'</p></section></div>';
  s+=routingEditorHtml(j,routeDraft?.jobId===j.id?routeDraft.operations:null,sessions.some(session=>session.jobId===j.id));
  return s;
}
function drawingSvg(j){
  const title=h(j.drawing.number),rev=h(j.drawing.revision),part=h(j.partNumber);
  return '<svg viewBox="0 0 720 420" role="img" aria-label="Illustrative generic plate drawing. Not for fabrication." xmlns="http://www.w3.org/2000/svg">'+
    '<rect width="720" height="420" fill="#eff4f4"/>'+
    '<g fill="none" stroke="#26404a" stroke-width="2"><rect x="123" y="104" width="328" height="167" rx="4"/>'+
    '<circle cx="175" cy="145" r="13"/><circle cx="399" cy="145" r="13"/><circle cx="175" cy="230" r="13"/><circle cx="399" cy="230" r="13"/>'+
    '<path d="M287 100V276 M120 188H454" stroke-dasharray="9 5" stroke="#8ca3ae"/>'+
    '<path d="M123 80V97M451 80V97M123 87H451 M104 104H117M104 271H117M110 104V271"/>'+
    '<rect x="460" y="308" width="245" height="95"/><path d="M460 346H705M460 378H705M638 346V403"/></g>'+
    '<g font-family="Arial,sans-serif" fill="#20333e"><text x="287" y="72" text-anchor="middle" font-size="16">120 REF</text>'+
    '<text x="97" y="186" font-size="15" text-anchor="middle" transform="rotate(-90 97 186)">60 REF</text>'+
    '<text x="123" y="42" font-size="15" font-weight="bold">ORIGINAL GENERIC PART SCHEMATIC</text>'+
    '<text x="472" y="330" font-size="12">'+title+'</text>'+
    '<text x="472" y="368" font-size="13">'+part+'</text>'+
    '<text x="653" y="367" font-size="18" font-weight="bold">'+rev+'</text>'+
    '<text x="472" y="392" font-size="10">NO PRODUCTION AUTHORITY</text>'+
    '<text x="360" y="291" text-anchor="middle" font-size="12">NOT TO SCALE · DIMENSIONS ILLUSTRATIVE</text>'+
    '<text x="360" y="209" text-anchor="middle" font-size="28" font-weight="900" fill="#b86770" opacity=".42">DEMO DRAWING ONLY</text></g></svg>';
}
function clockView(){
  const j=job(),issues=packetIssues(state,j.id),active=sessions.find(s=>s.employee===operator&&!s.end);
  const onJob=sessions.filter(s=>s.jobId===j.id),stepExists=j.routing.operations.some(o=>o.step===selectedStep);
  if(!stepExists)selectedStep=j.routing.operations[0].step;
  const elapsed=onJob.reduce((sum,s)=>sum+durationSeconds(s),0);
  let s=heading("Workstation / integrated operator terminal","Electronic work instructions & clocking",
    "Drawing and routed instructions stay together. Clock in/out timestamps are real and browser-local; the companion ERP emulator can issue explicit simulated receipts.");
  s+='<div class="metrics">'+metric("Work order",j.jobNumber,"Fictional")+
    metric("Current part",j.partNumber,"Revision "+j.revision)+
    metric("Operations",j.routing.operations.length,"Synthetic routing")+
    metric("Elapsed local time",hours(elapsed),"Includes active sessions")+'</div>';
  s+=issues.length?'<div class="alert"><b>CLOCKING BLOCKED:</b> '+issues.map(h).join(" · ")+'</div>':
    '<div class="success">Drawing / routing revision, example material reservation, and quality hold checks passed.</div>';
  s+='<div class="columns"><section class="panel"><div class="panel-head"><h2>Source A · Generic drawing</h2>'+status(j.drawing.status)+'</div>'+
     '<div class="diagram">'+drawingSvg(j)+'</div><p class="small">Original synthetic vector illustration. No engineering approval, PDF release, customer source or manufacturing authority.</p>'+
     '<a href="#documents" class="action secondary">Review drawing control</a></section>'+
     '<section class="panel"><div class="panel-head"><h2>Source B · Routed instructions</h2><span class="tag">'+h(j.routing.revision)+'</span></div>'+
     '<div class="steps">'+j.routing.operations.map(op=>
     '<div class="step-card"><h3>'+h(op.step)+' · '+h(op.name)+'</h3><small>'+h(op.center)+'</small>'+
     '<ol>'+op.instructions.map(x=>'<li>'+h(x)+'</li>').join("")+'</ol>'+
     '<p class="small">Required example check: '+h(op.check)+'</p></div>').join("")+'</div></section></div>';
  s+='<section class="panel"><div class="panel-head"><h2>Operator clock terminal</h2><span class="tag warn">LOCAL ONLY · NO JOBBOSS POSTING</span></div>'+
    '<div class="twocol"><div class="controls"><label>Fictional operator code<input id="operator-code" maxlength="21" value="'+h(operator)+'" placeholder="DEMO-01"></label>'+
    '<label>Routed operation<select id="clock-step">'+j.routing.operations.map(op=>
    '<option value="'+h(op.step)+'" '+(op.step===selectedStep?"selected":"")+'>'+h(op.step)+' · '+h(op.name)+'</option>').join("")+'</select></label></div>'+
    '<div><small class="sub-label">CURRENT OPERATOR SESSION</small><div class="clock-readout" data-live-clock>'+
    (active?hours(durationSeconds(active)):"00:00:00")+'</div><div class="small">'+(active?
    h(active.jobNumber+" / Step "+active.step)+" · ACTIVE":"No active clock for "+h(operator))+'</div></div></div>'+
    '<div class="controls" style="margin-top:16px"><button class="action" data-action="clock-in" '+(issues.length||active?"disabled":"")+
    '>Clock IN</button><button class="action danger" data-action="clock-out" '+(!active?"disabled":"")+'>Clock OUT</button>'+
    '<a href="#audit" class="action secondary">Local event history</a></div></section>';
  s+='<section class="panel"><h2>Clock history for '+h(j.jobNumber)+'</h2>'+
    table(["Operator","Operation","Start","Stop","Duration","Simulator receipt"],onJob.slice().reverse().map(c=>[
    h(c.employee),h(c.step+" / "+c.operation),h(stamp(c.start)),h(stamp(c.end)),h(hours(durationSeconds(c))),
    status(state.receipts.some(r=>r.sessionId===c.id)?"SIMULATED":"LOCAL ONLY")
  ]),"No sessions on this fictional job.")+
    '<p class="small">Sessions are shared with the separate EWI demonstration in the same browser. Simulated receipt is not an actual time ticket.</p></section>';
  return s;
}
function inventoryView(){
  const j=job();
  let s=heading("Material control / local demo","Inventory & allocation",
    "On-hand, reserved and available balances recalculate when you receive a PO or reserve material for a fictional job.");
  s+='<div class="metrics">'+metric("Material items",state.items.length,"Synthetic catalog")+
    metric("Reserved for current job",j.reserved+" / "+j.quantity,j.materialId)+
    metric("Available current stock",available(state,j.materialId),"After all job reservations")+
    metric("Open purchase orders",state.purchaseOrders.filter(p=>p.status==="ORDERED").length,"Pending demo receipts")+'</div>';
  const shownItems=contextSelection("inventory",state.items);
  s+='<section class="panel"><div class="panel-head"><h2>Material availability</h2><a href="#purchasing" class="action secondary">Purchasing</a></div>'+
    table(["Stock item","Description","On hand","Reserved","Available","Reorder"],shownItems.map(i=>[
      h(i.id),h(i.name),h(i.onHand+" "+i.unit),h(reservedTotal(state,i.id)),h(available(state,i.id)),
      available(state,i.id)<=i.reorder?status("LOW"):status("OK")
    ]),"No related fictional material.",shownItems.map(i=>({type:"stock",id:i.id})))+'</section>';
  const filteredStock=contextSelection("inventory",state.items);
  if(selectedContext&&filteredStock.length===1&&filteredStock[0].id!==j.materialId){
    s+='<div class="notice">This fictional material is not assigned to the currently selected job. Reserve stock only from a job that uses this material.</div>';
    return s;
  }
  s+='<section class="panel"><h2>Reserve stock for '+h(j.jobNumber)+'</h2><p>Required: '+h(j.quantity)+
    ' · Reserved: '+h(j.reserved)+' · Needed: '+h(Math.max(0,j.quantity-j.reserved))+
    ' · Available: '+h(available(state,j.materialId))+'</p>'+
    '<button class="action" data-action="reserve" '+(j.quantity===j.reserved?"disabled":"")+
    '>Reserve remaining material</button></section>';
  return s;
}
function purchasingView(){
  let s=heading("Purchasing / receiving","Purchase orders",
    "Issue fictional purchase orders, receive them into the shared inventory balance, then allocate the stock to a work order.");
  s+='<section class="panel"><h2>Issue demo PO</h2><form data-form="new-po" class="controls">'+
    '<label>Material item<select name="item">'+state.items.map(i=>'<option value="'+h(i.id)+'">'+h(i.id)+' · '+h(i.name)+'</option>').join("")+'</select></label>'+
    '<label>Quantity<input name="quantity" type="number" min="1" max="10000" required value="25"></label>'+
    '<button type="submit" class="action">Create PO</button></form><p class="small">Supplier is always FICTIONAL SUPPLIER. No real supplier names or prices.</p></section>';
  const shownPOs=contextSelection("purchasing",state.purchaseOrders);
  s+='<section class="panel"><h2>PO ledger</h2>'+table(["Purchase order","Stock item","Qty","Supplier","State","Action"],shownPOs.map(p=>[
     h(p.number),ctxSpan("stock",p.itemId,p.itemId),h(p.quantity),h(p.supplier),status(p.status),
     p.status==="ORDERED"?'<button class="action secondary" data-action="receive-po" data-id="'+h(p.id)+'">Receive</button>':h(stamp(p.receivedAt))
   ]),"No matching fictional POs. Use PO Entry above to issue one.",shownPOs.map(p=>({type:"po",id:p.id})))+'</section>';
  return s;
}
function qualityView(){
  const j=job(),open=openQuality(state,j.id);
  let s=heading("Quality management / job hold integration","Quality control",
    "Create a fictional nonconformance, review its linked job, record a sample disposition and follow-up. No production approval or signoff.");
  s+='<div class="metrics">'+metric("Quality records",state.quality.length,"Synthetic only")+
    metric("Open holds",state.quality.filter(q=>q.status==="OPEN").length,"Across all jobs")+
    metric("This job open",open.length,j.jobNumber)+metric("EWI readiness",packetIssues(state,j.id).length?"BLOCKED":"READY","Illustrative checks")+'</div>';
  s+='<section class="panel"><h2>Open demo nonconformance for '+h(j.jobNumber)+'</h2>'+
    '<form data-form="new-ncr" class="controls"><label>Fictional quality reason<select name="reason">'+
    QUALITY_REASONS.map(r=>'<option value="'+h(r)+'">'+h(r)+'</option>').join("")+
    '</select></label><button class="action danger" type="submit">Create quality hold</button></form></section>';
  const shownQuality=contextSelection("quality",state.quality);
  s+='<section class="panel"><h2>Nonconformance register</h2>'+
    table(["Record","Work order","Reason","State","Action"],shownQuality.map(q=>{
      const record=getJob(state,q.jobId);
      return [h(q.number),jobLink(record,"ewi"),h(q.reason),status(q.status),
        '<button class="action secondary" data-action="select-quality" data-id="'+h(q.id)+'">Review case</button>']
    }),"No matching fictional quality holds.",shownQuality.map(q=>({type:"quality",id:q.id})))+'</section>';
  const selected=shownQuality.find(record=>record.id===selectedQualityId)||shownQuality[0];
  s+=renderQualityCase(state,selected?.id);
  s+=qualityRcaHtml(state,workforce,qcdsmDepartment,localDay());
  return s;
}
function documentsView(){
  const j=job(),issues=packetIssues(state,j.id);
  let s=heading("Controlled documentation / teaching example","Drawing & revision control",
    "Switch a generic illustration revision to see the EWI interlock change. This simulates a record update, NOT an actual document release.");
  s+='<div class="metrics">'+metric("Selected work order",j.jobNumber,j.partNumber)+
    metric("Job revision",j.revision,"Target revision")+metric("Drawing revision",j.drawing.revision,"Illustrative only")+
    metric("Source check",issues.some(x=>x.toLowerCase().includes("drawing revision"))?"MISMATCH":"MATCH","Other holds may remain")+'</div>';
  s+='<div class="columns"><section class="panel context-record" '+contextAttrs("drawing",j.id)+'><h2>Generic drawing viewer</h2><div class="diagram">'+drawingSvg(j)+'</div>'+
    '<p class="small">Original geometric illustration. Not a file from a company, customer or manufacturing system.</p></section>'+
    '<section class="panel"><h2>Document record</h2><p>Document: <b>'+h(j.drawing.number)+'</b><br>Source: '+
    h(j.drawing.source)+'<br>Document state: '+h(j.drawing.status)+'<br>Part: '+h(j.partNumber)+'</p>'+
    '<form class="controls" data-form="drawing-rev"><label>Change example revision<select name="revision">'+
    ["A","B","C","D"].map(r=>'<option value="'+r+'" '+(r===j.drawing.revision?"selected":"")+'>'+r+'</option>').join("")+
    '</select></label><button class="action" type="submit">Apply simulated revision</button></form>'+
    '<p class="small">No actual file checksum, electronic signature or document approval occurs in this demo. Production desktop drawing control is separate.</p>'+
    '<a href="#ewi" class="action secondary">Verify clocking interlock</a></section></div>';
  return s;
}
function bridgeView(){
  let s=heading("Integrations / separate fictional upstream ERP","ERP connection emulator",
    "An explicit in-browser simulation of an external ERP adapter. Import mock jobs and submit completed LOCAL clock sessions for fake receipts. No HTTP endpoint, SQL database, ECI credentials or JobBOSS connection.");
  s+='<div class="metrics">'+metric("Mock external jobs",EXTERNAL_FIXTURES.length,"Separate fixture data")+
    metric("Imported jobs",state.jobs.filter(j=>j.origin==="SIMULATED ERP IMPORT").length,"Into Axiom local store")+
    metric("Simulated tickets",state.receipts.length,"Emulator receipts only")+
    metric("Live ERP access","NONE","Public Pages has no backend")+'</div>';
  s+='<section class="panel"><h2>Simulated external order feed</h2>'+
    table(["External order","Part","Revision","Qty","Adapter action"],emulatorFetchJobs().map(j=>[
      h(j.jobNumber),h(j.partNumber),h(j.revision),h(j.quantity),
      state.jobs.some(x=>x.jobNumber===j.jobNumber)?'<span class="tag ok">IMPORTED</span>':
      '<button class="action" data-action="sync" data-id="'+h(j.jobNumber)+'">Import to Axiom</button>'
    ]))+'<p class="small">Import also retrieves the fictional routing using the emulator contract. Real JobBOSS² API fields and access are NOT tested here.</p></section>';
  const postable=sessions.filter(x=>x.end&&!state.receipts.some(r=>r.sessionId===x.id)&&state.jobs.some(j=>j.id===x.jobId));
  s+='<section class="panel"><h2>Submit completed clock to mock ERP</h2><form data-form="mock-post" class="controls">'+
    '<label>Completed browser clock<select name="session">'+postable.map(x=>
    '<option value="'+h(x.id)+'">'+h(x.employee+" / "+x.jobNumber+" / "+x.step+" / "+hours(durationSeconds(x)))+'</option>').join("")+'</select></label>'+
    '<button type="submit" class="action" '+(!postable.length?"disabled":"")+'>Simulate time-ticket POST</button></form>'+
    (!postable.length?'<p class="small">Clock in and out of a job first. Only completed sessions appear here.</p>':'')+
    '<p class="small">This button calls local JavaScript, NOT a remote service. It returns a fictional acceptance receipt and prevents duplicate submission.</p></section>';
  s+='<section class="panel"><h2>Simulated API contract (illustrative, not ECI API)</h2>'+
    table(["Verb","Conceptual route","What is emulated"],EMULATOR_CONTRACT.map(x=>[
      '<span class="mono">'+h(x.method)+'</span>','<span class="mono">'+h(x.endpoint)+'</span>',h(x.description)
    ]))+'</section>';
  s+='<section class="panel"><h2>Emulator receipts</h2>'+
    table(["Receipt","Work order","Operator","Elapsed","State"],state.receipts.map(x=>[
      h(x.ticket),h(x.jobNumber),h(x.employee),h(hours(x.seconds)),status(x.status)
    ]),"No simulated time tickets yet.")+'</section>';
  return s;
}
function reportWithContext(id){
  const report=makeReport(state,sessions,id,localDay(),workforce);
  const selected=selectedContext&&resolveContext(state,selectedContext.type,selectedContext.id);
  if(selected&&selected.machineId&&id==="pm")report.rows=report.rows.filter(row=>row[1]===selected.machineId);
  if(selected&&selected.machineId&&id==="requests")report.rows=report.rows.filter(row=>row[1]===selected.machineId);
  return report;
}
function reportsView(){
  const selected=REPORTS.find(x=>x.id===selectedReport)||REPORTS[0];
  const report=reportWithContext(selected.id);
  let s=heading("Management / browser-local analytics","Operational report center",
    "Cross-module operational reports and the event ledger, using the same fictional ERP and workforce evidence. No private ERP or external data.");
  s+='<div class="metrics">'+metric("Available reports",REPORTS.length,"All functional")+
    metric("Selected rows",report.rows.length,"Current fictional records")+
    metric("Source systems","LOCAL","One Axiom demo state")+
    metric("Export","CSV","Spreadsheet-friendly synthetic data")+'</div>';
  s+='<section class="panel"><div class="panel-head"><h2>Report selection</h2>'+
    '<button type="button" class="action" data-action="download-report">Download report CSV</button></div>'+
    '<div class="controls"><label>Choose report<select id="report-select">'+REPORTS.map(x=>
    '<option value="'+h(x.id)+'" '+(x.id===selected.id?"selected":"")+'>'+h(x.label)+'</option>').join("")+
    '</select></label><span class="small muted">'+h(selected.description)+'</span></div></section>';
  s+='<section class="panel"><div class="panel-head"><h2>'+h(report.title)+'</h2><span class="tag accent">'+
    h(report.rows.length)+' rows</span></div>'+
    table(report.columns,report.rows.slice(0,100).map(row=>row.map(value=>h(value))),
      "This report has no records yet. Create a fictional transaction in its source module.")+
    (report.rows.length>100?'<p class="small">Showing first 100 rows. CSV includes the full fictional report.</p>':'')+
    '</section>';
  s+='<div class="notice">This is a functional reporting view over browser-local synthetic state, not a live BI connector, financial ledger, secured reporting service or production approval.</div>';
  return s;
}
function auditView(){
  let s=heading("Traceability / browser-only event history","Demonstration event ledger",
    "Transactions below are local browser actions. These are not secured, centrally audited, immutable or ERP-synchronized records.");
  s+='<section class="panel"><div class="panel-head"><h2>Local events</h2><div class="actions">'+
    '<button class="action secondary" data-action="export-json">Export demo snapshot</button>'+
    '<button class="action secondary" data-action="export-csv">Export clock CSV</button>'+
    '<button class="action danger" data-action="reset">Reset demo</button></div></div>'+
    table(["When","Event type","Detail"],state.events.slice().reverse().map(e=>[h(stamp(e.at)),h(e.type),h(e.detail)]))+'</section>';
  return s;
}
const renderers={dashboard,jobs:jobsView,routing:routingView,ewi:clockView,inventory:inventoryView,
  purchasing:purchasingView,quality:qualityView,documents:documentsView,pm:()=>renderPm(state.pm,selectedPmMachineId),requests:()=>renderRequestDesk(state,selectedRequest),hr:()=>renderHr(workforce),morale:()=>renderMorale(workforce),qcdsm:()=>renderQcdsm(state,workforce,qcdsmDepartment,localDay()),reports:reportsView,bridge:bridgeView,audit:auditView};
function rememberJob(id){
  if(!getJob(state,id))return;
  if(routeDraft&&routeDraft.jobId!==id)routeDraft=null;
  selectedJobId=id;selectedStep=job().routing.operations[0].step;
  history.replaceState(null,"",location.pathname+"?job="+encodeURIComponent(id)+location.hash);
}
function render(){
  if(!getJob(state,selectedJobId))selectedJobId=state.jobs[0].id;
  if(!getMachine(state.pm,selectedPmMachineId))selectedPmMachineId=state.pm.machines[0]?.id||"";
  const view=currentView(),j=job();
  $("breadcrumb").textContent=stateViews[view];
  $("storage-indicator").textContent=stored?"Local browser data":"In-memory only";
  $("context-status").innerHTML=packetIssues(state,j.id).length?status("REVIEW"):status("READY");
  $("job-context").innerHTML=state.jobs.map(x=>'<option value="'+h(x.id)+'" '+(x.id===selectedJobId?"selected":"")+'>'+
    h(x.jobNumber+" · "+x.partNumber)+'</option>').join("");
  menu?.markActive(view);
  $("view").innerHTML='<div id="flash" role="status">'+h(flash)+'</div>'+contextBanner()+renderers[view]();
  applyContextFocus();
}
function download(data,type,name){
  const url=URL.createObjectURL(new Blob([data],{type}));
  const a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);
  a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1200);
}
document.addEventListener("click",event=>{
  const link=event.target.closest("[data-job]");
  if(link){rememberJob(link.dataset.job);if(location.hash===link.getAttribute("href"))render();}
  const button=event.target.closest("[data-action]");
  if(!button)return;
  const action=button.dataset.action,id=button.dataset.id;
  try{
    if(action==="routing-start"){
      const j=job();
      if(sessions.some(s=>s.jobId===j.id))throw Error("Clocking history exists for this job. Use another fictional job for routing changes.");
      routeDraft={jobId:j.id,operations:editableRouting(j)};
      flash="Edit fictional routing, then save for demo review.";
      render();
      document.getElementById("routing-editor")?.scrollIntoView({block:"start"});
    }
    if(["routing-up","routing-down","routing-add","routing-remove"].includes(action)){
      if(!routeDraft||routeDraft.jobId!==job().id)throw Error("Open the routing editor for this fictional job first");
      routeDraft.operations=readRoutingEditor(document.getElementById("routing-editor-form"));
      const index=Number(button.dataset.index);
      if(action==="routing-up")routeDraft.operations=moveRouteStep(routeDraft.operations,index,-1);
      if(action==="routing-down")routeDraft.operations=moveRouteStep(routeDraft.operations,index,1);
      if(action==="routing-remove")routeDraft.operations=removeRouteStep(routeDraft.operations,index);
      if(action==="routing-add")routeDraft.operations=addRouteStep(routeDraft.operations);
      flash="";
      render();
      document.getElementById("routing-editor")?.scrollIntoView({block:"start"});
    }
    if(action==="routing-cancel"){routeDraft=null;flash="Routing edit cancelled, no changes saved.";render();}
    if(action==="routing-review"){
      if(routeDraft)throw Error("Save or cancel draft edits before review");
      transact(reviewRoutingDraft(state,job().id,sessions),"Sample routing reviewed. This is not a production release.");
    }
    if(action==="pm-select-machine") {selectedPmMachineId=id;flash="";render();document.getElementById("pm-machine-card")?.scrollIntoView({block:"start"});}
    if(action==="pm-select-task") {const item=getTask(state.pm,id);if(!item)throw Error("Demo task missing");selectedPmMachineId=item.machineId;render();const picker=document.getElementById("pm-completion-task");if(picker)picker.value=id;picker?.scrollIntoView({block:"center"});}
    if(action==="pm-open-requests") document.getElementById("pm-request-queue")?.scrollIntoView({block:"start"});
    if(action==="pm-copy-link") {
      const link=location.origin+location.pathname+"?machine="+encodeURIComponent(id)+"#pm";
      if(navigator.clipboard?.writeText){navigator.clipboard.writeText(link).then(()=>{flash="Fictional machine link copied.";render();}).catch(()=>window.prompt("Copy demo machine link:",link));}
      else window.prompt("Copy demo machine link:",link);
    }
    if(action==="clear-record-context"){selectedContext=null;selectedIntent="";flash="Record context cleared.";render();}
    if(action==="morale-close")workforceTransact(closeDemoAction(workforce,id),"morale.review.completed",id+" / FICTIONAL","Fictional workforce risk review marked complete.");
    if(action==="morale-approve"||action==="morale-reject")workforceTransact(reviewDemoNomination(workforce,id,action==="morale-approve"?"APPROVED":"REJECTED"),"morale.recognition.reviewed",id+" / FICTIONAL","Demonstration recognition nomination reviewed.");
    if(action==="pm-csv") download(completionsCsv(state.pm),"text/csv;charset=utf-8","axiom-synthetic-pm-completions.csv");
    if(action==="download-report") download(reportCsv(reportWithContext(selectedReport)),"text/csv;charset=utf-8","axiom-demo-"+selectedReport+"-report.csv");
    if(action==="pm-close-request"||action==="close-maint-request")pmTransact(closeMaintenanceRequest(state.pm,id),"pm.request.closed",id+" / SIMULATED","Fictional maintenance request closed.");
    if(action==="select-request"){selectedRequest={kind:button.dataset.kind,id};render();document.getElementById("request-detail")?.scrollIntoView({block:"start"});}
    if(action==="approve-request")transact(approvePurchaseRequest(state,id),"Purchase request approved. Still awaiting an actual fictional PO receipt.");
    if(action==="issue-request-po")transact(issueRequestPO(state,id),"Fictional PO issued for purchase request. Not completed until received.");
    if(action==="verify-purchase-request")transact(verifyPurchaseRequest(state,id),"Purchase request verified after linked PO receipt.");
    if(action==="reserve")transact(reserve(state,selectedJobId),"Material reserved for the selected fictional job.");
    if(action==="receive-po"){
      let next=receivePurchaseOrder(state,id);
      if(next.purchaseRequests.some(r=>r.linkedPoId===id&&r.status==="ORDERED"))next=syncReceivedRequests(next,id);
      transact(next,"Simulated PO received. Linked purchase request awaits confirmation.");
    }
    if(action==="select-quality"){
      const record=state.quality.find(q=>q.id===id);
      if(!record)throw Error("Fictional quality case not found");
      selectedQualityId=id;rememberJob(record.jobId);render();
      document.getElementById("quality-case-detail")?.scrollIntoView({block:"start"});
    }
    if(action==="sync"){
      const routing=emulatorFetchRouting(id);
      if(!routing.operations.length)throw Error("Emulator routing is missing");
      const result=syncEmulatorJob(state,id);state=result.state;rememberJob(result.jobId);
      transact(state,result.imported?"Imported fictional job and routed operations.":"This fictional job was already imported.");
      location.hash="#routing";
    }
    if(action==="clock-in"){
      const j=job();const clockIssues=packetIssues(state,j.id);if(clockIssues.length)throw Error("Clock start blocked: "+clockIssues.join("; "));
      const step=$("clock-step").value;operator=$("operator-code").value.trim().toUpperCase();
      sessions=startSession(sessions,{id:crypto.randomUUID(),employee:operator,job:deep(j),step,timestamp:new Date().toISOString()});
      selectedStep=step;flash="Clock IN recorded locally. Nothing sent to a live ERP.";persist();render();
    }
    if(action==="clock-out"){
      operator=$("operator-code").value.trim().toUpperCase();
      const active=sessions.find(s=>s.employee===operator&&!s.end);
      if(!active)throw Error("No active local clock for this demo operator");
      sessions=stopSession(sessions,{id:active.id,employee:operator,timestamp:new Date().toISOString()});
      flash="Clock OUT saved locally. Time ticket NOT posted to JobBOSS².";persist();render();
    }
    if(action==="export-json")download(JSON.stringify({demo:true,erp_connected:false,exportedAt:new Date().toISOString(),
      state,sessions,workforce},null,2),"application/json","axiom-erp-synthetic-demo.json");
    if(action==="export-csv")download(sessionsCsv(sessions),"text/csv;charset=utf-8","axiom-erp-demo-clock.csv");
    if(action==="reset" && confirm("Delete all fictional Axiom ERP and EWI clock records in this browser and reset the demo?")){
      state=seedState();sessions=[];workforce=seedWorkforce();selectedContext=null;selectedIntent="";rememberJob(state.jobs[0].id);
      flash="Local demo reset to fictional starter records.";persist();render();
    }
  }catch(e){flash=e.message;render();}
});
document.addEventListener("submit",event=>{
  const form=event.target.closest("[data-form]");if(!form)return;
  event.preventDefault();
  const f=new FormData(form);
  try{
    switch(form.dataset.form){
      case "hr-person":
        workforceTransact(addDemoPerson(workforce,String(f.get("role"))),"hr.demo.person.created","Fictional employee code created","Added a synthetic employee code.");break;
      case "hr-role":
        workforceTransact(assignDemoRole(workforce,String(f.get("person")),String(f.get("role"))),"hr.demo.role.assigned",String(f.get("person"))+" / DEMO","Fictional role assignment updated.");break;
      case "hr-training":
        workforceTransact(completeDemoTraining(workforce,String(f.get("person")),String(f.get("requirement"))),"hr.training.completed",String(f.get("person"))+" / DEMO","Simulated training verification recorded. Fictional points credited.");break;
      case "morale-pulse":
        qcdsmDepartment=String(f.get("department"));
        workforceTransact(recordDemoPulse(workforce,Object.fromEntries(f)),"morale.pulse.recorded","Synthetic aggregate workforce signal","Fictional company-pulse record added; QCDSM evidence recalculated.");break;
      case "qcdsm-department":
        qcdsmDepartment=String(f.get("department"));flash="";render();break;
      case "safety-incident":
        qcdsmDepartment=String(f.get("department"));
        workforceTransact(recordDemoIncident(workforce,Object.fromEntries(f)),"safety.synthetic.event.recorded","Fictional safety event / "+qcdsmDepartment,"Synthetic safety evidence recorded for QCDSM / RCA.");break;
      case "safety-survey":
        qcdsmDepartment=String(f.get("department"));
        workforceTransact(recordDemoSafetySurvey(workforce,Object.fromEntries(f)),"safety.synthetic.confidence.recorded","Fictional aggregate survey / "+qcdsmDepartment,"Aggregate fictional safety-confidence signal recorded.");break;
      case "quality-qcdsm-review":
        qcdsmDepartment=String(f.get("department"));
        transact(captureQualityContext(state,workforce,String(f.get("qualityId")),qcdsmDepartment),"QCDSM evidence linked to a synthetic quality investigation. Root cause remains unconfirmed.");break;
      case "morale-nominate":
        workforceTransact(nominateDemoRecognition(workforce,String(f.get("person")),String(f.get("category")),String(f.get("reason")),Number(f.get("points"))),"morale.recognition.nominated","Fictional recognition nomination","Nomination added for demonstration review.");break;
      case "routing-save":{
        if(!routeDraft||routeDraft.jobId!==job().id)throw Error("No active routing edit for this job");
        const updated=saveRoutingDraft(state,routeDraft.jobId,readRoutingEditor(form),sessions);
        routeDraft=null;
        transact(updated,"Edited routing saved for demo review. EWI clocking is blocked until reviewed.");break;
      }
      case "pm-new-machine": {
        const result=createMachine(state.pm,String(f.get("machine-type")),String(f.get("criticality")));
        selectedPmMachineId=result.id;
        pmTransact(result.pm,"pm.asset.created",result.id+" / FICTIONAL","Added a generic demonstration machine.");
        break;
      }
      case "pm-new-task": {
        const result=addPmTask(state.pm,selectedPmMachineId,Number(f.get("task-template")),Number(f.get("frequency")),localDay());
        pmTransact(result.pm,"pm.task.scheduled",result.id+" / FICTIONAL","Scheduled a recurring fictional PM task.");
        break;
      }
      case "pm-complete": {
        const taskId=String(f.get("task")),selected=getTask(state.pm,taskId);
        if(!selected||selected.machineId!==selectedPmMachineId)throw Error("Select a task belonging to the current demo machine");
        const result=completePmTask(state.pm,taskId,{operator:String(f.get("operator")).trim().toUpperCase(),
          result:String(f.get("result")),notes:String(f.get("notes")),checklistConfirmed:f.get("confirmed")!==null});
        pmTransact(result.pm,"pm.task.completed",result.id+" / "+taskId+" / FICTIONAL",
          result.raisedRequest?"Simulated PM completed with attention required. A demo request was opened.":"Fictional PM completion recorded and next due date recalculated.");
        break;
      }
      case "pm-request": {
        const result=requestMaintenance(state.pm,String(f.get("machine")),String(f.get("type")),String(f.get("priority")));
        pmTransact(result.pm,"pm.request.opened",result.id+" / FICTIONAL","A fictional maintenance request was opened.");
        break;
      }
      case "request-purchase":{
        const result=createPurchaseRequest(state,{itemId:String(f.get("item")),quantity:Number(f.get("quantity")),
          reason:String(f.get("reason")),priority:String(f.get("priority")),owner:String(f.get("owner")),dueDate:String(f.get("due"))});
        selectedRequest={kind:"purchase",id:result.id};
        transact(result.state,"Fictional purchase requisition submitted. Not yet ordered.");break;
      }
      case "request-maintenance":{
        const result=requestMaintenance(state.pm,String(f.get("machine")),String(f.get("type")),String(f.get("priority")));
        const pm=assignMaintenanceRequest(result.pm,result.id,String(f.get("owner")),String(f.get("due")));
        selectedRequest={kind:"maintenance",id:result.id};
        pmTransact(pm,"pm.request.opened",result.id+" / assigned","Fictional maintenance request assigned.");break;
      }
      case "request-assign":
        transact(assignPurchaseRequest(state,String(f.get("id")),String(f.get("owner")),String(f.get("due"))),"Purchase request ownership and deadline updated.");break;
      case "request-purchase-followup":
        transact(followupPurchaseRequest(state,String(f.get("id")),String(f.get("note"))),"Purchase follow-up recorded.");break;
      case "request-maint-assign":
        pmTransact(assignMaintenanceRequest(state.pm,String(f.get("id")),String(f.get("owner")),String(f.get("due"))),
          "pm.request.assigned",String(f.get("id")),"Maintenance owner and due date updated.");break;
      case "request-maint-followup":
        pmTransact(followupMaintenanceRequest(state.pm,String(f.get("id")),String(f.get("note"))),
          "pm.request.followup",String(f.get("id")),"Maintenance follow-up recorded.");break;
      case "new-job":{
        const result=createJob(state,String(f.get("part")),Number(f.get("quantity")));
        state=result.state;rememberJob(result.jobId);flash="Created a fictional Axiom work order. Reserve material to enable clocking.";
        persist();render();location.hash="#routing";break;
      }
      case "new-po":
        transact(makePurchaseOrder(state,String(f.get("item")),Number(f.get("quantity"))),"Created synthetic purchase order.");break;
      case "new-ncr":{
        const next=raiseQuality(state,selectedJobId,String(f.get("reason")));
        selectedQualityId=next.quality.at(-1).id;
        transact(next,"Fictional NCR opened and linked to this work order. EWI clocking is blocked.");break;
      }
      case "quality-inspection":
        selectedQualityId=String(f.get("id"));
        transact(recordQualityInspection(state,selectedQualityId,String(f.get("stage")),
          String(f.get("step")),String(f.get("result")),String(f.get("observation"))),
          "Fictional inspection observation saved on this NCR and routed step. No job release.");break;
      case "quality-disposition":
        selectedQualityId=String(f.get("id"));
        transact(recordQualityDisposition(state,selectedQualityId,String(f.get("decision")),String(f.get("note"))),
          "Fictional disposition recorded. The job hold remains until reviewed closure.");break;
      case "quality-followup":
        selectedQualityId=String(f.get("id"));
        transact(recordQualityFollowup(state,selectedQualityId,String(f.get("note"))),
          "Case follow-up saved to this fictional NCR.");break;
      case "quality-reviewed-close":
        selectedQualityId=String(f.get("id"));
        transact(closeReviewedQuality(state,selectedQualityId),
          "Reviewed fictional NCR closed. The linked EWI hold was recalculated.");break;
      case "drawing-rev":
        transact(setDrawingRevision(state,selectedJobId,String(f.get("revision"))),"Updated illustration revision, not an official release.");break;
      case "mock-post":{
        const session=sessions.find(s=>s.id===f.get("session"));
        transact(postEmulatorTicket(state,session),"Fictional time ticket accepted by the in-browser emulator ONLY.");break;
      }
    }
  }catch(e){flash=e.message;render();}
});
$("job-context").addEventListener("change",e=>{rememberJob(e.target.value);flash="";render();});
document.addEventListener("change",e=>{
  if(e.target.id==="clock-step")selectedStep=e.target.value;
  if(e.target.id==="report-select") {selectedReport=e.target.value;render();}
});
document.addEventListener("input",e=>{if(e.target.id==="operator-code")operator=e.target.value;});
window.addEventListener("hashchange",()=>{flash="";render();});
window.addEventListener("storage",e=>{if(e.key===ERP_KEY||e.key===CLOCK_KEY||e.key===WORKFORCE_KEY){load();render();}});
window.addEventListener("focus",()=>{if(stored){load();render();}});
setInterval(()=>{
  document.querySelectorAll("[data-live-clock]").forEach(el=>{
    const active=sessions.find(s=>s.employee===operator&&!s.end);
    el.textContent=active?hours(durationSeconds(active)):"00:00:00";
  });
},1000);
load();
const requested=new URLSearchParams(location.search).get("job");
selectedJobId=state.jobs.some(j=>j.id===requested)?requested:state.jobs[0].id;
const requestedMachine=new URLSearchParams(location.search).get("machine");
selectedPmMachineId=state.pm.machines.some(m=>m.id===requestedMachine)?requestedMachine:state.pm.machines[0]?.id||"";
selectedStep=job().routing.operations[0].step;
menu=installMenu({root:$("module-nav"),search:$("menu-search"),tabs:$("menu-tabs"),launch:$("menu-launch"),
  getCurrent:currentView,onNavigate:id=>{selectedContext=null;selectedIntent="";if(location.hash==="#"+id)render();}});
installContextMenu({getState:()=>state,onNavigate:openContext});
render();
