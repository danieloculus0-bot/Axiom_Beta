/* Axiom AutoNest DXF reader/exporter. Supports closed LWPOLYLINE (including bulge
 * arcs) and CIRCLE. Rejects unsupported cutting entities rather than losing edges.
 */
import {polygonArea,pointInPolygon} from "./autonest-engine.mjs";
const num=(s,name)=>{const n=Number(s);if(!Number.isFinite(n))throw Error("Invalid DXF "+name);return n;};
function pairs(text){
  if(typeof text!=="string"||text.length>6000000)throw Error("DXF must be a text file under 6 MB");
  const rows=text.replace(/\r/g,"").split("\n"),out=[];
  for(let i=0;i+1<rows.length;i+=2)out.push([rows[i].trim(),rows[i+1].trim()]);
  return out;
}
function flattenBulge(a,b,bulge,tolerance){
  if(Math.abs(bulge)<1e-10)return [[a[0],a[1]]];
  const theta=4*Math.atan(bulge),dx=b[0]-a[0],dy=b[1]-a[1];
  const chord=Math.hypot(dx,dy);
  if(chord<1e-9)throw Error("Degenerate bulge arc");
  const mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2;
  const distance=chord*(1-bulge*bulge)/(4*bulge);
  const cx=mx-dy/chord*distance,cy=my+dx/chord*distance;
  const r=Math.hypot(a[0]-cx,a[1]-cy);
  const maxStep=2*Math.acos(Math.max(-1,Math.min(1,1-tolerance/r)));
  const n=Math.max(2,Math.min(256,Math.ceil(Math.abs(theta)/Math.max(maxStep,0.02))));
  const start=Math.atan2(a[1]-cy,a[0]-cx);
  return Array.from({length:n},(_,i)=>{
    const t=start+theta*i/n;
    return [cx+r*Math.cos(t),cy+r*Math.sin(t)];
  });
}
function entityGroups(groups){
  const output=[];
  let section="",entity=null;
  for(let i=0;i<groups.length;i++){
    const [code,value]=groups[i];
    if(code==="0"&&value==="SECTION"){section=groups[i+1]?.[1]==="ENTITIES"?"ENTITIES":"";i++;continue;}
    if(code==="0"&&value==="ENDSEC"){if(entity&&section==="ENTITIES")output.push(entity);entity=null;section="";continue;}
    if(section!=="ENTITIES")continue;
    if(code==="0"){
      if(entity)output.push(entity);
      if(value==="ENDSEC"||value==="EOF"){entity=null;continue;}
      entity={type:value,fields:[]};
    }else if(entity)entity.fields.push([code,value]);
  }
  if(entity)output.push(entity);
  return output;
}
const first=(fields,code,def)=>fields.find(x=>x[0]===code)?.[1]??def;
function lwpoly(fields,tolerance){
  const flags=Number(first(fields,"70","0"));
  if(!(flags&1))throw Error("Open LWPOLYLINE is not a closed cutting contour");
  if(Number(first(fields,"43","0"))!==0)throw Error("Constant-width LWPOLYLINE is unsupported");
  const verts=[];let active=null;
  for(const [code,value] of fields){
    if(code==="10"){active={x:num(value,"vertex x"),y:null,bulge:0};verts.push(active);}
    if(code==="20"&&active)active.y=num(value,"vertex y");
    if(code==="42"&&active)active.bulge=num(value,"bulge");
  }
  if(verts.length<3||verts.some(v=>v.y===null))throw Error("Incomplete DXF polyline");
  const output=[];
  for(let i=0;i<verts.length;i++){
    const v=verts[i],next=verts[(i+1)%verts.length];
    output.push(...flattenBulge([v.x,v.y],[next.x,next.y],v.bulge,tolerance));
  }
  if(output.length>1000)throw Error("DXF contour exceeds 1000 vertices after arc approximation");
  return output;
}
function circle(fields,tolerance){
  const cx=num(first(fields,"10",null),"circle center x"),
        cy=num(first(fields,"20",null),"circle center y"),
        r=num(first(fields,"40",null),"radius");
  if(r<=0)throw Error("Invalid DXF circle radius");
  const n=Math.max(24,Math.min(256,Math.ceil(2*Math.PI/Math.max(0.05,2*Math.acos(Math.max(-1,Math.min(1,1-tolerance/r)))))));
  return Array.from({length:n},(_,i)=>[cx+r*Math.cos(2*Math.PI*i/n),cy+r*Math.sin(2*Math.PI*i/n)]);
}
/** One DXF file represents one part with one outer contour and optional holes. */
export function importDxfPart(text,{id="PART-01",quantity=1,arcTolerance=0.08}={}){
  if(!Number.isFinite(arcTolerance)||arcTolerance<=0)throw Error("Arc chord tolerance must be positive");
  const entities=entityGroups(pairs(text));
  if(!entities.length)throw Error("DXF has no ENTITIES section");
  const loops=[];
  for(const ent of entities){
    if(ent.type==="LWPOLYLINE")loops.push(lwpoly(ent.fields,arcTolerance));
    else if(ent.type==="CIRCLE")loops.push(circle(ent.fields,arcTolerance));
    else throw Error("Unsupported DXF entity "+ent.type+"; convert geometry to closed LWPOLYLINE or CIRCLE");
  }
  if(!loops.length)throw Error("No closed geometry found");
  loops.sort((a,b)=>polygonArea(b)-polygonArea(a));
  const outer=loops[0],holes=loops.slice(1);
  for(const hole of holes)if(!hole.every(p=>pointInPolygon(p,outer)))
    throw Error("DXF contains multiple disjoint contours; upload one part per file");
  return {id,quantity,outline:outer,holes};
}
const put=(target,code,value)=>{target.push(String(code),String(value));};
function contour(target,poly,layer){
  put(target,0,"LWPOLYLINE");put(target,8,layer);put(target,90,poly.length);put(target,70,1);
  for(const p of poly){put(target,10,Number(p[0].toFixed(6)));put(target,20,Number(p[1].toFixed(6)));}
}
/** Separate cutting DXF for each sheet; stock boundary is deliberately not in CUT layer. */
export function exportDxfSheet(result,sheetIndex){
  if(!result||!result.sheets?.[sheetIndex])throw Error("Sheet index not found");
  const data=[];
  put(data,0,"SECTION");put(data,2,"HEADER");put(data,9,"$ACADVER");put(data,1,"AC1015");
  put(data,0,"ENDSEC");put(data,0,"SECTION");put(data,2,"ENTITIES");
  for(const part of result.sheets[sheetIndex]){
    contour(data,part.points,"CUT_OUTER");
    for(const hole of part.holes)contour(data,hole,"CUT_INNER");
  }
  put(data,0,"ENDSEC");put(data,0,"EOF");
  return data.join("\n")+"\n";
}
