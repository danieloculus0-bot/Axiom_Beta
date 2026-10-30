import test from "node:test";
import assert from "node:assert/strict";
import {
 MENU_GROUPS,MENU_ITEMS,getMenuItem,cleanMenuPrefs,toggleFavorite,visitMenu,searchMenu
} from "./navigation.mjs";
test("every navigation entry is unique and maps to a hash route",()=>{
 const ids=MENU_ITEMS.map(x=>x.id);
 assert.equal(ids.length,12);
 assert.equal(new Set(ids).size,ids.length);
 assert.ok(MENU_GROUPS.every(g=>g.items.length>0));
 assert.ok(MENU_ITEMS.every(x=>x.href==="#"+x.id&&x.groupLabel&&x.hint));
 for(const id of ["dashboard","jobs","routing","ewi","documents","inventory","purchasing","quality","pm","reports","bridge","audit"])
   assert.ok(getMenuItem(id));
 assert.equal(getMenuItem("nonexistent"),null);
});
test("search finds working screens by label, synonym and group",()=>{
 assert.equal(searchMenu("PM")[0].id,"pm");
 assert.equal(searchMenu("time ticket")[0].id,"ewi");
 assert.equal(searchMenu("purchase order")[0].id,"purchasing");
 assert.equal(searchMenu("JobBOSS")[0].id,"bridge");
 assert.equal(searchMenu("reporting")[0].id,"reports");
 assert.ok(searchMenu("manufacturing").some(x=>x.id==="routing"));
 assert.equal(searchMenu("make a fake dummy module").length,0);
 assert.equal(searchMenu("").length,MENU_ITEMS.length);
});
test("favorites and recents cannot accept nonexistent/deceptive links",()=>{
 let p=cleanMenuPrefs({favorites:["jobs","missing","jobs","pm"],recent:["pm","missing","quality","pm"]});
 assert.deepEqual(p.favorites,["jobs","pm"]);
 assert.deepEqual(p.recent,["pm","quality"]);
 p=toggleFavorite(p,"reports");
 assert.deepEqual(p.favorites,["jobs","pm","reports"]);
 p=toggleFavorite(p,"jobs");
 assert.deepEqual(p.favorites,["pm","reports"]);
 assert.throws(()=>toggleFavorite(p,"../../private"),/does not exist/);
 p=visitMenu(p,"quality");
 assert.equal(p.recent[0],"quality");
 assert.equal(p.recent.length,2);
 assert.deepEqual(visitMenu(p,"nonexistent"),p);
});
test("preference cleaning remains bounded and tolerates invalid storage",()=>{
 assert.deepEqual(cleanMenuPrefs(null),{favorites:[],recent:[]});
 assert.deepEqual(cleanMenuPrefs("invalid"),{favorites:[],recent:[]});
 const p=cleanMenuPrefs({favorites:Array(100).fill("dashboard"),recent:MENU_ITEMS.map(x=>x.id)});
 assert.deepEqual(p.favorites,["dashboard"]);
 assert.ok(p.recent.length<=12);
});
