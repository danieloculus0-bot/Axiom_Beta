/* Explicitly synthetic HR workflow previews. No payroll authority, HR accounts or backend. */
const h=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clone=v=>structuredClone(v);
const number=(v,label,min,max)=>{const n=Number(v);if(!Number.isFinite(n)||n<min||n>max)throw Error(label+" must be between "+min+" and "+max);return n;};
const validPerson=(w,id)=>{if(!w.people.some(p=>p.id===id))throw Error("Select an existing fictional employee");};
const date=v=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(String(v))||new Date(v+"T00:00:00Z").toISOString().slice(0,10)!==v)throw Error("Use a valid date");return v;};
export function submitDemoPto(w,{personId,startDate,endDate}){
 validPerson(w,personId);
 const start=date(startDate),end=date(endDate);
 const days=Math.round((Date.parse(end+"T00:00:00Z")-Date.parse(start+"T00:00:00Z"))/86400000)+1;
 if(days<1||days>30)throw Error("Select a 1 to 30 day fictional request");
 const current=w.ptoRequests||[];
 if(current.some(r=>r.personId===personId&&r.status!=="DECLINED"&&start<=r.endDate&&end>=r.startDate))throw Error("This demo employee already has an overlapping request");
 const next=clone(w);
 next.ptoRequests=[...current,{id:"PTO-"+(current.length+1),personId,startDate:start,endDate:end,days,status:"SUBMITTED"}];
 return next;
}
export function reviewDemoPto(w,id,decision){
 if(!["APPROVED_SIMULATION","DECLINED"].includes(decision))throw Error("Invalid fictional review decision");
 const next=clone(w),request=(next.ptoRequests||[]).find(r=>r.id===id);
 if(!request||request.status!=="SUBMITTED")throw Error("Submitted fictional request not found");
 request.status=decision;
 return next;
}
export function previewDemoPay(w,input){
 validPerson(w,input.personId);
 if(!["hourly","salary"].includes(input.payType))throw Error("Select hourly or salary");
 const rate=number(input.rate,"Rate",0,50000),hours=number(input.hours,"Regular hours",0,120);
 const overtime=number(input.overtime,"Overtime hours",0,80),bonus=number(input.bonus,"Bonus",0,100000);
 const tax=number(input.tax,"Explicit withholding",0,100000),deductions=number(input.deductions,"Explicit deductions",0,100000);
 if(input.payType==="salary"&&overtime>0)throw Error("Salary overtime rules are not configured; use zero overtime in this illustration");
 const gross=Math.round(((input.payType==="hourly"?rate*(hours+overtime*1.5):rate)+bonus)*100)/100;
 const net=Math.round((gross-tax-deductions)*100)/100;
 if(net<0)throw Error("Explicit deductions and withholding exceed this fictional gross pay");
 return {personId:input.personId,payType:input.payType,gross,net,tax,deductions,bonus};
}
const money=v=>"$"+Number(v).toFixed(2);
const personChoices=w=>w.people.map(p=>'<option value="'+h(p.id)+'">'+h(p.id)+'</option>').join("");
export function renderPto(w){
 const entries=w.ptoRequests||[];
 return '<div class="lead"><div><div class="eyebrow">People & Culture / Human Resources</div><h1>PTO request demonstration</h1><p class="subtitle">Fictional employee codes and browser-local review only. No real balances, availability, attendance, pay rules, notifications or authenticated approval.</p></div></div>'+
 '<div class="notice">This public demo must never contain actual employment or absence records. A displayed approval is a simulation, not a real leave authorization.</div>'+
 '<section class="panel"><h2>Submit fictional time off</h2><form class="controls" data-form="pto-submit"><label>Demo employee<select name="personId">'+personChoices(w)+'</select></label>'+
 '<label>First day<input name="startDate" type="date" required></label><label>Last day<input name="endDate" type="date" required></label>'+
 '<button class="action" type="submit">Add sample request</button></form></section>'+
 '<section class="panel"><h2>Fictional requests and review</h2><div class="tablewrap"><table><thead><tr><th>Request</th><th>Employee</th><th>Dates</th><th>Days</th><th>Status</th><th>Review</th></tr></thead><tbody>'+
 (entries.length?entries.slice().reverse().map(r=>'<tr><td>'+h(r.id)+'</td><td>'+h(r.personId)+'</td><td>'+h(r.startDate)+' to '+h(r.endDate)+'</td><td>'+h(r.days)+'</td><td>'+h(r.status)+'</td><td>'+
 (r.status==="SUBMITTED"?'<button class="action secondary" type="button" data-action="pto-approve" data-id="'+h(r.id)+'">Approve simulation</button> <button class="action secondary" type="button" data-action="pto-decline" data-id="'+h(r.id)+'">Decline simulation</button>':"Reviewed")+'</td></tr>').join(""):'<tr><td colspan="6">No fictional PTO requests yet.</td></tr>')+
 '</tbody></table></div><p class="small">Request days are calendar days, not a legal or contractual PTO balance calculation.</p><a class="action secondary" href="#hr">Return to Human Resources</a></section>';
}
export function renderPayroll(w,result=null){
 return '<div class="lead"><div><div class="eyebrow">People & Culture / Finance</div><h1>Payroll preview</h1><p class="subtitle">A functional arithmetic sandbox using fictional employee codes and your explicit hypothetical inputs. No pay-run ledger, tax rules or payments.</p></div></div>'+
 '<div class="notice">Private SuperForge has tested payroll pay-run and accounting workflows. This Pages calculator is NOT that backend; it cannot approve a check, withhold statutory taxes, issue payment or store pay details.</div>'+
 '<section class="panel"><h2>Try a fictional payroll calculation</h2><form class="controls" data-form="pay-preview"><label>Demo employee<select name="personId">'+personChoices(w)+'</select></label>'+
 '<label>Pay basis<select name="payType"><option value="hourly">Hourly</option><option value="salary">Salary period amount</option></select></label>'+
 '<label>Hourly rate / salary period amount ($)<input name="rate" type="number" value="25" min="0" max="50000" step="any" required></label>'+
 '<label>Regular hours (hourly)<input name="hours" type="number" value="40" min="0" max="120" step="any" required></label>'+
 '<label>Overtime hours (hourly)<input name="overtime" type="number" value="5" min="0" max="80" step="any" required></label>'+
 '<label>Bonus ($)<input name="bonus" type="number" value="0" min="0" max="100000" step="any" required></label>'+
 '<label>Entered withholding ($)<input name="tax" type="number" value="200" min="0" max="100000" step="any" required></label>'+
 '<label>Entered deductions ($)<input name="deductions" type="number" value="50" min="0" max="100000" step="any" required></label>'+
 '<button class="action" type="submit">Preview sample pay</button></form>'+
 (result?'<div class="metrics"><div class="metric"><small>Demo code</small><strong>'+h(result.personId)+'</strong></div><div class="metric"><small>Gross</small><strong>'+money(result.gross)+'</strong></div><div class="metric"><small>Net</small><strong>'+money(result.net)+'</strong></div></div><p class="small">Withholding '+money(result.tax)+' · deductions '+money(result.deductions)+'. This is an unsaved calculation, not an actual pay stub.</p>':'')+
 '</section><section class="panel"><h2>Real local beta boundary</h2><p>SuperForge implements employee pay profiles, pay-run drafts, explicit input withholding, controlled approvals, payment receipts and balanced ledger posting. Those features require the local private application and are not exposed on this static site.</p><a class="action secondary" href="#hr">Open fictional employee roster</a></section>';
}