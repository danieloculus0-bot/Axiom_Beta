/* Record-only contextual navigation for Axiom's fictional Pages demo.
 * Based on the existing local SuperForge Open with behavior, no backend.
 * Native right-click remains intact on inputs, links and selected text.
 */
import {resolveContext,contextActions} from "./context-actions.mjs";

export function installContextMenu({getState,onNavigate}){
 const root=document.createElement("div");
 root.id="axiom-record-menu";
 root.className="record-menu";
 root.setAttribute("role","menu");
 root.setAttribute("aria-label","Open record with Axiom module");
 root.hidden=true;
 document.body.append(root);
 let opener=null;
 function close({restore=false}={}){
  if(root.hidden)return;
  root.hidden=true;root.replaceChildren();
  if(restore)opener?.focus?.({preventScroll:true});
  opener=null;
 }
 const add=(parent,tag,className,text)=>{
  const el=document.createElement(tag);
  if(className)el.className=className;
  if(text!==undefined)el.textContent=text;
  parent.append(el);return el;
 };
 function openFor(target,coordinates){
  const {ctxType:type,ctxId:id}=target.dataset;
  const state=getState();
  const record=resolveContext(state,type,id);
  const actions=contextActions(state,type,id);
  if(!record||!actions.length)return false;
  close();
  opener=target;
  const title=add(root,"div","record-menu-heading",record.label);
  title.title="Invented example record";
  const note=add(root,"div","record-menu-subtitle","OPEN WITH · SYNTHETIC RECORD");
  note.setAttribute("aria-hidden","true");
  const search=actions.length>5?add(root,"input","record-menu-search"):null;
  if(search){
   search.type="search";search.placeholder="Find an action...";
   search.setAttribute("aria-label","Search record actions");
   search.autocomplete="off";
  }
  const suggested=add(root,"div","record-menu-section");
  const others=add(root,"details","record-menu-more");
  const summary=add(others,"summary","","More workspaces ("+actions.filter(a=>!a.suggested).length+")");
  const more=add(others,"div","record-menu-section");
  const rows=[];
  for(const action of actions){
   const parent=action.suggested?suggested:more;
   const btn=add(parent,"button","record-menu-action");
   btn.type="button";btn.setAttribute("role","menuitem");
   add(btn,"span","record-menu-action-label",action.label);
   const symbol=add(btn,"span","record-menu-action-suffix","↗");
   symbol.setAttribute("aria-hidden","true");
   btn.addEventListener("click",()=>{
    if(!contextActions(getState(),type,id).some(x=>x.id===action.id)){close();return;}
    close();onNavigate({type,id},action);
   });
   rows.push({btn,action});
  }
  if(!rows.some(x=>!x.action.suggested))others.hidden=true;
  if(search){
   search.addEventListener("input",()=>{
    const terms=search.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    for(const {btn,action} of rows){
     btn.hidden=terms.some(term=>!action.label.toLocaleLowerCase().includes(term));
    }
    others.open=terms.length>0;
    const suggestedVisible=rows.some(({btn,action})=>action.suggested&&!btn.hidden);
    const otherVisible=rows.some(({btn,action})=>!action.suggested&&!btn.hidden);
    suggested.hidden=!suggestedVisible;others.hidden=!otherVisible;
    empty.hidden=suggestedVisible||otherVisible;
   });
  }
  const empty=add(root,"p","record-menu-empty","No matching actions.");
  empty.hidden=true;
  const footer=add(root,"div","record-menu-footer","Esc closes · Shift+right-click for browser menu");
  footer.setAttribute("aria-hidden","true");
  root.hidden=false;
  const rect=root.getBoundingClientRect();
  const x=Math.max(8,Math.min(coordinates.x,window.innerWidth-rect.width-8));
  const y=Math.max(8,Math.min(coordinates.y,window.innerHeight-rect.height-8));
  root.style.left=x+"px";root.style.top=y+"px";
  if(coordinates.keyboard)(search||rows[0]?.btn)?.focus({preventScroll:true});
  return true;
 }
 const preserve='a,button,input,textarea,select,[contenteditable],[role="textbox"],[data-context-native]';
 document.addEventListener("contextmenu",e=>{
  if(e.shiftKey||e.target.closest(preserve)||String(window.getSelection?.()?.toString()||"").trim())return;
  const target=e.target.closest("[data-ctx-type][data-ctx-id]");
  if(!target||!openFor(target,{x:e.clientX,y:e.clientY,keyboard:false}))return;
  e.preventDefault();
 });
 document.addEventListener("keydown",e=>{
  if(e.key==="Escape"&&!root.hidden){e.preventDefault();close({restore:true});return;}
  if(e.key!=="ContextMenu"&&!(e.shiftKey&&e.key==="F10"))return;
  if(e.target.closest(preserve))return;
  const target=e.target.closest("[data-ctx-type][data-ctx-id]");
  if(!target)return;
  const rect=target.getBoundingClientRect();
  if(openFor(target,{x:rect.left+14,y:rect.top+18,keyboard:true}))e.preventDefault();
 });
 document.addEventListener("pointerdown",e=>{if(!root.hidden&&!root.contains(e.target))close();});
 document.addEventListener("scroll",event=>{if(!root.contains(event.target))close();},true);
 window.addEventListener("resize",()=>close());
 window.addEventListener("hashchange",()=>close());
 root.addEventListener("keydown",e=>{
  if(!["ArrowDown","ArrowUp"].includes(e.key))return;
  const options=[...root.querySelectorAll(".record-menu-action:not([hidden])")].
    filter(btn=>!btn.closest("details")||btn.closest("details").open);
  if(!options.length)return;
  e.preventDefault();
  const idx=options.indexOf(document.activeElement),step=e.key==="ArrowDown"?1:-1;
  options[(idx+step+options.length)%options.length].focus();
 });
 return {close,root};
}
