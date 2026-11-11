import test from "node:test";
import assert from "node:assert/strict";
import {JOURNAL_KEY,persistBrowserSave,recoverBrowserSave} from "./storage-journal.mjs";
const keys=["erp","clock","people"];
function store(initial={},failAt=Infinity) {
  const data=new Map(Object.entries(initial)); let writes=0;
  return {data,getItem:k=>data.get(k)??null,setItem(k,v){if(++writes===failAt)throw Error("injected failure");data.set(k,v);},removeItem:k=>data.delete(k)};
}
const old=[{revision:1},[],{revision:1}], next=[{revision:2},[{id:"fictional"}],{revision:2}];
function seeded() {const s=store();persistBrowserSave(s,keys,old);return Object.fromEntries(s.data);}
for (let n=1;n<=4;n++) test("failure at write "+n+" never leaves mixed generation after recovery",()=>{
  const s=store(seeded(),n);
  assert.throws(()=>persistBrowserSave(s,keys,next),/injected/);
  const reboot=store(Object.fromEntries(s.data));
  recoverBrowserSave(reboot,keys);
  const got=keys.map(k=>JSON.parse(reboot.getItem(k)));
  assert.deepEqual(got,n===1?old:next);
  assert.equal(reboot.getItem(JOURNAL_KEY),null);
});
test("legacy three-key data loads without migration",()=>{
 const s=store(seeded());assert.equal(recoverBrowserSave(s,keys),false);
 assert.deepEqual(keys.map(k=>JSON.parse(s.getItem(k))),old);
});
test("corrupt journal is rejected without overwriting legacy records",()=>{
 const s=store({...seeded(),[JOURNAL_KEY]:"{broken"});
 assert.throws(()=>recoverBrowserSave(s,keys));
 assert.deepEqual(keys.map(k=>JSON.parse(s.getItem(k))),old);
});
test("recovery can be retried after a transient write failure",()=>{
 const s=store(seeded(),2);assert.throws(()=>persistBrowserSave(s,keys,next));
 const failed=store(Object.fromEntries(s.data),1);
 assert.throws(()=>recoverBrowserSave(failed,keys));
 const retry=store(Object.fromEntries(failed.data));
 assert.equal(recoverBrowserSave(retry,keys),true);
 assert.deepEqual(keys.map(k=>JSON.parse(retry.getItem(k))),next);
});


test("quota rejection of journal leaves all legacy records unchanged",()=>{
  const initial={erp:'{"v":1}',clock:"[]",people:'{"v":1}'};
  const s=quotaStore(80,initial);
  assert.throws(()=>persistBrowserSave(s,keys,[{v:2},[{id:"fictional"}],{v:2}]),{name:"QuotaExceededError"});
  assert.deepEqual(Object.fromEntries(s.data),initial);
});
test("quota rejection after journal write retains recoverable snapshot",()=>{
  const initial={erp:'{"v":1}',clock:"[]",people:'{"v":1}'};
  const s=quotaStore(140,initial);
  assert.throws(()=>persistBrowserSave(s,keys,[{v:2},[{id:"fictional"}],{v:2}]),{name:"QuotaExceededError"});
  assert.ok(s.getItem(JOURNAL_KEY));
  const recovered=quotaStore(1000,Object.fromEntries(s.data));
  assert.equal(recoverBrowserSave(recovered,keys),true);
  assert.deepEqual(JSON.parse(recovered.getItem("erp")),{v:2});
});
function quotaStore(limit,seed={}) {
  const data=new Map(Object.entries(seed));
  return {data,getItem:k=>data.get(k)??null,setItem(k,v){
    const size=[...data].reduce((n,[a,b])=>n+(a===k?0:a.length+b.length),0)+k.length+v.length;
    if(size>limit)throw new DOMException("Quota exceeded","QuotaExceededError");
    data.set(k,v);
  },removeItem:k=>data.delete(k)};
}
