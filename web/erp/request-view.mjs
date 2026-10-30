/* Axiom Request Desk. Existing dark/lime theme; no independent styling.
 * All records are invented and local to the viewer's browser.
 */
import {PURCHASE_REASONS,DEMO_OWNERS,REQUEST_FOLLOWUPS,requestMetrics,
        latestFollowup,dueLabel} from "./requests.mjs";
import {MAINTENANCE_FOLLOWUPS,REQUEST_TYPES,PRIORITIES,localDay,dayAdd,getMachine} from "./pm.mjs";

const h=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const opt=(arr,selected)=>arr.map(x=>'<option value="'+h(x)+'"'+(x===selected?' selected':'')+'>'+h(x)+'</option>').join("");
const pill=(text,extra="")=>'<span class="tag '+extra+'">'+h(text)+'</span>';
const badge=(due,status,today)=>{const label=dueLabel(due,status,today);return pill(label,label==="OVERDUE"?"bad":label==="DUE SOON"?"warn":"");};
const context=(type,id,title)=>'<span class="context-record" tabindex="0" data-ctx-type="'+h(type)+'" data-ctx-id="'+h(id)+'" title="Right-click for Open with">'+h(title)+'</span>';
const row=(cells,type,id)=>'<tr class="context-record-row" tabindex="0" data-ctx-type="'+h(type)+'" data-ctx-id="'+h(id)+'" title="Right-click for Open with">'+cells.map(x=>'<td>'+x+'</td>').join("")+'</tr>';
const tab=(headers,rows,empty)=>rows.length?
 '<div class="tablewrap"><table><thead><tr>'+headers.map(x=>'<th>'+h(x)+'</th>').join("")+'</tr></thead><tbody>'+
 rows.join("")+'</tbody></table></div>':'<p class="empty">'+h(empty)+'</p>';
const latest=r=>r.followups?.length?r.followups.at(-1).note:"No follow-up recorded";
const requestState=r=>pill(r.status,r.status==="CLOSED"||r.status==="VERIFIED"?"ok":
 r.status==="ORDERED"||r.status==="IN PROGRESS"?"warn":"");
const field=(title,html)=>'<label>'+h(title)+html+'</label>';
const select=(name,values,selected)=>'<select name="'+h(name)+'">'+opt(values,selected)+'</select>';
const dateField=(name,value)=>'<input type="date" name="'+h(name)+'" value="'+h(value)+'" required>';
const form=(name,body,button)=>'<form data-form="'+h(name)+'" class="controls">'+body+
 '<button class="action" type="submit">'+h(button)+'</button></form>';

export function renderRequestDesk(state,selected={kind:"",id:""}){
 const today=localDay(),metrics=requestMetrics(state,today);
 const purchases=state.purchaseRequests||[],maint=state.pm.requests;
 const selectedPurchase=selected?.kind==="purchase"?purchases.find(r=>r.id===selected.id):null;
 const selectedMaintenance=selected?.kind==="maintenance"?maint.find(r=>r.id===selected.id):null;
 let s='<div class="lead"><div><div class="eyebrow">Operations / follow-up and accountability</div>'+
  '<h1>Request Desk</h1>'+
  '<p class="subtitle">Submit, assign, follow up, and verify that requests actually get done. Purchasing requires a linked received PO before final verification; maintenance can simply close after the work.</p></div>'+
  '<span class="tag accent">FICTIONAL LOCAL WORKFLOW</span></div>';
 s+='<div class="metrics">'+
  '<div class="metric"><small>Open purchase requests</small><strong>'+metrics.openPurchases+'</strong><em>Pending receipt or signoff</em></div>'+
  '<div class="metric"><small>Open maintenance</small><strong>'+metrics.openMaintenance+'</strong><em>Not yet closed</em></div>'+
  '<div class="metric"><small>Overdue follow-ups</small><strong>'+metrics.overdue+'</strong><em>Against requested due dates</em></div>'+
  '<div class="metric"><small>Purchases to verify</small><strong>'+metrics.needsVerification+'</strong><em>Received, awaiting requester</em></div></div>';
 s+='<div class="columns"><section class="panel"><h2>New purchase request</h2>'+
 form("request-purchase",
   field("Fictional material",'<select name="item">'+state.items.map(i=>'<option value="'+h(i.id)+'">'+h(i.id+" · "+i.name)+'</option>').join("")+'</select>')+
   field("Quantity",'<input type="number" name="quantity" min="1" max="10000" value="10" required>')+
   field("Purpose",select("reason",PURCHASE_REASONS))+
   field("Priority",select("priority",PRIORITIES,"Medium"))+
   field("Assigned to",select("owner",DEMO_OWNERS,"DEMO-BUYER"))+
   field("Needed by",dateField("due",dayAdd(today,7))),
   "Submit purchase request")+
 '<p class="small">This creates a requisition, not a purchase order. The demo buyer must approve and issue the PO.</p></section>'+
 '<section class="panel"><h2>New maintenance request</h2>'+
 form("request-maintenance",
   field("Equipment",'<select name="machine">'+state.pm.machines.map(m=>'<option value="'+h(m.id)+'">'+h(m.id+" · "+m.name)+'</option>').join("")+'</select>')+
   field("Example issue",select("type",REQUEST_TYPES))+
   field("Priority",select("priority",PRIORITIES,"Medium"))+
   field("Assign to",select("owner",["DEMO-MAINT","DEMO-OPS","DEMO-QA"],"DEMO-MAINT"))+
   field("Target completion",dateField("due",dayAdd(today,3))),
   "Submit maintenance request")+
 '<p class="small">Machine and fault descriptions are invented. Closure means the example work is finished. No separate verification required.</p></section></div>';
 s+='<section class="panel"><div class="panel-head"><h2>Purchase request tracker</h2><span class="tag">'+purchases.length+' records</span></div>'+
 tab(["Request","Material / quantity","Owner","Due","Status","Latest follow-up","Manage"],
 purchases.slice().reverse().map(r=>row([
  context("purchase_request",r.id,r.id),h(r.itemId)+" · "+h(r.quantity),
  h(r.owner),h(r.dueDate||"Unscheduled")+' '+badge(r.dueDate,r.status,today),
  requestState(r),h(latest(r)),
  '<button type="button" class="action secondary" data-action="select-request" data-kind="purchase" data-id="'+h(r.id)+'">Manage</button>'
 ],"purchase_request",r.id)),"No fictional purchasing requests yet. Submit one above.")+'</section>';
 s+='<section class="panel"><div class="panel-head"><h2>Maintenance request tracker</h2><span class="tag">'+maint.length+' records</span></div>'+
 tab(["Request","Equipment / issue","Owner","Due","Status","Latest follow-up","Manage"],
 maint.slice().reverse().map(r=>row([
  context("pm_request",r.id,r.id),h(getMachine(state.pm,r.machineId)?.name||"General")+" · "+h(r.type),
  h(r.assignedTo||"Unassigned"),h(r.dueDate||"Unscheduled")+' '+badge(r.dueDate,r.status,today),
  requestState(r),h(latest(r)),
  '<button type="button" class="action secondary" data-action="select-request" data-kind="maintenance" data-id="'+h(r.id)+'">Manage</button>'
 ],"pm_request",r.id)),"No fictional maintenance requests yet. Submit one above.")+'</section>';
 if(selectedPurchase){
  const r=selectedPurchase,open=!["VERIFIED","CANCELLED"].includes(r.status);
  const po=state.purchaseOrders.find(p=>p.id===r.linkedPoId);
  s+='<section class="panel" id="request-detail"><div class="panel-head"><h2>Purchase request '+h(r.id)+'</h2>'+requestState(r)+'</div>'+
   '<p>Fictional material <b>'+h(r.itemId)+'</b> · '+h(r.quantity)+' units · Reason: '+h(r.reason)+
   ' · Linked PO: '+h(po?.number||"Not issued")+' · PO receipt: '+h(po?.receivedAt?.slice(0,10)||"Not received")+'</p>';
  if(open){
    s+=form("request-assign",
       '<input type="hidden" name="id" value="'+h(r.id)+'">'+
       field("Responsible",select("owner",DEMO_OWNERS,r.owner))+
       field("Next target date",dateField("due",r.dueDate||dayAdd(today,7))),
       "Update owner / due date");
    s+=form("request-purchase-followup",
      '<input type="hidden" name="id" value="'+h(r.id)+'">'+
      field("Follow-up event",select("note",REQUEST_FOLLOWUPS)),
      "Record follow-up");
    s+='<div class="actions">';
    if(["SUBMITTED","REVIEWING"].includes(r.status))s+='<button type="button" class="action" data-action="approve-request" data-id="'+h(r.id)+'">Approve request</button>';
    if(r.status==="APPROVED")s+='<button type="button" class="action" data-action="issue-request-po" data-id="'+h(r.id)+'">Issue fictional PO</button>';
    if(r.status==="ORDERED")s+='<a href="#purchasing" class="action secondary">Go to purchasing to receive PO</a>';
    if(r.status==="RECEIVED")s+='<button type="button" class="action" data-action="verify-purchase-request" data-id="'+h(r.id)+'">Confirm received / complete request</button>';
    s+='</div>';
  }
  s+='<h3>Follow-up history</h3>'+history(r.followups)+
   '<p class="small">Only a received PO can advance this request to requester confirmation. Approval and order creation are not completion.</p></section>';
 }
 if(selectedMaintenance){
  const r=selectedMaintenance,open=!["CLOSED","CANCELLED"].includes(r.status);
  s+='<section class="panel" id="request-detail"><div class="panel-head"><h2>Maintenance request '+h(r.id)+'</h2>'+requestState(r)+'</div>'+
  '<p>'+h(getMachine(state.pm,r.machineId)?.name||"General")+" · "+h(r.type)+
  ' · Target '+h(r.dueDate||"Unscheduled")+'</p>';
  if(open){
   s+=form("request-maint-assign",'<input type="hidden" name="id" value="'+h(r.id)+'">'+
    field("Responsible",select("owner",["DEMO-MAINT","DEMO-OPS","DEMO-QA"],r.assignedTo||"DEMO-MAINT"))+
    field("Target date",dateField("due",r.dueDate||dayAdd(today,3))),"Assign / update maintenance");
   s+=form("request-maint-followup",'<input type="hidden" name="id" value="'+h(r.id)+'">'+
    field("Update",select("note",MAINTENANCE_FOLLOWUPS)),"Record maintenance follow-up");
   s+='<button type="button" class="action" data-action="close-maint-request" data-id="'+h(r.id)+'">Mark work done / close</button>';
  }
  s+='<h3>Follow-up history</h3>'+history(r.followups)+
   (r.status==="CLOSED"?'<p class="small">Closed: '+h(r.closedAt||"Recorded")+' · '+h(r.resolution||"Example work completed")+'</p>':"")+
   '</section>';
 }
 s+='<div class="notice"><b>Browser-only simulation.</b> Records are not submitted to a purchasing department or maintenance staff. There are no emails, assignments to real people, notifications or automatic reminders. Due and overdue indicators update when Axiom is opened.</div>';
 return s;
}
function history(events=[]){
 if(!events?.length)return '<p class="small muted">No follow-up recorded.</p>';
 return events.slice().reverse().map(x=>'<div class="receipt"><b>'+h(x.note)+'</b> · '+h(x.by)+' · '+h(x.at.slice(0,16).replace("T"," "))+'</div>').join("");
}
