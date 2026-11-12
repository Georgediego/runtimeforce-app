/**
 * RuntimeForce — SIGNAL DECK
 * A live orchestration topology built from observed entities and real relationships.
 * No spherical layout, synthetic hubs, or decorative connections.
 */
import { eventBus } from "../core/event_bus.js";

(() => {
  const host = document.getElementById("rf-rg");
  if (!host) return;
  const $ = (tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}) => {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, String(v)));
    return el;
  };
  const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
  const projectId = () => localStorage.getItem("rf_active_project_id") || "";
  const hash = (s, salt = 0) => {
    let h = (2166136261 ^ salt) >>> 0;
    for (let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}
    h^=h>>>15; h=Math.imul(h,2246822519); h^=h>>>13;
    return (h>>>0)/4294967296;
  };
  const palette = {
    memory:"#a78bfa", workspace:"#38bdf8", mode:"#fbbf24",
    role:"#fb7185", provider:"#34d399", model:"#a3e635", tool:"#f97316"
  };
  const lane = {memory:0,workspace:0,mode:1,role:1,provider:2,model:2,tool:3};
  const state = {
    nodes:new Map(), edges:new Map(), positions:new Map(), memory:{nodes:[],edges:[],totalNodes:0,totalEdges:0},
    workspace:[], selected:{}, registry:{roles:[],tools:[]}, health:{memory:"wait",workspace:"wait",models:"wait",registry:"wait"},
    activeNodes:new Set(), activeEdges:new Set(), run:false, status:"STANDBY", current:{}, events:[], hover:"",
    project:"", raf:0, collapsed:false
  };

  const header = $("header","rf-sd-head");
  const brand = $("div","rf-sd-brand");
  const emblem = $("div","rf-sd-emblem","R");
  const brandText = $("div","rf-sd-brand-text");
  brandText.append($("strong","","RUNTIME SIGNAL DECK"),$("span","","LIVE SYSTEM TOPOLOGY"));
  brand.append(emblem,brandText);
  const status = $("div","rf-sd-status");
  const statusLight = $("i","rf-sd-status-light");
  const statusText = $("b","","STANDBY");
  status.append(statusLight,statusText);
  const actions = $("div","rf-sd-actions");
  const expand = $("button","rf-sd-action","EXPAND");
  const hide = $("button","rf-sd-action","HIDE");
  actions.append(expand,hide);
  header.append(brand,status,actions);

  const stage = $("section","rf-sd-stage");
  const stageTop = $("div","rf-sd-stage-top");
  const stageLabel = $("span","","SYSTEM FLOW / OBSERVED RELATIONSHIPS");
  const stageHint = $("span","","SELECT A NODE TO INSPECT");
  stageTop.append(stageLabel,stageHint);
  const viewport = $("div","rf-sd-viewport");
  const svg = svgEl("svg",{viewBox:"0 0 1000 560",preserveAspectRatio:"xMidYMid meet","aria-label":"Live runtime topology"});
  const defs = svgEl("defs");
  const glow = svgEl("filter",{id:"rf-sd-glow",x:"-100%",y:"-100%",width:"300%",height:"300%"});
  glow.append(svgEl("feGaussianBlur",{stdDeviation:"3",result:"blur"}));
  const merge = svgEl("feMerge"); merge.append(svgEl("feMergeNode",{in:"blur"}),svgEl("feMergeNode",{in:"SourceGraphic"})); glow.append(merge);
  defs.append(glow);
  const grid = svgEl("g",{class:"rf-sd-grid"});
  const edgeLayer = svgEl("g",{class:"rf-sd-edges"});
  const pulseLayer = svgEl("g",{class:"rf-sd-pulses"});
  const nodeLayer = svgEl("g",{class:"rf-sd-nodes"});
  svg.append(defs,grid,edgeLayer,pulseLayer,nodeLayer);
  viewport.append(svg);
  stage.append(stageTop,viewport);

  const lower = $("div","rf-sd-lower");
  const metrics = $("div","rf-sd-metrics");
  const metricValues = {};
  [["OBJECTS","objects"],["LINKS","links"],["MEMORY","memory"],["ACTIVE","active"]].forEach(([label,key])=>{
    const item=$("div","rf-sd-metric"); metricValues[key]=$("strong","","0"); item.append(metricValues[key],$("span","",label)); metrics.append(item);
  });
  const inspector = $("div","rf-sd-inspector");
  inspector.append($("span","rf-sd-inspector-label","INSPECTOR"));
  const inspectorTitle = $("strong","","No node selected");
  const inspectorMeta = $("span","","Hover over a node to inspect its source");
  inspector.append(inspectorTitle,inspectorMeta);
  lower.append(metrics,inspector);

  const activity = $("section","rf-sd-activity");
  const activityHead = $("div","rf-sd-activity-head");
  activityHead.append($("b","","EVENT STREAM"),$("span","","LATEST 5"));
  const activityList = $("div","rf-sd-activity-list");
  activity.append(activityHead,activityList);
  host.replaceChildren(header,stage,lower,activity);

  const columns = [
    {x:125,title:"CONTEXT",sub:"MEMORY / WORKSPACE"},
    {x:375,title:"ORCHESTRATION",sub:"MODES / AGENTS"},
    {x:625,title:"INFERENCE",sub:"PROVIDERS / MODELS"},
    {x:875,title:"EXECUTION",sub:"TOOLS"}
  ];
  columns.forEach((c,i)=>{
    grid.append(svgEl("rect",{x:c.x-112,y:24,width:224,height:510,rx:13,class:"rf-sd-lane"}));
    grid.append(svgEl("text",{x:c.x,y:48,"text-anchor":"middle",class:"rf-sd-lane-title"})).textContent=c.title;
    grid.append(svgEl("text",{x:c.x,y:64,"text-anchor":"middle",class:"rf-sd-lane-sub"})).textContent=c.sub;
    if(i<3) grid.append(svgEl("path",{d:`M ${c.x+125} 280 l 0 0`,class:"rf-sd-lane-divider"}));
  });

  const authFetch = async url => {
    const headers={}; const jwt=token(); if(jwt) headers.Authorization="Bearer "+jwt;
    const response=await fetch(url,{headers,credentials:"same-origin",cache:"no-store"});
    if(!response.ok) throw new Error("HTTP "+response.status);
    return response.json();
  };
  function addNode(id,kind,label,detail=""){
    if(!id)return;
    state.nodes.set(id,{id,kind,label:String(label||id),detail:String(detail||"")});
  }
  function addEdge(id,a,b,kind="relation",detail=""){
    if(id&&state.nodes.has(a)&&state.nodes.has(b)&&a!==b) state.edges.set(id,{id,a,b,kind,detail});
  }
  function rebuild(){
    state.nodes.clear();state.edges.clear();
    state.registry.roles.forEach(r=>addNode("role:"+r.name.toLowerCase(),"role",r.name,(r.allowed_tools||[]).join(", ")));
    state.registry.tools.forEach(t=>addNode("tool:"+t.name,"tool",t.name,t.description));
    const select=document.getElementById("strategy-select");
    if(select) Array.from(select.options).forEach(o=>addNode("mode:"+o.value,"mode",(o.textContent||o.value).trim(),"chat mode"));
    Object.entries(state.selected).forEach(([provider,ids])=>{
      addNode("provider:"+provider.toLowerCase(),"provider",provider,"selected provider");
      (ids||[]).forEach(id=>{
        addNode("model:"+id,"model",String(id).split("/").pop(),id);
        addEdge("provides:"+provider+":"+id,"provider:"+provider.toLowerCase(),"model:"+id,"provides");
      });
    });
    state.memory.nodes.forEach(n=>addNode("mem:"+n.id,"memory",n.label||n.id,n.type||"memory node"));
    state.memory.edges.forEach(e=>addEdge("memory:"+e.id,"mem:"+e.source,"mem:"+e.target,"memory",e.relation));
    state.workspace.forEach(w=>{
      addNode("ws:"+w.path,"workspace",w.name,w.path);
      if(w.parent)addEdge("contains:"+w.path,"ws:"+w.parent,"ws:"+w.path,"workspace");
    });
    layout(); render();
  }
  function layout(){
    state.positions.clear();
    const groups=[[],[],[],[]];
    state.nodes.forEach(n=>groups[lane[n.kind]??1].push(n));
    groups.forEach((items,idx)=>{
      items.sort((a,b)=>hash(a.id,4)-hash(b.id,4));
      const x=columns[idx].x;
      const top=88,bottom=512,available=bottom-top;
      items.forEach((n,i)=>{
        const count=items.length;
        const y=count===1?280:top+(available/(count-1))*i;
        const jitter=(hash(n.id,17)-.5)*13;
        state.positions.set(n.id,{x:x+(hash(n.id,23)-.5)*72,y:y+jitter});
      });
    });
  }
  function render(){
    edgeLayer.replaceChildren();pulseLayer.replaceChildren();nodeLayer.replaceChildren();
    state.edges.forEach(edge=>{
      const a=state.positions.get(edge.a),b=state.positions.get(edge.b);if(!a||!b)return;
      const active=state.activeEdges.has(edge.id);
      const mid=(a.x+b.x)/2;
      const path=svgEl("path",{d:`M ${a.x} ${a.y} C ${mid} ${a.y}, ${mid} ${b.y}, ${b.x} ${b.y}`,class:"rf-sd-edge"+(active?" is-active":"")});
      path.dataset.edge=edge.id;edgeLayer.append(path);
      if(active&&state.run){
        const dot=svgEl("circle",{r:3.4,class:"rf-sd-packet",filter:"url(#rf-sd-glow)"});
        const motion=svgEl("animateMotion",{dur:"1.15s",repeatCount:"indefinite",rotate:"auto"});
        motion.append(svgEl("mpath",{href:"#"+(path.id="rf-edge-"+hash(edge.id).toString(16).slice(2))}));
        path.setAttribute("id",path.id);dot.append(motion);pulseLayer.append(dot);
      }
    });
    state.nodes.forEach(n=>{
      const p=state.positions.get(n.id);if(!p)return;
      const active=state.activeNodes.has(n.id)&&state.run;
      const g=svgEl("g",{class:"rf-sd-node"+(active?" is-active":"")+(state.hover===n.id?" is-hover":"")});
      g.dataset.id=n.id;
      const c=palette[n.kind]||"#9ca3af";
      g.append(svgEl("circle",{cx:p.x,cy:p.y,r:active?8:5.2,fill:c,class:"rf-sd-node-core"}));
      g.append(svgEl("circle",{cx:p.x,cy:p.y,r:active?17:10,stroke:c,class:"rf-sd-node-ring"}));
      const label=svgEl("text",{x:p.x+12,y:p.y+3.5,class:"rf-sd-node-label"});
      label.textContent=n.label.length>23?n.label.slice(0,21)+"…":n.label;
      g.append(label);
      const hit=svgEl("circle",{cx:p.x,cy:p.y,r:15,fill:"transparent",class:"rf-sd-hit"});
      g.append(hit);
      g.addEventListener("pointerenter",()=>inspect(n.id));
      g.addEventListener("pointerleave",()=>{state.hover="";stageHint.textContent="SELECT A NODE TO INSPECT";renderNodesOnly();});
      nodeLayer.append(g);
    });
    metricValues.objects.textContent=state.nodes.size;
    metricValues.links.textContent=state.edges.size;
    metricValues.memory.textContent=state.memory.totalNodes||state.memory.nodes.length;
    metricValues.active.textContent=state.activeNodes.size;
    statusText.textContent=state.run?state.status:"STANDBY";
    status.classList.toggle("is-live",state.run);
    host.classList.toggle("is-running",state.run);
    renderHealth();
  }
  function renderNodesOnly(){
    nodeLayer.querySelectorAll(".rf-sd-node").forEach(g=>{
      g.classList.toggle("is-hover",g.dataset.id===state.hover);
    });
  }
  function inspect(id){
    const n=state.nodes.get(id);if(!n)return;
    state.hover=id;stageHint.textContent="NODE / "+n.kind.toUpperCase();
    inspectorTitle.textContent=n.label;
    inspectorMeta.textContent=(n.detail||n.id)+" · "+n.kind.toUpperCase();
    renderNodesOnly();
  }
  function renderHealth(){
    const labels=Object.entries(state.health).map(([k,v])=>k.toUpperCase()+":"+v.toUpperCase()).join("  /  ");
    stageLabel.textContent="SYSTEM FLOW / "+labels;
  }
  async function loadMemory(){
    const pid=projectId();
    if(!pid){state.memory={nodes:[],edges:[],totalNodes:0,totalEdges:0};state.health.memory="off";rebuild();return;}
    try{
      const p=await authFetch("/api/v1/memory/graph-status/"+encodeURIComponent(pid));
      if(pid!==projectId())return;
      state.memory={nodes:p.nodes||[],edges:p.edges||[],totalNodes:p.total_nodes||0,totalEdges:p.total_edges||0};
      state.health.memory="ok";rebuild();
    }catch(_){state.health.memory="err";renderHealth();}
  }
  async function loadWorkspace(){
    const pid=projectId();
    if(!pid){state.workspace=[];state.health.workspace="off";rebuild();return;}
    try{
      const p=await authFetch("/api/v1/workspaces/tree?project_id="+encodeURIComponent(pid));
      if(pid!==projectId())return;
      const tree=p.tree,items=[];
      if(tree&&tree.path){
        items.push({name:tree.name||"workspace",path:tree.path,parent:""});
        (tree.children||[]).filter(x=>x&&x.path).slice(0,100).forEach(x=>{
          if([".git","node_modules","venv",".venv","__pycache__"].includes(x.name))return;
          items.push({name:x.name,path:x.path,parent:tree.path});
        });
      }
      state.workspace=items;state.health.workspace="ok";rebuild();
    }catch(_){state.health.workspace="err";renderHealth();}
  }
  async function loadModels(){
    try{const p=await authFetch("/api/v1/keys/selected-models");state.selected=p.selected_models||{};state.health.models="ok";rebuild();}
    catch(_){state.health.models="err";renderHealth();}
  }
  async function loadRegistry(){
    try{const p=await authFetch("/api/v1/memory/runtime-registry");state.registry={roles:p.roles||[],tools:p.tools||[]};state.health.registry="ok";rebuild();}
    catch(_){state.health.registry="err";renderHealth();}
  }
  function refreshAll(){loadMemory();loadWorkspace();loadModels();loadRegistry();}
  function logEvent(title,meta="",tone=""){
    state.events.unshift({time:new Date().toLocaleTimeString(),title:String(title).slice(0,70),meta:String(meta).slice(0,80),tone});
    state.events.length=Math.min(state.events.length,30);renderEvents();
  }
  function renderEvents(){
    activityList.replaceChildren();
    if(!state.events.length){activityList.append($("div","rf-sd-event-empty","Awaiting orchestration events"));return;}
    state.events.slice(0,5).forEach(e=>{
      const row=$("div","rf-sd-event"+(e.tone?" is-"+e.tone:""));
      row.append($("i","rf-sd-event-mark"),$("b","",e.title),$("span","",e.meta||e.time));
      activityList.append(row);
    });
  }
  function activateEdge(a,b,id){
    if(state.nodes.has(a)&&state.nodes.has(b)){
      state.edges.set(id,{id,a,b,kind:"runtime"});
      state.activeEdges.add(id);
    }
  }
  function onGraphEvent(ev){
    if(!ev||typeof ev!=="object"||!state.run)return;
    if(ev.status==="phase"){
      state.status=String(ev.label||"PROCESSING").toUpperCase();
      if(ev.role){
        const id="role:"+ev.role.toLowerCase();
        if(!state.nodes.has(id))addNode(id,"role",ev.role,"observed runtime role");
        state.current.role=ev.role;state.activeNodes.add(id);
      }
      logEvent("Agent phase",ev.label||ev.role||"");
    }else if(ev.status==="model_try"){
      const model=String(ev.model||"unknown"),provider=String(ev.provider||model.split("/")[0]).toLowerCase();
      const mid="model:"+model,pid="provider:"+provider;
      if(!state.nodes.has(mid))addNode(mid,"model",model.split("/").pop(),model);
      if(!state.nodes.has(pid))addNode(pid,"provider",ev.provider||provider);
      const rid=state.current.role?"role:"+state.current.role.toLowerCase():"";
      activateEdge(rid,pid,"runtime:role-provider");activateEdge(pid,mid,"runtime:provider-model");
      state.current.provider=ev.provider||provider;state.current.model=model;
      state.activeNodes.add(pid);state.activeNodes.add(mid);state.status="INFERENCE";
      layout();logEvent("Model selected",model);
    }else if(ev.status==="tool_start"){
      const id="tool:"+ev.tool_name;
      if(!state.nodes.has(id))addNode(id,"tool",ev.tool_name,"observed runtime tool");
      if(ev.role){const rid="role:"+ev.role.toLowerCase();if(!state.nodes.has(rid))addNode(rid,"role",ev.role);state.current.role=ev.role;state.activeNodes.add(rid);}
      const rid=state.current.role?"role:"+state.current.role.toLowerCase():"";
      activateEdge(rid,id,"runtime:role-tool:"+ev.tool_name);
      state.current.tool=ev.tool_name;state.activeNodes.add(id);state.status="TOOL EXECUTION";
      layout();logEvent("Tool invoked",ev.tool_name);
    }else if(ev.status==="tool_end"){
      state.current.tool="";state.status="RETURNING";logEvent("Tool completed",ev.tool_name||"");
    }else if(ev.status==="memory_graph"){
      state.status="MEMORY ACCESS";
      const item=ev.event||ev;
      (item.active_node_ids||[]).forEach(id=>{const key="mem:"+id;if(state.nodes.has(key))state.activeNodes.add(key);});
      (item.active_edge_ids||[]).forEach(id=>{const key="memory:"+id;if(state.edges.has(key))state.activeEdges.add(key);});
      if(ev.phase==="completed"){logEvent("Memory graph traversed");loadMemory();}
    }else if(ev.status==="reasoning"||ev.status==="streaming"){
      state.status=ev.status==="streaming"?"GENERATING":"REASONING";
      if(ev.status==="streaming")logEvent("Response streaming");
    }else if(ev.status==="warning")logEvent("Warning",ev.warning||"","warn");
    else if(ev.status==="error"||ev.status==="failed"){state.status="FAILED";logEvent("Execution failed",ev.error||"","err");}
    else if(ev.status==="done"||ev.status==="aborted"){finish(ev.status);return;}
    render();
  }
  function start(){
    state.run=true;state.status="INITIALIZING";state.current={};state.activeNodes.clear();state.activeEdges.clear();
    const mode=document.getElementById("strategy-select")?.value||"";
    state.current.mode=mode;if(mode)state.activeNodes.add("mode:"+mode);
    logEvent("Orchestration started",mode);render();
  }
  function finish(result="completed"){
    state.run=false;state.status=result.toUpperCase();state.activeNodes.clear();state.activeEdges.clear();
    logEvent("Run "+result);render();
  }
  function setCollapsed(value){
    state.collapsed=value;host.classList.toggle("is-collapsed",value);
    hide.textContent=value?"SHOW":"HIDE";
    try{localStorage.setItem("rf_runtime_graph_collapsed",value?"1":"0");}catch(_){}
  }
  hide.addEventListener("click",()=>setCollapsed(!state.collapsed));
  expand.addEventListener("click",()=>{
    const overlay=$("div","rf-sd-overlay"),panel=$("section","rf-sd-expanded");
    const close=$("button","rf-sd-action","CLOSE");close.addEventListener("click",()=>overlay.remove());
    const clone=svg.cloneNode(true);panel.append($("div","rf-sd-expanded-title","RUNTIME SIGNAL DECK"),close,clone);
    overlay.append(panel);document.body.append(overlay);
  });
  eventBus.on("generation:state",s=>{if(s?.active&&!state.run)start();else if(!s?.active&&state.run)finish("aborted");});
  eventBus.on("agent:graph_event",onGraphEvent);
  eventBus.on("project.activated",project=>{
    const id=typeof project==="string"?project:(project&&project.id)||"";
    if(id)localStorage.setItem("rf_active_project_id",id);else localStorage.removeItem("rf_active_project_id");
    state.project=id;state.run=false;state.current={};state.activeNodes.clear();state.activeEdges.clear();state.events=[];
    state.memory={nodes:[],edges:[],totalNodes:0,totalEdges:0};state.workspace=[];state.selected={};state.registry={roles:[],tools:[]};
    renderEvents();refreshAll();
  });
  eventBus.on("auth:success",refreshAll);
  eventBus.on("session:deleted",loadMemory);
  document.getElementById("strategy-select")?.addEventListener("change",()=>{
    if(!state.run)state.current.mode=document.getElementById("strategy-select").value;
  });
  try{state.collapsed=localStorage.getItem("rf_runtime_graph_collapsed")==="1";}catch(_){}
  setCollapsed(state.collapsed);renderEvents();refreshAll();
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refreshAll();});
  window.addEventListener("resize",()=>{if(!state.collapsed)render();});
  setInterval(()=>{if(!document.hidden&&!state.run&&!state.collapsed)refreshAll();},30000);
})();
