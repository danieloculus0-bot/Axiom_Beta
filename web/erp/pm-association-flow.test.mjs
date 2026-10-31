/* Synthetic DOM-lifecycle integration check for the existing Axiom PM form.
 * No browser, live BEAN, real equipment, or production approval is involved.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {ERP_KEY} from "./engine.mjs";
import {assessAlternateCenters} from "./routing-capacity-advice.mjs";

class FakeElement {
  constructor(tag="div") {
    this.tagName=tag.toUpperCase();this.dataset={};this.style={};this.children=[];
    this.classList={add(){},toggle(){},remove(){}};
    this.listeners=new Map();this.value="";this.innerHTML="";
  }
  addEventListener(type,callback) {
    const list=this.listeners.get(type)||[];list.push(callback);this.listeners.set(type,list);
  }
  setAttribute(name,value){this[name]=String(value);}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];}
  querySelectorAll(){return [];}
  closest(selector){return selector==="[data-form]"&&this.dataset.form?this:null;}
}
function fakeDocument() {
  const nodes=new Map(),events=new Map();
  return {
    body:new FakeElement("body"),events,
    getElementById(id){if(!nodes.has(id))nodes.set(id,new FakeElement());return nodes.get(id);},
    createElement(tag){return new FakeElement(tag);},
    querySelector(){return null;},
    addEventListener(type,handler){const list=events.get(type)||[];list.push(handler);events.set(type,list);}
  };
}
function scenario(window) {
  return {window,centers:[{
    id:"PRESS-02",routedOperationCount:0,
    capability:{operation:"Laser cut blank",supported:true,sourceRef:"SYN-CAP-001"},
    calendarHours:8,bookedHours:0,queuedHours:0,maintenanceHours:0,setupHours:1,runHours:1,
    capacitySourceRef:"SYN-CALENDAR-001",readinessSourceRef:"SYN-READY-001",
    maintenanceState:"CLEAR",tooling:"READY",fixture:"READY",material:"READY",deliveryState:"ON_TIME"
  }]};
}
function dispatchForm(doc,fields) {
  const form=new FakeElement("form");form.dataset.form="pm-work-center-link";form.fields=fields;
  let prevented=false;
  const event={target:form,preventDefault(){prevented=true;}};
  for(const handler of doc.events.get("submit")||[])handler(event);
  assert.equal(prevented,true,"actual Axiom form handler intercepted submission");
}

test("PM association form persists through a simulated reload and remains historical review-only",async()=>{
  const original={document:globalThis.document,localStorage:globalThis.localStorage,
    location:globalThis.location,window:globalThis.window,history:globalThis.history,
    FormData:globalThis.FormData,setInterval:globalThis.setInterval};
  const data=new Map();
  const storage={getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,String(value)),
    removeItem:key=>data.delete(key)};
  const fakeFormData=class {constructor(form){this.fields=form.fields;}get(key){return this.fields[key]??null;}};
  const mount=async token=>{
    const doc=fakeDocument();globalThis.document=doc;
    globalThis.localStorage=storage;
    globalThis.location={hash:"#pm",search:"?machine=DEMO-M-001",pathname:"/erp/index.html",origin:"https://example.invalid"};
    globalThis.window={addEventListener(){},innerWidth:1200,innerHeight:800};
    globalThis.history={replaceState(){}};
    globalThis.FormData=fakeFormData;
    globalThis.setInterval=()=>0;
    await import("./app.mjs?pm-association-flow="+token);
    return doc;
  };
  try {
    const first=await mount("first");
    assert.match(first.getElementById("view").innerHTML,/data-form="pm-work-center-link"/);
    const fields={machine:"DEMO-M-001",center:"PRESS-02",reviewer:"DEMO-PLANNER",source:"SYN-LINK-001"};
    dispatchForm(first,fields);
    assert.equal(storage.getItem(ERP_KEY),null,"missing confirmation cannot persist a change");
    assert.match(first.getElementById("view").innerHTML,/Explicit fictional association review is required/);
    dispatchForm(first,{...fields,confirmed:"on"});
    const state=JSON.parse(storage.getItem(ERP_KEY));
    assert.equal(state.pm.machines[0].workCenterLink.centerId,"PRESS-02");
    assert.equal(state.pm.workCenterLinkHistory.length,1);
    assert.equal(state.events.at(-1).type,"pm.work_center.demo_link_reviewed");
    assert.match(first.getElementById("view").innerHTML,/SYN-LINK-001/);

    const second=await mount("reload");
    assert.match(second.getElementById("view").innerHTML,/value="PRESS-02" selected/);
    assert.match(second.getElementById("view").innerHTML,/SYN-LINK-001/);
    const job=state.jobs[0];
    const before=assessAlternateCenters(job,"10",{
      ...scenario({start:"2020-11-02T08:00:00Z",end:"2020-11-02T16:00:00Z"}),
      pmContext:{state:state.pm}
    });
    assert.equal(before.assessments[0].pmEvidence.status,"UNMAPPED",
      "later association cannot establish historical availability");
    assert.equal(before.suggestions.length,0);
    const after=assessAlternateCenters(job,"10",{
      ...scenario({start:"2099-11-02T08:00:00Z",end:"2099-11-02T16:00:00Z"}),
      pmContext:{state:state.pm}
    });
    assert.equal(after.assessments[0].pmEvidence.machineId,"DEMO-M-001");
    assert.equal(after.canAutoApply,false);
  } finally {
    for(const [key,value] of Object.entries(original)) {
      if(value===undefined)delete globalThis[key];else globalThis[key]=value;
    }
  }
});
