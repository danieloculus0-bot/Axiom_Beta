/* One QCDSM wheel driven by evidence in Axiom ERP and workforce models. */
import {qcdsmEvidence,qualityContextFor} from "./qcdsm.mjs";
import {DEPARTMENTS} from "./workforce.mjs";
const h=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const options=(items,selected)=>items.map(x=>'<option '+(x===selected?'selected ':'')+'value="'+h(x)+'">'+h(x)+'</option>').join("");
const fmt=x=>x===null||x===undefined?"N/A":String(x);
export function wheelHtml(e){
 // Five equal 72-degree domains. Morale is a driver, not a sixth category or a larger slice.
 const domains=[
  {key:"Quality",measure:e.quality.openHolds+" open NCRs"},
  {key:"Cost",measure:"COPQ N/A"},
  {key:"Delivery",measure:"OTD N/A"},
  {key:"Safety",measure:e.safetyPriority===null?"Priority N/A":"Priority "+e.safetyPriority},
  {key:"Morale",measure:e.moraleRisk===null?"Risk N/A":"Risk "+e.moraleRisk+"/100",driver:true}
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
  return '<g data-qcdsm-domain="'+domain.key+'"'+(domain.driver?' data-driver="true"':'')+'>'+
   '<path d="'+path+'" fill="'+(domain.driver?"#183c29":i%2?"#182127":"#202d30")+
   '" stroke="'+(domain.driver?"#79de4b":"#536b69")+'" stroke-width="2"/>'+
   '<g text-anchor="middle" fill="#ecf3f2">'+
   '<text x="'+x+'" y="'+(y-6)+'" font-size="18" font-weight="700">'+domain.key+'</text>'+
   '<text x="'+x+'" y="'+(y+15)+'" font-size="12" fill="#b5c9c2">'+h(domain.measure)+'</text>'+
   (domain.driver?'<text x="'+x+'" y="'+(y+34)+'" font-size="11" font-weight="800" fill="#79de4b">DRIVER</text>':"")+
   '</g></g>';
 }).join("");
 return '<div style="max-width:470px;margin:0 auto"><svg viewBox="0 0 460 460" role="img" '+
  'aria-label="Five equal QCDSM sectors: Quality, Cost, Delivery, Safety, Morale. All five are essential. Morale is the organizational driver, not an extra sixth domain. Scores show synthetic records or N/A for missing baselines." '+
  'style="width:100%;height:auto;display:block">'+sectors+
  '<circle cx="230" cy="230" r="70" fill="#111a1e" stroke="#657b78" stroke-width="2"/>'+
  '<g text-anchor="middle" fill="#e9f5ed"><text x="230" y="226" font-size="26" font-weight="850">QCDSM</text>'+
  '<text x="230" y="248" font-size="12" fill="#b5c9c2">5 domains</text></g></svg></div>';
}
export function renderQcdsm(state,workforce,department="Assembly",today){
 const e=qcdsmEvidence(state,workforce,department,today);
 const signalRows=e.possibleFactors.length?e.possibleFactors.map(x=>
  '<tr><td>'+h(x.label)+'</td><td>'+h(x.evidence)+'</td><td>Investigate; not established root cause</td></tr>').join(""):
  '<tr><td colspan="3">No current warning signals in entered evidence. This is not proof of zero risk.</td></tr>';
 return '<div class="lead"><div><div class="eyebrow">Cross-functional performance / evidence</div>'+
  '<h1>QCDSM operating wheel</h1><p class="subtitle">Five essential domains: Quality, Cost, Delivery, Safety and Morale. Morale is the Pareto driver influencing the other four, not a sixth category or a replacement for them.</p></div></div>'+
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
  '<a href="#morale"><b>Morale · driver</b><span>'+h(fmt(e.moraleRisk))+' / 100 aggregate risk; open workforce pulse</span></a>'+
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
