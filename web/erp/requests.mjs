/* Browser-local purchase requisition workflow. Invented records only.
 * Requisitions are not purchase orders. A request is only verified
 * after a demo PO has actually been received in the same local state.
 */
import {change,makePurchaseOrder} from "./engine.mjs";
import {dayAdd,dayDiff,localDay} from "./pm.mjs";

export const DEMO_OWNERS=["DEMO-BUYER","DEMO-OPS","DEMO-MAINT","DEMO-QA"];
export const PURCHASE_REASONS=[
 "Sample stock replenishment","Fictional job material shortage",
 "Demonstration tooling requirement","Generic consumables request"
];
export const REQUEST_FOLLOWUPS=[
 "Follow-up requested","Awaiting review","Supplier status checked",
 "Delivery date checked","Requester notified","Work completion checked",
 "Further action required"
];
const copy=x=>structuredClone(x);
const accepted=(val,choices,name)=>{if(!choices.includes(val))throw Error("Choose a fictional "+name);return val;};
const stamp=at=>{if(!Number.isFinite(Date.parse(at)))throw Error("Invalid timestamp");return at;};
const day=due=>{
 if(!/^\d{4}-\d{2}-\d{2}$/.test(due)||dayAdd(due,0)!==due)throw Error("Invalid due date");
 return due;
};
export function requestMetrics(state,today=localDay()){
 const purchase=state.purchaseRequests||[];
 const maintenance=state.pm.requests||[];
 const incomplete=purchase.filter(r=>!["VERIFIED","CANCELLED"].includes(r.status));
 const maintenancePending=maintenance.filter(r=>!["CLOSED","CANCELLED"].includes(r.status));
 const verification=purchase.filter(r=>r.status==="RECEIVED").length;
 const overdue=[...incomplete,...maintenancePending].filter(r=>r.dueDate&&dayDiff(r.dueDate,today)<0).length;
 return {openPurchases:incomplete.length,openMaintenance:maintenancePending.length,
   needsVerification:verification,overdue,followups:incomplete.length+maintenancePending.length};
}
export function createPurchaseRequest(state,{itemId,quantity,reason,priority="Medium",owner="DEMO-BUYER",dueDate,
  at=new Date().toISOString()}){
 if(!state.items.some(i=>i.id===itemId))throw Error("Select a fictional stock item");
 if(!Number.isInteger(quantity)||quantity<1||quantity>10000)throw Error("Quantity must be 1 to 10000");
 accepted(reason,PURCHASE_REASONS,"reason");accepted(priority,["Low","Medium","High"],"priority");
 accepted(owner,DEMO_OWNERS,"owner");stamp(at);day(dueDate);
 const today=at.slice(0,10);
 if(dayDiff(dueDate,today)<0||dayDiff(dueDate,today)>365)throw Error("Due date must be within 365 days");
 const index=(state.purchaseRequests||[]).length+1,id="SIM-REQ-"+String(index).padStart(4,"0");
 const next=change(state,"purchase_request.submitted",id+" / "+itemId,n=>{
   n.purchaseRequests.push({id,itemId,quantity,reason,priority,owner,dueDate,
    submittedBy:"DEMO-REQUESTER",status:"SUBMITTED",requestedAt:at,
    followups:[],linkedPoId:null,receivedAt:null,verifiedAt:null,closedAt:null});
 },at);
 return {state:next,id};
}
export function assignPurchaseRequest(state,id,owner,dueDate,at=new Date().toISOString()){
 accepted(owner,DEMO_OWNERS,"owner");day(dueDate);stamp(at);
 const req=(state.purchaseRequests||[]).find(r=>r.id===id);
 if(!req||["VERIFIED","CANCELLED"].includes(req.status))throw Error("Active fictional purchase request not found");
 return change(state,"purchase_request.assigned",id+" / "+owner,n=>{
   const r=n.purchaseRequests.find(x=>x.id===id);
   r.owner=owner;r.dueDate=dueDate;
   if(r.status==="SUBMITTED")r.status="REVIEWING";
 },at);
}
export function approvePurchaseRequest(state,id,at=new Date().toISOString()){
 const req=(state.purchaseRequests||[]).find(r=>r.id===id);
 if(!req||!["SUBMITTED","REVIEWING"].includes(req.status))throw Error("Request is not awaiting approval");
 stamp(at);
 return change(state,"purchase_request.approved",id,n=>{
   n.purchaseRequests.find(r=>r.id===id).status="APPROVED";
 },at);
}
export function issueRequestPO(state,id,at=new Date().toISOString()){
 const r=(state.purchaseRequests||[]).find(x=>x.id===id);
 if(!r||r.status!=="APPROVED")throw Error("Approve fictional request before ordering");
 const next=makePurchaseOrder(state,r.itemId,r.quantity,at);
 const poId=next.purchaseOrders.at(-1).id;
 return change(next,"purchase_request.ordered",id+" / "+poId,n=>{
   const request=n.purchaseRequests.find(x=>x.id===id);
   request.status="ORDERED";request.linkedPoId=poId;
 },at);
}
export function syncReceivedRequests(state,poId,at=new Date().toISOString()){
 stamp(at);
 if(!state.purchaseOrders.some(p=>p.id===poId&&p.status==="RECEIVED"))throw Error("PO has not been received");
 return change(state,"purchase_request.receipt_linked",poId,n=>{
   for(const request of n.purchaseRequests){
     if(request.linkedPoId===poId&&request.status==="ORDERED"){
       request.status="RECEIVED";request.receivedAt=at;
     }
   }
 },at);
}
export function verifyPurchaseRequest(state,id,at=new Date().toISOString()){
 const r=(state.purchaseRequests||[]).find(x=>x.id===id);
 if(!r||r.status!=="RECEIVED")throw Error("Receive the linked fictional PO before verifying");
 if(!state.purchaseOrders.some(p=>p.id===r.linkedPoId&&p.status==="RECEIVED"))
   throw Error("Linked purchase order must have a receipt");
 return change(state,"purchase_request.verified",id+" / DEMO-REQUESTER",n=>{
   const request=n.purchaseRequests.find(x=>x.id===id);
   request.status="VERIFIED";request.verifiedAt=at;request.closedAt=at;
 },at);
}
export function followupPurchaseRequest(state,id,note,at=new Date().toISOString()){
 const r=(state.purchaseRequests||[]).find(x=>x.id===id);
 if(!r||["VERIFIED","CANCELLED"].includes(r.status))throw Error("Request already completed");
 accepted(note,REQUEST_FOLLOWUPS,"follow-up");stamp(at);
 return change(state,"purchase_request.followup",id+" / "+note,n=>{
   n.purchaseRequests.find(x=>x.id===id).followups.push({at,by:"DEMO-OPS",note});
 },at);
}
export function latestFollowup(row){return row.followups?.at(-1)?.note||"No follow-up yet";}
export function dueLabel(dueDate,status,today=localDay()){
 if(["VERIFIED","CLOSED","CANCELLED"].includes(status))return "COMPLETE";
 if(!dueDate)return "UNSCHEDULED";
 const days=dayDiff(dueDate,today);
 return days<0?"OVERDUE":days===0?"DUE TODAY":days<=3?"DUE SOON":"ON TRACK";
}
