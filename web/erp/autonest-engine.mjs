/* Axiom AutoNest v1: deterministic polygon nesting with evidence-backed multi-strategy search.
 * Synthetic/browser-local input. No machine controller integration or live BEAN inference.
 */
const EPS=1e-7;
const round=n=>Math.round(n*1e6)/1e6;
const finite=(n,name,min=0,max=1e7)=>{
  if(typeof n!=="number"||!Number.isFinite(n)||n<min||n>max)throw Error(name+" must be a finite number in ["+min+","+max+"]");
  return n;
};
const point=p=>{
  if(!Array.isArray(p)||p.length!==2)throw Error("Point must be [x,y]");
  return [finite(p[0],"x",-1e7),finite(p[1],"y",-1e7)];
};
export function signedArea(poly){
  let a=0;for(let i=0;i<poly.length;i++){const p=poly[i],q=poly[(i+1)%poly.length];a+=p[0]*q[1]-q[0]*p[1];}
  return a/2;
}
export const polygonArea=poly=>Math.abs(signedArea(poly));
export function perimeter(poly){let n=0;for(let i=0;i<poly.length;i++)n+=Math.hypot(poly[i][0]-poly[(i+1)%poly.length][0],poly[i][1]-poly[(i+1)%poly.length][1]);return n;}
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
const onSegment=(a,b,p)=>Math.abs(cross(a,b,p))<EPS&&p[0]>=Math.min(a[0],b[0])-EPS&&p[0]<=Math.max(a[0],b[0])+EPS&&p[1]>=Math.min(a[1],b[1])-EPS&&p[1]<=Math.max(a[1],b[1])+EPS;
function intersect(a,b,c,d){
  const ca=cross(a,b,c),da=cross(a,b,d),ac=cross(c,d,a),bc=cross(c,d,b);
  if((ca>EPS&&da<-EPS||ca<-EPS&&da>EPS)&&(ac>EPS&&bc<-EPS||ac<-EPS&&bc>EPS))return true;
  return Math.abs(ca)<EPS&&onSegment(a,b,c)||Math.abs(da)<EPS&&onSegment(a,b,d)||Math.abs(ac)<EPS&&onSegment(c,d,a)||Math.abs(bc)<EPS&&onSegment(c,d,b);
}
export function pointInPolygon(p,poly){
  let inside=false;
  for(let i=0,j=poly.length-1;i<poly.length;j=i++){
    const a=poly[j],b=poly[i];
    if(onSegment(a,b,p))return true;
    if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
  }
  return inside;
}
function normalizePolygon(value,name){
  if(!Array.isArray(value)||value.length<3||value.length>1000)throw Error(name+": need 3 to 1000 vertices");
  const poly=value.map(point);
  if(poly.length>3&&Math.hypot(poly[0][0]-poly.at(-1)[0],poly[0][1]-poly.at(-1)[1])<EPS)poly.pop();
  if(poly.length<3||polygonArea(poly)<EPS)throw Error(name+": degenerate polygon");
  for(let i=0;i<poly.length;i++){
    if(Math.hypot(poly[i][0]-poly[(i+1)%poly.length][0],poly[i][1]-poly[(i+1)%poly.length][1])<EPS)throw Error(name+": duplicate adjacent vertices");
    for(let j=i+1;j<poly.length;j++){
      if(j===i+1||(i===0&&j===poly.length-1))continue;
      if(intersect(poly[i],poly[(i+1)%poly.length],poly[j],poly[(j+1)%poly.length]))
        throw Error(name+": self-intersecting outline");
    }
  }
  return poly;
}
export function polygonsOverlap(a,b,clearance=0){
  for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++)
    if(intersect(a[i],a[(i+1)%a.length],b[j],b[(j+1)%b.length]))return true;
  if(pointInPolygon(a[0],b)||pointInPolygon(b[0],a))return true;
  if(clearance<=EPS)return false;
  const dist=(p,a,b)=>{
    const dx=b[0]-a[0],dy=b[1]-a[1],len2=dx*dx+dy*dy;
    const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/len2));
    return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);
  };
  for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++){
    const c=a[i],d=a[(i+1)%a.length],e=b[j],f=b[(j+1)%b.length];
    if(Math.min(dist(c,e,f),dist(d,e,f),dist(e,c,d),dist(f,c,d))<clearance-EPS)return true;
  }
  return false;
}
function rotate(poly,degree){
  const theta=degree*Math.PI/180,c=Math.cos(theta),s=Math.sin(theta);
  return poly.map(p=>[round(p[0]*c-p[1]*s),round(p[0]*s+p[1]*c)]);
}
function variant(part,angle){
  const rotated=rotate(part.outline,angle);
  const minX=Math.min(...rotated.map(p=>p[0])),minY=Math.min(...rotated.map(p=>p[1]));
  const translate=poly=>poly.map(p=>[round(p[0]-minX),round(p[1]-minY)]);
  const points=translate(rotated);
  return {angle,points,holes:part.holes.map(h=>translate(rotate(h,angle))),
    width:Math.max(...points.map(p=>p[0])),height:Math.max(...points.map(p=>p[1])),area:part.area,cutLength:part.cutLength};
}
function normalizeInput(input){
  if(!input||typeof input!=="object"||Array.isArray(input))throw Error("Nest input must be an object");
  const width=finite(input.sheet?.width,"sheet width",1),height=finite(input.sheet?.height,"sheet height",1);
  const margin=finite(input.sheet?.margin??0,"sheet margin",0,width/2);
  const spacing=finite(input.spacing??2,"minimum web",0),kerf=finite(input.kerf??0,"kerf",0);
  if(!Array.isArray(input.parts)||!input.parts.length||input.parts.length>100)throw Error("Require 1 to 100 part definitions");
  const ids=new Set();let total=0;
  const parts=input.parts.map((p,index)=>{
    const id=String(p.id??"").trim();
    if(!/^[\w.-]{1,64}$/.test(id)||ids.has(id))throw Error("Each part needs a unique simple ID");
    ids.add(id);
    const quantity=p.quantity??1;
    if(!Number.isInteger(quantity)||quantity<1||quantity>200)throw Error(id+": quantity must be 1 to 200");
    total+=quantity;if(total>250)throw Error("Limit 250 total pieces per job");
    const outline=normalizePolygon(p.outline,id+" outline");
    const holes=(p.holes??[]).map((h,i)=>normalizePolygon(h,id+" hole "+i));
    for(const hole of holes){
      if(!hole.every(v=>pointInPolygon(v,outline))||polygonsOverlap(hole,outline,0))
        throw Error(id+": hole must be strictly inside outline");
      if(holes.some(other=>other!==hole&&polygonsOverlap(hole,other,0)))throw Error(id+": overlapping holes");
    }
    const angles=p.rotations??[0,90,180,270];
    if(!Array.isArray(angles)||!angles.length||angles.length>24||
      !angles.every(a=>typeof a==="number"&&Number.isFinite(a)&&a>=0&&a<360))
      throw Error(id+": invalid rotation angles");
    const area=polygonArea(outline)-holes.reduce((a,h)=>a+polygonArea(h),0);
    if(area<EPS)throw Error(id+": nonpositive net material area");
    const cutLength=perimeter(outline)+holes.reduce((s,h)=>s+perimeter(h),0);
    const part={id,quantity,outline,holes,area,cutLength,rotations:[...new Set(angles)].sort((a,b)=>a-b)};
    part.variants=part.rotations.map(a=>variant(part,a));
    return part;
  });
  return {sheet:{width,height,margin},spacing,kerf,parts,total};
}
function bbox(points){
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  return {minX:Math.min(...xs),minY:Math.min(...ys),maxX:Math.max(...xs),maxY:Math.max(...ys)};
}
function position(part,v,x,y,sheetIndex){
  const move=poly=>poly.map(p=>[round(p[0]+x),round(p[1]+y)]);
  const points=move(v.points);
  return {id:part.id,sheetIndex,angle:v.angle,x:round(x),y:round(y),
    points,holes:v.holes.map(move),area:part.area,cutLength:part.cutLength,bbox:bbox(points)};
}
function collision(candidate,other,gap){
  const a=candidate.bbox,b=other.bbox;
  if(a.maxX+gap<b.minX-EPS||b.maxX+gap<a.minX-EPS||a.maxY+gap<b.minY-EPS||b.maxY+gap<a.minY-EPS)return false;
  return polygonsOverlap(candidate.points,other.points,gap);
}
function candidates(placed,v,limits,style){
  const xs=new Set([round(limits.minX)]),ys=new Set([round(limits.minY)]);
  const push=(set,n,min,max)=>{if(n>=min-EPS&&n<=max+EPS)set.add(round(Math.max(min,Math.min(max,n))));};
  for(const p of placed){
    const b=p.bbox;
    for(const x of [b.maxX+limits.gap,b.minX-v.width-limits.gap,b.minX,b.maxX-v.width])
      push(xs,x,limits.minX,limits.maxX-v.width);
    for(const y of [b.maxY+limits.gap,b.minY-v.height-limits.gap,b.minY,b.maxY-v.height])
      push(ys,y,limits.minY,limits.maxY-v.height);
    for(const a of p.points)for(const b of v.points){
      for(const d of [-limits.gap,0,limits.gap]){
        push(xs,a[0]-b[0]+d,limits.minX,limits.maxX-v.width);
        push(ys,a[1]-b[1]+d,limits.minY,limits.maxY-v.height);
      }
    }
  }
  const maxAxes=80;
  const sample=set=>[...set].sort((a,b)=>a-b).slice(0,maxAxes);
  const ax=sample(xs),ay=sample(ys);
  const positions=[];
  for(const x of ax)for(const y of ay)positions.push([x,y]);
  if(style==="left")positions.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  else if(style==="compact")positions.sort((a,b)=>Math.max(a[0]+v.width,a[1]+v.height)**2||a[1]-b[1]||a[0]-b[0]);
  else positions.sort((a,b)=>a[1]-b[1]||a[0]-b[0]);
  return positions.slice(0,3000);
}
function findPlacement(part,placed,cfg,style,sheetIndex){
  const edge=cfg.sheet.margin+cfg.kerf/2,gap=cfg.spacing+cfg.kerf;
  const limits={minX:edge,minY:edge,maxX:cfg.sheet.width-edge,maxY:cfg.sheet.height-edge,gap};
  let best=null,bestScore=Infinity;
  for(const v of part.variants){
    if(v.width>limits.maxX-limits.minX+EPS||v.height>limits.maxY-limits.minY+EPS)continue;
    for(const [x,y] of candidates(placed,v,limits,style)){
      const candidate=position(part,v,x,y,sheetIndex);
      if(placed.some(other=>collision(candidate,other,gap)))continue;
      const bb=candidate.bbox;
      const envelopeX=Math.max(bb.maxX,...placed.map(p=>p.bbox.maxX),0);
      const envelopeY=Math.max(bb.maxY,...placed.map(p=>p.bbox.maxY),0);
      const score=style==="left"?x*100000+y:
        style==="compact"?envelopeX*envelopeY*100+x+y:
        y*100000+x;
      if(score<bestScore-EPS){best=candidate;bestScore=score;}
      break; // First valid coordinate is best for this rotation under this ordering.
    }
  }
  return best;
}
function trial(cfg,style,order){
  const ordered=[...cfg.parts].sort((a,b)=>{
    const value=p=>order==="long"?Math.max(...p.variants.map(v=>Math.max(v.width,v.height))):
      order==="perimeter"?p.cutLength:p.area;
    return (order==="small"?value(a)-value(b):value(b)-value(a))||a.id.localeCompare(b.id);
  });
  const items=ordered.flatMap(p=>Array.from({length:p.quantity},()=>p));
  const sheets=[],unplaced=[];
  for(const part of items){
    let fit=null;
    for(let i=0;i<sheets.length;i++){
      fit=findPlacement(part,sheets[i],cfg,style,i);
      if(fit){sheets[i].push(fit);break;}
    }
    if(!fit){
      fit=findPlacement(part,[],cfg,style,sheets.length);
      if(fit)sheets.push([fit]);
      else unplaced.push(part.id);
    }
  }
  const bounds=sheets.map(ps=>{
    const maxX=Math.max(...ps.map(p=>p.bbox.maxX)),maxY=Math.max(...ps.map(p=>p.bbox.maxY));
    return round(maxX*maxY);
  });
  const area=sheets.flat().reduce((v,p)=>v+p.area,0);
  const cutLength=sheets.flat().reduce((v,p)=>v+p.cutLength,0);
  const score=unplaced.length*1e14+sheets.length*1e11+bounds.reduce((a,b)=>a+b,0);
  return {strategy:order+" / "+style,sheets,unplaced,bounds,area,cutLength,score,
    utilization:sheets.length?round(100*area/(sheets.length*cfg.sheet.width*cfg.sheet.height)):0};
}
/** Independent deterministic search variants. The lowest sheet count is always preferred. */
export function solveNest(input){
  const cfg=normalizeInput(input);
  const designs=[];
  for(const order of ["area","long","perimeter","small"])
    for(const style of ["bottom","left","compact"])designs.push(trial(cfg,style,order));
  designs.sort((a,b)=>a.score-b.score||a.strategy.localeCompare(b.strategy));
  const selected=designs[0];
  return {schema:"axiom.autonest.v1",name:"Axiom AutoNest",units:input.units==="in"?"in":"mm",
    sheet:cfg.sheet,spacing:cfg.spacing,kerf:cfg.kerf,clearance:round(cfg.spacing+cfg.kerf),
    requested:cfg.total,placed:selected.sheets.flat().length,unplaced:selected.unplaced,
    sheets:selected.sheets,materialArea:round(selected.area),cutLength:round(selected.cutLength),
    utilization:selected.utilization,strategy:selected.strategy,
    status:selected.unplaced.length?"PARTIAL":"NESTED",
    trials:designs.map(d=>({strategy:d.strategy,sheetCount:d.sheets.length,
      unplaced:d.unplaced.length,utilization:d.utilization,occupiedEnvelope:round(d.bounds.reduce((a,b)=>a+b,0))})),
    intelligence:{source:"deterministic_multi_strategy_search",trials:designs.length,
      beanConnected:false,requiresGeometryReview:true,
      note:"Evidence available for BEAN review; no live BEAN model or learned policy ran."}};
}
/** Fail-closed independent placement review, including all sheet boundary and pairwise clearances. */
export function verifyNest(result){
  if(!result||!Array.isArray(result.sheets)||!result.sheet)throw Error("Invalid nest result");
  const edge=result.sheet.margin+result.kerf/2,gap=result.spacing+result.kerf;
  const failures=[];
  result.sheets.forEach((placements,i)=>{
    placements.forEach((p,j)=>{
      const b=bbox(p.points);
      if(b.minX<edge-EPS||b.minY<edge-EPS||b.maxX>result.sheet.width-edge+EPS||
        b.maxY>result.sheet.height-edge+EPS)failures.push("Sheet "+i+" part "+j+": outside usable stock");
      for(let k=0;k<j;k++)
        if(collision({...p,bbox:b},{...placements[k],bbox:bbox(placements[k].points)},gap))
          failures.push("Sheet "+i+" parts "+k+" and "+j+": collision/insufficient clearance");
    });
  });
  return {ok:failures.length===0,failures,verifiedPlacements:result.sheets.flat().length};
}
