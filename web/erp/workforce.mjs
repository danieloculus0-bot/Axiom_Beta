/* Browser-only synthetic adapters for existing SuperForge leadership and org rules.
 * Reference: superforge/modules/leadership.py, superforge/org_schema.py.
 * No HR database, live auth, payroll, vendor, API or real employee data.
 */
export const WORKFORCE_KEY="axiom_public_workforce_demo_v1";
export const DEPARTMENTS=["Assembly","Machining","Quality","Maintenance","HR / Finance"];
export const ROLES=[
 {id:"operator",title:"Operator",department:"Assembly"},
 {id:"machinist",title:"Machinist",department:"Machining"},
 {id:"inspector",title:"Inspector",department:"Quality"},
 {id:"technician",title:"Maintenance Technician",department:"Maintenance"},
 {id:"supervisor",title:"Production Supervisor",department:"Assembly"},
 {id:"hr",title:"HR / Training Coordinator",department:"HR / Finance"}
];
export const CATEGORIES=["quality","safety","training","kaizen","recognition"];
export const REASONS=["First-pass quality","Safety improvement","Training milestone","Kaizen suggestion","Teamwork"];
const copy=x=>structuredClone(x);
const whole=(v,min=0,max=10000)=>{
 const n=Number(v);
 if(!Number.isInteger(n)||n<min||n>max)throw Error("Enter a valid synthetic whole-number count");
 return n;
};
const number=(v,min=0,max=100000)=>{
 const n=Number(v);
 if(!Number.isFinite(n)||n<min||n>max)throw Error("Enter a valid synthetic number");
 return n;
};
const requirePerson=(w,id)=>{
 const p=w.people.find(x=>x.id===id);
 if(!p)throw Error("Demo employee code not found");
 return p;
};
const requireRole=id=>{
 const r=ROLES.find(x=>x.id===id);
 if(!r)throw Error("Choose a listed demo role");
 return r;
};
export function calculateMoraleRisk(data={}){
 // Same aggregate bounded heuristic and weights as leadership.calculate_morale_risk.
 const rawScheduled=Number(data.scheduled_headcount)||0;
 const scheduled=Math.max(rawScheduled,Number(data.present_headcount)||0,1);
 const present=Math.max(Number(data.present_headcount)||0,0);
 const gap=rawScheduled>0?Math.max(scheduled-present,0)/scheduled:0;
 const ot=(Number(data.overtime_hours)||0)/Math.max(scheduled*40,1);
 const ratio=key=>(Number(data[key])||0)/scheduled;
 const quality=Math.max(0,Math.min(Number(data.quality_risk_signal)||0,100))/100;
 const weighted=Math.min(gap/.10,1)*.25+
   Math.min(ot/.15,1)*.15+
   Math.min(ratio("over_50_hours_count")/.10,1)*.10+
   Math.min(ratio("exhausted_pto_count")/.15,1)*.10+
   Math.min(ratio("sick_absence_clusters")/.10,1)*.10+
   Math.min(ratio("turnover_count")/.08,1)*.15+
   Math.min(ratio("staffing_shortage_count")/.10,1)*.10+
   quality*.05;
 return Math.round(Math.max(0,Math.min(weighted*100,100))*10)/10;
}
export function seedWorkforce(){
 const people=[
  {id:"DEMO-01",role:"operator"}, {id:"DEMO-02",role:"machinist"},
  {id:"DEMO-03",role:"inspector"}, {id:"DEMO-04",role:"technician"},
  {id:"DEMO-05",role:"supervisor"}
 ];
 const requirements=[
  {id:"TR-01",title:"Safety orientation",role:"operator",recurrenceDays:365,points:10},
  {id:"TR-02",title:"First-piece inspection",role:"inspector",recurrenceDays:365,points:10},
  {id:"TR-03",title:"Machine startup checklist",role:"machinist",recurrenceDays:180,points:5}
 ];
 const pulse={id:"P-01",period:"DEMO SEED",department:"Assembly",
  scheduled_headcount:12,present_headcount:11,overtime_hours:72,
  over_50_hours_count:1,exhausted_pto_count:1,pto_absence_count:0,
  sick_absence_clusters:0,turnover_count:0,staffing_shortage_count:0,quality_risk_signal:12};
 pulse.risk_score=calculateMoraleRisk(pulse);
 return {schema:1,demo:true,people,requirements,completions:[],pulses:[pulse],
  nominations:[],ledger:[],actions:[],incidents:[],safetySurveys:[]};
}
export function validateWorkforce(raw){
 if(raw?.schema===1&&raw?.demo===true){
  if(raw.incidents===undefined)raw.incidents=[];
  if(raw.safetySurveys===undefined)raw.safetySurveys=[];
 }
 if(!raw||raw.schema!==1||raw.demo!==true||
  !["people","requirements","completions","pulses","nominations","ledger","actions","incidents","safetySurveys"]
   .every(key=>Array.isArray(raw[key])&&raw[key].length<=2000))throw Error("Invalid browser demo workforce state");
 return raw;
}
export function addDemoPerson(workforce,roleId){
 requireRole(roleId);
 const next=copy(validateWorkforce(workforce));
 const max=Math.max(0,...next.people.map(p=>Number(/^DEMO-(\d+)$/.exec(p.id)?.[1])||0));
 if(max>=999)throw Error("Demonstration roster full");
 const id="DEMO-"+String(max+1).padStart(2,"0");
 next.people.push({id,role:roleId});
 return next;
}
export function assignDemoRole(workforce,personId,roleId){
 requireRole(roleId);
 const next=copy(validateWorkforce(workforce));
 requirePerson(next,personId).role=roleId;
 return next;
}
export function recordDemoPulse(workforce,input){
 const next=copy(validateWorkforce(workforce));
 if(!DEPARTMENTS.includes(input.department))throw Error("Select a generic department");
 const scheduled=whole(input.scheduled_headcount,1,1000);
 const present=whole(input.present_headcount,0,1000);
 if(present>scheduled)throw Error("Present count cannot exceed scheduled count");
 const fields=["over_50_hours_count","exhausted_pto_count","pto_absence_count",
  "sick_absence_clusters","turnover_count","staffing_shortage_count"];
 const pulse={id:"P-"+String(next.pulses.length+1).padStart(2,"0"),
  period:new Date().toISOString().slice(0,10),department:input.department,
  scheduled_headcount:scheduled,present_headcount:present,
  overtime_hours:number(input.overtime_hours,0,100000),
  quality_risk_signal:number(input.quality_risk_signal,0,100)};
 for(const key of fields)pulse[key]=whole(input[key],0,1000);
 pulse.risk_score=calculateMoraleRisk(pulse);
 next.pulses.push(pulse);
 if(pulse.risk_score>=60)next.actions.push({id:"ACT-"+pulse.id,pulseId:pulse.id,
  title:"Review aggregate workforce signal",department:pulse.department,status:"OPEN"});
 return next;
}
export function completeDemoTraining(workforce,personId,requirementId){
 const next=copy(validateWorkforce(workforce));
 requirePerson(next,personId);
 const req=next.requirements.find(x=>x.id===requirementId);
 if(!req)throw Error("Choose a training requirement");
 const duplicate=next.completions.some(x=>x.personId===personId&&x.requirementId===requirementId);
 if(duplicate)throw Error("This fictional training is already recorded");
 const id="TC-"+(next.completions.length+1);
 next.completions.push({id,personId,requirementId,verifiedBy:"SIMULATED",on:new Date().toISOString().slice(0,10)});
 if(req.points>0)next.ledger.push({id:"RE-"+(next.ledger.length+1),
  personId,category:"training",points:req.points,reason:req.title,source:id,approvedBy:"SIMULATED"});
 return next;
}
export function nominateDemoRecognition(workforce,personId,category,reason,points){
 const next=copy(validateWorkforce(workforce));
 requirePerson(next,personId);
 if(!CATEGORIES.includes(category)||!REASONS.includes(reason))throw Error("Choose demo recognition options");
 const amount=whole(points,1,100);
 next.nominations.push({id:"N-"+(next.nominations.length+1),personId,category,reason,points:amount,status:"PENDING"});
 return next;
}
export function reviewDemoNomination(workforce,id,decision){
 if(!["APPROVED","REJECTED"].includes(decision))throw Error("Invalid review decision");
 const next=copy(validateWorkforce(workforce)),nom=next.nominations.find(x=>x.id===id);
 if(!nom||nom.status!=="PENDING")throw Error("Nomination is not pending review");
 nom.status=decision;
 if(decision==="APPROVED")next.ledger.push({id:"RE-"+(next.ledger.length+1),
  personId:nom.personId,category:nom.category,reason:nom.reason,
  points:nom.points,source:nom.id,approvedBy:"SIMULATED"});
 return next;
}
export function closeDemoAction(workforce,id){
 const next=copy(validateWorkforce(workforce));
 const action=next.actions.find(x=>x.id===id);
 if(!action||action.status!=="OPEN")throw Error("Open review action not found");
 action.status="COMPLETED";
 return next;
}
export function demoBalance(workforce,personId){
 return workforce.ledger.filter(x=>x.personId===personId).reduce((sum,x)=>sum+x.points,0);
}


// Aggregate safety evidence only. No personally identifiable injury records belong in this public demo.
export const INCIDENT_KINDS=["recordable","first_aid","near_miss"];
export function recordDemoIncident(workforce,input,today=new Date().toISOString().slice(0,10)){
 const next=copy(validateWorkforce(workforce));
 if(!DEPARTMENTS.includes(input.department))throw Error("Select a generic department");
 if(!INCIDENT_KINDS.includes(input.kind))throw Error("Select a listed safety event classification");
 const date=String(input.observedOn||today);
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date))||
   new Date(date).toISOString().slice(0,10)!==date)throw Error("Enter a valid safety event date");
 if(date>today)throw Error("Safety event date cannot be in the future");
 const id="SI-"+(next.incidents.length+1);
 next.incidents.push({id,department:input.department,kind:input.kind,observedOn:date,
  classification:"SIMULATED / UNVERIFIED"});
 return next;
}
export function recordDemoSafetySurvey(workforce,input,today=new Date().toISOString().slice(0,10)){
 const next=copy(validateWorkforce(workforce));
 if(!DEPARTMENTS.includes(input.department))throw Error("Select a generic department");
 const respondents=whole(input.respondents,1,1000);
 const concerned=whole(input.concerned,0,1000);
 if(concerned>respondents)throw Error("Safety concerns cannot exceed survey responses");
 next.safetySurveys.push({id:"SS-"+(next.safetySurveys.length+1),department:input.department,
  respondents,concerned,observedOn:today});
 return next;
}
