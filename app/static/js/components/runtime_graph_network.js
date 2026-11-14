import { eventBus } from "../core/event_bus.js";
(() => {
const root=document.getElementById("rf-memory-widget"),canvas=document.getElementById("rf-network-canvas");
if(!root||!canvas)return;const ctx=canvas.getContext("2d",{alpha:false});if(!ctx)return;
const $=id=>document.getElementById(id);
const S={nodes:new Map(),edges:new Map(),memory:{nodes:[],edges:[]},roles:[],tools:[],providers:{},models:{},workspace:[],extraNodes:new Map(),extraEdges:new Map(),pos:new Map(),active:new Map(),activeEdges:new Map(),events:[],selected:"",hover:"",rotation:0,raf:0,w:1,h:1,dpr:1,failed:false,running:false,disposed:false};
const C={memory:[125,184,235],agent:[126,220,255],tool:[106,185,255],provider:[126,166,220],model:[175,202,236],directory:[111,164,210],file:[147,183,219],runtime:[255,208,116]};
const token=()=>((localStorage.getItem("rf_jwt_token")||localStorage.getItem("access_token")||"").replace(/^Bearer\s+/i,""));
const pid=()=>localStorage.getItem("rf_active_project_id")||"";
function api(url){const headers={},t=token();if(t)headers.Authorization="Bearer "+t;return fetch(url,{headers,credentials:"same-origin",cache:"no-store"}).then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json();});}
function txt(id,v){const e=$(id);if(e)e.textContent=String(v||"—");}
function status(v){root.dataset.state=S.failed?"failed":S.running?"active":"idle";txt("rf-network-status-text",v);}
function log(title,detail,tone){S.events.unshift({title,detail,tone});S.events=S.events.slice(0,5);const el=$("rf-network-events");if(el){el.replaceChildren();S.events.forEach(e=>{const d=document.createElement("div");d.className="rf-network-event"+(e.tone?" is-"+e.tone:"");d.textContent=e.title+(e.detail?" · "+e.detail:"");el.append(d);});}}
function node(id,kind,label,detail,meta){if(id)S.nodes.set(String(id),{id:String(id),kind,label:String(label||id),detail:String(detail||""),meta:meta||{}});}
function edge(id,source,target,kind,detail){if(id&&S.nodes.has(source)&&S.nodes.has(target)&&source!==target)S.edges.set(String(id),{id:String(id),source,target,kind,detail});}
function tree(item,parent,out){if(!item||!item.path||out.length>=140)return;const name=String(item.name||item.path.split("/").pop());if([".git","node_modules","venv",".venv","__pycache__"].includes(name))return;const kind=item.type==="directory"||Array.isArray(item.children)?"directory":"file";out.push({id:"workspace:"+item.path,name,path:item.path,parent,kind});(item.children||[]).forEach(x=>tree(x,item.path,out));}
function compose(){
S.nodes.clear();S.edges.clear();
S.roles.forEach(r=>node("agent:"+String(r.name).toLowerCase(),"agent",r.name,"Agent role · "+(r.allowed_tools||[]).join(", "),r));
S.tools.forEach(t=>node("tool:"+t.name,"tool",t.name,t.description||"Registered tool",t));
S.roles.forEach(r=>(r.allowed_tools||[]).forEach(t=>edge("role-tool:"+r.name+":"+t,"agent:"+String(r.name).toLowerCase(),"tool:"+t,"permission","Declared role permission")));
Object.entries(S.providers).forEach(([p,ok])=>{const ms=S.models[p]||[];if(!ok&&!ms.length)return;const id="provider:"+p.toLowerCase();node(id,"provider",p,ok?"Configured provider":"Provider with selected models");ms.forEach(m=>{node("model:"+m,"model",String(m).split("/").pop(),m,{provider:p});edge("provider-model:"+p+":"+m,id,"model:"+m,"configuration","Selected model");});});
S.memory.nodes.forEach(n=>node("memory:"+n.id,"memory",n.label||n.id,"Graph node · "+(n.type||"memory")+" · usage "+(n.usage_count||0),n));
S.memory.edges.forEach(e=>edge("memory-edge:"+e.id,"memory:"+e.source,"memory:"+e.target,"memory",e.relation||"RELATED_TO"));
S.workspace.forEach(x=>{node(x.id,x.kind,x.name,x.path,x);if(x.parent)edge("workspace:"+x.path,"workspace:"+x.parent,x.id,"filesystem","Contains");});
S.extraNodes.forEach(n=>node(n.id,n.kind,n.label,n.detail,n.meta));S.extraEdges.forEach(e=>edge(e.id,e.source,e.target,e.kind,e.detail));
const arr=[...S.nodes.values()].sort((a,b)=>a.id.localeCompare(b.id));S.pos.clear();arr.forEach((n,i)=>{const y=1-2*(i+.5)/Math.max(1,arr.length),r=Math.sqrt(1-y*y),a=i*2.3999632297;S.pos.set(n.id,{x:Math.cos(a)*r,y,z:Math.sin(a)*r});});
txt("rf-network-count",S.nodes.size+" NODES · "+S.edges.size+" LINKS");schedule();
}
function project(p,cx,cy,r){const a=S.rotation,ca=Math.cos(a),sa=Math.sin(a),x=p.x*ca-p.z*sa,z=p.x*sa+p.z*ca,k=3.4/(3.4+z*.32);return{x:cx+x*r*k,y:cy-p.y*r*k,z,k};}
function draw(now){
const w=S.w,h=S.h,cx=w*.46,cy=h*.53,r=Math.min(h*.43,w*.29);ctx.fillStyle="#050912";ctx.fillRect(0,0,w,h);
const pp=new Map();S.nodes.forEach((n,id)=>pp.set(id,project(S.pos.get(id),cx,cy,r)));
S.edges.forEach(e=>{const a=pp.get(e.source),b=pp.get(e.target);if(!a||!b)return;const hot=S.active.has(e.source)||S.active.has(e.target),pulse=S.activeEdges.has(e.id);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=pulse?"rgba(255,207,111,.92)":hot?"rgba(181,216,248,.48)":"rgba(111,151,190,.13)";ctx.lineWidth=pulse?1.2:.5;ctx.stroke();if(pulse){const t=((now-S.activeEdges.get(e.id))/800)%1;ctx.beginPath();ctx.arc(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,2,0,Math.PI*2);ctx.fillStyle="#ffe5ad";ctx.shadowColor="#ffc85e";ctx.shadowBlur=9;ctx.fill();ctx.shadowBlur=0;}});
const ordered=[...S.nodes.values()].map(n=>({n,p:pp.get(n.id)})).sort((a,b)=>a.p.z-b.p.z);
ordered.forEach(({n,p})=>{const hot=S.active.has(n.id),sel=S.selected===n.id||S.hover===n.id,col=C[n.kind]||C.memory;ctx.beginPath();ctx.arc(p.x,p.y,hot?2.5:sel?2.2:1.2,0,Math.PI*2);ctx.fillStyle=hot?"#ffe2a0":"rgba("+col.join(",")+","+(0.48+Math.max(0,(p.z+1)/2)*.45)+")";if(hot||sel){ctx.shadowColor=hot?"#ffd06c":"#a8d7ff";ctx.shadowBlur=hot?14:8;}ctx.fill();ctx.shadowBlur=0;if(sel){ctx.beginPath();ctx.arc(p.x,p.y,6,0,Math.PI*2);ctx.strokeStyle="rgba(190,224,255,.7)";ctx.lineWidth=.7;ctx.stroke();}});
const deg=new Map();S.edges.forEach(e=>{deg.set(e.source,(deg.get(e.source)||0)+1);deg.set(e.target,(deg.get(e.target)||0)+1);});
const max=Math.max(0,Math.min(6,Math.floor((w-cx-r-15)/40)));
const calls=ordered.filter(v=>(deg.get(v.n.id)||0)>0).sort((a,b)=>(deg.get(b.n.id)||0)-(deg.get(a.n.id)||0)).slice(0,max);
calls.forEach((v,i)=>{const y=cy-r*.72+i*(r*1.44/Math.max(1,calls.length-1)),p=v.p,hot=S.active.has(v.n.id);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.bezierCurveTo(p.x+r*.3,p.y,p.x+r*.5,y,cx+r+9,y);ctx.strokeStyle=hot?"rgba(255,207,111,.9)":"rgba(111,157,204,.4)";ctx.lineWidth=.65;ctx.stroke();ctx.fillStyle=hot?"#ffe2a0":"rgba(163,190,219,.85)";ctx.font="7px JetBrains Mono,monospace";ctx.textAlign="left";ctx.textBaseline="middle";ctx.fillText(v.n.label.length>16?v.n.label.slice(0,15)+"…":v.n.label,cx+r+13,y);});
if(!S.nodes.size){ctx.fillStyle="#8397ae";ctx.font="9px JetBrains Mono,monospace";ctx.textAlign="center";ctx.fillText("WAITING FOR GRAPH DATA",w/2,h/2);}
}
function schedule(){if(!S.raf&&!document.hidden)S.raf=requestAnimationFrame(frame);}
function frame(t){S.raf=0;if(S.disposed||document.hidden)return;S.rotation+=.00009*Math.min(40,t-(S.last||t));S.last=t;draw(t);S.active.forEach((v,k)=>{if(t-v>1800)S.active.delete(k);});S.activeEdges.forEach((v,k)=>{if(t-v>1800)S.activeEdges.delete(k);});S.raf=requestAnimationFrame(frame);}
function resize(){const b=canvas.getBoundingClientRect();S.dpr=Math.min(devicePixelRatio||1,1.5);S.w=Math.max(1,b.width);S.h=Math.max(1,b.height);canvas.width=Math.round(S.w*S.dpr);canvas.height=Math.round(S.h*S.dpr);ctx.setTransform(S.dpr,0,0,S.dpr,0,0);schedule();}
function activate(id,tone){if(!id)return;S.active.set(id,performance.now());if(tone==="error")S.failed=true;schedule();}
function mem(item,tone){(item.active_node_ids||[]).forEach(id=>activate("memory:"+id,tone));(item.active_edge_ids||[]).forEach(id=>{const k="memory-edge:"+id;if(S.edges.has(k))S.activeEdges.set(k,performance.now());});}
function addObservedNode(id,kind,label,detail,meta){if(!id||S.nodes.has(id))return;const n={id,kind,label,detail,meta:meta||{}};S.extraNodes.set(id,n);node(id,kind,label,detail,meta);const a=[...S.nodes.values()].sort((x,y)=>x.id.localeCompare(y.id));const i=a.findIndex(x=>x.id===id),y=1-2*(i+.5)/a.length,q=Math.sqrt(1-y*y);S.pos.set(id,{x:Math.cos(i*2.3999632297)*q,y,z:Math.sin(i*2.3999632297)*q});txt("rf-network-count",S.nodes.size+" NODES · "+S.edges.size+" LINKS");}
function addObservedEdge(id,source,target,detail){if(!S.nodes.has(source)||!S.nodes.has(target)||S.edges.has(id))return;const e={id,source,target,kind:"runtime",detail};S.extraEdges.set(id,e);edge(id,source,target,"runtime",detail);txt("rf-network-count",S.nodes.size+" NODES · "+S.edges.size+" LINKS");}
function graphEvent(e){if(!e||typeof e!=="object")return;const s=String(e.status||"");if(s==="memory_graph"){const v=e.event||e;if(e.phase==="started"){S.running=true;status("MEMORY ACCESS");log("Memory retrieval",e.mode||"");}if(e.phase==="activity"){mem(v);status("MEMORY ACTIVITY");log(v.label||v.operation||"Memory operation",v.detail||"","active");}if(e.phase==="completed"){mem(v);log("Memory completed",v.detail||"");}if(e.phase==="failed"){S.failed=true;mem(v,"error");status("MEMORY FAILED");log("Memory failed",e.error||v.detail||"","error");}return;}
if(s==="phase"){S.running=true;const id="agent:"+String(e.role||"").toLowerCase();activate(id);status(e.label||"ORCHESTRATOR");log("Agent phase",e.label||e.role||"");}
else if(s==="model_try"){const p=String(e.provider||""),m=String(e.model||""),a="provider:"+p.toLowerCase(),b="model:"+m;if(p)addObservedNode(a,"provider",p,"Provider observed at runtime");addObservedNode(b,"model",m.split("/").pop(),m,{provider:p});if(p)addObservedEdge("runtime-model:"+p+":"+m,a,b,"Model selection");activate(b);status("MODEL INFERENCE");log("Model selected",m+" · "+p,"active");}
else if(s==="tool_start"){const t=String(e.tool_name||""),r=String(e.role||""),a="agent:"+r.toLowerCase(),b="tool:"+t;if(r)addObservedNode(a,"agent",r,"Agent observed at runtime");addObservedNode(b,"tool",t,"Tool observed at runtime");addObservedEdge("runtime-tool:"+a+":"+b,a,b,"Tool invocation");activate(b);status("TOOL EXECUTION");log("Tool started",t+" · "+r,"active");}
else if(s==="tool_end"){const t=String(e.tool_name||"");let bad=false;try{const r=JSON.parse(e.result||"{}");bad=Object.hasOwn(r,"exit_code")&&Number(r.exit_code)!==0;}catch(_){}if(bad){S.failed=true;activate("tool:"+t,"error");status("TOOL FAILED");log("Tool failed",t,"error");}else{status("TOOL COMPLETED");log("Tool completed",t);}}
else if(s==="reasoning"||s==="streaming"){S.running=true;status(s==="streaming"?"GENERATING":"REASONING");}
else if(s==="warning")log("Orchestrator warning",e.warning||"","warn");
else if(s==="error"||s==="failed"){S.failed=true;status("FAILED");log("Execution failed",e.error||e.message||"","error");}
else if(s==="done"){S.running=false;S.failed=false;status("IDLE");log("Execution completed","");}schedule();}
async function loadGraph(){const id=pid();if(!id){S.memory={nodes:[],edges:[]};compose();status("NO PROJECT");return;}try{const d=await api("/api/v1/memory/graph-status/"+encodeURIComponent(id));if(id!==pid())return;S.memory={nodes:d.nodes||[],edges:d.edges||[]};compose();}catch(e){log("Graph unavailable",e.message||"","error");}}
async function loadRegistry(){try{const d=await api("/api/v1/memory/runtime-registry");S.roles=d.roles||[];S.tools=d.tools||[];compose();}catch(e){log("Registry unavailable",e.message||"","error");}}
async function loadProviders(){try{const r=await Promise.all([api("/api/v1/keys/status"),api("/api/v1/keys/selected-models")]);S.providers=r[0].providers||{};S.models=r[1].selected_models||{};compose();}catch(e){log("Providers unavailable",e.message||"","error");}}
async function loadWorkspace(){const id=pid();if(!id){S.workspace=[];compose();return;}try{const d=await api("/api/v1/workspaces/tree?project_id="+encodeURIComponent(id)),out=[];if(d.tree)tree(d.tree,"",out);if(id!==pid())return;S.workspace=out;compose();}catch(_){}}
function refresh(){loadGraph();loadRegistry();loadProviders();loadWorkspace();}
function hit(x,y){const b=canvas.getBoundingClientRect(),px=x-b.left,py=y-b.top,cx=S.w*.46,cy=S.h*.53,r=Math.min(S.h*.43,S.w*.29);let best="",dist=11;S.nodes.forEach((n,id)=>{const p=project(S.pos.get(id),cx,cy,r),d=Math.hypot(px-p.x,py-p.y);if(d<dist){dist=d;best=id;}});return best;}
function collapse(v){root.classList.toggle("is-collapsed",v);const b=$("rf-memory-widget-toggle");b?.setAttribute("aria-expanded",String(!v));b?.setAttribute("aria-label",v?"Show Runtime Graph":"Hide Runtime Graph");try{localStorage.setItem("rf_runtime_graph_collapsed",v?"1":"0");}catch(_){}if(!v)resize();}
$("rf-memory-widget-toggle")?.addEventListener("click",()=>collapse(!root.classList.contains("is-collapsed")));
canvas.addEventListener("pointermove",e=>{S.hover=hit(e.clientX,e.clientY);canvas.style.cursor=S.hover?"pointer":"crosshair";});
canvas.addEventListener("click",e=>{const id=hit(e.clientX,e.clientY),n=S.nodes.get(id);if(n){S.selected=id;txt("rf-network-inspector",n.label+" · "+n.kind.toUpperCase()+" · "+n.detail);}});
eventBus.on("agent:graph_event",graphEvent);eventBus.on("generation:state",v=>{S.running=Boolean(v?.active);if(S.running)status("RUNNING");else if(!S.failed)status("IDLE");});
eventBus.on("project.activated",p=>{const id=typeof p==="string"?p:(p&&p.id)||"";if(id)localStorage.setItem("rf_active_project_id",id);else localStorage.removeItem("rf_active_project_id");S.extraNodes.clear();S.extraEdges.clear();S.active.clear();S.activeEdges.clear();S.memory={nodes:[],edges:[]};S.workspace=[];S.events=[];log("Project changed","");refresh();});
eventBus.on("auth:success",refresh);eventBus.on("workspace:changed",loadWorkspace);eventBus.on("providers.updated",loadProviders);eventBus.on("session:selected",()=>{S.running=false;S.failed=false;S.active.clear();S.activeEdges.clear();status("IDLE");});
const ro=new ResizeObserver(resize);ro.observe(canvas);document.addEventListener("visibilitychange",()=>{if(document.hidden&&S.raf){cancelAnimationFrame(S.raf);S.raf=0;}else if(!document.hidden){refresh();schedule();}});
window.addEventListener("pagehide",()=>{S.disposed=true;ro.disconnect();if(S.raf)cancelAnimationFrame(S.raf);},{once:true});
try{collapse(localStorage.getItem("rf_runtime_graph_collapsed")==="1");}catch(_){collapse(false);}resize();refresh();schedule();
})();