import {
 NAV_KEY,MENU_GROUPS,MENU_ITEMS,getMenuItem,cleanMenuPrefs,
 toggleFavorite,visitMenu,searchMenu
} from "./navigation.mjs";

/* No external dependencies; stays within Axiom's existing palette/layout. */
export function installMenu({root,search,tabs,launch,getCurrent,onNavigate=()=>{}}){
 let mode="menu",prefs=cleanMenuPrefs(null),query="";
 const openGroups=new Set(["workspace","production"]);
 try{prefs=cleanMenuPrefs(JSON.parse(localStorage.getItem(NAV_KEY)||"{}"));}catch{}
 const el=(tag,cls,text)=>{
  const item=document.createElement(tag);
  if(cls)item.className=cls;
  if(text!==undefined)item.textContent=text;
  return item;
 };
 function persist(){
  try{localStorage.setItem(NAV_KEY,JSON.stringify(prefs));}catch{}
 }
 function addRow(item){
  const row=el("div","menu-entry");
  const anchor=el("a","menu-entry-link");
  anchor.href=item.href;
  anchor.dataset.nav=item.id;
  anchor.title=item.hint;
  anchor.append(el("span","menu-glyph",item.icon));
  const words=el("span","menu-entry-words");
  words.append(el("span","menu-entry-name",item.label));
  if(mode!=="menu"||query)words.append(el("small","menu-entry-path",item.groupLabel+" / "+item.hint));
  anchor.append(words);
  if(getCurrent()===item.id){
   anchor.classList.add("active");
   anchor.setAttribute("aria-current","page");
  }
  anchor.addEventListener("click",()=>{
   prefs=visitMenu(prefs,item.id);
   persist();
   if(query){query="";search.value="";}
   onNavigate(item.id);
   render();
  });
  const star=el("button","menu-star"+(prefs.favorites.includes(item.id)?" is-favorite":""),prefs.favorites.includes(item.id)?"★":"☆");
  star.type="button";
  star.setAttribute("aria-label",(prefs.favorites.includes(item.id)?"Remove ":"Add ")+item.label+
    (prefs.favorites.includes(item.id)?" from favorites":" to favorites"));
  star.setAttribute("aria-pressed",String(prefs.favorites.includes(item.id)));
  star.title=prefs.favorites.includes(item.id)?"Remove from favorites":"Save as favorite";
  star.addEventListener("click",()=>{
   prefs=toggleFavorite(prefs,item.id);persist();render();
  });
  row.append(anchor,star);
  return row;
 }
 function groupView(group,items){
  const details=el("details","menu-group");
  const shouldOpen=!!query||openGroups.has(group.id)||items.some(x=>x.id===getCurrent());
  details.open=shouldOpen;
  const summary=el("summary","menu-group-heading",group.label);
  const count=el("span","menu-group-count",String(items.length));
  summary.append(count);
  const children=el("div","menu-group-items");
  items.forEach(item=>children.append(addRow(item)));
  details.append(summary,children);
  details.addEventListener("toggle",()=>{
   if(query)return;
   if(details.open)openGroups.add(group.id);
   else openGroups.delete(group.id);
  });
  return details;
 }
 function render(){
  root.replaceChildren();
  tabs.querySelectorAll("[data-menu-tab]").forEach(btn=>{
   const active=btn.dataset.menuTab===mode;
   btn.classList.toggle("selected",active);
   btn.setAttribute("aria-selected",String(active));
   btn.tabIndex=0;
  });
  let shown=[];
  const q=query.trim();
  if(q){
   shown=searchMenu(q);
   const heading=el("div","menu-result-heading",shown.length+" matching screen"+(shown.length===1?"":"s"));
   root.append(heading);
   shown.forEach(item=>root.append(addRow(item)));
  }else if(mode==="menu"){
   MENU_GROUPS.forEach(group=>root.append(groupView(group,group.items.map(item=>getMenuItem(item.id)))));
   shown=MENU_ITEMS;
  }else{
   const ids=mode==="favorites"?prefs.favorites:prefs.recent;
   shown=ids.map(getMenuItem).filter(Boolean);
   if(!shown.length){
    root.append(el("p","menu-emptystate",mode==="favorites"?
      "Star a screen to keep it here.":"Open a screen to build your recent list."));
   }else shown.forEach(item=>root.append(addRow(item)));
  }
  root.setAttribute("data-menu-mode",q?"search":mode);
 }
 tabs.addEventListener("keydown",event=>{
  if(!["ArrowLeft","ArrowRight"].includes(event.key))return;
  const buttons=[...tabs.querySelectorAll("[data-menu-tab]")];
  const index=buttons.indexOf(document.activeElement);
  if(index<0)return;
  event.preventDefault();
  const next=buttons[(index+(event.key==="ArrowRight"?1:-1)+buttons.length)%buttons.length];
  mode=next.dataset.menuTab;query="";search.value="";next.focus();render();
 });
 tabs.addEventListener("click",event=>{
  const btn=event.target.closest("[data-menu-tab]");
  if(!btn)return;
  mode=btn.dataset.menuTab;
  query="";search.value="";
  render();
 });
 search.addEventListener("input",()=>{
  query=search.value;render();
 });
 search.addEventListener("keydown",event=>{
  if(event.key==="Enter"){
   const first=searchMenu(query)[0];
   if(!query.trim()||!first)return;
   event.preventDefault();
   location.hash=first.href;
   prefs=visitMenu(prefs,first.id);persist();
   query="";search.value="";
   onNavigate(first.id);
   render();
  }
  if(event.key==="Escape"){
   search.value="";query="";
   search.blur();render();
  }
 });
 launch.addEventListener("click",()=>{
  search.focus();search.select();search.scrollIntoView({block:"nearest"});
 });
 document.addEventListener("keydown",event=>{
  const node=event.target,typing=node?.matches?.("input,textarea,select,[contenteditable='true']");
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){
   event.preventDefault();search.focus();search.select();
  }else if(event.key==="/"&&!typing&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
   event.preventDefault();search.focus();search.select();
  }
 });
 function markActive(id){
  const found=getMenuItem(id);
  if(found){prefs=visitMenu(prefs,id);persist();}
  if(found&&!openGroups.has(found.group))openGroups.add(found.group);
  render();
 }
 prefs=visitMenu(prefs,getCurrent());persist();
 render();
 return {markActive,getPrefs:()=>cleanMenuPrefs(prefs)};
}
