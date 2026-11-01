/* Review-only BEAN Core reasoning_proposals SQLite row adapter.
 * No BEAN service call, automatic operation translation, data writes or release.
 * Source: BEAN main bean/reasoning/proposal_store.py:get_proposal.
 */
import {reviewRoutingCandidate} from "./routing-advice.mjs";
const str=v=>typeof v==="string"?v.trim():"";
const limits=[
 "Caller-supplied BEAN record: provider, provenance and filter outcomes not verified.",
 "BEAN candidate steps are free-text advice, not manufacturing operations.",
 "Drawings, machine capabilities, evidence and program times are not independently verified.",
 "Neither proposals nor optional mapped candidates authorize routing changes."
];
const reject=issue=>({status:"INVALID_SOURCE",proposalOnly:true,canAutoApply:false,
 proposal:null,routingReview:null,issues:[issue],limitations:[...limits]});
const parseList=(record,key)=>{
 const raw=record[key];
 if(typeof raw!=="string"||raw.length>24000)throw Error("Invalid field");
 const value=JSON.parse(raw);
 if(!Array.isArray(value)||value.length>60||
    !value.every(v=>typeof v==="string"&&v.length<=1000))throw Error("Invalid list");
 return [...value];
};
/** Bind a stored BEAN proposal to a selected canonical Axiom job. No inference.
 * An optional independently supplied structured candidate uses Axiom's existing
 * reviewRoutingCandidate; BEAN text is never silently converted into operations.
 */
export function reviewBeanCoreRoutingProposal(job,record,binding,mappedCandidate=null){
 if(!job||!Array.isArray(job.routing?.operations)||!str(job.jobNumber)||
    !str(job.partNumber)||!str(job.revision))
   return reject("An existing Axiom job and canonical routing are required.");
 if(!binding||binding.jobNumber!==job.jobNumber||
    binding.partNumber!==job.partNumber||binding.revision!==job.revision)
   return reject("Explicit job, part and revision binding does not match.");
 if(!record||typeof record!=="object"||Array.isArray(record)||
    !/^proposal_[a-f0-9]{12}$/.test(record.proposal_id||"")||
    !str(record.request_id)||!str(record.response_id)||
    record.proposal_type!=="reasoning"||record.status!=="pending_review"||
    !str(record.summary)||record.summary.length>2000||
    typeof record.confidence!=="number"||!Number.isFinite(record.confidence)||
    record.confidence<0||record.confidence>1)
   return reject("BEAN Core proposal identity, state or confidence is invalid.");
 let data;
 try{
   data={
     observations:parseList(record,"observations_json"),
     interpretations:parseList(record,"interpretations_json"),
     assumptions:parseList(record,"assumptions_json"),
     uncertainties:parseList(record,"uncertainties_json"),
     evidenceRefs:parseList(record,"evidence_refs_json"),
     candidateSteps:parseList(record,"candidate_steps_json"),
     riskFlags:parseList(record,"risk_flags_json")
   };
 }catch{return reject("Stored BEAN proposal JSON fields are invalid.");}
 const routingReview=mappedCandidate===null?null:
   reviewRoutingCandidate(job,mappedCandidate);
 const issues=[];
 if(data.candidateSteps.length&&!data.evidenceRefs.length)
   issues.push("Candidate steps have no asserted evidence references.");
 if(data.riskFlags.length)issues.push("BEAN risk flags require review.");
 if(routingReview)issues.push(...routingReview.issues);
 return {
   status:routingReview?.status==="INVALID"?"INVALID_MAPPING":
     routingReview?"REVIEW_REQUIRED":"ADVISORY_ONLY",
   proposalOnly:true,canAutoApply:false,
   binding:{jobNumber:job.jobNumber,partNumber:job.partNumber,revision:job.revision},
   proposal:{proposalId:record.proposal_id,requestId:record.request_id,
     responseId:record.response_id,reviewState:record.status,
     summary:record.summary,confidence:record.confidence,...data},
   routingReview,issues,limitations:[...limits]
 };
}
