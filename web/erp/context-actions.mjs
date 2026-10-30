/* Axiom public ERP Open With actions.
 * Modelled on the existing Flask superforge/context_menu.py system, but with
 * ONLY implemented GitHub Pages routes and exclusively fictional records.
 * Never fetch remote data, infer real associations, or expose fake modules.
 */
import {CATALOG,getJob} from "./engine.mjs";
import {getMachine,getTask} from "./pm.mjs";

export const CONTEXT_TYPES=["job","part","stock","po","quality","drawing","machine","pm_task","pm_request"];
const TARGETS={
  job:[
    ["jobs","Job Tracker","track"],["routing","Routing & Planning","route"],
    ["ewi","EWI & Clocking","clock"],["documents","Drawing Control","drawing"],
    ["inventory","Material Tracker","material"],["quality","Quality Control","quality"],
    ["purchasing","PO Tracker (material)","purchase"],["purchasing","PO Entry (material)","new-po"]
  ],
  part:[
    ["jobs","Job Tracker (this part)","track"],["jobs","Job Entry (this part)","new-job"],
    ["routing","Routing (related job)","route"],["documents","Drawing (related job)","drawing"],
    ["inventory","Raw Material Tracker","material"],["purchasing","PO Entry (material)","new-po"]
  ],
  stock:[
    ["inventory","Material Tracker","material"],["purchasing","PO Tracker","purchase"],
    ["purchasing","PO Entry","new-po"],["jobs","Jobs using this material","track"]
  ],
  po:[
    ["purchasing","PO Tracker","purchase"],["inventory","Material Tracker","material"],
    ["purchasing","PO Entry (same material)","new-po"],
    ["jobs","Jobs using this material","track"]
  ],
  quality:[
    ["quality","Quality Control","quality"],["jobs","Job Tracker","track"],
    ["ewi","EWI & Clocking","clock"],["documents","Drawing Control","drawing"]
  ],
  drawing:[
    ["documents","Drawing Control","drawing"],["jobs","Job Tracker","track"],
    ["routing","Routing & Planning","route"],["ewi","EWI & Clocking","clock"]
  ],
  machine:[
    ["pm","PM Tracker / Machine","machine"],["reports","PM Schedule Report","pm-report"]
  ],
  pm_task:[
    ["pm","PM Task & Machine","machine"],["reports","PM Schedule Report","pm-report"]
  ],
  pm_request:[
    ["pm","Maintenance Requests","requests"],["reports","Maintenance Request Report","request-report"]
  ]
};
export function resolveContext(state,type,id){
  if(!CONTEXT_TYPES.includes(type)||typeof id!=="string"||id.length>120)return null;
  let record=null,jobId=null,part=null,itemId=null,machineId=null;
  switch(type){
   case "job":record=getJob(state,id);jobId=record?.id;break;
   case "part":record=CATALOG.find(x=>x.partNumber===id);part=record?.partNumber;break;
   case "stock":record=state.items.find(x=>x.id===id);itemId=record?.id;break;
   case "po":record=state.purchaseOrders.find(x=>x.id===id);itemId=record?.itemId;break;
   case "quality":record=state.quality.find(x=>x.id===id);jobId=record?.jobId;break;
   case "drawing":record=getJob(state,id);jobId=record?.id;break;
   case "machine":record=getMachine(state.pm,id);machineId=record?.id;break;
   case "pm_task":record=getTask(state.pm,id);machineId=record?.machineId;break;
   case "pm_request":record=state.pm.requests.find(x=>x.id===id);machineId=record?.machineId;break;
  }
  if(!record)return null;
  if(jobId){
    const j=getJob(state,jobId);
    if(!j)return null;
    part=j.partNumber;itemId=j.materialId;
  }
  if(part&&!itemId)itemId=CATALOG.find(x=>x.partNumber===part)?.materialId||null;
  if(itemId&&!state.items.some(x=>x.id===itemId))itemId=null;
  const related=state.jobs.filter(j=>jobId?j.id===jobId:part?j.partNumber===part:itemId?j.materialId===itemId:false);
  return {type,id,record,jobId,part,itemId,machineId,
    relatedJobs:related.map(j=>j.id),
    label: type==="job"?record.jobNumber:
       type==="part"?record.partNumber:
       type==="stock"?record.id+" · "+record.name:
       type==="po"?record.number:
       type==="quality"?record.number:
       type==="drawing"?record.drawing.number+" / Rev "+record.drawing.revision:
       type==="machine"?record.name:
       type==="pm_task"?record.name:
       type==="pm_request"?record.id:"Record"};
}
export function contextActions(state,type,id){
 const record=resolveContext(state,type,id);
 if(!record)return [];
 return TARGETS[type].filter(([view,,intent])=>{
   if(["route","drawing","clock"].includes(intent)&&record.relatedJobs.length===0)return false;
   if(["new-po","purchase","material"].includes(intent)&&!record.itemId)return false;
   if(intent==="new-job"&&!record.part)return false;
   if(intent==="track"&&type==="stock"&&!record.relatedJobs.length)return false;
   if(intent==="track"&&type==="po"&&!record.relatedJobs.length)return false;
   return true;
 }).map(([view,label,intent],index)=>({view,label,intent,id:type+":"+id+":"+intent,suggested:index<4}));
}
export function contextRelated(state,context,view){
 const c=context&&resolveContext(state,context.type,context.id);
 if(!c)return null;
 if(view==="jobs"&&["part","stock","po"].includes(c.type))
    return c.relatedJobs;
 if(view==="inventory"&&c.itemId)return [c.itemId];
 if(view==="purchasing"&&c.itemId)return [c.itemId];
 if(view==="quality"&&c.jobId)return [c.jobId];
 return null;
}
