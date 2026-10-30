import test from "node:test";
import assert from "node:assert/strict";
import {seedState,receivePurchaseOrder,validateState} from "./engine.mjs";
import {createPurchaseRequest,approvePurchaseRequest,assignPurchaseRequest,issueRequestPO,
  syncReceivedRequests,verifyPurchaseRequest,followupPurchaseRequest,requestMetrics,dueLabel,
  PURCHASE_REASONS} from "./requests.mjs";
import {requestMaintenance,assignMaintenanceRequest,followupMaintenanceRequest,
 closeMaintenanceRequest,pmOverview,MAINTENANCE_FOLLOWUPS} from "./pm.mjs";
import {resolveContext,contextActions} from "./context-actions.mjs";
import {searchMenu} from "./navigation.mjs";
import {makeReport} from "./reports.mjs";
import {renderRequestDesk} from "./request-view.mjs";

const day="2026-10-30",at=day+"T12:00:00.000Z",later=day+"T13:00:00.000Z";
const args={itemId:"MAT-PLATE",quantity:10,reason:PURCHASE_REASONS[0],
 priority:"Medium",owner:"DEMO-BUYER",dueDate:"2026-11-06",at};

test("old demo state upgrades and retains prior work orders",()=>{
 let prior=seedState(),jobNumber=prior.jobs[0].jobNumber;
 delete prior.purchaseRequests;
 const next=validateState(prior);
 assert.equal(next.jobs[0].jobNumber,jobNumber);
 assert.deepEqual(next.purchaseRequests,[]);
});
test("purchase request stays open from submission through purchase-order issue",()=>{
 let state=seedState(),r=createPurchaseRequest(state,args);state=r.state;
 assert.equal(state.purchaseRequests[0].status,"SUBMITTED");
 assert.equal(state.purchaseOrders.length,0);
 assert.equal(requestMetrics(state,day).openPurchases,1);
 assert.ok(contextActions(state,"purchase_request",r.id).some(a=>a.view==="requests"));
 assert.equal(resolveContext(state,"purchase_request",r.id).itemId,"MAT-PLATE");
 state=assignPurchaseRequest(state,r.id,"DEMO-OPS","2026-11-02",later);
 assert.equal(state.purchaseRequests[0].status,"REVIEWING");
 state=followupPurchaseRequest(state,r.id,"Follow-up requested",later);
 assert.equal(state.purchaseRequests[0].followups.length,1);
 state=approvePurchaseRequest(state,r.id,later);
 assert.equal(state.purchaseRequests[0].status,"APPROVED");
 state=issueRequestPO(state,r.id,later);
 assert.equal(state.purchaseRequests[0].status,"ORDERED");
 assert.equal(state.purchaseOrders[0].status,"ORDERED");
 assert.equal(requestMetrics(state,day).openPurchases,1);
 assert.throws(()=>verifyPurchaseRequest(state,r.id,later),/Receive/);
 assert.equal(state.purchaseRequests[0].linkedPoId,state.purchaseOrders[0].id);
});
test("only a received linked PO can complete a purchase request",()=>{
 let state=createPurchaseRequest(seedState(),args).state,id=state.purchaseRequests[0].id;
 state=approvePurchaseRequest(state,id,later);
 state=issueRequestPO(state,id,later);
 const poId=state.purchaseOrders[0].id;
 assert.throws(()=>syncReceivedRequests(state,poId,later),/not been received/);
 state=receivePurchaseOrder(state,poId,later);
 assert.equal(state.purchaseRequests[0].status,"ORDERED");
 state=syncReceivedRequests(state,poId,later);
 assert.equal(state.purchaseRequests[0].status,"RECEIVED");
 assert.equal(requestMetrics(state,day).needsVerification,1);
 state=verifyPurchaseRequest(state,id,later);
 assert.equal(state.purchaseRequests[0].status,"VERIFIED");
 assert.equal(requestMetrics(state,day).openPurchases,0);
 assert.equal(makeReport(state,[],"purchase_requests").rows[0][5],"VERIFIED");
 assert.throws(()=>verifyPurchaseRequest(state,id,later),/Receive/);
});
test("maintenance is closed when completed, no purchasing verification requirement",()=>{
 let state=seedState(),r=requestMaintenance(state.pm,"DEMO-M-001","Illustrative abnormal noise","High","DEMO-01",at);
 state.pm=r.pm;
 state.pm=assignMaintenanceRequest(state.pm,r.id,"DEMO-MAINT","2026-11-02",at);
 assert.equal(state.pm.requests[0].status,"IN PROGRESS");
 assert.equal(pmOverview(state.pm,day).openRequests,1);
 state.pm=followupMaintenanceRequest(state.pm,r.id,MAINTENANCE_FOLLOWUPS[0],later);
 assert.equal(state.pm.requests[0].followups.length,1);
 assert.equal(requestMetrics(state,day).openMaintenance,1);
 state.pm=closeMaintenanceRequest(state.pm,r.id,undefined,later);
 assert.equal(state.pm.requests[0].status,"CLOSED");
 assert.equal(state.pm.requests[0].assignedTo,"DEMO-MAINT");
 assert.equal(pmOverview(state.pm,day).openRequests,0);
 assert.equal(requestMetrics(state,day).openMaintenance,0);
 assert.ok(contextActions(state,"pm_request",r.id).some(a=>a.view==="requests"));
});
test("tracking uses due dates and exposes both functional request modules",()=>{
 let state=createPurchaseRequest(seedState(),args).state;
 assert.equal(requestMetrics(state,"2026-11-07").overdue,1);
 assert.equal(dueLabel("2026-11-06","SUBMITTED","2026-11-07"),"OVERDUE");
 assert.equal(searchMenu("purchase request")[0].id,"requests");
 assert.equal(searchMenu("maintenance request")[0].id,"requests");
 const html=renderRequestDesk(state);
 assert.match(html,/Purchase request tracker/);
 assert.match(html,/Maintenance request tracker/);
 assert.match(html,/SIM-REQ-0001/);
 assert.match(html,/data-form="request-purchase"/);
 assert.match(html,/data-form="request-maintenance"/);
});
test("request desk rejects non-fictional material and unregistered follow-up notes",()=>{
 let state=seedState();
 assert.throws(()=>createPurchaseRequest(state,{...args,itemId:"PRIVATE-REAL-ASSET"}),/fictional/);
 state=createPurchaseRequest(state,args).state;
 assert.throws(()=>followupPurchaseRequest(state,state.purchaseRequests[0].id,"Real operator notes"),/fictional/);
});
