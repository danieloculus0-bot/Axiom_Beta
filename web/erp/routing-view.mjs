/* Editing controls for the existing Axiom routing module.
 * Existing form, panel, tag and button styles are reused.
 * Displayed work centers are synthetic labels, NOT verified machine capabilities.
 */
import {DEMO_CENTER_OPTIONS} from "./routing-edit.mjs";
const h=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
export function routingEditorHtml(job,draft,hasClockHistory){
 const state=job.routing.reviewState||"EXAMPLE SOURCE";
 const heading='<section class="panel" id="routing-editor"><div class="panel-head"><h2>Routing editor</h2>'+
    '<span class="tag">'+h(state)+'</span></div>';
 if(!draft){
  return heading+
   '<p>Edit the selected fictional job routing, operation order, work centers, source checks and instructions. Changes are saved to the same work order record used by EWI.</p>'+
   (hasClockHistory?'<div class="alert">This job already has clocking history. Edit a new fictional work order instead to preserve the original execution record.</div>':
    '<button class="action" type="button" data-action="routing-start">Edit this routing</button>')+
   (state==="REVIEW_REQUIRED"?'<div class="alert">Edited routing awaits demo review. Clocking is blocked until reviewed.</div>'+
    '<button class="action secondary" type="button" data-action="routing-review">Mark demo review complete</button>':"")+
   '<p class="small">No live BEAN analysis, drawing extraction or certified work-center availability is connected to this browser demo. Routing review is not production release.</p></section>';
 }
 let output=heading+'<p class="small">Editing is local to this browser. Reorder, add or remove steps, then save this draft for explicit review. Changes are not released by saving.</p>'+
   '<form id="routing-editor-form" data-form="routing-save">';
 draft.forEach((op,i)=>{
   const options=DEMO_CENTER_OPTIONS.map(center=>'<option value="'+h(center)+'"'+(center===op.center?" selected":"")+'>'+h(center)+'</option>').join("");
   output+='<div class="step-card" data-route-row="'+i+'">'+
     '<div class="panel-head"><h3>Operation '+(i+1)+'</h3><div class="actions">'+
     '<button type="button" class="action secondary" data-action="routing-up" data-index="'+i+'" '+(i===0?"disabled":"")+'>Move up</button>'+
     '<button type="button" class="action secondary" data-action="routing-down" data-index="'+i+'" '+(i===draft.length-1?"disabled":"")+'>Move down</button>'+
     '<button type="button" class="action danger" data-action="routing-remove" data-index="'+i+'" '+(draft.length===1?"disabled":"")+'>Remove</button>'+
     '</div></div><div class="controls">'+
     '<label>Step number<input name="step-'+i+'" maxlength="24" required value="'+h(op.step)+'"></label>'+
     '<label>Operation<input name="name-'+i+'" maxlength="120" required value="'+h(op.name)+'"></label>'+
     '<label>Work center<select name="center-'+i+'">'+options+'</select></label>'+
     '<label style="flex-basis:100%">Instructions (one per line, up to 12)<textarea name="instructions-'+i+'" rows="3" maxlength="12000" required>'+h(op.instructions.join("\n"))+'</textarea></label>'+
     '<label style="flex-basis:100%">Illustrative inspection / check<input name="check-'+i+'" maxlength="500" required value="'+h(op.check)+'"></label>'+
     '</div></div>';
 });
 output+='</form><div class="actions">'+
   '<button type="button" class="action secondary" data-action="routing-add">Add operation</button>'+
   '<button type="submit" form="routing-editor-form" class="action">Save draft for review</button>'+
   '<button type="button" class="action secondary" data-action="routing-cancel">Cancel</button>'+
   '</div><p class="small">This editor uses the EWI routing validator; duplicate step IDs, invalid fields and unrecognized fictional work centers are rejected. Edits are logged in Axiom’s local event ledger.</p></section>';
 return output;
}
export function readRoutingEditor(form){
 if(!form)return null;
 const rows=[...form.querySelectorAll("[data-route-row]")];
 return rows.map((row,i)=>({
  step:row.querySelector('[name="step-'+i+'"]').value.trim(),
  name:row.querySelector('[name="name-'+i+'"]').value.trim(),
  center:row.querySelector('[name="center-'+i+'"]').value,
  instructions:row.querySelector('[name="instructions-'+i+'"]').value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean),
  check:row.querySelector('[name="check-'+i+'"]').value.trim()
 }));
}
