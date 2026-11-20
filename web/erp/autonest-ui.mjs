import {solveNest,verifyNest} from "./autonest-engine.mjs";
import {importDxfPart,exportDxfSheet} from "./autonest-dxf.mjs";
const $=id=>document.getElementById(id);
const safe=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const sample=[
  {id:"SYN-U-BRACKET",quantity:1,outline:[[0,0],[14,0],[14,12],[10,12],[10,4],[4,4],[4,12],[0,12]]},
  {id:"SYN-BASE",quantity:2,outline:[[0,0],[12,0],[12,5],[0,5]],holes:[[[2,2],[3,2],[3,3],[2,3]]]},
  {id:"SYN-ANGLE",quantity:2,outline:[[0,0],[9,0],[9,3],[3,3],[3,9],[0,9]]},
  {id:"SYN-BAR",quantity:1,outline:[[0,0],[3,0],[3,7],[0,7]]}
];
let result=null,review=null;
const setStatus=(s,error=false)=>{$("status").className="status"+(error?" error":"");$("status").textContent=s;};
const readNumber=id=>Number($(id).value);
const loadSample=()=>{$("parts").value=JSON.stringify(sample,null,2);};
loadSample();
function download(name,content,type="application/octet-stream"){
  const url=URL.createObjectURL(new Blob([content],{type}));
  const a=document.createElement("a");
  a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
}
function svgPath(points){return "M"+points.map(p=>p[0].toFixed(5)+","+p[1].toFixed(5)).join("L")+"Z";}
function drawing(sheet,placements){
  const outlines=placements.map((p,i)=>{
    const hue=(i*67+82)%360;
    const path=[svgPath(p.points),...p.holes.map(svgPath)].join(" ");
    return '<path class="part" d="'+path+'" fill="hsl('+hue+',65%,65%)" fill-rule="evenodd"><title>'+
      safe(p.id)+" · "+p.angle+"°</title></path>";
  }).join("");
  return '<svg viewBox="0 0 '+sheet.width+" "+sheet.height+'" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Verified nesting layout">' +
    '<g transform="translate(0 '+sheet.height+') scale(1 -1)">'+
    '<rect class="stock" x="0" y="0" width="'+sheet.width+'" height="'+sheet.height+'"></rect>'+
    outlines+'</g></svg>';
}
function render(data){
  const checked=verifyNest(data);
  review=checked;
  const stats=[
    ["Sheets",data.sheets.length],["Placed",data.placed+" / "+data.requested],
    ["Material yield",data.utilization+"%"],["Cut perimeter",data.cutLength.toFixed(2)+" "+data.units],
    ["Geometry check",checked.ok?"PASS":"FAIL"],["Unplaced",data.unplaced.length]
  ];
  $("results").innerHTML='<div class="stats" style="margin-top:14px">'+
    stats.map(([k,v])=>'<div class="stat"><small>'+safe(k)+'</small><strong>'+safe(v)+'</strong></div>').join("")+'</div>'+
    data.sheets.map((parts,i)=>{
      return '<div class="sheet"><div class="sheet-title"><strong>Sheet '+(i+1)+' · '+parts.length+' parts</strong>'+
        '<button type="button" class="secondary" data-export="'+i+'" '+(!checked.ok?'disabled':'')+
        '>Export sheet DXF</button></div>'+drawing(data.sheet,parts)+
        '<div class="legend">'+parts.map(p=>safe(p.id)+" ("+p.angle+"°)").join(" · ")+'</div></div>';
    }).join("")+
    '<div class="actions"><button class="secondary" type="button" id="download-evidence">Export BEAN review evidence</button></div>';
  $("results").querySelectorAll("[data-export]").forEach(b=>b.addEventListener("click",()=>{
    const i=Number(b.dataset.export);
    download("Axiom_AutoNest_Sheet_"+(i+1)+".dxf",exportDxfSheet(data,i),"application/dxf");
  }));
  $("download-evidence").addEventListener("click",()=>{
    const evidence={
      schema:"axiom.autonest.review.v1",
      title:"Axiom AutoNest candidate review",
      input:JSON.parse($("parts").value),
      sheet:data.sheet,units:data.units,spacing:data.spacing,kerf:data.kerf,
      geometryReview:checked,status:data.status,
      placed:data.placed,unplaced:data.unplaced,
      sheetCount:data.sheets.length,materialUtilizationPercent:data.utilization,
      selectedStrategy:data.strategy,alternatives:data.trials,
      intelligentOptimizer:data.intelligence,
      note:"Solver-generated evidence only. This file is not a BEAN Core model inference or production-cut approval."
    };
    download("Axiom_AutoNest_BEAN_Review.json",JSON.stringify(evidence,null,2),"application/json");
  });
  const rows=data.trials.map(t=>'<tr><td>'+safe(t.strategy)+'</td><td>'+t.sheetCount+'</td><td>'+t.unplaced+'</td><td>'+t.utilization+'%</td></tr>').join("");
  $("evidence").innerHTML='<p><strong>Selected:</strong> '+safe(data.strategy)+
    '. <strong>Geometry verification:</strong> '+(checked.ok?"PASS":"FAIL")+
    '. <strong>BEAN live connection:</strong> not connected.</p>'+
    '<details><summary>Review all '+data.trials.length+' search outcomes</summary><table><thead><tr><th>Strategy</th><th>Sheets</th><th>Unplaced</th><th>Yield</th></tr></thead><tbody>'+rows+'</tbody></table></details>'+
    (checked.failures.length?'<p>'+safe(checked.failures.join("; "))+'</p>':"");
  setStatus(!checked.ok?"Geometry failed verification. DXF export disabled.":
    data.unplaced.length?"Partial nest. "+data.unplaced.length+" pieces could not be placed; review the sheet and part sizes.":
    "Verified. "+data.placed+" pieces nested on "+data.sheets.length+" sheet(s).",!checked.ok);
}
$("sample").addEventListener("click",()=>{
  loadSample();result=null;review=null;$("results").innerHTML="";
  setStatus("Synthetic example restored. Run AutoNest to recompute.");
});
$("upload-dxf").addEventListener("change",async event=>{
  const files=[...event.target.files];
  if(!files.length)return;
  try{
    const parts=[];
    const tol=readNumber("arc-tol");
    for(const [i,file] of files.entries()){
      const id=file.name.replace(/\.dxf$/i,"").toUpperCase().replace(/[^\w.-]/g,"_").slice(0,54)+"-"+(i+1);
      parts.push(importDxfPart(await file.text(),{id,quantity:1,arcTolerance:tol}));
    }
    $("parts").value=JSON.stringify(parts,null,2);
    setStatus(parts.length+" DXF part(s) imported with closed geometry. Adjust quantities and generate a nest.");
  }catch(error){setStatus("DXF import rejected: "+error.message,true);}
});
$("nest").addEventListener("click",()=>{
  const button=$("nest");button.disabled=true;
  try{
    const input={
      units:$("units").value,
      sheet:{width:readNumber("sheet-width"),height:readNumber("sheet-height"),margin:readNumber("margin")},
      spacing:readNumber("spacing"),kerf:readNumber("kerf"),
      parts:JSON.parse($("parts").value)
    };
    result=solveNest(input);
    render(result);
  }catch(error){
    setStatus("Nesting rejected: "+error.message,true);
    $("results").innerHTML="";
  }finally{button.disabled=false;}
});
