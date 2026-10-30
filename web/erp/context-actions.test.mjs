import test from "node:test";
import assert from "node:assert/strict";
import {seedState,makePurchaseOrder,raiseQuality,createJob,CATALOG} from "./engine.mjs";
import {resolveContext,contextActions,contextRelated,CONTEXT_TYPES} from "./context-actions.mjs";
import {searchMenu} from "./navigation.mjs";
import {readFileSync} from "node:fs";

test("all browser Open with actions resolve only to working registered ERP modules",()=>{
 const state=seedState();
 for(const type of CONTEXT_TYPES){
   const id=type==="job"?state.jobs[0].id:type==="part"?CATALOG[0].partNumber:
     type==="stock"?state.items[0].id:type==="drawing"?state.jobs[0].id:
     type==="machine"?state.pm.machines[0].id:type==="pm_task"?state.pm.tasks[0].id:null;
   if(!id)continue;
   const rows=contextActions(state,type,id);
   assert.ok(rows.length>0,type);
   for(const action of rows) {
     assert.ok(searchMenu("").some(x=>x.id===action.view),type+" bad screen "+action.view);
     assert.ok(action.label&&action.intent);
   }
 }
});
test("right-click a job and open a related record without losing its identity",()=>{
 const state=seedState(),job=state.jobs[0];
 const context=resolveContext(state,"job",job.id);
 assert.equal(context.label,job.jobNumber);
 assert.equal(context.jobId,job.id);
 assert.equal(context.part,job.partNumber);
 assert.equal(context.itemId,job.materialId);
 assert.ok(contextActions(state,"job",job.id).some(x=>x.label==="Job Tracker"));
 assert.ok(contextActions(state,"job",job.id).some(x=>x.label==="PO Entry (material)"));
 assert.deepEqual(contextRelated(state,{type:"job",id:job.id},"inventory"),[job.materialId]);
});
test("part offers Job Entry and filters related jobs without conflating material and finished part",()=>{
 let state=seedState();
 const part=CATALOG[2].partNumber;
 let c=resolveContext(state,"part",part);
 assert.deepEqual(c.relatedJobs,[]);
 assert.equal(c.itemId,CATALOG[2].materialId);
 assert.ok(contextActions(state,"part",part).some(x=>x.intent==="new-job"));
 assert.ok(!contextActions(state,"part",part).some(x=>x.intent==="route"));
 state=createJob(state,part,7).state;
 c=resolveContext(state,"part",part);
 assert.equal(c.relatedJobs.length,1);
 assert.deepEqual(contextRelated(state,{type:"part",id:part},"jobs"),c.relatedJobs);
 assert.ok(contextActions(state,"part",part).some(x=>x.intent==="route"));
});
test("PO Tracker and PO Entry use the selected fictional stock item",()=>{
 let state=seedState();
 state=makePurchaseOrder(state,"MAT-BAR",23);
 const po=state.purchaseOrders[0];
 const c=resolveContext(state,"po",po.id);
 assert.equal(c.itemId,"MAT-BAR");
 assert.deepEqual(contextRelated(state,{type:"po",id:po.id},"purchasing"),["MAT-BAR"]);
 assert.ok(contextActions(state,"po",po.id).some(x=>x.intent==="new-po"));
 assert.ok(contextActions(state,"stock","MAT-BAR").some(x=>x.label==="PO Tracker"));
});
test("quality and drawing context preserve associated job ID",()=>{
 let state=seedState(),job=state.jobs[0];
 state=raiseQuality(state,job.id,"Generic drawing revision conflict");
 const quality=resolveContext(state,"quality",state.quality[0].id);
 assert.equal(quality.jobId,job.id);
 assert.deepEqual(contextRelated(state,{type:"quality",id:quality.id},"quality"),[job.id]);
 const drawing=resolveContext(state,"drawing",job.id);
 assert.equal(drawing.label,job.drawing.number+" / Rev "+job.drawing.revision);
 assert.ok(contextActions(state,"drawing",job.id).some(x=>x.view==="ewi"));
});
test("PM actions stay with the selected fictional machine",()=>{
 const state=seedState(),machine=state.pm.machines[0],task=state.pm.tasks[0];
 assert.equal(resolveContext(state,"machine",machine.id).machineId,machine.id);
 assert.equal(resolveContext(state,"pm_task",task.id).machineId,task.machineId);
 assert.ok(contextActions(state,"pm_task",task.id).some(x=>x.view==="pm"));
 assert.deepEqual(contextActions(state,"pm_request","MISSING"),[]);
});
test("invalid records cannot silently open another demo record",()=>{
 const state=seedState();
 assert.equal(resolveContext(state,"job","internal-job-record"),null);
 assert.equal(resolveContext(state,"../../../foo",state.jobs[0].id),null);
 assert.deepEqual(contextActions(state,"po","NOT-REAL"),[]);
 assert.equal(contextRelated(state,{type:"stock",id:"missing"},"inventory"),null);
});
test("search menu recognizes ERP tracking and entry aliases",()=>{
 assert.equal(searchMenu("PO Entry")[0].id,"purchasing");
 assert.equal(searchMenu("PO Tracker")[0].id,"purchasing");
 assert.equal(searchMenu("Job Entry")[0].id,"jobs");
 assert.equal(searchMenu("Part Tracker")[0].id,"inventory");
});
test("right click uses native-menu guards and typed records, not a global hijack",()=>{
 const source=readFileSync(new URL("./context-ui.mjs",import.meta.url),"utf8");
 assert.match(source,/if\(e\.shiftKey\|\|e\.target\.closest\(preserve\)/);
 assert.match(source,/getSelection/);
 assert.match(source,/data-ctx-type/);
 assert.match(source,/if\(!target\|\|!openFor/);
 assert.match(source,/e\.preventDefault\(\)/);
 assert.match(source,/e\.key==="Escape"/);
 assert.match(source,/onNavigate\(\{type,id\},action\)/);
 assert.match(source,/search\.addEventListener\("input"/);
});
