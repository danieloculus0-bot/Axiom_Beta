import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Exercise the actual browser loader without importing DOM-dependent UI modules.
const source=readFileSync(new URL("./app.mjs",import.meta.url),"utf8");
const loader=source.slice(source.indexOf("function load(){"),source.indexOf("\nfunction persist(){"));
assert.ok(loader.startsWith("function load(){") && loader.endsWith("}\n"));
const keys=["erp","clock","workforce"];
function run({erp='{"generation":2}',clock="[]",workforce='{"generation":2}',recoveryFails=false}={}){
  const data=new Map([[keys[0],erp],[keys[1],clock],[keys[2],workforce]]);
  const context={
    ERP_KEY:keys[0],CLOCK_KEY:keys[1],WORKFORCE_KEY:keys[2],
    state:{generation:0},sessions:[{id:"stale"}],workforce:{generation:0},stored:false,
    seedState:()=>({generation:"seed"}),seedWorkforce:()=>({generation:"seed"}),
    validateState:x=>x,validateWorkforce:x=>x,
    recoverBrowserSave:()=>{if(recoveryFails)throw Error("interrupted replay");},
    localStorage:{getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}
  };
  vm.runInNewContext(loader+"\nload();",context);
  return {state:context.state,sessions:context.sessions,workforce:context.workforce,stored:context.stored};
}
test("failed journal recovery never exposes independently loaded workforce",()=>{
  const result=run({recoveryFails:true});
  assert.equal(result.stored,false);
  assert.equal(result.state.generation,"seed");
  assert.equal(result.workforce.generation,"seed");
  assert.equal(result.sessions.length,0);
});
test("invalid workforce rejects the whole browser-local generation",()=>{
  const result=run({workforce:"{invalid"});
  assert.equal(result.stored,false);
  assert.equal(result.state.generation,"seed");
  assert.equal(result.workforce.generation,"seed");
  assert.equal(result.sessions.length,0);
});
test("valid three-record generation loads together",()=>{
  const result=run();
  assert.equal(result.stored,true);
  assert.equal(result.state.generation,2);
  assert.equal(result.workforce.generation,2);
});
