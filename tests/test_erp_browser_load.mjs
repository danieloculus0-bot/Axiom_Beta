import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

// Exercise the actual app load() body with isolated browser-storage doubles.
const source=readFileSync(new URL("../web/erp/app.mjs",import.meta.url),"utf8");
const match=source.match(/function load\(\)\{[\s\S]*?\n\}\nfunction persist\(/);
assert.ok(match,"ERP application load() must remain discoverable");
const loadSource=match[0].slice(0,-"\nfunction persist(".length);

function exercise(values={},fault=false){
  const keys={ERP_KEY:"erp",CLOCK_KEY:"clock",WORKFORCE_KEY:"workforce"};
  const records=new Map(Object.entries(values));
  const storage={
    getItem(key){if(fault)throw Error("Storage denied");return records.has(key)?records.get(key):null;},
    setItem(key,value){if(fault)throw Error("Storage denied");records.set(key,value);},
    removeItem(key){if(fault)throw Error("Storage denied");records.delete(key);}
  };
  const context={
    ...keys,localStorage:storage,recoverBrowserSave(){},
    seedState(){return {demo:true,jobs:[{id:"seed"}]};},
    seedWorkforce(){return {seed:true};},
    validateState(value){if(value?.demo!==true)throw Error("Invalid ERP");return value;},
    validateWorkforce(value){if(!value?.valid)throw Error("Invalid workforce");return value;},
  };
  const result=runInNewContext(
    'let state=seedState(),workforce=seedWorkforce(),sessions=[],stored=false,recoveryFailure=null;'+
    loadSource+';load();({state,workforce,sessions,stored,recoveryFailure:!!recoveryFailure})',context
  );
  return result;
}
test("empty browser storage retains editable fictional starter state",()=>{
  const result=exercise();
  assert.equal(result.stored,true);
  assert.equal(result.recoveryFailure,false);
});
for(const [name,values] of [
  ["malformed ERP",{erp:"{"}],
  ["oversized ERP",{erp:"x".repeat(1800000)}],
  ["invalid ERP schema",{erp:'{"demo":false}'}],
  ["malformed workforce",{workforce:"{"}],
  ["oversized workforce",{workforce:"x".repeat(800000)}],
  ["non-array clocks",{clock:"{}"}],
  ["oversized clocks",{clock:"x".repeat(2500000)}],
]){
  test(name+" blocks editing without replacing stored bytes",()=>{
    const result=exercise(values);
    assert.equal(result.stored,false);
    assert.equal(result.recoveryFailure,true);
  });
}
test("storage access denied blocks editing",()=>{
  const result=exercise({},true);
  assert.equal(result.stored,false);
  assert.equal(result.recoveryFailure,true);
});
test("valid saved fictional state is restored",()=>{
  const result=exercise({erp:'{"demo":true,"jobs":[{"id":"saved"}]}',workforce:'{"valid":true}',clock:"[]"});
  assert.equal(result.stored,true);
  assert.equal(result.recoveryFailure,false);
  assert.equal(result.state.jobs[0].id,"saved");
});
