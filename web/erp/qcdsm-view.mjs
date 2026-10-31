/* QCDSM is a navigable operating view of current synthetic ERP evidence.
 * Each of five equal sectors opens its own functional domain, with no fabricated KPIs.
 */
import {qcdsmEvidence,qualityContextFor} from "./qcdsm.mjs";
import {DEPARTMENTS} from "./workforce.mjs";
import {packetIssues} from "./engine.mjs";
import {durationSeconds} from "../ewi/engine.mjs";
const h=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const options=(items,selected)=>items.map(x=>'<option '+(x===selected?'selected ':'')+'value="'+h(x)+'">'+h(x)+'</option>').join("");
const fmt=x=>x===null||x===undefined?"N/A":String(x);
const metric=(title,value,detail)=>'<div class="metric"><small>'+h(title)+'</small><strong>'+h(value)+'</strong><em>'+h(detail)+'</em></div>';
const heading=(label,sub)=>'<div class="lead"><div><div class="eyebrow">Operations / QCDSM</div>'+
 '<h1>'+h(label)+'</h1><p class="subtitle">'+h(sub)+'</p></div>'+
 '<a class="action secondary" href="#qcdsm">All domains</a></div>';
const demoNote='<p class="small">Updated from the current fictional records in this browser; not an external ERP, regulatory, payroll or BEAN data feed.</p>';
const dataTable=(headers,rows,empty)=>!rows.length?'<p class="small">'+h(empty)+'</p>':
 '<div class="tablewrap"><table><thead><tr>'+headers.map(x=>'<th>'+h(x)+'</th>').join("")+
 '</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(x=>'<td>'+h(x)+'</td>').join("")+'</tr>').join("")+
 '</tbody></table></div>';

export function wheelHtml(e){
 const domains=[
  {key:"Quality",route:"quality",measure:e.quality.openHolds+" open NCRs"},
  {key:"Cost",route:"cost",measure:"COPQ N/A"},
  {key:"Delivery",route:"delivery",measure:"OTD N/A"},
  {key:"Safety",route:"safety",measure:e.safetyPriority===null?"Priority N/A":"Priority "+e.safetyPriority},
  {key:"Morale",route:"morale",measure:e.moraleRisk===null?"Risk N/A":"Risk "+e.moraleRisk+"/100",driver:true}
 ];
 const polar=(radius,deg)=>[
  230+radius*Math.cos(deg*Math.PI/180),
  230+radius*Math.sin(deg*Math.PI/180)
 ];
 const sectors=domains.map((domain,i)=>{
  const start=-54+i*72,end=start+72;
  const [ax,ay]=polar(72,start),[bx,by]=polar(210,start);
  const [cx,cy]=polar(210,end),[dx,dy]=polar(72,end);
  const path="M "+ax+" "+ay+" L "+bx+" "+by+" A 210 210 0 0 1 "+cx+" "+cy+
   " L "+dx+" "+dy+" A 72 72 0 0 0 "+ax+" "+ay+" Z";
  const [x,y]=polar(147,start+36);
  return '<a href="#'+domain.route+'" class="wheel-sector" tabindex="0" '+
   'data-qcdsm-domain="'+domain.key+'"'+(domain.driver?' data-driver="true"':'')+
   ' aria-label="Open '+domain.key+': '+h(domain.measure)+'">'+
   '<title>Open '+domain.key+'</title>'+
   '<path d="'+path+'" fill="'+(domain.driver?"#183c29":i%2?"#182127":"#202d30")+
   '" stroke="'+(domain.driver?"#79de4b":"#536b69")+'" stroke-width="2"/>'+
   '<g text-anchor="middle" fill="#ecf3f2" pointer-events="none">'+
   '<text x="'+x+'" y="'+(y-6)+'" font-size="18" font-weight="700">'+domain.key+'</text>'+
   '<text x="'+x+'" y="'+(y+15)+'" font-size="12" fill="#b5c9c2">'+h(domain.measure)+'</text>'+
   (domain.driver?'<text x="'+x+'" y="'+(y+34)+'" font-size="11" font-weight="800" fill="#79de4b">DRIVER</text>':"")+
   '</g></a>';
 }).join("");
 return '<div class="wheel-graphic"><svg viewBox="0 0 460 460" role="group" '+
  'aria-label="Choose one of five equal QCDSM domains to open its current ERP section: Quality, Cost, Delivery, Safety, or Morale. Morale is the performance driver." '+
  'style="width:100%;height:auto;display:block">'+sectors+
  '<circle cx="230" cy="230" r="70" fill="#111a1e" stroke="#657b78" stroke-width="2" pointer-events="none"/>'+
  '<circle cx="230" cy="230" r="13" fill="#79de4b" opacity=".8" pointer-events="none"/></svg></div>';
}
export function renderQcdsm(state,workforce,department="Assembly",today){
 const e=qcdsmEvidence(state,workforce,department,today);
 return '<div class="eyebrow">QCDSM / Operations</div>'+
  '<p class="subtitle">Select a section to open its current records.</p>'+
  '<section class="panel wheel-panel">'+wheelHtml(e)+'</section>'+
  '<form class="controls" data-form="qcdsm-department" style="margin-bottom:15px">'+
  '<label>Workforce and safety context<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<button type="submit" class="action secondary">Apply</button></form>'+
  '<p class="small">Figures come from this browser’s current fictional ERP records. Cost and delivery outcome rates remain N/A until those underlying transactions exist. Morale is the driver, while all five domains matter.</p>';
}
export function renderCost(state,sessions=[]){
 const open=state.purchaseOrders.filter(p=>p.status==="ORDERED");
 const received=state.purchaseOrders.filter(p=>p.status==="RECEIVED");
 const completed=sessions.filter(s=>s.end);
 const secs=completed.reduce((n,s)=>n+durationSeconds(s),0);
 return heading("Cost","Procurement transactions and logged operation time from the same ERP records. No monetary baseline has been recorded.")+
  '<div class="metrics">'+metric("Actual cost","N/A","No prices, labor rates or verified cost postings")+
  metric("Outstanding POs",open.length,"Awaiting receiving")+
  metric("Received POs",received.length,"Fictional receipt records")+
  metric("Completed clock time",(secs/3600).toFixed(2)+" h","Elapsed shop-floor sessions; not paid labor")+'</div>'+
  '<section class="panel"><div class="panel-head"><h2>Procurement activity</h2><a class="action secondary" href="#purchasing">Purchasing</a></div>'+
  dataTable(["PO","Stock item","Quantity","Status"],state.purchaseOrders.slice().reverse().map(p=>[p.number,p.itemId,p.quantity,p.status]),
   "No purchase orders entered. Create one in Purchasing to see it here.")+'</section>'+
  '<section class="panel"><div class="panel-head"><h2>Operation time evidence</h2><a class="action secondary" href="#ewi">EWI & Clocking</a></div>'+
  dataTable(["Work order","Operation","Completed hours"],completed.slice().reverse().slice(0,20).map(s=>[s.jobNumber,s.operation,(durationSeconds(s)/3600).toFixed(2)]),
   "No completed fictional clock sessions recorded.")+
  '<p class="small">Clock time is not automatically a labor expense. Verified COPQ and monetary totals require documented scrap/rework costs, labor rates and material prices.</p></section>'+demoNote;
}
export function renderDelivery(state){
 const queue=state.jobs.map(j=>({...j,issues:packetIssues(state,j.id)}));
 const ready=queue.filter(j=>!j.issues.length).length;
 const outstanding=state.purchaseOrders.filter(p=>p.status==="ORDERED").length;
 const blocked=queue.length-ready;
 return heading("Delivery","Work-order readiness and purchasing status update as jobs, holds, reservations and receipts change.")+
  '<div class="metrics">'+metric("On-time delivery","N/A","No confirmed shipment or promised-delivery dates")+
  metric("Ready work orders",ready+" / "+queue.length,"Example packet and material checks")+
  metric("Needs attention",blocked,"Open holds, revision issues or material gaps")+
  metric("Outstanding POs",outstanding,"Stock awaiting receipt")+'</div>'+
  '<section class="panel"><div class="panel-head"><h2>Current work-order queue</h2><a class="action secondary" href="#jobs">Work Orders</a></div>'+
  '<div class="tablewrap"><table><thead><tr><th>Work order</th><th>Part</th><th>Readiness</th><th>Issues</th></tr></thead><tbody>'+
  queue.map(j=>'<tr><td><a href="#jobs" class="cell-link" data-job="'+h(j.id)+'">'+h(j.jobNumber)+'</a></td><td>'+h(j.partNumber)+
   '</td><td>'+(!j.issues.length?"READY":"REVIEW")+'</td><td>'+h(j.issues.join("; ")||"Demo checks passed")+'</td></tr>').join("")+
  '</tbody></table></div></section>'+
  '<section class="panel"><h2>Delivery evidence boundary</h2><p>Readiness does not equal on-time delivery. Actual OTD requires due dates and confirmed shipment events. This view does not invent them.</p>'+
  '<a class="action secondary" href="#purchasing">Open Purchasing</a></section>'+demoNote;
}
export function renderSafety(state,workforce,department="Assembly",today){
 const e=qcdsmEvidence(state,workforce,department,today);
 const signalRows=e.possibleFactors.length?e.possibleFactors.map(x=>
  '<tr><td>'+h(x.label)+'</td><td>'+h(x.evidence)+'</td><td>Review; not established root cause</td></tr>').join(""):
  '<tr><td colspan="3">No flagged signals in the recorded evidence. Missing data is not proof of safety.</td></tr>';
 const recent=e.incidents.slice().reverse();
 return heading("Safety","Recent safety events, department confidence evidence and potential workload pressures recorded in this fictional ERP.")+
  '<section class="panel"><form class="controls" data-form="qcdsm-department">'+
  '<label>Department<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<button type="submit" class="action secondary">View</button></form></section>'+
  '<div class="metrics">'+metric("Safety priority",fmt(e.safetyPriority),"Attention heuristic, not a regulatory rate")+
  metric("Recent recordable examples",e.recordables,"Last 30 days in selected department")+
  metric("Near misses",e.nearMisses,"Last 30 days")+
  metric("Surveyed concerns",e.survey?e.survey.concerned+" / "+e.survey.respondents:"N/A","Aggregate responses only")+'</div>'+
  '<section class="panel"><h2>Recent recorded examples</h2>'+
  dataTable(["Event","Date","Classification"],recent.map(i=>[i.id,i.observedOn,i.kind.replace(/_/g," ")]),
   "No safety events recorded in this department in the last 30 days.")+'</section>'+
  '<section class="panel"><h2>Record synthetic safety evidence</h2><div class="columns">'+
  '<div><h3>Fictional event</h3><form class="controls" data-form="safety-incident">'+
  '<label>Department<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<label>Classification<select name="kind"><option value="recordable">Recordable-classified example</option>'+
  '<option value="first_aid">First aid</option><option value="near_miss">Near miss</option></select></label>'+
  '<label>Date<input name="observedOn" type="date" value="'+h(today)+'" max="'+h(today)+'" required></label>'+
  '<button type="submit" class="action">Record event</button></form>'+
  '<p class="small">Not a regulatory classification or an actual employee injury report. No names or medical details.</p></div>'+
  '<div><h3>Aggregate safety confidence</h3><form class="controls" data-form="safety-survey">'+
  '<label>Department<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<label>Respondents<input name="respondents" type="number" min="1" max="1000" value="12" required></label>'+
  '<label>Reported concern<input name="concerned" type="number" min="0" max="1000" value="3" required></label>'+
  '<button type="submit" class="action">Record aggregate</button></form>'+
  '<p class="small">Event records do not establish how employees feel; confidence data requires its own entered evidence.</p></div>'+
  '</div></section>'+
  '<section class="panel"><h2>Investigation signals</h2>'+
  '<div class="tablewrap"><table><thead><tr><th>Potential factor</th><th>Source</th><th>Meaning</th></tr></thead>'+
  '<tbody>'+signalRows+'</tbody></table></div>'+
  '<div class="actions"><a class="action secondary" href="#quality">Quality / RCA</a>'+
  '<a class="action secondary" href="#pm">PM Tracker</a>'+
  '<a class="action secondary" href="#morale">Morale</a></div></section>'+demoNote;
}
export function qualityRcaHtml(state,workforce,department,today){
 const choices=(state.quality||[]).map(q=>'<option value="'+h(q.id)+'">'+h(q.number)+' · '+h(q.reason)+'</option>').join("");
 const e=qcdsmEvidence(state,workforce,department,today);
 const latest=state.quality.map(q=>({q,ctx:qualityContextFor(state,q.id)})).filter(x=>x.ctx);
 const history=latest.map(({q,ctx})=>'<tr><td>'+h(q.number)+'</td><td>'+h(ctx.department)+'</td>'+
  '<td>'+h(ctx.moraleRisk===null?"N/A":ctx.moraleRisk)+
  '</td><td>'+h(ctx.safetyEventIds.length)+' event(s)</td><td>'+h(ctx.finding)+
  '</td><td>'+h(ctx.recordedOn)+'</td></tr>').join("");
 return '<section class="panel"><div class="panel-head"><h2>QCDSM root-cause investigation</h2>'+
  '<a class="action secondary" href="#qcdsm">All domains</a></div>'+
  '<p>Review contributing workforce and safety conditions alongside machine, material, method and measurement evidence. The system never assigns a root cause automatically.</p>'+
  '<p class="small">Current '+h(department)+' morale risk: <b>'+h(fmt(e.moraleRisk))+
  '</b> / 100; recent recordable-classified events: <b>'+h(e.recordables)+
  '</b>; overtime burden: <b>'+h(e.overtimeLoad===null?"N/A":(e.overtimeLoad*100).toFixed(1)+"%")+'</b>.</p>'+
  (state.quality.length?'<form data-form="quality-qcdsm-review" class="controls">'+
   '<label>Existing NCR<select name="qualityId">'+choices+'</select></label>'+
   '<label>Department context<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
   '<button class="action" type="submit">Capture QCDSM evidence for RCA</button></form>':
   '<p class="small">Create a fictional quality hold above to enable an RCA evidence snapshot.</p>')+
  '<div class="tablewrap"><table><thead><tr><th>NCR</th><th>Department</th><th>Morale risk</th><th>Safety evidence</th><th>Finding</th><th>Date</th></tr></thead>'+
  '<tbody>'+(history||'<tr><td colspan="6">No investigation snapshots recorded.</td></tr>')+
  '</tbody></table></div><p class="small">Recorded context is historical evidence for human RCA review, not a corrective action, confirmed cause, regulatory conclusion, or job release.</p></section>';
}
