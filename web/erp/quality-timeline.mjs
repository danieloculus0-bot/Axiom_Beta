/* Read-only Quality Forge case chronology over the canonical fictional NCR.
 * No second store, status mutation, approval, or external integration.
 */
export function qualityCaseTimeline(record){
  if(!record||typeof record!=="object")return [];
  const entries=[];
  const add=(kind,at,title,detail,sourceId=null)=>{
    const time=typeof at==="string"&&Number.isFinite(Date.parse(at))?at:null;
    entries.push({kind,at:time,title:String(title??""),detail:String(detail??""),sourceId:sourceId??null,order:entries.length});
  };
  if(record.openedAt)add("opened",record.openedAt,"NCR opened",record.reason,record.id);
  for(const item of Array.isArray(record.inspections)?record.inspections:[]){
    if(!item||typeof item!=="object")continue;
    add("inspection",item.at,"Inspection: "+String(item.stage??"UNKNOWN")+" / "+String(item.result??"UNKNOWN"),
      "Step "+String(item.step??"unknown")+" · "+String(item.observation??""),item.id);
  }
  if(record.disposition&&typeof record.disposition==="object"){
    const d=record.disposition;
    add("disposition",d.recordedAt,"Disposition: "+String(d.decision??"UNKNOWN"),d.note,record.id);
  }
  for(const action of Array.isArray(record.correctiveActions)?record.correctiveActions:[]){
    if(!action||typeof action!=="object")continue;
    add("corrective",action.createdAt,"Corrective action: "+String(action.ownerRole??"UNASSIGNED"),
      action.description,action.id);
    for(const review of Array.isArray(action.reviews)?action.reviews:[]){
      if(!review||typeof review!=="object")continue;
      add("effectiveness",review.at,"Effectiveness: "+String(review.result??"UNKNOWN"),review.note,
        review.id??action.id);
    }
  }
  for(const item of Array.isArray(record.followUps)?record.followUps:[]){
    if(!item||typeof item!=="object")continue;
    add("followup",item.at,"Case follow-up",item.note,item.id);
  }
  if(record.closedAt)add("closed",record.closedAt,"NCR closed","Fictional case closure; not a production release.",record.id);
  return entries.sort((a,b)=>{
    const ta=a.at?Date.parse(a.at):Infinity,tb=b.at?Date.parse(b.at):Infinity;
    return ta-tb||a.order-b.order;
  }).map(({order,...entry})=>entry);
}
