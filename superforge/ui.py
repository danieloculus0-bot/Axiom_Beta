from __future__ import annotations

from flask import render_template_string
from .context_menu import MODULES
from .db import db

def preference():
    with db() as con:
        row=con.execute("SELECT * FROM user_preferences WHERE user_key='local'").fetchone()
    if not row:
        return {"theme_mode":"dark","accent":"#1F6FBC","compact_mode":0}
    return dict(row)

def page(title:str,body:str,*,module_key:str="",context_type:str="",context_id:str="")->str:
    pref=preference()
    nav="".join(
        f"<a class='nav-item {'active' if key==module_key else ''}' href='{path}'>{label}</a>"
        for key,label,path in MODULES if key not in {"audit"}
    )
    css=r"""
:root{--accent:ACCENT;--bg:#090B0E;--panel:#11161C;--panel2:#171E26;--line:#28313C;--text:#F4F7FB;--muted:#9BA8B7;--shadow:0 16px 45px rgba(0,0,0,.24)}
html[data-mode="light"]{--bg:#F4F6F8;--panel:#FFFFFF;--panel2:#F8FAFC;--line:#D8DEE7;--text:#121820;--muted:#5C6978;--shadow:0 14px 36px rgba(30,40,55,.10)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
a{color:inherit}.app{min-height:100vh;display:grid;grid-template-columns:245px 1fr}.sidebar{background:var(--panel);border-right:1px solid var(--line);position:sticky;top:0;height:100vh;overflow:auto;padding:18px 12px}
.brand{font-weight:900;font-size:22px;letter-spacing:-.5px;padding:6px 10px 16px}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:1.7px;text-transform:uppercase;margin-top:4px}
.nav-item{display:block;text-decoration:none;padding:9px 11px;border-radius:9px;color:var(--muted);margin:2px 0;font-weight:650}.nav-item:hover,.nav-item.active{background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--text)}.nav-item.active{box-shadow:inset 3px 0 0 var(--accent)}
.main{min-width:0}.topbar{height:58px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;padding:0 22px;background:color-mix(in srgb,var(--panel) 94%,transparent);position:sticky;top:0;z-index:20;backdrop-filter:blur(12px)}
.topbar .grow{flex:1}.crumb{font-weight:800}.hint{color:var(--muted);font-size:12px}.content{padding:22px;max-width:1600px;margin:auto}.page-head{display:flex;align-items:flex-start;gap:18px;margin-bottom:18px}.page-head .grow{flex:1}.eyebrow{font-size:11px;letter-spacing:1.4px;text-transform:uppercase;color:var(--muted);font-weight:800;margin:0 0 6px}h1,h2,h3{margin-top:0}h1{font-size:29px;letter-spacing:-.7px;margin-bottom:6px}h2{font-size:19px}.sub{color:var(--muted);max-width:900px;line-height:1.55}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:16px;box-shadow:var(--shadow)}.card strong.big{font-size:28px;display:block;margin-bottom:4px}.card .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.7px}
.panel{margin:0 0 14px}.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}.button,button{border:0;background:var(--accent);color:white;padding:9px 13px;border-radius:8px;font-weight:800;text-decoration:none;cursor:pointer}.button.secondary,button.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--line)}.button:hover,button:hover{filter:brightness(1.08)}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.6px;text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}tr.sf-context:hover td{background:color-mix(in srgb,var(--accent) 6%,transparent);cursor:context-menu}
.badge{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:3px 8px;font-size:11px;font-weight:800;background:var(--panel2)}.badge.accent{border-color:color-mix(in srgb,var(--accent) 55%,var(--line));color:var(--text);background:color-mix(in srgb,var(--accent) 16%,var(--panel2))}
input,select,textarea{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:9px 10px;min-height:38px;width:100%}textarea{min-height:96px}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.wide{grid-column:1/-1}label{font-weight:750;font-size:12px;color:var(--muted)}label input,label select,label textarea{display:block;margin-top:5px}
.empty{padding:35px;text-align:center;color:var(--muted)}.statline{display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:var(--muted)}code{background:var(--panel2);padding:2px 5px;border-radius:5px}
.ctx{position:fixed;z-index:9999;min-width:270px;background:var(--panel);border:1px solid var(--line);box-shadow:0 18px 60px rgba(0,0,0,.42);border-radius:11px;padding:7px;display:none}.ctx.open{display:block}.ctx-head{padding:7px 9px;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.8px}.ctx a{display:flex;justify-content:space-between;text-decoration:none;padding:9px 10px;border-radius:7px}.ctx a:hover{background:color-mix(in srgb,var(--accent) 16%,transparent)}.ctx hr{border:0;border-top:1px solid var(--line);margin:5px 0}.ctx .group{padding:5px 9px;font-weight:900}.ctx .small{font-size:11px;color:var(--muted)}
@media(max-width:900px){.app{grid-template-columns:1fr}.sidebar{display:none}.content{padding:14px}.form-grid{grid-template-columns:1fr}.topbar{padding:0 14px}}
""".replace("ACCENT",pref["accent"])
    js=r"""
const menu=document.getElementById('sf-context-menu');
function closeMenu(){menu.classList.remove('open')}
document.addEventListener('click',closeMenu);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu()});
document.addEventListener('contextmenu',async e=>{
  e.preventDefault(); closeMenu();
  const target=e.target.closest('.sf-context');
  const type=target?.dataset.entityType||'';
  const id=target?.dataset.entityId||'';
  const label=target?.dataset.entityLabel||'SuperForge';
  const current=document.body.dataset.module||'';
  const q=new URLSearchParams({entity_type:type,entity_id:id,current_module:current});
  try{
    const res=await fetch('/api/context-menu?'+q.toString());
    const data=await res.json();
    let html='<div class="ctx-head">'+escapeHtml(label)+'</div>';
    if(type&&id){
      html+='<a href="/context/'+encodeURIComponent(type)+'/'+encodeURIComponent(id)+'"><b>Open record</b><span>↵</span></a><hr>';
    }
    html+='<div class="group">Open with</div>';
    html+=data.items.map(x=>'<a href="'+x.href+'"><span>'+escapeHtml(x.label)+'</span><span class="small">'+(x.current?'current':'')+'</span></a>').join('');
    menu.innerHTML=html;
    const w=290,h=Math.min(620,60+data.items.length*38);
    menu.style.left=Math.min(e.clientX,window.innerWidth-w-8)+'px';
    menu.style.top=Math.min(e.clientY,window.innerHeight-h-8)+'px';
    menu.classList.add('open');
  }catch(err){console.error(err)}
});
function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
"""
    return render_template_string("""<!doctype html>
<html data-mode="{{ mode }}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title><style>{{ css|safe }}</style></head>
<body data-module="{{ module_key }}" class="sf-context" data-entity-type="{{ context_type }}" data-entity-id="{{ context_id }}" data-entity-label="{{ title }}">
<div class="app"><aside class="sidebar"><div class="brand">SuperForge<small>Unified Manufacturing OS</small></div>{{ nav|safe }}
<hr style="border:0;border-top:1px solid var(--line);margin:12px 7px">
<a class="nav-item" href="/logic">Logic Map</a><a class="nav-item" href="/audit">Audit Trail</a><a class="nav-item" href="/appearance">Appearance</a>
</aside><main class="main"><div class="topbar"><div class="crumb">{{ title }}</div><div class="grow"></div><div class="hint">Right-click anything</div></div>
<div class="content">{{ body|safe }}</div></main></div><div id="sf-context-menu" class="ctx"></div><script>{{ js|safe }}</script></body></html>""",
        title=title,body=body,css=css,js=js,nav=nav,mode=pref["theme_mode"],module_key=module_key,context_type=context_type,context_id=context_id)
