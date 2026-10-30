/* Browser-only views. All values are invented or selected from fixed demo options. */
import {DEPARTMENTS,ROLES,CATEGORIES,REASONS,demoBalance} from "./workforce.mjs";
const h=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const options=(values,selected)=>values.map(x=>'<option value="'+h(x.value)+'" '+(x.value===selected?'selected':'')+'>'+h(x.label)+'</option>').join("");
const roleOptions=selected=>options(ROLES.map(x=>({value:x.id,label:x.title})),selected);
const peopleOptions=w=>options(w.people.map(x=>({value:x.id,label:x.id})));
const trainingOptions=w=>options(w.requirements.map(x=>({value:x.id,label:x.title})));
const table=(headers,rows,empty="No synthetic records yet.")=>rows.length?
 '<div class="tablewrap"><table><thead><tr>'+headers.map(x=>'<th>'+h(x)+'</th>').join("")+
 '</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(x=>'<td>'+x+'</td>').join("")+'</tr>').join("")+
 '</tbody></table></div>':'<div class="empty">'+h(empty)+'</div>';
const heading=(path,title,description)=>'<div class="lead"><div><div class="eyebrow">'+h(path)+'</div><h1>'+h(title)+
 '</h1><p class="subtitle">'+h(description)+'</p></div></div>';
const metric=(label,value,detail)=>'<div class="metric"><small>'+h(label)+'</small><strong>'+h(value)+
 '</strong><em>'+h(detail)+'</em></div>';
const notice='<div class="notice">Entirely synthetic, saved only in this browser. No real identities, confidential HR records, payroll, authenticated approvals, employee surveillance, or live BEAN analysis.</div>';
export function renderHr(w){
 const earned=w.ledger.reduce((n,x)=>n+x.points,0);
 let html=heading("People / HR demonstration","Human Resources",
  "Demo-only employee codes, organizational role assignments, verified-training examples, and positive recognition. Based on existing Axiom org and leadership structures.");
 html+=notice;
 html+='<div class="metrics">'+metric("Demo employees",w.people.length,"Fictional codes only")+
  metric("Role definitions",ROLES.length,"Generic organization")+
  metric("Training completions",w.completions.length,"Simulated verification")+
  metric("Recognition points",earned,"Not cash or payroll")+'</div>';
 html+='<div class="columns"><section class="panel"><div class="panel-head"><h2>Organization & role assignments</h2>'+
  '<span class="tag">DEMO identities</span></div>'+
  table(["Employee code","Department","Assigned role","Change role"],w.people.map(p=>{
   const role=ROLES.find(r=>r.id===p.role)||ROLES[0];
   return [h(p.id),h(role.department),h(role.title),
    '<form class="controls" data-form="hr-role"><input type="hidden" name="person" value="'+h(p.id)+'">'+
    '<label><span class="small">Role</span><select name="role" aria-label="Role for '+h(p.id)+'">'+roleOptions(role.id)+'</select></label>'+
    '<button class="action secondary" type="submit">Assign</button></form>'];
  }))+'</section><section class="panel"><h2>Add fictional employee code</h2>'+
  '<p class="small">Generate a DEMO code. No names, emails, birthdates or personal records are collected.</p>'+
  '<form class="controls" data-form="hr-person"><label>Generic role<select name="role">'+roleOptions("operator")+
  '</select></label><button class="action" type="submit">Add demo code</button></form>'+
  '<h3 style="margin-top:22px">HR workflow boundary</h3>'+
  '<p class="small">Actual employment records, qualifications, time-off approvals, pay profiles and role permissions belong to Axiom’s authenticated local backend. None are loaded here.</p>'+
  '<a class="action secondary" href="#morale">Open Morale & Recognition</a></section></div>';
 html+='<section class="panel"><div class="panel-head"><h2>Training requirements and verification</h2><span class="tag">Synthetic completions</span></div>'+
  table(["Key","Requirement","Applies to role","Recurs after","Recognition"],w.requirements.map(t=>[
   h(t.id),h(t.title),h(ROLES.find(r=>r.id===t.role)?.title||t.role),
   h(t.recurrenceDays)+" days",h(t.points)+" points"]))+
  '<form class="controls" data-form="hr-training" style="margin-top:18px">'+
  '<label>Demo employee<select name="person">'+peopleOptions(w)+'</select></label>'+
  '<label>Training requirement<select name="requirement">'+trainingOptions(w)+'</select></label>'+
  '<button class="action" type="submit">Simulate verified completion</button></form>'+
  '<p class="small">The local backend also tracks verification and recurrence. This illustration awards only fictional recognition points.</p></section>';
 html+='<section class="panel"><h2>Training completion register</h2>'+
  table(["Employee","Training","Recorded on","Verified by"],w.completions.slice().reverse().map(c=>[
   h(c.personId),h(w.requirements.find(t=>t.id===c.requirementId)?.title||c.requirementId),
   h(c.on),h(c.verifiedBy)]))+'</section>';
 return html;
}
export function renderMorale(w){
 const latest=w.pulses.at(-1),pending=w.nominations.filter(x=>x.status==="PENDING");
 const actions=w.actions.filter(x=>x.status==="OPEN");
 let html=heading("Leadership / QCDSM / workforce health","Morale & Recognition",
  "Aggregate company-pulse signals, human-reviewed recognition and management follow-ups. The score is an attention heuristic, never an individual employee rating.");
 html+=notice;
 html+='<div class="metrics">'+metric("Latest pulse risk",latest?latest.risk_score+"/100":"n/a","Aggregate attention score")+
  metric("Recorded pulses",w.pulses.length,"Department-level samples")+
  metric("Pending recognition",pending.length,"Explicit simulation review")+
  metric("Open follow-ups",actions.length,"Leadership review actions")+'</div>';
 html+='<div class="columns"><section class="panel"><h2>Record synthetic workforce pulse</h2>'+
  '<p class="small">This is the bounded scoring model already used by Axiom’s SuperForge leadership backend. It reports department aggregates, not identifiable people.</p>'+
  '<form class="controls" data-form="morale-pulse">'+
  '<label>Generic department<select name="department">'+options(DEPARTMENTS.map(v=>({value:v,label:v})))+'</select></label>'+
  '<label>Scheduled<input type="number" name="scheduled_headcount" value="12" min="1" max="1000" required></label>'+
  '<label>Present<input type="number" name="present_headcount" value="10" min="0" max="1000" required></label>'+
  '<label>Overtime hours<input type="number" name="overtime_hours" value="80" min="0" max="100000" required></label>'+
  '<label>50+ hour count<input type="number" name="over_50_hours_count" value="2" min="0" max="1000" required></label>'+
  '<label>Exhausted PTO<input type="number" name="exhausted_pto_count" value="1" min="0" max="1000" required></label>'+
  '<label>PTO absences<input type="number" name="pto_absence_count" value="1" min="0" max="1000" required></label>'+
  '<label>Sick absence clusters<input type="number" name="sick_absence_clusters" value="1" min="0" max="1000" required></label>'+
  '<label>Turnover count<input type="number" name="turnover_count" value="0" min="0" max="1000" required></label>'+
  '<label>Staffing shortages<input type="number" name="staffing_shortage_count" value="1" min="0" max="1000" required></label>'+
  '<label>Quality risk signal (0-100)<input type="number" name="quality_risk_signal" value="10" min="0" max="100" required></label>'+
  '<button class="action" type="submit">Record synthetic pulse</button></form>'+
  '<p class="small">A score of 60 or higher opens a fictional leadership review action. It does not diagnose an issue or make a personnel decision.</p></section>'+
  '<section class="panel"><h2>Leadership follow-ups</h2>'+
  table(["Source pulse","Department","Status","Action"],actions.map(a=>[
   h(a.pulseId),h(a.department),h(a.status),
   '<button class="action secondary" type="button" data-action="morale-close" data-id="'+h(a.id)+'">Mark reviewed</button>']))+
  '<h3 style="margin-top:20px">Pulse scoring</h3>'+
  '<p class="small">Attendance gaps, overtime load, 50+ hours, PTO pressure, sick-absence clusters, turnover, staffing shortages and aggregate quality risk contribute to a bounded 0-100 attention score. PTO absence count is recorded but not used directly in the existing formula.</p></section></div>';
 html+='<section class="panel"><h2>Department pulse history</h2>'+
  table(["Period","Department","Scheduled","Present","OT hours","Turnover","Risk"],w.pulses.slice().reverse().map(p=>[
   h(p.period),h(p.department),h(p.scheduled_headcount),h(p.present_headcount),
   h(p.overtime_hours),h(p.turnover_count),h(p.risk_score)+"/100"]))+'</section>';
 html+='<section class="panel"><h2>Recognition nomination</h2>'+
  '<form class="controls" data-form="morale-nominate">'+
  '<label>Demo code<select name="person">'+peopleOptions(w)+'</select></label>'+
  '<label>Category<select name="category">'+options(CATEGORIES.map(v=>({value:v,label:v})))+'</select></label>'+
  '<label>Reason<select name="reason">'+options(REASONS.map(v=>({value:v,label:v})))+'</select></label>'+
  '<label>Points<input type="number" name="points" min="1" max="100" value="5" required></label>'+
  '<button class="action" type="submit">Nominate</button></form>'+
  '<p class="small">A nomination must be reviewed before points enter the fictional recognition ledger. No monetary conversion or vendor redemption.</p></section>';
 html+='<section class="panel"><h2>Recognition review queue</h2>'+
  table(["Nomination","Employee","Reason","Points","Status","Review"],w.nominations.slice().reverse().map(n=>[
   h(n.id),h(n.personId),h(n.reason),h(n.points),h(n.status),
   n.status==="PENDING"?
    '<div class="actions"><button class="action secondary" data-action="morale-approve" data-id="'+h(n.id)+'">Approve demo</button>'+
    '<button class="action secondary" data-action="morale-reject" data-id="'+h(n.id)+'">Reject</button></div>':"Reviewed"]))+'</section>';
 html+='<section class="panel"><h2>Positive recognition ledger</h2>'+
  table(["Demo code","Category","Reason","Points","Approved by","Balance"],w.ledger.slice().reverse().map(x=>[
   h(x.personId),h(x.category),h(x.reason),"+"+h(x.points),h(x.approvedBy),h(demoBalance(w,x.personId))]))+
  '<p class="small">Points are illustrative only. The actual Axiom ISO-Hungry backend requires separate payroll review, batch approval and external payment confirmation. This browser page does none of those steps.</p></section>';
 return html;
}
