import test from "node:test";
import assert from "node:assert/strict";
import {solveNest,verifyNest,polygonsOverlap,polygonArea} from "./autonest-engine.mjs";
import {importDxfPart,exportDxfSheet} from "./autonest-dxf.mjs";

const rect=(id,w,h,quantity=1)=>({id,quantity,outline:[[0,0],[w,0],[w,h],[0,h]]});
const job=(parts,sheet={width:10,height:10,margin:0},spacing=1)=>({sheet,spacing,kerf:0,parts});

test("Axiom AutoNest nests four 4x4 panels on one 10x10 sheet with 1-unit webs",()=>{
  const result=solveNest(job([rect("SQ",4,4,4)]));
  assert.equal(result.status,"NESTED");
  assert.equal(result.sheets.length,1);
  assert.equal(result.placed,4);
  assert.equal(result.requested,4);
  assert.equal(result.utilization,64);
  assert.equal(result.trials.length,12);
  assert.deepEqual(verifyNest(result),{ok:true,failures:[],verifiedPlacements:4});
});
test("rotation permits a part that cannot otherwise fit",()=>{
  const result=solveNest(job([rect("ROT",7,3)],{width:4,height:8,margin:0},0.3));
  assert.equal(result.sheets.length,1);
  assert.ok(result.sheets[0][0].angle===90||result.sheets[0][0].angle===270);
  assert.equal(verifyNest(result).ok,true);
});
test("concave U outline allows a smaller rectangle to nest inside a genuine open recess",()=>{
  const concave={id:"U",quantity:1,outline:[[0,0],[10,0],[10,10],[7,10],[7,3],[3,3],[3,10],[0,10]]};
  const result=solveNest(job([concave,rect("FILL",2,5)],{width:10.4,height:10.4,margin:0},0.2));
  assert.equal(result.sheets.length,1);
  assert.equal(result.placed,2);
  assert.equal(verifyNest(result).ok,true);
});
test("multiple sheets and impossible geometry are reported explicitly",()=>{
  const result=solveNest(job([rect("PANEL",7,7,3),rect("TOO_BIG",100,2)],
    {width:10,height:10,margin:0},1));
  assert.equal(result.sheets.length,3);
  assert.deepEqual(result.unplaced,["TOO_BIG"]);
  assert.equal(result.status,"PARTIAL");
  assert.equal(verifyNest(result).ok,true);
});
test("a hole is retained and subtracted from material area, but not falsely used for part-on-part nesting",()=>{
  const plate={...rect("PLATE",8,8),holes:[[[2,2],[6,2],[6,6],[2,6]]]};
  const result=solveNest(job([plate],{width:10,height:10,margin:0},0.5));
  assert.equal(result.materialArea,48);
  assert.equal(result.sheets[0][0].holes.length,1);
  assert.equal(verifyNest(result).ok,true);
});
test("genuinely intersecting parts are rejected during independent verification",()=>{
  const result=solveNest(job([rect("A",4,4,2)]));
  const bad=structuredClone(result);
  bad.sheets[0][1].points=bad.sheets[0][0].points.map(p=>[...p]);
  assert.equal(verifyNest(bad).ok,false);
  assert.match(verifyNest(bad).failures[0],/collision/);
  assert.equal(polygonsOverlap([[0,0],[4,0],[4,4],[0,4]],[[5,0],[8,0],[8,3],[5,3]],1.1),true);
});
test("search is deterministic for identical inputs",()=>{
  const input=job([rect("A",3,2,3),rect("B",2,4,2),rect("C",4,1,2)]);
  assert.deepEqual(solveNest(input),solveNest(input));
});
test("invalid or ambiguous part geometry fails without silently approximating",()=>{
  assert.throws(()=>solveNest(job([{id:"BAD",outline:[[0,0],[4,4],[0,4],[4,0]]}])),/degenerate|self-intersecting/);
  assert.throws(()=>solveNest(job([rect("X",3,3),rect("X",2,2)])),/unique/);
  assert.throws(()=>solveNest(job([{...rect("VOID",5,5),holes:[[[4,4],[6,4],[6,6],[4,6]]]}])),/hole/);
  assert.throws(()=>solveNest(job([{...rect("ROT",5,5),rotations:[NaN]}])),/rotation/);
});
test("export cutting DXF and import one part with an internal void, preserving geometry",()=>{
  const part={...rect("SQUARE",8,8),holes:[[[2,2],[6,2],[6,6],[2,6]]]};
  const result=solveNest(job([part],{width:9,height:9,margin:0},0));
  const dxf=exportDxfSheet(result,0);
  assert.match(dxf,/CUT_OUTER/);
  assert.match(dxf,/CUT_INNER/);
  assert.ok(!dxf.includes("SHEET_REF"));
  const imported=importDxfPart(dxf,{id:"IMPORTED"});
  assert.equal(imported.holes.length,1);
  assert.equal(polygonArea(imported.outline),64);
  assert.equal(polygonArea(imported.holes[0]),16);
});
test("DXF bulge arcs are genuinely tessellated; open/unsupported entities are refused",()=>{
  const prefix="0\nSECTION\n2\nENTITIES\n";
  const suffix="\n0\nENDSEC\n0\nEOF\n";
  const arcDxf=prefix+
    "0\nLWPOLYLINE\n90\n3\n70\n1\n10\n0\n20\n0\n42\n1\n10\n10\n20\n0\n10\n5\n20\n-8"+suffix;
  const arc=importDxfPart(arcDxf,{id:"ARC"});
  assert.ok(arc.outline.length>5);
  assert.throws(()=>importDxfPart(prefix+"0\nLINE\n10\n0\n20\n0"+suffix),/Unsupported/);
  assert.throws(()=>importDxfPart(prefix+"0\nLWPOLYLINE\n90\n3\n70\n0\n10\n0\n20\n0\n10\n1\n20\n0\n10\n0\n20\n1"+suffix),/Open/);
});
