import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {seedState,packetIssues,getJob} from "./engine.mjs";
import {startSession} from "../ewi/engine.mjs";
import {
 editableRouting,addRouteStep,removeRouteStep,moveRouteStep,
 validateRoutingDraft,saveRoutingDraft,reviewRoutingDraft,DEMO_CENTER_OPTIONS
} from "./routing-edit.mjs";
import {routingEditorHtml} from "./routing-view.mjs";

const editedAt="2026-10-30T12:00:00.000Z";
const reviewedAt="2026-10-30T13:00:00.000Z";

test("routing draft edits reuse the EWI operation schema and do not mutate source on cancel",()=>{
 const state=seedState(),job=state.jobs[0];
 const original=structuredClone(job.routing.operations);
 let draft=editableRouting(job);
 draft[0].name="Fictional new process name";
 draft=moveRouteStep(draft,0,1);
 draft=addRouteStep(draft);
 assert.equal(draft.length,original.length+1);
 assert.equal(draft[1].name,"Fictional new process name");
 assert.equal(validateRoutingDraft(job,draft).length,draft.length);
 draft=removeRouteStep(draft,1);
 assert.equal(draft.length,original.length);
 assert.deepEqual(job.routing.operations,original,"Editing must not touch persisted job without Save");
});
test("save edits the selected job, keeps other jobs unchanged, and blocks both EWI and ERP readiness",()=>{
 let state=seedState(),job=state.jobs[0],other=structuredClone(state.jobs[1].routing);
 let draft=editableRouting(job);
 draft[0].name="Demo laser setup verification";
 draft[0].instructions=["Confirm fictional drawing reference.","Inspect illustrative stock cut."];
 state=saveRoutingDraft(state,job.id,draft,[],editedAt);
 assert.equal(state.jobs[0].routing.operations[0].name,"Demo laser setup verification");
 assert.equal(state.jobs[0].routing.reviewState,"REVIEW_REQUIRED");
 assert.equal(state.jobs[0].routing.source,"BROWSER-LOCAL ROUTING DRAFT");
 assert.deepEqual(state.jobs[1].routing,other,"Other work orders must not change");
 assert.match(packetIssues(state,job.id).join(" "),/Edited routing awaiting demo review/);
 assert.throws(()=>startSession([],{id:"clock-1",employee:"DEMO-01",job:getJob(state,job.id),step:"10",timestamp:reviewedAt}),/Drawing and routing checks must pass/);
 assert.equal(state.jobs[0].routing.history.at(-1).kind,"DRAFT_EDIT");
 assert.equal(state.events.at(-1).type,"routing.draft_edited");
});
test("explicit demo review clears draft interlock but does not claim production approval",()=>{
 let state=seedState(),job=state.jobs[0];
 state=saveRoutingDraft(state,job.id,editableRouting(job),[],editedAt);
 state=reviewRoutingDraft(state,job.id,[],reviewedAt);
 assert.equal(state.jobs[0].routing.reviewState,"DEMO_REVIEWED");
 assert.equal(state.jobs[0].routing.reviewedBy,"DEMO-PLANNER");
 assert.deepEqual(packetIssues(state,job.id),[]);
 const sessions=startSession([],{id:"clock-1",employee:"DEMO-01",job:getJob(state,job.id),step:"10",timestamp:reviewedAt});
 assert.equal(sessions.length,1);
 assert.equal(state.events.at(-1).type,"routing.demo_reviewed");
 assert.throws(()=>reviewRoutingDraft(state,job.id,[],reviewedAt),/No edited route/);
});
test("historical clocks prevent silent rewriting of an executed route",()=>{
 const s=seedState(),j=s.jobs[0],ops=editableRouting(j);
 const clockHistory=[{jobId:j.id,id:"clock-old",start:editedAt,end:reviewedAt}];
 assert.throws(()=>saveRoutingDraft(s,j.id,ops,clockHistory,reviewedAt),/recorded clocking/);
 let draft=saveRoutingDraft(s,j.id,ops,[],editedAt);
 assert.throws(()=>reviewRoutingDraft(draft,j.id,clockHistory,reviewedAt),/Clock history/);
 assert.equal(s.jobs[0].routing.reviewState,undefined);
});
test("malformed draft IDs, work centers, and incomplete operations cannot be saved",()=>{
 const state=seedState(),j=state.jobs[0];
 let op=editableRouting(j);
 op[1].step=op[0].step;
 assert.throws(()=>validateRoutingDraft(j,op),/Duplicate routed step/);
 op=editableRouting(j);op[0].center="ACTUAL-PRIVATE-MACHINE";
 assert.throws(()=>saveRoutingDraft(state,j.id,op),/fictional work center/);
 op=editableRouting(j);op[0].instructions=[];
 assert.throws(()=>validateRoutingDraft(j,op),/1 to 12/);
 assert.ok(DEMO_CENTER_OPTIONS.includes("LASER-01"));
 assert.throws(()=>removeRouteStep([op[0]],0),/at least one/);
});
test("routing screen exposes actual editor and review actions, no BEAN connection claim",()=>{
 const s=seedState(),j=s.jobs[0];
 const closed=routingEditorHtml(j,null,false);
 assert.match(closed,/Edit this routing/);
 const open=routingEditorHtml(j,editableRouting(j),false);
 for(const label of ["routing-editor-form","routing-add","routing-up","routing-down","routing-remove","routing-save","routing-cancel"])
   assert.match(open,new RegExp(label));
 assert.match(open,/No live BEAN|not released by saving/);
 const source=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
 assert.match(source,/routingEditorHtml\(j,/);
 assert.match(source,/saveRoutingDraft\(state,/);
 assert.match(source,/reviewRoutingDraft\(state,/);
 assert.match(source,/readRoutingEditor\(form\)/);
});
