/* Quality Forge browser-case increment. Fictional, browser-local and advisory.
 * Reuses the canonical ERP quality record and event ledger, not a second case store.
 */
import {change,closeQuality} from "./engine.mjs";

export const QUALITY_DISPOSITIONS=[
  {id:"REWORK",label:"Rework (fictional)"},
  {id:"SCRAP",label:"Scrap (fictional)"},
  {id:"RETURN_FOR_REVIEW",label:"Return for review (fictional)"}
];
const recordFor=(state,id)=>state.quality.find(q=>q.id===id);
const noteText=value=>{
  const note=String(value??"").trim();
  if(note.length<5||note.length>500)throw Error("Enter a fictional case note of 5 to 500 characters");
  return note;
};
const timestamp=at=>{
  if(typeof at!=="string"||!Number.isFinite(Date.parse(at)))throw Error("Invalid case timestamp");
  return at;
};
export function recordQualityDisposition(state,id,decision,note,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  if(!QUALITY_DISPOSITIONS.some(item=>item.id===decision))throw Error("Choose a listed fictional disposition");
  const detail=noteText(note),time=timestamp(at);
  return change(state,"quality.disposition.recorded",record.number+" / "+decision,n=>{
    n.quality.find(q=>q.id===id).disposition={decision,note:detail,recordedAt:time};
  },time);
}
export function recordQualityFollowup(state,id,note,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record)throw Error("Fictional quality case not found");
  const detail=noteText(note),time=timestamp(at);
  return change(state,"quality.followup.recorded",record.number+" / case follow-up",n=>{
    const q=n.quality.find(item=>item.id===id);
    if(!Array.isArray(q.followUps))q.followUps=[];
    q.followUps.push({id:id+"-followup-"+(q.followUps.length+1),note:detail,at:time});
  },time);
}
export function closeReviewedQuality(state,id,at=new Date().toISOString()){
  const record=recordFor(state,id);
  if(!record||record.status!=="OPEN")throw Error("Select an open fictional quality case");
  if(!record.disposition||!QUALITY_DISPOSITIONS.some(item=>item.id===record.disposition.decision))
    throw Error("Record a fictional disposition before closing this case");
  return closeQuality(state,id,timestamp(at));
}
