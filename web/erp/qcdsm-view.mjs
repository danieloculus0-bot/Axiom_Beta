/* One QCDSM wheel driven by evidence in Axiom ERP and workforce models. */
import {qcdsmEvidence,qualityContextFor} from "./qcdsm.mjs";
import {DEPARTMENTS} from "./workforce.mjs";
const h=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const options=(items,selected)=>items.map(x=>'<option '+(x===selected?'selected ':'')+'value="'+h(x)+'">'+h(x)+'</option>').join("");
const fmt=x=>x===null||x===undefined?"N/A":String(x);
export function wheelHtml(e){
 const slices=[
  {key:"Quality",x:149,y:145,v:String(e.quality.openHolds)+" open NCR(s)",angle:-90},
  {key:"Cost",x:311,y:145,v:"N/A",angle:0},
  {key:"Delivery",x:311,y:315,v:"N/A",angle:90},
  {key:"Safety",x:149,y:315,v:fmt(e.safetyPriority)+" priority",angle:180}
 ];
 // A four-sector ring with Morale in the center; positions express relationships, not a causal verdict.
 const arcs=slices.map((s,i)=>{
  const start=-180+i*90,end=start+90;
  const p=(r,a)=>[230+r*Math.cos(a*Math.PI/180),230+r*Math.sin(a*Math.PI/180)];
  const [ax,ay]=p(82,start),[bx,by]=p(205,start),[cx,cy]=p(205,end),[dx,dy]=p(82,end);
  const path="M "+ax+" "+ay+" L "+bx+" "+by+" A 205 205 0 0 1 "+cx+" "+cy+
    " L "+dx+" "+dy+" A 82 82 0 0 0 "+ax+" "+ay+" Z";
  return '<path d="'+path+'" fill="'+(i%2?"#182127":"#202d30")+'" stroke="#536b69" stroke-width="2"/>';
 }).join("");
 const labels=slices.map(s=>'<g text-anchor="middle" fill="#ecf3f2">'+
  '<text x="'+s.x+'" y="'+s.y+'" font-size="18" font-weight="700">'+s.key+'</text>'+
  '<text x="'+s.x+'" y="'+(s.y+20)+'" font-size="12" fill="#b5c9c2">'+h(s.v)+'</text></g>').join("");
 return '<div style="max-width:470px;margin:0 auto"><svg viewBox="0 0 460 460" role="img" '+
  'aria-label="QCDSM wheel: Quality, Cost, Delivery and Safety around Morale. Current scores use observed synthetic evidence and report missing baselines as N/A." '+
  'style="width:100%;height:auto;display:block">'+arcs+
  '<circle cx="230" cy="230" r="80" fill="#172b20" stroke="#79de4b" stroke-width="3"/>'+
  '<g text-anchor="middle" fill="#d0f4c8"><text x="230" y="220" font-size="22" font-weight="800">MORALE</text>'+
  '<text x="230" y="250" font-size="20" font-weight="700">'+h(fmt(e.moraleRisk))+
  '<tspan font-size="11"> / 100 risk</tspan></text></g>'+labels+'</svg></div>';
}
export function renderQcdsm(state,workforce,department="Assembly",today){
 const e=qcdsmEvidence(state,workforce,department,today);
 const signalRows=e.possibleFactors.length?e.possibleFactors.map(x=>
  '<tr><td>'+h(x.label)+'</td><td>'+h(x.evidence)+'</td><td>Investigate; not established root cause</td></tr>').join(""):
  '<tr><td colspan="3">No current warning signals in entered evidence. This is not proof of zero risk.</td></tr>';
 return '<div class="lead"><div><div class="eyebrow">Cross-functional performance / evidence</div>'+
  '<h1>QCDSM operating wheel</h1><p class="subtitle">Morale is the central organizational lever. Quality, Cost, Delivery and Safety connect through source-backed records, not invented outcomes.</p></div></div>'+
  '<div class="notice">Synthetic browser-local demonstration. Missing data is N/A. The wheel highlights candidates for investigation; it cannot establish employee feelings, actual root cause, incident classification or production fitness.</div>'+
  '<section class="panel"><form class="controls" data-form="qcdsm-department">'+
  '<label>Department<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<button class="action secondary">View department context</button></form></section>'+
  '<div class="columns"><section class="panel"><h2>QCDSM wheel</h2>'+wheelHtml(e)+
  '<p class="small">Safety priority is a demonstration attention score, not an OSHA rate. Quality shows all open job-linked NCRs because the current ERP has no reliable department mapping. Cost and Delivery require source baselines.</p></section>'+
  '<section class="panel"><h2>What the evidence actually says</h2>'+
  '<div class="feature" style="grid-template-columns:1fr 1fr">'+
  '<a href="#quality"><b>Quality</b><span>'+h(e.quality.openHolds)+' open NCRs in ERP</span></a>'+
  '<a href="#reports"><b>Cost</b><span>No verified COPQ baseline</span></a>'+
  '<a href="#reports"><b>Delivery</b><span>No verified OTD baseline</span></a>'+
  '<a href="#qcdsm-safety"><b>Safety</b><span>'+h(e.recordables)+' recent recordable-classified examples, '+h(e.nearMisses)+' near misses</span></a>'+
  '</div><div class="receipt"><b>Morale</b>: '+h(fmt(e.moraleRisk))+
  ' / 100 aggregate risk. Latest department pulse '+h(e.pulse?.id||"not recorded")+
  '; overtime burden '+h(e.overtimeLoad===null?"N/A":(e.overtimeLoad*100).toFixed(1)+"% of scheduled straight-time hours")+'.</div>'+
  '<div class="receipt"><b>Safety confidence</b>: '+(e.survey?
  h(e.survey.concerned)+" of "+h(e.survey.respondents)+" fictional respondents reported concern ("+
  h((100*e.survey.concerned/e.survey.respondents).toFixed(1))+"%).":"N/A. An incident alone does not prove how people feel.")+'</div>'+
  '<a class="action secondary" href="#morale">Open Morale & Recognition</a></section></div>'+
  '<section class="panel"><h2>Cross-domain investigation signals</h2>'+
  '<div class="tablewrap"><table><thead><tr><th>Candidate factor</th><th>Source</th><th>RCA interpretation</th></tr></thead><tbody>'+
  signalRows+'</tbody></table></div><p class="small">An elevated overtime ratio is a fatigue/workload hypothesis, not a personal diagnosis. A recordable is a safety-review trigger; employee safety perceptions require distinct evidence.</p></section>'+
  '<section id="qcdsm-safety" class="panel"><h2>Safety evidence (synthetic)</h2>'+
  '<div class="columns"><div><h3>Log a fictional event</h3><form class="controls" data-form="safety-incident">'+
  '<label>Department<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<label>Classification<select name="kind"><option value="recordable">Recordable-classified example</option><option value="first_aid">First aid</option><option value="near_miss">Near miss</option></select></label>'+
  '<label>Date<input name="observedOn" type="date" value="'+h(today)+'" max="'+h(today)+'" required></label>'+
  '<button class="action">Record fictional event</button></form>'+
  '<p class="small">Classification is a hypothetical input, not a regulatory determination. No names or medical details.</p></div>'+
  '<div><h3>Aggregate safety-confidence response</h3><form class="controls" data-form="safety-survey">'+
  '<label>Department<select name="department">'+options(DEPARTMENTS,department)+'</select></label>'+
  '<label>Survey respondents<input name="respondents" type="number" min="1" max="1000" value="12" required></label>'+
  '<label>Reported concern<input name="concerned" type="number" min="0" max="1000" value="3" required></label>'+
  '<button class="action">Record example survey</button></form>'+
  '<p class="small">This is entered aggregate evidence only, not an actual confidential employee survey.</p></div></div></section>'+
  '<section class="panel"><h2>Quality root-cause analysis handoff</h2><p>Open a quality record and capture the current department pulse and safety evidence as an auditable, time-stamped investigation snapshot. Existing EWI hold/release behavior is unchanged.</p>'+
  '<a class="action" href="#quality">Open Quality Control / RCA</a><p class="small"><a href="https://danieloculus0-bot.github.io/64-/" rel="noopener noreferrer">Open the separate 64Δ facility board</a>. Its 8×8 layout is a scenario and location model, not a synchronized feed from this public ERP demo.</p></section>';
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
  '<a class="action secondary" href="#qcdsm">Open QCDSM wheel</a></div>'+
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
