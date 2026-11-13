import * as THREE from "https://esm.sh/three@0.160.0";
import { OrbitControls } from "https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js";
import { eventBus } from "../core/event_bus.js";

(() => {
  const root = document.getElementById("rf-memory-widget");
  const viewport = document.getElementById("rf-astrolabe-viewport");
  if (!root || !viewport) return;
  const $ = id => document.getElementById(id);
  const state = {
    scene:null,camera:null,renderer:null,controls:null,observer:null,raf:0,dirty:true,disposed:false,lastFrame:0,
    orbitRoot:null,edgeRoot:null,pulseRoot:null,core:null,coreGlow:null,
    nodes:new Map(),edges:new Map(),meshes:new Map(),rings:new Map(),edgeObjects:new Map(),pulses:[],rotations:[],beam:null,
    memory:{nodes:[],edges:[]},registry:{roles:[],tools:[]},providers:{},models:{},workspace:[],
    observedNodes:new Map(),observedEdges:new Map(),activeNodes:new Set(),activeEdges:new Set(),
    current:{model:"",provider:"",agent:"",tool:"",mode:""},status:"IDLE",running:false,failed:false,
    hovered:"",selected:""
  };
  const ORBITS={
    agents:{radius:0.92,tilt:0.12,color:0x4dffad},
    systems:{radius:1.55,tilt:-0.34,color:0x25d79a},
    memory:{radius:2.22,tilt:0.48,color:0x168b68}
  };
  const COLORS={agent:0x9cffbd,tool:0x52f5bd,provider:0x27d99b,model:0xa4ff87,memory:0x38d9a0,workspace:0x5ac9b0,directory:0x4cae92,file:0x6ad9c2,core:0x8dffc1};

  const token=()=>((localStorage.getItem("rf_jwt_token")||localStorage.getItem("access_token")||"").replace(/^Bearer\s+/i,""));
  const projectId=()=>localStorage.getItem("rf_active_project_id")||"";
  function api(url){const headers={};const jwt=token();if(jwt)headers.Authorization="Bearer "+jwt;return fetch(url,{headers,credentials:"same-origin",cache:"no-store"}).then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.json();});}
  function txt(id,value){const el=$(id);if(el)el.textContent=String(value||"—");}
  function status(value){state.status=String(value||"IDLE").toUpperCase();txt("rf-astrolabe-status",state.status);root.dataset.state=state.failed?"failed":state.running?"active":"idle";}
  function hud(){txt("rf-astrolabe-model",state.current.model);txt("rf-astrolabe-provider",state.current.provider);txt("rf-astrolabe-agent",state.current.agent);txt("rf-astrolabe-tool",state.current.tool);txt("rf-astrolabe-mode",state.current.mode);status(state.status);}
  function log(title,detail,tone){
    const feed=$("rf-astrolabe-events");if(!feed)return;
    const row=document.createElement("div");row.className="rf-astrolabe-event"+(tone?" is-"+tone:"");
    const dot=document.createElement("i"),copy=document.createElement("span"),b=document.createElement("b"),small=document.createElement("small"),time=document.createElement("time");
    b.textContent=String(title||"Runtime event");small.textContent=String(detail||"");copy.append(b,small);time.textContent=new Date().toLocaleTimeString();row.append(dot,copy,time);feed.prepend(row);
    while(feed.children.length>4)feed.lastElementChild.remove();
  }
  function addNode(id,kind,label,detail,orbit,meta){if(id)state.nodes.set(String(id),{id:String(id),kind:kind||"memory",label:String(label||id),detail:String(detail||""),orbit:orbit||"memory",meta:meta||{}});}
  function addEdge(id,source,target,kind,detail){if(id&&state.nodes.has(source)&&state.nodes.has(target)&&source!==target)state.edges.set(String(id),{id:String(id),source,target,kind:kind||"relation",detail:String(detail||"")});}
  function walkTree(item,parent,out,limit){
    if(!item||!item.path||out.length>=limit)return;
    const name=String(item.name||item.path.split("/").pop()||"workspace");
    if([".git","node_modules","venv",".venv","__pycache__"].includes(name))return;
    const kind=item.type==="directory"||Array.isArray(item.children)?"directory":"file";
    out.push({id:"workspace:"+item.path,name,path:item.path,parent,kind});
    (item.children||[]).forEach(child=>walkTree(child,item.path,out,limit));
  }
  function composeData(){
    state.nodes.clear();state.edges.clear();
    addNode("core:orchestrator","core","Orchestrator","RuntimeForce orchestration core","core",{});
    state.registry.roles.forEach(role=>{
      const id="agent:"+String(role.name).toLowerCase();
      addNode(id,"agent",role.name,"Agent role · "+(role.allowed_tools||[]).join(", "),"agents",role);
    });
    state.registry.tools.forEach(tool=>addNode("tool:"+tool.name,"tool",tool.name,tool.description||"Registered tool","systems",tool));
    state.registry.roles.forEach(role=>(role.allowed_tools||[]).forEach(name=>addEdge("role-tool:"+role.name+":"+name,"agent:"+String(role.name).toLowerCase(),"tool:"+name,"permission","Declared role permission")));
    Object.entries(state.providers).forEach(([provider,configured])=>{
      const models=state.models[provider]||[];
      if(!configured&&!models.length)return;
      const pid="provider:"+provider.toLowerCase();
      addNode(pid,"provider",provider,configured?"Configured provider key":"Provider with selected models","systems",{configured:Boolean(configured),modelCount:models.length});
      models.forEach(model=>{
        const mid="model:"+model;addNode(mid,"model",String(model).split("/").pop(),String(model),"systems",{provider});
        addEdge("provider-model:"+provider.toLowerCase()+":"+model,pid,mid,"configuration","Selected model");
      });
    });
    state.memory.nodes.forEach(n=>addNode("memory:"+n.id,"memory",n.label||n.id,"SQLite graph node · "+(n.type||"memory")+" · usage "+(n.usage_count||0),"memory",n));
    state.memory.edges.forEach(e=>addEdge("memory-edge:"+e.id,"memory:"+e.source,"memory:"+e.target,"memory",e.relation||"RELATED_TO"));
    state.workspace.forEach(item=>{
      addNode(item.id,item.kind,item.name,item.path,"memory",item);
      if(item.parent)addEdge("workspace-edge:"+item.path,"workspace:"+item.parent,item.id,"filesystem","Contains");
    });
    state.observedNodes.forEach(n=>addNode(n.id,n.kind,n.label,n.detail,n.orbit,n.meta));
    state.observedEdges.forEach(e=>addEdge(e.id,e.source,e.target,e.kind,e.detail));
    buildSceneGraph();hud();
  }
  function disposeObject(object){
    object.traverse(child=>{
      if(child.geometry)child.geometry.dispose();
      if(child.material){const list=Array.isArray(child.material)?child.material:[child.material];list.forEach(m=>{if(m.map)m.map.dispose();m.dispose();});}
    });
  }
  function clearGroup(group){while(group.children.length){const child=group.children[0];group.remove(child);disposeObject(child);}}
  function labelTexture(text){
    const c=document.createElement("canvas");c.width=512;c.height=96;const x=c.getContext("2d");
    x.fillStyle="rgba(2,16,11,.9)";x.strokeStyle="rgba(73,255,172,.7)";x.lineWidth=3;x.beginPath();x.roundRect(3,3,506,90,18);x.fill();x.stroke();
    x.font="600 30px Inter,sans-serif";x.fillStyle="#caffdf";x.textAlign="center";x.textBaseline="middle";x.fillText(String(text).slice(0,30),256,48);
    const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t;
  }
  function geometry(kind){
    if(kind==="agent")return new THREE.OctahedronGeometry(.105,0);
    if(kind==="tool")return new THREE.BoxGeometry(.15,.15,.15);
    if(kind==="provider")return new THREE.DodecahedronGeometry(.11,0);
    if(kind==="model")return new THREE.IcosahedronGeometry(.09,0);
    if(kind==="directory")return new THREE.BoxGeometry(.13,.13,.13);
    if(kind==="file")return new THREE.TetrahedronGeometry(.095,0);
    return new THREE.IcosahedronGeometry(.09,0);
  }
  function buildSceneGraph(){
    if(!state.orbitRoot)return;
    state.rings.forEach(r=>clearGroup(r.group));state.rings.clear();clearGroup(state.edgeRoot);clearGroup(state.pulseRoot);
    state.meshes.clear();state.edgeObjects.clear();state.pulses=[];state.beam=null;state.rotations=[];
    Object.entries(ORBITS).forEach(([key,cfg])=>{
      const group=new THREE.Group();group.rotation.x=cfg.tilt;state.orbitRoot.add(group);
      const torus=new THREE.Mesh(new THREE.TorusGeometry(cfg.radius,.006,4,128),new THREE.MeshBasicMaterial({color:cfg.color,transparent:true,opacity:.34}));
      torus.rotation.x=Math.PI/2;group.add(torus);state.rings.set(key,{group,radius:cfg.radius,nodes:[],config:cfg});
    });
    const core=new THREE.Group();
    const shell=new THREE.Mesh(new THREE.IcosahedronGeometry(.24,1),new THREE.MeshBasicMaterial({color:0x65ffae,transparent:true,opacity:.88,wireframe:true}));
    shell.userData.nodeId="core:orchestrator";core.add(shell);
    const inner=new THREE.Mesh(new THREE.SphereGeometry(.105,16,12),new THREE.MeshBasicMaterial({color:0xc5ffdc,transparent:true,opacity:.95}));
    inner.userData.nodeId="core:orchestrator";core.add(inner);
    const halo=new THREE.Mesh(new THREE.TorusGeometry(.34,.008,4,64),new THREE.MeshBasicMaterial({color:0x2bff9b,transparent:true,opacity:.55}));
    halo.rotation.x=Math.PI/2.4;core.add(halo);
    if(state.core){state.scene.remove(state.core);disposeObject(state.core);}state.core=core;state.coreGlow=inner;state.scene.add(core);
    const groups={agents:[],systems:[],memory:[]};
    state.nodes.forEach(n=>{if(groups[n.orbit])groups[n.orbit].push(n);});
    Object.entries(groups).forEach(([orbit,nodes])=>{
      const ring=state.rings.get(orbit);nodes.sort((a,b)=>a.kind.localeCompare(b.kind)||a.label.localeCompare(b.label));
      nodes.forEach((n,i)=>{
        const angle=2*Math.PI*i/Math.max(1,nodes.length)-Math.PI/2,pos=new THREE.Vector3(Math.cos(angle)*ring.radius,0,Math.sin(angle)*ring.radius);
        const group=new THREE.Group();group.position.copy(pos);group.userData={nodeId:n.id,angle,orbit};
        const color=COLORS[n.kind]||0x42e8a4;
        const body=new THREE.Mesh(geometry(n.kind),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.9}));body.userData.nodeId=n.id;group.add(body);
        const aura=new THREE.Mesh(new THREE.SphereGeometry(.17,8,6),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.12,wireframe:true}));group.add(aura);
        const label=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture(n.label),transparent:true,depthWrite:false,opacity:0}));
        label.scale.set(.82,.155,1);label.position.y=.19;label.visible=false;group.add(label);
        group.userData.body=body;group.userData.label=label;ring.group.add(group);ring.nodes.push(group);state.meshes.set(n.id,group);
      });
    });
    state.meshes.set("core:orchestrator",state.core);
    updateEdges();schedule();
  }
  function worldPos(id){const mesh=state.meshes.get(id);if(!mesh)return null;state.scene.updateMatrixWorld(true);return mesh.getWorldPosition(new THREE.Vector3());}
  function makeCurve(aId,bId){
    const a=worldPos(aId),b=worldPos(bId);if(!a||!b)return null;
    const mid=a.clone().add(b).multiplyScalar(.5);mid.add(mid.clone().normalize().multiplyScalar(.18));
    return new THREE.QuadraticBezierCurve3(a,mid,b);
  }
  function updateEdges(){
    clearGroup(state.edgeRoot);state.edgeObjects.clear();
    state.edges.forEach(edge=>{
      const curve=makeCurve(edge.source,edge.target);if(!curve)return;
      const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(18)),new THREE.LineBasicMaterial({
        color:edge.kind==="memory"?0x32c98d:0x277f61,transparent:true,opacity:edge.kind==="memory"?.42:.3
      }));
      line.userData.edgeId=edge.id;state.edgeRoot.add(line);state.edgeObjects.set(edge.id,{line,curve,edge});
    });
    schedule();
  }
  function refreshEdgePositions(){
    state.edgeObjects.forEach(item=>{
      const curve=makeCurve(item.edge.source,item.edge.target);
      if(!curve)return;
      item.curve=curve;
      state.pulses.forEach(pulse=>{if(pulse.edgeId===item.edge.id)pulse.curve=curve;});
      const points=curve.getPoints(18);
      item.line.geometry.dispose();
      item.line.geometry=new THREE.BufferGeometry().setFromPoints(points);
    });
  }
  function schedule(){state.dirty=true;if(!state.raf&&!state.disposed&&!document.hidden)state.raf=requestAnimationFrame(frame);}
  function hasMotion(){return state.rotations.length>0||state.pulses.length>0||Boolean(state.beam);}
  function frame(now){
    state.raf=0;if(state.disposed||!state.renderer)return;
    if(state.lastFrame&&now-state.lastFrame<30){schedule();return;}
    state.lastFrame=now;let moving=false;
    state.rotations=state.rotations.filter(r=>{
      const t=Math.min(1,(now-r.started)/r.duration),e=t*t*(3-2*t);r.ring.group.rotation.y=r.from+r.delta*e;
      if(t<1){moving=true;return true;}r.ring.group.rotation.y=r.to;return false;
    });
    if(moving)refreshEdgePositions();
    state.pulses=state.pulses.filter(p=>{
      const t=Math.min(1,(now-p.started)/p.duration);p.mesh.position.copy(p.curve.getPoint(t));p.mesh.material.opacity=t>.72?Math.max(0,(1-t)/.28):1;
      if(t<1){moving=true;return true;}state.pulseRoot.remove(p.mesh);disposeObject(p.mesh);
      if(p.edgeId){state.activeEdges.delete(p.edgeId);const edge=state.edgeObjects.get(p.edgeId);if(edge){edge.line.material.color.setHex(0x277f61);edge.line.material.opacity=.3;}}return false;
    });
    if(state.beam){
      const b=state.beam,target=worldPos(b.targetId);
      if(target){const mid=target.clone().multiplyScalar(.5);mid.y+=.22;b.curve.v1.copy(mid);b.curve.v2.copy(target);b.line.geometry.dispose();b.line.geometry=new THREE.BufferGeometry().setFromPoints(b.curve.getPoints(22));}
      const t=Math.min(1,(now-b.started)/b.duration);b.mesh.position.copy(b.curve.getPoint(t));b.mesh.material.opacity=t>.75?Math.max(0,(1-t)/.25):1;
      if(t>=1){state.pulseRoot.remove(b.mesh);disposeObject(b.mesh);state.edgeRoot.remove(b.line);disposeObject(b.line);state.beam=null;}else moving=true;}
    if(state.coreGlow&&state.running){state.coreGlow.scale.setScalar(.92+Math.sin(now*.009)*.08);moving=true;}
    const controlsChanged=state.controls?state.controls.update():false;
    if(state.dirty||moving||controlsChanged){state.renderer.render(state.scene,state.camera);state.dirty=false;}
    if(moving||controlsChanged||hasMotion())schedule();
  }
  function align(id){
    const mesh=state.meshes.get(id);if(!mesh||!mesh.userData.orbit)return;
    const ring=state.rings.get(mesh.userData.orbit);if(!ring)return;
    const from=ring.group.rotation.y,raw=mesh.userData.angle-from,delta=Math.atan2(Math.sin(raw),Math.cos(raw));
    state.rotations=state.rotations.filter(r=>r.ring!==ring);state.rotations.push({ring,from,delta,to:from+delta,started:performance.now(),duration:900});schedule();
  }
  function pulse(curve,edgeId,tone){
    if(!curve)return;const color=tone==="error"?0xff665b:0x9affc2;
    const mesh=new THREE.Mesh(new THREE.SphereGeometry(.035,8,6),new THREE.MeshBasicMaterial({color,transparent:true,opacity:1}));
    state.pulseRoot.add(mesh);state.pulses.push({mesh,curve,edgeId:edgeId||"",started:performance.now(),duration:1000});
    if(edgeId){state.activeEdges.add(edgeId);const e=state.edgeObjects.get(edgeId);if(e){e.line.material.color.setHex(color);e.line.material.opacity=0.95;}}
    schedule();
  }
  function beam(id,tone){
    const target=worldPos(id);if(!target)return;
    if(state.beam){state.pulseRoot.remove(state.beam.mesh);disposeObject(state.beam.mesh);state.edgeRoot.remove(state.beam.line);disposeObject(state.beam.line);}
    const start=new THREE.Vector3(),mid=target.clone().multiplyScalar(.5);mid.y+=.22;
    const curve=new THREE.QuadraticBezierCurve3(start,mid,target),color=tone==="error"?0xff665b:0x69ffad;
    const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(22)),new THREE.LineBasicMaterial({color,transparent:true,opacity:.8}));
    state.edgeRoot.add(line);
    const mesh=new THREE.Mesh(new THREE.SphereGeometry(.05,8,6),new THREE.MeshBasicMaterial({color,transparent:true,opacity:1}));state.pulseRoot.add(mesh);
    state.beam={curve,line,mesh,targetId:id,started:performance.now(),duration:1050};schedule();
  }
  function activity(id,tone){
    if(!state.meshes.has(id))return;state.activeNodes.add(id);const mesh=state.meshes.get(id),body=mesh.userData.body||mesh.children.find(c=>c.isMesh);
    if(body&&body.material){body.material.color.setHex(tone==="error"?0xff665b:0xbaffd2);body.material.opacity=1;}
    align(id);beam(id,tone);schedule();
  }
  function complete(ids){
    (ids||[]).forEach(id=>state.activeNodes.delete(id));state.failed=false;
    state.meshes.forEach((mesh,id)=>{if(state.activeNodes.has(id))return;const n=state.nodes.get(id),body=mesh.userData.body||mesh.children.find(c=>c.isMesh);if(n&&body&&body.material){body.material.color.setHex(COLORS[n.kind]||0x42e8a4);body.material.opacity=.9;}});
    if(!state.running)status("IDLE");schedule();
  }
  function inspect(id){
    const n=state.nodes.get(id);if(!n)return;state.selected=id;
    const links=Array.from(state.edges.values()).filter(e=>e.source===id||e.target===id).length;
    txt("rf-astrolabe-inspector-title",n.label);txt("rf-astrolabe-inspector-kind",n.kind.toUpperCase());
    txt("rf-astrolabe-inspector-detail",n.detail);txt("rf-astrolabe-inspector-links",links+" real relationships");
    state.meshes.forEach((m,key)=>{if(m.userData.label)m.userData.label.visible=key===state.selected||key===state.hovered;});schedule();
  }
  function pick(event){
    const rect=state.renderer.domElement.getBoundingClientRect(),p=new THREE.Vector2(((event.clientX-rect.left)/rect.width)*2-1,-((event.clientY-rect.top)/rect.height)*2+1);
    const ray=new THREE.Raycaster();ray.setFromCamera(p,state.camera);const objects=[];
    state.meshes.forEach(m=>m.traverse(o=>{if(o.isMesh)objects.push(o);}));
    const hit=ray.intersectObjects(objects,false).find(h=>h.object.userData.nodeId);return hit?hit.object.userData.nodeId:"";
  }
  function pointerMove(e){
    const id=pick(e);if(id===state.hovered)return;state.hovered=id;state.renderer.domElement.style.cursor=id?"pointer":"grab";
    if(id)inspect(id);else state.meshes.forEach((m,key)=>{if(m.userData.label)m.userData.label.visible=key===state.selected;});
    schedule();
  }
  function observedNode(id,kind,label,detail,orbit,meta){
    if(!id||state.nodes.has(id))return;
    const n={id,kind,label,detail,orbit,meta:meta||{}};state.observedNodes.set(id,n);addNode(id,kind,label,detail,orbit,meta);buildSceneGraph();
  }
  function observedEdge(id,source,target,detail){
    if(!source||!target||!state.nodes.has(source)||!state.nodes.has(target)||state.edges.has(id))return;
    const e={id,source,target,kind:"runtime",detail:detail||"Observed runtime invocation"};state.observedEdges.set(id,e);addEdge(id,source,target,e.kind,e.detail);updateEdges();
  }
  function memoryActivity(item,tone){
    const ids=(item.active_node_ids||[]).map(id=>"memory:"+id),edgeIds=(item.active_edge_ids||[]).map(id=>"memory-edge:"+id);
    ids.forEach(id=>activity(id,tone));
    edgeIds.forEach(id=>{const e=state.edges.get(id);if(e)pulse(makeCurve(e.source,e.target),id,tone);});
    if(ids.length&&!edgeIds.length)beam(ids[0],tone);return ids;
  }
  function onGraphEvent(event){
    if(!event||typeof event!=="object")return;const s=String(event.status||"");
    if(s==="memory_graph"){
      const item=event.event||event;
      if(event.phase==="started"){state.running=true;status("MEMORY ACCESS");log("Memory retrieval started",event.mode||state.current.mode);}
      if(event.phase==="activity"){memoryActivity(item);status("MEMORY ACTIVITY");log(item.label||item.operation||"Memory operation",item.detail||"","active");}
      if(event.phase==="completed"){const ids=memoryActivity(item);log(item.label||"Memory operation completed",item.detail||"");window.setTimeout(()=>complete(ids),850);}
      if(event.phase==="failed"){state.failed=true;status("MEMORY FAILED");const ids=memoryActivity(item,"error");log("Memory operation failed",event.error||item.detail||"","error");window.setTimeout(()=>complete(ids),1700);}
      hud();return;
    }
    if(s==="phase"){
      state.running=true;if(event.role)state.current.agent=String(event.role);status(event.label||"ORCHESTRATOR");
      const id="agent:"+String(event.role||"").toLowerCase();if(event.role&&state.meshes.has(id))activity(id);
      log("Orchestrator phase",event.label||event.role||""); 
    }else if(s==="model_try"){
      state.current.model=String(event.model||"");state.current.provider=String(event.provider||"");state.current.agent=String(event.role||state.current.agent||"");
      const pid="provider:"+state.current.provider.toLowerCase(),mid="model:"+state.current.model;
      if(state.current.provider)observedNode(pid,"provider",state.current.provider,"Provider observed during model selection","systems",{observed:true});
      observedNode(mid,"model",state.current.model.split("/").pop(),state.current.model,"systems",{provider:state.current.provider,observed:true});
      if(state.current.provider)observedEdge("runtime-model:"+state.current.provider+":"+state.current.model,pid,mid,"Live model selection");
      activity(mid);status("MODEL INFERENCE");log("Model selected",state.current.model+" · "+state.current.provider,"active");
    }else if(s==="tool_start"){
      state.current.tool=String(event.tool_name||"");state.current.agent=String(event.role||state.current.agent||"");
      const tid="tool:"+state.current.tool,aid="agent:"+state.current.agent.toLowerCase();
      observedNode(aid,"agent",state.current.agent,"Agent observed in live execution","agents",{observed:true});
      observedNode(tid,"tool",state.current.tool,"Tool observed in live execution","systems",{observed:true});
      observedEdge("runtime-tool:"+aid+":"+tid,aid,tid,"Live tool invocation");
      activity(tid);status("TOOL EXECUTION");log("Tool started",state.current.tool+" · "+state.current.agent,"active");
    }else if(s==="tool_end"){
      const name=String(event.tool_name||state.current.tool||"");let failed=false;
      try{const result=JSON.parse(event.result||"{}");failed=Object.prototype.hasOwnProperty.call(result,"exit_code")&&Number(result.exit_code)!==0;}catch(_){}
      if(failed){state.failed=true;status("TOOL FAILED");activity("tool:"+name,"error");log("Tool failed",name,"error");}
      else{log("Tool completed",name);complete(["tool:"+name]);status("TOOL COMPLETED");}
      state.current.tool="";
    }else if(s==="reasoning"||s==="streaming"){state.running=true;status(s==="streaming"?"GENERATING":"REASONING");}
    else if(s==="warning"){log("Orchestrator warning",event.warning||"","warn");}
    else if(s==="error"||s==="failed"){
      state.failed=true;status("FAILED");const ids=Array.from(state.activeNodes);ids.forEach(id=>activity(id,"error"));log("Execution failed",event.error||event.message||"","error");window.setTimeout(()=>complete(ids),1800);
    }else if(s==="done"){
      state.running=false;state.current.tool="";const ids=Array.from(state.activeNodes);log("Execution completed",state.current.model||"Orchestrator");window.setTimeout(()=>complete(ids),700);
    }
    hud();
  }
  async function loadGraph(){
    const pid=projectId();if(!pid){state.memory={nodes:[],edges:[]};composeData();status("NO PROJECT");return;}
    try{const d=await api("/api/v1/memory/graph-status/"+encodeURIComponent(pid));if(pid!==projectId())return;state.memory={nodes:d.nodes||[],edges:d.edges||[]};composeData();}
    catch(e){log("Graph data unavailable",e.message||"Request failed","warn");}
  }
  async function loadRegistry(){try{const d=await api("/api/v1/memory/runtime-registry");state.registry={roles:d.roles||[],tools:d.tools||[]};composeData();}catch(e){log("Runtime registry unavailable",e.message||"Request failed","warn");}}
  async function loadProviders(){try{const r=await Promise.all([api("/api/v1/keys/status"),api("/api/v1/keys/selected-models")]);state.providers=r[0].providers||{};state.models=r[1].selected_models||{};composeData();}catch(e){log("Provider data unavailable",e.message||"Request failed","warn");}}
  async function loadWorkspace(){
    const pid=projectId();if(!pid){state.workspace=[];composeData();return;}
    try{const d=await api("/api/v1/workspaces/tree?project_id="+encodeURIComponent(pid));if(pid!==projectId())return;const out=[];if(d.tree)walkTree(d.tree,"",out,160);state.workspace=out;composeData();}catch(_){}
  }
  function refresh(){loadGraph();loadRegistry();loadProviders();loadWorkspace();const select=$("strategy-select");if(select)state.current.mode=select.options[select.selectedIndex]?.textContent.trim()||select.value;hud();}
  function resize(){if(!state.renderer||!state.camera)return;const w=Math.max(1,viewport.clientWidth),h=Math.max(1,viewport.clientHeight);state.camera.aspect=w/h;state.camera.updateProjectionMatrix();state.renderer.setSize(w,h,false);schedule();}
  function resetCamera(){if(!state.camera||!state.controls)return;state.camera.position.set(4.4,3,5);state.controls.target.set(0,0,0);state.controls.update();schedule();}
  function init(){
    state.scene=new THREE.Scene();state.camera=new THREE.PerspectiveCamera(38,1,.1,100);state.camera.position.set(4.4,3,5);
    try{state.renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:"low-power"});}
    catch(e){status("WEBGL UNAVAILABLE");log("3D rendering unavailable",e.message||"WebGL unsupported","error");return;}
    state.renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.35));state.renderer.setClearColor(0x020b08,0);viewport.replaceChildren(state.renderer.domElement);state.renderer.domElement.className="rf-astrolabe-canvas";
    state.controls=new OrbitControls(state.camera,state.renderer.domElement);state.controls.enableDamping=true;state.controls.dampingFactor=.08;state.controls.enablePan=false;state.controls.minDistance=3.1;state.controls.maxDistance=8.5;state.controls.addEventListener("change",schedule);
    state.orbitRoot=new THREE.Group();state.edgeRoot=new THREE.Group();state.pulseRoot=new THREE.Group();state.scene.add(state.orbitRoot,state.edgeRoot,state.pulseRoot);
    state.observer=new ResizeObserver(resize);state.observer.observe(viewport);state.renderer.domElement.addEventListener("pointermove",pointerMove);state.renderer.domElement.addEventListener("click",e=>{const id=pick(e);if(id)inspect(id);});resize();
  }
  function dispose(){state.disposed=true;if(state.raf)cancelAnimationFrame(state.raf);state.observer?.disconnect();state.controls?.dispose();if(state.scene)clearGroup(state.scene);state.renderer?.dispose();state.renderer?.forceContextLoss?.();}
  function collapse(value){
    root.classList.toggle("is-collapsed",value);const btn=$("rf-memory-widget-toggle");
    if(btn){btn.setAttribute("aria-expanded",String(!value));btn.setAttribute("aria-label",value?"Show Runtime Graph":"Hide Runtime Graph");}
    try{localStorage.setItem("rf_runtime_graph_collapsed",value?"1":"0");}catch(_){}
    if(!value)resize();
  }
  $("rf-memory-widget-toggle")?.addEventListener("click",()=>collapse(!root.classList.contains("is-collapsed")));
  $("rf-astrolabe-reset")?.addEventListener("click",resetCamera);
  eventBus.on("agent:graph_event",onGraphEvent);
  eventBus.on("generation:state",v=>{state.running=Boolean(v?.active);if(state.running)status("RUNNING");else if(!state.failed)status("IDLE");hud();schedule();});
  eventBus.on("project.activated",p=>{
    const id=typeof p==="string"?p:(p&&p.id)||"";if(id)localStorage.setItem("rf_active_project_id",id);else localStorage.removeItem("rf_active_project_id");
    state.observedNodes.clear();state.observedEdges.clear();state.activeNodes.clear();state.current={model:"",provider:"",agent:"",tool:"",mode:state.current.mode};
    state.memory={nodes:[],edges:[]};state.workspace=[];const feed=$("rf-astrolabe-events");if(feed)feed.replaceChildren();refresh();
  });
  eventBus.on("auth:success",refresh);eventBus.on("workspace:changed",loadWorkspace);eventBus.on("providers.updated",loadProviders);
  eventBus.on("session:selected",()=>{state.running=false;state.activeNodes.clear();state.current.tool="";status("IDLE");schedule();});
  $("strategy-select")?.addEventListener("change",e=>{state.current.mode=e.target.options[e.target.selectedIndex]?.textContent.trim()||e.target.value;hud();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden){if(state.raf)cancelAnimationFrame(state.raf);state.raf=0;}else{refresh();schedule();}});
  window.addEventListener("pagehide",dispose,{once:true});
  init();try{collapse(localStorage.getItem("rf_runtime_graph_collapsed")==="1");}catch(_){collapse(false);}refresh();schedule();
})();