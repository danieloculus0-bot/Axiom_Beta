/* Axiom ERP-native PM Tracker interface.
 * Uses existing Axiom ERP CSS; no custom theme or employer assets.
 * Data and workflows reference the original public PM-Tracker feature model.
 */
import {
 MACHINE_TYPES,PM_TEMPLATES,REQUEST_TYPES,PRIORITIES,COMPLETION_NOTES,
 pmOverview,machineSummary,getMachine,getTask,taskDue,localDay
} from "./pm.mjs";
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";

const h=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const label=(name,kind="")=>{
 const cls=["overdue","today"].includes(kind)?"bad":kind==="soon"?"warn":kind==="clear"?"ok":"";
 return '<span class="tag '+cls+'">'+h(name)+'</span>';
};
const section=(title,body,extra="")=>'<section class="panel"><div class="panel-head"><h2>'+h(title)+'</h2>'+extra+'</div>'+body+'</section>';
const metric=(title,value,caption)=>'<div class="metric"><small>'+h(title)+'</small><strong>'+h(value)+'</strong><em>'+h(caption)+'</em></div>';
const table=(headers,rows,empty,contexts=[])=>{
 if(!rows.length)return '<div class="empty">'+h(empty)+'</div>';
 return '<div class="tablewrap"><table><thead><tr>'+headers.map(x=>'<th>'+h(x)+'</th>').join("")+'</tr></thead><tbody>'+
  rows.map((cols,index)=>{
   const rec=contexts[index],attr=rec?' class="context-record-row" tabindex="0" data-ctx-type="'+h(rec.type)+'" data-ctx-id="'+h(rec.id)+'" title="Right-click for Open with"':"";
   return '<tr'+attr+'>'+cols.map(value=>'<td>'+value+'</td>').join("")+'</tr>';
  }).join("")+'</tbody></table></div>';
};
const fieldOptions=(values,select)=>values.map((value,index)=>'<option value="'+h(select?index:value)+'">'+h(value)+'</option>').join("");
const dayStamp=at=>at?at.slice(0,10):"Not recorded";

export function renderPm(pm,selectedMachineId){
 const today=localDay(),stats=pmOverview(pm,today),
   machine=getMachine(pm,selectedMachineId)||pm.machines[0],
   summary=machine?machineSummary(pm,machine.id,today):null;
 let s='<div class="lead"><div><div class="eyebrow">Operations / integrated maintenance</div>'+
  '<h1>Preventive Maintenance Tracker</h1>'+
  '<p class="subtitle">Machine register, recurring PM, completion history, and maintenance requests. Integrated in Axiom and modeled after the existing standalone PM Tracker. All assets and records are invented.</p></div>'+
  '<span class="tag accent">AXIOM MODULE · BROWSER DEMO</span></div>';
 s+='<div class="notice"><b>DEMONSTRATION, NOT A SAFETY CONTROL:</b> Checklists and completion buttons record fictional events only. They do not isolate equipment, perform lockout/tagout, verify zero energy, authorize maintenance, or create site work orders.</div>';
 s+='<div class="metrics">'+metric("Demo machines",stats.machines,"Active fictional assets")+
  metric("Overdue PM",stats.overdue,"Calculated against local date")+
  metric("Due today / soon",stats.dueToday+" / "+stats.dueSoon,"Within next 7 days")+
  metric("Open requests",stats.openRequests,"Fictional repair queue")+'</div>';
 s+='<div class="columns"><section class="panel"><div class="panel-head"><h2>Equipment register</h2>'+
  '<span class="tag">SYNTHETIC REGISTER</span></div>'+
  table(["Machine","Department / location","Criticality","PM status","Next due","Select"],
   stats.summaries.map(item=>[h(item.machine.name)+'<div class="small muted">'+h(item.machine.id)+'</div>',
     h(item.machine.department)+'<div class="small muted">'+h(item.machine.location)+'</div>',
     h(item.machine.criticality),label(item.label,item.kind),h(item.nextDue||"Unscheduled"),
     '<button type="button" class="action secondary" data-action="pm-select-machine" data-id="'+h(item.machine.id)+'">Open</button>'
   ]),"No fictional machines yet.",stats.summaries.map(item=>({type:"machine",id:item.machine.id})))+
  '</section><section class="panel"><h2>Add a fictional machine</h2>'+
  '<form class="controls" data-form="pm-new-machine"><label>Demo equipment type<select name="machine-type">'+fieldOptions(MACHINE_TYPES)+'</select></label>'+
  '<label>Criticality<select name="criticality">'+fieldOptions(["Low","Medium","High"])+'</select></label>'+
  '<button class="action" type="submit">Add machine</button></form>'+
  '<p class="small">Equipment types are restricted to generic prewritten examples. No real serial numbers, locations or asset files.</p>'+
  '<h2 style="margin-top:22px">PM snapshot</h2>'+
  '<div class="receipt">Completed today: <b>'+h(stats.completedToday)+'</b></div>'+
  '<div class="receipt">Tasks tracked: <b>'+h(stats.tasks)+'</b></div>'+
  '<div class="receipt">Open maintenance requests: <b>'+h(stats.openRequests)+'</b></div>'+
  '<div class="actions" style="margin-top:12px"><button type="button" class="action secondary" data-action="pm-open-requests">Open request queue</button>'+
  '<button class="action secondary" data-action="pm-csv">Export demo PM CSV</button></div></section></div>';
 if(machine&&summary){
  s+='<section class="panel context-record" tabindex="0" data-ctx-type="machine" data-ctx-id="'+h(machine.id)+'" title="Right-click for Open with" id="pm-machine-card"><div class="panel-head"><div><div class="eyebrow">Equipment / '+h(machine.id)+'</div>'+
    '<h2>'+h(machine.name)+'</h2></div><div class="pills">'+label(summary.label,summary.kind)+
    '<span class="tag">'+h(machine.criticality)+' criticality</span></div></div>'+
    '<div class="twocol"><div><p><b>Area:</b> '+h(machine.department)+' / '+h(machine.location)+
    '<br><b>Active recurring tasks:</b> '+h(summary.tasks.length)+
    '<br><b>Next due:</b> '+h(summary.nextDue||"Unscheduled")+
    '<br><b>Equipment record:</b> fictional browser-local</p></div>'+
    '<div><div class="eyebrow">Link to demo machine</div>'+
    '<p class="small">Machine page: use the URL below to reopen this fictional asset. This is not a QR scan or a connected site machine.</p>'+
    '<button class="action secondary" type="button" data-action="pm-copy-link" data-id="'+h(machine.id)+'">Copy machine link</button></div></div></section>';
  // The canonical PM machine remains the only association store. These
  // browser-local review controls are illustrative, not authenticated approval.
  const linkedCenter=machine.workCenterLink?.centerId ?? null;
  const associationHistory=Array.isArray(pm.workCenterLinkHistory)?
    pm.workCenterLinkHistory.filter(item=>item.machineId===machine.id).slice(-5).reverse():[];
  s+=section("Work-center association / review only",
    '<p class="small">Optional link to an existing fictional routing work center. A match is not proof of capacity, machine qualification, or maintenance clearance. No live BEAN or ERP connection.</p>'+
    '<p><b>Current link:</b> '+h(linkedCenter||"UNMAPPED")+
    (linkedCenter?' <span class="tag">DEMO REVIEWED</span>':' <span class="tag warn">UNKNOWN</span>')+'</p>'+
    '<form class="controls" data-form="pm-work-center-link">'+
    '<input type="hidden" name="machine" value="'+h(machine.id)+'">'+
    '<label>Fictional work center<select name="center">'+
    '<option value="">Unlink / unknown</option>'+
    DEMO_CENTER_OPTIONS.map(id=>'<option value="'+h(id)+'"'+(id===linkedCenter?' selected':'')+'>'+h(id)+'</option>').join("")+
    '</select></label>'+
    '<label>Demo reviewer code<input name="reviewer" value="DEMO-PLANNER" pattern="DEMO-[A-Z0-9-]{1,20}" maxlength="25" required></label>'+
    '<label>Fictional evidence reference<input name="source" placeholder="SYN-LINK-001" pattern="SYN-[A-Z0-9-]{1,60}" maxlength="64" required></label>'+
    '<label style="flex-basis:100%"><input type="checkbox" name="confirmed" required style="width:auto;min-height:auto;display:inline-block;margin-right:8px">I reviewed this fictional association. This is not production authorization.</label>'+
    '<button class="action secondary" type="submit">Record demo association review</button></form>'+
    '<h3>Recent association history</h3>'+
    (associationHistory.length?table(["Recorded","Previous","Current","Reviewer","Evidence"],
      associationHistory.map(item=>[h(item.at),h(item.previousCenterId||"UNMAPPED"),
        h(item.centerId||"UNMAPPED"),h(item.reviewedBy),h(item.sourceRef)]),
      "No association history."):'<p class="small muted">No fictional association reviews recorded.</p>'));
  s+=section("Scheduled tasks for "+machine.id,
   table(["Task & safety note","Interval / role","Next due","Status","Log"],
    summary.tasks.map(task=>[
      '<b>'+h(task.name)+'</b><div class="small muted">'+h(task.id)+
        ' · '+h(task.description)+'</div><div class="small warning">SAFETY: '+h(task.safety)+'</div>',
      h(task.frequencyDays)+" days<div class='small muted'>"+h(task.role)+" · "+h(task.estimatedMinutes)+" min</div>",
      h(task.due||"Unscheduled"),label(task.label,task.kind),
      '<button class="action secondary" data-action="pm-select-task" data-id="'+h(task.id)+'" type="button">Complete</button>'
    ]),"No tasks assigned to this fictional asset.",summary.tasks.map(task=>({type:"pm_task",id:task.id}))),
   '<span class="tag">'+h(summary.tasks.length)+' recurring tasks</span>');
  s+='<div class="columns"><section class="panel"><h2>Add recurring PM task</h2>'+
    '<form data-form="pm-new-task" class="controls">'+
    '<label>Template<select name="task-template">'+fieldOptions(PM_TEMPLATES.map(t=>t.name),true)+'</select></label>'+
    '<label>Frequency (days)<input name="frequency" type="number" min="1" max="3650" value="30" required></label>'+
    '<button type="submit" class="action">Schedule PM</button></form>'+
    '<p class="small">Schedule starts from the local date. Each template has an example inspection statement and a safety notice. The browser does not manage actual equipment.</p></section>'+
    '<section class="panel"><h2>Quick completion</h2>'+
    '<form data-form="pm-complete" class="controls">'+
    '<label>Fictional PM task<select name="task" id="pm-completion-task">'+summary.tasks.map(t=>
      '<option value="'+h(t.id)+'">'+h(t.id+" · "+t.name)+'</option>').join("")+'</select></label>'+
    '<label>Demo operator code<input name="operator" value="DEMO-01" pattern="DEMO-[A-Za-z0-9]{1,16}" maxlength="21" required></label>'+
    '<label>Result<select name="result"><option value="PASS">PASS / demo</option><option value="NEEDS ATTENTION">NEEDS ATTENTION / opens demo request</option></select></label>'+
    '<label>Recorded note<select name="notes">'+fieldOptions(COMPLETION_NOTES)+'</select></label>'+
    '<label style="flex-basis:100%"><input name="confirmed" type="checkbox" required style="width:auto;min-height:auto;display:inline-block;margin-right:8px">'+
    'I reviewed this illustrative checklist and understand no real maintenance was done</label>'+
    '<button type="submit" class="action">Log fictional completion</button></form></section></div>';
 }
 s+=section("Completion history",
   table(["Completed","Machine","PM task","Demo code","Result","Notes"],
     pm.completions.slice().reverse().slice(0,25).map(c=>[
      h(c.completedAt?c.completedAt.replace("T"," ").slice(0,19):"Unknown"),
      h(getMachine(pm,c.machineId)?.name||c.machineId),h(getTask(pm,c.taskId)?.name||c.taskId),
      h(c.operator),label(c.result,c.result==="PASS"?"clear":"today"),h(c.notes)
     ]),"No fictional PM completions recorded yet."));
 s+='<section class="panel" id="pm-request-queue"><div class="panel-head"><h2>Maintenance request queue</h2><span class="tag warn">FICTIONAL REQUESTS ONLY</span></div>'+
  '<form class="controls" data-form="pm-request">'+
  '<label>Machine<select name="machine">'+pm.machines.map(m=>'<option value="'+h(m.id)+'" '+(machine&&m.id===machine.id?"selected":"")+'>'+
    h(m.id+" · "+m.name)+'</option>').join("")+'<option value="">General demo request</option></select></label>'+
  '<label>Example issue<select name="type">'+fieldOptions(REQUEST_TYPES)+'</select></label>'+
  '<label>Priority<select name="priority">'+fieldOptions(PRIORITIES)+'</select></label>'+
  '<button type="submit" class="action">Submit demo request</button></form>'+
  '<p class="small">Requests are not submitted to facilities, employees, a service desk, or a maintenance database.</p>'+
  table(["Request","Equipment","Issue","Priority","Submitted","Status","Action"],
   pm.requests.slice().reverse().map(r=>[
    h(r.id),h(getMachine(pm,r.machineId)?.name||"General"),h(r.type),
    label(r.priority,r.priority==="High"?"today":"soon"),h(dayStamp(r.submittedAt)),
    label(r.status,r.status==="CLOSED"?"clear":"today"),
    ["OPEN","IN PROGRESS"].includes(r.status)?'<button class="action secondary" data-action="pm-close-request" data-id="'+h(r.id)+'">Close example</button>':
    '<span class="small muted">'+h(dayStamp(r.closedAt))+'</span>'
   ]),"No fictional maintenance requests yet.",pm.requests.slice().reverse().map(r=>({type:"pm_request",id:r.id})))+'</section>';
 s+='<div class="notice"><b>MODULE BOUNDARY:</b> The full PM Tracker is still a separate Flask/SQLite/Excel-backed application. This GitHub Pages module reproduces its public-facing PM workflows using fictional local state. It does not connect to that server, sync workbooks, or perform actual QR scanning.</div>';
 return s;
}
