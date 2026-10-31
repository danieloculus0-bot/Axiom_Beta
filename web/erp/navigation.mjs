/* Axiom public ERP navigation registry.
 * Only routes with implemented, functional browser screens are listed.
 * Inspired by common ERP navigation conventions, not copied vendor UI.
 */
export const NAV_KEY="axiom_public_erp_menu_v1";

export const MENU_GROUPS=[
  {id:"workspace",label:"Workspace",items:[
    {id:"dashboard",label:"Command Center",icon:"◫",hint:"Home KPIs and quick links",keywords:["home","overview","dashboard","today","right click help","open with"]},
    {id:"qcdsm",label:"QCDSM",icon:"◉",hint:"Open Quality, Cost, Delivery, Safety or Morale directly from five equal sectors",keywords:["performance","pareto","wheel","quality","cost","delivery","safety","morale","RCA","root cause"]}
  ]},
  {id:"production",label:"Manufacturing",items:[
    {id:"jobs",label:"Work Orders",icon:"▦",hint:"Create and track fictional jobs",keywords:["job entry","job tracker","production order","work order entry","job tracking"]},
    {id:"routing",label:"Routing & Planning",icon:"☷",hint:"Job-specific operations",keywords:["engineering","methods","work centers"]},
    {id:"ewi",label:"EWI & Clocking",icon:"▤",hint:"Operator drawings and time",keywords:["shop floor","data collection","time tickets","MES"]},
    {id:"documents",label:"Drawing Control",icon:"▧",hint:"Generic document revisions",keywords:["drawing","revision","document control","engineering"]}
  ]},
  {id:"supply",label:"Supply Chain",items:[
    {id:"inventory",label:"Inventory",icon:"◈",hint:"Stock and reservations",keywords:["material","part tracker","material tracker","inventory entry","stock tracker","on hand"]},
    {id:"purchasing",label:"Purchasing",icon:"▥",hint:"Issue and receive demo POs",keywords:["purchase order","purchase order tracker","po tracker","po entry","purchase order entry","purchasing entry","receiving","procurement","suppliers"]},
    {id:"requests",label:"Request Desk",icon:"☑",hint:"Purchase and maintenance requests, assignments, follow-ups",keywords:["purchase request","requisition","purchase requisition","maintenance request","requests","follow up","assigned","overdue","request tracker"]}
  ]},
  {id:"operations",label:"Quality & Assets",items:[
    {id:"quality",label:"Quality Control",icon:"◉",hint:"Hold and release examples",keywords:["NCR","inspection","nonconformance"]},
    {id:"cost",label:"Cost",icon:"▥",hint:"Current purchasing and operation time records; cost baselines when available",keywords:["copq","cost of poor quality","costing","expenses","labor","purchasing"]},
    {id:"delivery",label:"Delivery",icon:"▤",hint:"Live work-order readiness and purchasing status",keywords:["delivery","otd","on time","readiness","due date","schedule","blocked"]},
    {id:"safety",label:"Safety",icon:"◈",hint:"Recent synthetic incidents, safety confidence and investigation signals",keywords:["incident","recordable","near miss","safety","safety confidence","workload"]},
    {id:"pm",label:"PM Tracker",icon:"⚙",hint:"Scheduled asset maintenance",keywords:["preventive maintenance","machine","asset","due date"]}
  ]},
  {id:"people",label:"People & Culture",items:[
    {id:"hr",label:"Human Resources",icon:"♙",hint:"Fictional roster, roles and training verification",keywords:["human resources","HR","people","staff","roles","organization","training matrix","employee"]},
    {id:"morale",label:"Morale & Recognition",icon:"♡",hint:"Aggregate company pulse and reviewed recognition",keywords:["morale","company pulse","workforce health","recognition","rewards","employee engagement","leadership"]},
  ]},
  {id:"oversight",label:"Analytics & Integration",items:[
    {id:"reports",label:"Report Center",icon:"▤",hint:"Real browser-local data reports",keywords:["reporting","export","job status","time","metrics"]},
    {id:"bridge",label:"ERP Emulator",icon:"⛓",hint:"Fictional external integration",keywords:["JobBOSS","simulator","integration","API"]},
    {id:"audit",label:"Event History",icon:"◷",hint:"Browser-local change history",keywords:["audit","activity","events","export"]}
  ]}
];
export const MENU_ITEMS=MENU_GROUPS.flatMap(group=>group.items.map(item=>({
 ...item,group:group.id,groupLabel:group.label,href:"#"+item.id
})));
const IDS=new Set(MENU_ITEMS.map(item=>item.id));
const uniq=list=>[...new Set(list)].filter(id=>IDS.has(id));
export function getMenuItem(id){return MENU_ITEMS.find(item=>item.id===id)||null;}
export function cleanMenuPrefs(value){
 const v=value&&typeof value==="object"&&!Array.isArray(value)?value:{};
 const favorites=uniq(Array.isArray(v.favorites)?v.favorites:[]).slice(0,20);
 const recent=uniq(Array.isArray(v.recent)?v.recent:[]).slice(0,12);
 return {favorites,recent};
}
export function toggleFavorite(prefs,id){
 if(!IDS.has(id))throw Error("Screen does not exist");
 const p=cleanMenuPrefs(prefs);
 return {...p,favorites:p.favorites.includes(id)?
   p.favorites.filter(x=>x!==id):[...p.favorites,id]};
}
export function visitMenu(prefs,id){
 if(!IDS.has(id))return cleanMenuPrefs(prefs);
 const p=cleanMenuPrefs(prefs);
 return {...p,recent:[id,...p.recent.filter(x=>x!==id)].slice(0,12)};
}
export function searchMenu(query){
 const q=String(query||"").trim().toLocaleLowerCase().replace(/\s+/g," ");
 if(!q)return MENU_ITEMS;
 const terms=q.split(" ");
 return MENU_ITEMS.map(item=>{
   const label=item.label.toLocaleLowerCase(),path=item.groupLabel.toLocaleLowerCase();
   const blob=[label,path,item.hint,...item.keywords].join(" ").toLocaleLowerCase();
   if(!terms.every(term=>blob.includes(term)))return null;
   const score=(label===q?100:0)+(label.startsWith(q)?25:0)+(label.includes(q)?8:0)+
     (path.includes(q)?4:0)+item.keywords.filter(k=>k.toLowerCase().includes(q)).length;
   return {...item,_score:score};
 }).filter(Boolean).sort((a,b)=>b._score-a._score||a.label.localeCompare(b.label));
}
