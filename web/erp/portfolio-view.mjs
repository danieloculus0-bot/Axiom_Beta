/* Audited Axiom/SuperForge feature directory. Browser demo ≠ local authenticated beta.
 * Independent apps are linked by source, never presented as installed Axiom components.
 */
const escapeHtml=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
export const MODULE_CATALOG=[
 ["Manufacturing & engineering",[
  ["Work orders & Job Tracker","Browser-local","jobs","Canonical fictional jobs, part identity and readiness."],
  ["Routing, methods & planning","Browser-local","routing","Editable fictional job routing; no machine dispatch."],
  ["EWI / time tickets","Browser-local","ewi","Operator clock simulator linked to work orders."],
  ["EZ CAM","Independent alpha","cam","Synthetic facing assumptions here; independent EZ-CAM owns detailed toolpaths."],
  ["EZstimate / quoting","Independent app",null,"Separate estimating workbench; no Axiom quote import on this site."],
  ["EZ Methods dependencies","Local beta","routing","Local SuperForge method planning; browser routing is not a sync."],
  ["Drawing Control / ForgeVault","Local beta","documents","Browser drawing revision examples; controlled private files remain local."],
  ["EZ-FAIR / FAI","Local beta","quality","FAI characteristic extraction is a separate tested desktop workflow."],
  ["Job Passport","Local beta","jobs","Linked local job evidence; browser job view is a subset."]
 ]],
 ["Supply, equipment & operations",[
  ["Inventory & part tracker","Browser-local","inventory","Fictional stock, reservations and availability."],
  ["Purchasing, receipts & requisitions","Browser-local","purchasing","Browser purchase orders and verified receipt examples."],
  ["Purchase / maintenance requests","Browser-local","requests","Fictional ownership, follow-up and closeout."],
  ["Preventive maintenance","Browser-local","pm","Fictional machines, PM intervals and closeout."],
  ["Supplier intelligence","Local beta","purchasing","Local vendor offers, delivery and invoice matching are not synced here."],
  ["Cost & supplier reconciliation","Local beta","cost","Browser cost view does not replace local actuals / GL."],
  ["Production quality & RCA","Browser-local","quality","Fictional quality cases, hold and investigation records."],
  ["Safety / QCDSM","Browser-local","qcdsm","Five working operational-domain entry points."]
 ]],
 ["People, finance & oversight",[
  ["Human Resources & training","Browser-local","hr","Demo-coded employees, role and training verification."],
  ["PTO requests","Browser-local","pto","Fictional review queue only; no actual leave balances."],
  ["Payroll","Browser preview","payroll","Calculation preview only. Real pay runs use private local SuperForge."],
  ["Morale, leadership & recognition","Browser-local","morale","Department aggregate pulse, employee training and recognition; no individual morale scoring."],
  ["Accounting & journal","Local beta","payroll","Balanced ledger and controlled pay runs remain in local backend."],
  ["Sheet Workbench","Local beta",null,"CSV/XLSX staging is supported locally, not loaded into public Pages."],
  ["ISO-Hungry rewards","Local beta","morale","Browser recognition points are not payments or redemption."],
  ["Executive intelligence","Local beta","reports","Review-only evidence recommendations, not autonomous decisions."],
  ["Reporting and activity history","Browser-local","reports","Current fictional reports, CSV and event receipts."],
  ["Collaboration, workflow & learning","Local beta","audit","Local workflow event contracts; the demo has its own event history."],
  ["BEAN reasoning / advice","Not connected",null,"Separate Core service. No live adapter or approval authority."]
 ]]
];
export function renderModuleDirectory(){
 const groups=MODULE_CATALOG.map(([name,items])=>
  '<section class="panel"><h2>'+escapeHtml(name)+'</h2><div class="tablewrap"><table><thead><tr><th>Capability</th><th>Availability</th><th>What it does here</th><th>Open</th></tr></thead><tbody>'+
  items.map(([title,status,route,detail])=>'<tr><td>'+escapeHtml(title)+'</td><td>'+escapeHtml(status)+'</td><td>'+escapeHtml(detail)+'</td><td>'+
   (route?'<a class="action secondary" href="#'+route+'">Open related demo</a>':'<span class="small">No public in-app screen</span>')+'</td></tr>').join("")+
  '</tbody></table></div></section>').join("");
 return '<div class="lead"><div><div class="eyebrow">Axiom / SuperForge audited scope</div><h1>All workbenches</h1><p class="subtitle">One place to discover the actual capabilities, the browser-local equivalents, and what still belongs to the private local beta. No pretend sync.</p></div></div>'+
  '<div class="notice">This is a fictional public demo. Local SuperForge modules and independent repositories are not automatically integrated. No personal records, uploaded documents or production authority.</div>'+
  '<section class="panel"><h2>Independent engineering workbenches</h2><p>EZ CAM and EZstimate are separate projects. Browse their current implementations without implying a connected production service.</p>'+
  '<div class="actions"><a class="action secondary" href="https://github.com/danieloculus0-bot/EZ-CAM" target="_blank" rel="noopener noreferrer">EZ CAM source</a>'+
  '<a class="action secondary" href="https://github.com/danieloculus0-bot/EZstimate" target="_blank" rel="noopener noreferrer">EZstimate source</a>'+
  '<a class="action secondary" href="https://github.com/danieloculus0-bot/EZ-FAIR" target="_blank" rel="noopener noreferrer">EZ-FAIR source</a></div></section>'+groups;
}
const positive=(raw,label,min,max)=>{const v=Number(raw);if(!Number.isFinite(v)||v<min||v>max)throw Error(label+" must be between "+min+" and "+max);return v;};
export function camFacingEnvelope(input){
 const width=positive(input.width,"Stock width (mm)",1,2000),height=positive(input.height,"Stock height (mm)",1,2000);
 const diameter=positive(input.diameter,"Tool diameter (mm)",1,100),stepover=positive(input.stepover,"Stepover (%)",1,80);
 const depth=positive(input.depth,"Facing allowance (mm)",.01,25),stepdown=positive(input.stepdown,"Stepdown (mm)",.01,10);
 const rows=Math.ceil((height+diameter)/(diameter*stepover/100))+1,levels=Math.ceil(depth/stepdown);
 if(rows*levels>10000)throw Error("Preview exceeds safe browser demonstration limit");
 return {rows,levels,passCount:rows*levels,estimatedFeedTravelMm:Math.round(rows*levels*(width+diameter))};
}
export function renderCam(job,preview=null){
 const operationRows=job?.routing?.operations||[];
 return '<div class="lead"><div><div class="eyebrow">Manufacturing / independent EZ CAM boundary</div><h1>CAM preparation</h1><p class="subtitle">Planning context from the selected fictional work order, plus a separate sample facing-envelope calculator. No CNC code or machine setup.</p></div></div>'+
  '<div class="notice">The sample stock below is NOT a dimension or programmed operation from this job. EZ CAM is an independently developed v0.1 prototype. This page does not import STEP, post G-code, simulate stock removal, or synchronize estimates.</div>'+
  '<section class="panel"><h2>Selected work order context</h2><p><strong>'+escapeHtml(job?.jobNumber||"No job")+'</strong> · '+escapeHtml(job?.partNumber||"")+' · revision '+escapeHtml(job?.revision||"")+'</p>'+
  '<p>Actual demo routing steps (read-only here):</p><ul>'+operationRows.map(s=>'<li>'+escapeHtml(s.step)+' · '+escapeHtml(s.name)+' · '+escapeHtml(s.center)+'</li>').join("")+'</ul>'+
  '<div class="actions"><a class="action secondary" href="#routing">Open this job routing</a><a class="action secondary" href="#documents">Review fictional drawing</a></div></section>'+
  '<section class="panel"><h2>Generic facing-envelope exercise</h2><p>Enter imaginary rectangular stock and tool assumptions. It reports a geometrical pass-count envelope, not a verified toolpath, machine capacity, cycle time or cutting recommendation.</p>'+
  '<form class="controls" data-form="cam-envelope"><label>Width (mm)<input name="width" type="number" value="120" min="1" max="2000" step="any" required></label>'+
  '<label>Height (mm)<input name="height" type="number" value="80" min="1" max="2000" step="any" required></label>'+
  '<label>Cutter diameter (mm)<input name="diameter" type="number" value="16" min="1" max="100" step="any" required></label>'+
  '<label>Stepover (%)<input name="stepover" type="number" value="55" min="1" max="80" step="any" required></label>'+
  '<label>Facing allowance (mm)<input name="depth" type="number" value="0.5" min="0.01" max="25" step="any" required></label>'+
  '<label>Stepdown (mm)<input name="stepdown" type="number" value="0.5" min="0.01" max="10" step="any" required></label>'+
  '<button class="action" type="submit">Calculate fictional envelope</button></form>'+
  (preview?'<div class="metrics"><div class="metric"><small>Rows / level</small><strong>'+preview.rows+'</strong></div><div class="metric"><small>Depth levels</small><strong>'+preview.levels+'</strong></div><div class="metric"><small>Illustrative passes</small><strong>'+preview.passCount+'</strong></div></div><p class="small">Rough feed-travel envelope '+preview.estimatedFeedTravelMm+' mm. Tool entry, clearance, physics, feeds, fixture and collisions NOT assessed.</p>':'')+
  '</section><section class="panel"><h2>Detailed EZ CAM prototype</h2><p>Its independent browser code implements synthetic facing-path preview and manual-assumption laser/brake estimators. Axiom has no accepted estimate-import contract or live equipment connection.</p>'+
  '<a class="action secondary" href="https://github.com/danieloculus0-bot/EZ-CAM" target="_blank" rel="noopener noreferrer">Inspect independent EZ CAM workbench</a></section>';
}