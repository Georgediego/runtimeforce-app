import * as THREE from "https://esm.sh/three@0.160.0";
import { OrbitControls } from "https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js";
import { eventBus } from "../core/event_bus.js";

(() => {
  const root = document.getElementById("rf-memory-widget");
  const viewport = document.getElementById("rf-cube-viewport");
  if (!root || !viewport) return;

  const $ = id => document.getElementById(id);
  const statusEl = $("rf-memory-widget-status");
  const countEl = $("rf-memory-widget-count");
  const edgeCountEl = $("rf-memory-widget-edges");
  const feedEl = $("rf-memory-activity");
  const toggle = $("rf-memory-widget-toggle");
  const collapsedKey = "rf_memory_graph_collapsed";
  const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
  const projectId = () => localStorage.getItem("rf_active_project_id") || "";
  const palette = { memory: 0x39f5a0 };
  const state = {
    nodes: new Map(), edges: new Map(), cells: [], memory: {nodes: [], edges: []},
    registry: {roles: [], tools: []}, selected: {}, workspace: [],
    activeNodes: new Set(), activeEdges: new Set(), failedNodes: new Set(), events: [],
    current: {model: "", provider: "", agent: "", tool: "", mode: ""},
    status: "IDLE", running: false, failed: false, project: "",
    side: 2, cubeSize: 0.78, spacing: 0.9, selectedNode: "",
    rotationQueue: [], rotation: null, lastTurn: new Map(),
    pulses: new Map(), dirty: true, lastRender: 0, raf: 0,
    renderer: null, scene: null, camera: null, controls: null,
    cubeRoot: null, edgeRoot: null, raycaster: new THREE.Raycaster(),
    pointer: new THREE.Vector2(), resizeObserver: null, disposed: false
  };

  function setStatus(value) {
    state.status = String(value || "IDLE").toUpperCase();
    if (statusEl) statusEl.textContent = state.status;
    root.dataset.state = state.failed ? "failed" : (state.running ? "active" : "idle");
  }

  function addLog(title, detail, tone) {
    if (!feedEl) return;
    const empty = feedEl.querySelector(".rf-memory-activity-empty");
    if (empty) empty.remove();
    const row = document.createElement("div");
    row.className = "rf-memory-activity-row" + (tone ? " is-" + tone : "");
    const dot = document.createElement("span");
    dot.className = "rf-memory-activity-pulse";
    const copy = document.createElement("div");
    copy.className = "rf-memory-activity-copy";
    const label = document.createElement("b");
    label.textContent = String(title || "Orchestrator event");
    const meta = document.createElement("small");
    meta.textContent = String(detail || "");
    copy.append(label, meta);
    const time = document.createElement("time");
    time.textContent = new Date().toLocaleTimeString();
    row.append(dot, copy, time);
    feedEl.prepend(row);
    while (feedEl.children.length > 5) feedEl.lastElementChild.remove();
  }

  function authFetch(url) {
    const headers = {};
    const jwt = token();
    if (jwt) headers.Authorization = "Bearer " + jwt;
    return fetch(url, {headers, credentials: "same-origin", cache: "no-store"}).then(response => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  function addNode(id, kind, label, detail, source) {
    if (!id) return;
    state.nodes.set(id, {
      id: String(id), kind: String(kind || "memory"),
      label: String(label || id), detail: String(detail || ""),
      source: source || "runtime"
    });
  }

  function addEdge(id, source, target, kind, detail) {
    if (!id || !state.nodes.has(source) || !state.nodes.has(target) || source === target) return;
    state.edges.set(String(id), {
      id: String(id), source, target, kind: kind || "relationship",
      detail: String(detail || "")
    });
  }

  function rebuildData() {
    state.nodes.clear();
    state.edges.clear();

    // Graph topology comes exclusively from persisted SQLite graph data.
    state.memory.nodes.forEach(node => {
      addNode("mem:" + node.id, "memory", node.label || node.id,
        "SQLite graph node · " + node.id, "graph_nodes");
    });
    state.memory.edges.forEach(edge => {
      addEdge("memory:" + edge.id, "mem:" + edge.source, "mem:" + edge.target,
        "memory", edge.relation || "RELATED_TO");
    });

    buildCube();
    updateHud();
  }

  function clearGroup(group) {
    while (group.children.length) {
      const child = group.children[0];
      group.remove(child);
      child.traverse(object => {
        if (object.geometry) object.geometry.dispose();
        if (object.material) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => {
            if (material.map) material.map.dispose();
            material.dispose();
          });
        }
      });
    }
  }

  function makeCell(node, coord) {
    const group = new THREE.Group();
    group.position.copy(coord);
    group.userData.nodeId = node.id;
    const point = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 16, 16),
      new THREE.MeshPhongMaterial({color: 0x39f5a0, emissive: 0x0b6b3d, emissiveIntensity: 0.35, shininess: 110})
    );
    point.userData.nodeId = node.id;
    group.add(point);
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(0.085, 12, 12),
      new THREE.MeshBasicMaterial({color: 0x39f5a0, transparent: true, opacity: 0.10, depthWrite: false})
    );
    halo.userData.nodeId = node.id;
    group.add(halo);
    group.userData.point = point;
    group.userData.halo = halo;
    return group;
  }

  function buildCube() {
    if (!state.cubeRoot) return;
    if (state.rotation) {
      state.rotation.members.forEach(cell => state.cubeRoot.attach(cell));
      state.cubeRoot.remove(state.rotation.pivot);
      state.rotation = null;
    }
    state.rotationQueue.length = 0;
    clearGroup(state.cubeRoot);
    state.cells = [];
    state.pulses.forEach(pulse => {
      state.scene.remove(pulse.mesh);
      pulse.mesh.geometry.dispose();
      pulse.mesh.material.dispose();
    });
    state.pulses.clear();

    // Fibonacci sphere: every point represents one real persisted graph node.
    const nodes = Array.from(state.nodes.values());
    const radius = 1.55;
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    nodes.forEach((node, index) => {
      const y = nodes.length <= 1 ? 0 : 1 - (2 * index) / (nodes.length - 1);
      const ring = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = goldenAngle * index;
      const coord = new THREE.Vector3(Math.cos(theta) * ring * radius, y * radius, Math.sin(theta) * ring * radius);
      const cell = makeCell(node, coord);
      state.nodes.get(node.id).cell = cell;
      state.cells.push(cell);
      state.cubeRoot.add(cell);
    });
    rebuildEdges();
    updateHud();
    state.dirty = true;
  }

  function rebuildEdges() {
    if (!state.edgeRoot) return;
    clearGroup(state.edgeRoot);
    state.edges.forEach(edge => {
      const a = state.nodes.get(edge.source)?.cell;
      const b = state.nodes.get(edge.target)?.cell;
      if (!a || !b) return;
      const geometry = new THREE.BufferGeometry().setFromPoints([a.position.clone(), b.position.clone()]);
      const active = state.activeEdges.has(edge.id);
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: active ? 0xaaffce : 0x4dffad,
        transparent: true, opacity: active ? 0.96 : 0.30
      }));
      line.userData.edgeId = edge.id;
      state.edgeRoot.add(line);
    });
    state.pulses.forEach((pulse, edgeId) => {
      const edge = state.edges.get(edgeId);
      const a = edge && state.nodes.get(edge.source)?.cell;
      const b = edge && state.nodes.get(edge.target)?.cell;
      if (a && b) { pulse.from.copy(a.position); pulse.to.copy(b.position); }
    });
    if (edgeCountEl) edgeCountEl.textContent = state.edges.size + " LINKS";
    state.dirty = true;
  }

  function updateLiveEdges() {
    if (!state.edgeRoot) return;
    const from = new THREE.Vector3();
    const to = new THREE.Vector3();
    state.edgeRoot.children.forEach(line => {
      const edge = state.edges.get(line.userData.edgeId);
      const a = edge && state.nodes.get(edge.source)?.cell;
      const b = edge && state.nodes.get(edge.target)?.cell;
      if (!a || !b) return;
      a.getWorldPosition(from);
      b.getWorldPosition(to);
      const position = line.geometry.attributes.position;
      position.setXYZ(0, from.x, from.y, from.z);
      position.setXYZ(1, to.x, to.y, to.z);
      position.needsUpdate = true;
      line.geometry.computeBoundingSphere();
    });
    state.pulses.forEach((pulse, edgeId) => {
      const edge = state.edges.get(edgeId);
      const a = edge && state.nodes.get(edge.source)?.cell;
      const b = edge && state.nodes.get(edge.target)?.cell;
      if (a && b) {
        a.getWorldPosition(pulse.from);
        b.getWorldPosition(pulse.to);
      }
    });
  }

  function updateHud() {
    if (countEl) countEl.textContent = state.nodes.size + " OBJECTS";
    if (edgeCountEl) edgeCountEl.textContent = state.edges.size + " LINKS";
    const put = (id, value) => { const el = $(id); if (el) el.textContent = value || "—"; };
    put("rf-cube-model", state.current.model ? state.current.model.split("/").pop() : "");
    put("rf-cube-provider", state.current.provider);
    put("rf-cube-agent", state.current.agent);
    put("rf-cube-tool", state.current.tool);
    put("rf-cube-mode", state.current.mode);
    put("rf-cube-inspector-title", state.selectedNode ? state.nodes.get(state.selectedNode)?.label : "Select a segment");
    const selected = state.selectedNode ? state.nodes.get(state.selectedNode) : null;
    put("rf-cube-inspector-detail", selected ? selected.detail + " · " + selected.kind.toUpperCase() : "Hover or click a real object to inspect it");
    state.dirty = true;
  }

  function inspect(nodeId) {
    if (!nodeId || !state.nodes.has(nodeId)) return;
    state.selectedNode = nodeId;
    const node = state.nodes.get(nodeId);
    const related = Array.from(state.edges.values()).filter(edge => edge.source === nodeId || edge.target === nodeId).length;
    const detail = node.detail + " · " + related + " real links";
    const title = $("rf-cube-inspector-title");
    const meta = $("rf-cube-inspector-detail");
    if (title) title.textContent = node.label;
    if (meta) meta.textContent = detail;
    state.dirty = true;
  }

  function pulseEdge(edgeId, tone) {
    const edge = state.edges.get(edgeId);
    if (!edge) return;
    const source = state.nodes.get(edge.source)?.cell;
    const target = state.nodes.get(edge.target)?.cell;
    if (!source || !target) return;
    const old = state.pulses.get(edgeId);
    if (old) {
      state.scene.remove(old.mesh);
      old.mesh.geometry.dispose(); old.mesh.material.dispose();
    }
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.055, 12, 12),
      new THREE.MeshBasicMaterial({color: tone === "error" ? 0xff5d52 : 0xcaffdf})
    );
    state.scene.add(mesh);
    state.pulses.set(edgeId, {mesh, from: source.position.clone(), to: target.position.clone(), started: performance.now(), duration: 1500});
    state.activeEdges.add(edgeId);
    const line = state.edgeRoot.children.find(item => item.userData.edgeId === edgeId);
    if (line) { line.material.color.setHex(tone === "error" ? 0xff6258 : 0x9dffbd); line.material.opacity = 1; }
    state.dirty = true;
  }

  function activateMemoryEvent(item) {
    (item.active_node_ids || []).forEach(id => {
      const key = "mem:" + id;
      if (state.nodes.has(key)) state.activeNodes.add(key);
    });
    (item.active_edge_ids || []).forEach(id => {
      const key = "memory:" + id;
      if (state.edges.has(key)) pulseEdge(key);
    });
  }

  function enqueueTurn(nodeId, kind) {
    const now = performance.now();
    if (!state.nodes.has(nodeId)) return;
    if (now - (state.lastTurn.get(nodeId) || 0) < 950) return;
    state.lastTurn.set(nodeId, now);
    const axis = kind === "tool" ? "z" : (kind === "role" || kind === "agent" ? "x" : "y");
    state.rotationQueue.push({nodeId, axis});
    state.dirty = true;
  }

  function beginTurn() {
    if (state.rotation || !state.rotationQueue.length) return;
    const request = state.rotationQueue.shift();
    const target = state.nodes.get(request.nodeId);
    if (!target || !target.cell) return;
    const coord = target.cell.userData.coord;
    const layer = coord[request.axis];
    const pivot = new THREE.Group();
    state.cubeRoot.add(pivot);
    state.cubeRoot.updateMatrixWorld(true);
    pivot.updateMatrixWorld(true);
    const members = state.cells.filter(cell => Math.abs(cell.userData.coord[request.axis] - layer) < 0.001);
    members.forEach(cell => pivot.attach(cell));
    state.rotation = {pivot, members, axis: request.axis, layer, started: performance.now(), duration: 720};
    state.dirty = true;
  }

  function finishTurn(turn) {
    const axis = turn.axis;
    turn.members.forEach(cell => {
      const c = cell.userData.coord;
      let next;
      if (axis === "x") next = {x: c.x, y: -c.z, z: c.y};
      else if (axis === "y") next = {x: c.z, y: c.y, z: -c.x};
      else next = {x: -c.y, y: c.x, z: c.z};
      cell.userData.coord = next;
      state.cubeRoot.attach(cell);
      cell.position.set(next.x * state.spacing, next.y * state.spacing, next.z * state.spacing);
      cell.rotation.set(0, 0, 0);
    });
    state.cubeRoot.remove(turn.pivot);
    state.rotation = null;
    rebuildEdges();
  }

  function resolveModelNode(model) {
    const exact = "model:" + model;
    if (state.nodes.has(exact)) return exact;
    const shortName = String(model || "").split("/").pop();
    for (const [id, node] of state.nodes) {
      if (node.kind === "model" && (node.label === shortName || node.detail === model)) return id;
    }
    return "";
  }

  function handleGraphEvent(event) {
    if (!event || typeof event !== "object") return;
    const status = String(event.status || "");
    if (status === "memory_graph") {
      const item = event.event || event;
      if (event.phase === "failed") {
        state.failed = true;
        state.failedNodes = new Set(state.activeNodes);
        setStatus("MEMORY FAILED");
        state.pulses.forEach(pulse => pulse.mesh.material.color.setHex(0xff6258));
        state.edgeRoot.children.forEach(line => {
          if (state.activeEdges.has(line.userData.edgeId)) {
            line.material.color.setHex(0xff6258);
            line.material.opacity = 1;
          }
        });
        addLog("Memory access failed", event.error || "", "error");
        window.setTimeout(() => {
          state.failed = false; state.failedNodes.clear();
          setStatus(state.running ? "PROCESSING" : "IDLE"); state.dirty = true;
        }, 1800);
        return;
      }
      if (event.phase === "activity" || event.phase === "completed") {
        setStatus("MEMORY ACCESS");
        activateMemoryEvent(item);
        if (event.phase === "activity") addLog(item.label || item.operation || "Memory activity", item.detail || item.phase || "");
        if (event.phase === "completed") {
          const completedIds = (item.active_node_ids || []).map(id => "mem:" + id);
          addLog("Memory context ready", completedIds.length + " nodes selected");
          // Keep activated nodes and edges visible until the next run.
          window.setTimeout(async () => {
            await loadMemory();
            (item.active_edge_ids || []).forEach(id => pulseEdge("memory:" + id));
          }, 900);
        }
      }
    } else if (status === "phase" || status === "model_try" || status === "tool_start" || status === "tool_end") {
      // Runtime telemetry updates the HUD only. It must never invent graph nodes or edges.
      if (status === "phase") state.current.agent = String(event.role || state.current.agent || "");
      if (status === "model_try") {
        state.current.model = String(event.model || "");
        state.current.provider = String(event.provider || state.current.model.split("/")[0] || "");
      }
      if (status === "tool_start") state.current.tool = String(event.tool_name || "");
      if (status === "tool_end") state.current.tool = "";
      setStatus(status === "phase" ? (event.label || "PROCESSING") :
        status === "model_try" ? "INFERENCE" :
        status === "tool_start" ? "TOOL EXECUTION" : "TOOL COMPLETED");
      addLog(status === "phase" ? "Agent phase" : status === "model_try" ? "Model selected" :
        status === "tool_start" ? "Tool invoked" : "Tool completed",
        event.label || event.model || event.tool_name || event.role || "");
    } else if (status === "warning") {
      addLog("Orchestrator warning", event.warning || "", "warn");
    } else if (status === "error" || status === "failed") {
      failRun(event.error || "Execution failed");
    } else if (status === "done" || status === "aborted") {
      finishRun(status);
    }
    updateHud();
  }

  function failRun(message) {
    state.failed = true;
    state.running = false;
    state.failedNodes = new Set(state.activeNodes);
    setStatus("FAILED");
    addLog("Execution failed", message, "error");
    state.activeNodes.forEach(id => {
      const node = state.nodes.get(id);
      if (node?.cell?.userData.point) {
        node.cell.userData.point.material.color.setHex(0xff6258);
        node.cell.userData.point.material.emissive.setHex(0x8a1717);
      }
      if (node?.cell?.userData.halo) node.cell.userData.halo.material.color.setHex(0xff6258);
    });
    state.pulses.forEach(pulse => pulse.mesh.material.color.setHex(0xff6258));
    state.edgeRoot.children.forEach(line => {
      if (state.activeEdges.has(line.userData.edgeId)) {
        line.material.color.setHex(0xff6258);
        line.material.opacity = 1;
      }
    });
    state.dirty = true;
    // Keep the failed process highlighted until the next explicit run.
    state.dirty = true;
  }

  function startRun() {
    state.running = true; state.failed = false; state.failedNodes.clear();
    state.current.tool = ""; state.current.model = ""; state.current.provider = ""; state.current.agent = "";
    state.activeNodes.clear(); state.activeEdges.clear();
    state.rotationQueue.length = 0;
    const mode = document.getElementById("strategy-select")?.value || "";
    state.current.mode = mode;
    if (mode && state.nodes.has("mode:" + mode)) state.activeNodes.add("mode:" + mode);
    setStatus("STARTED");
    addLog("Orchestration started", mode || "active session");
    updateHud();
  }

  function finishRun(result) {
    state.running = false;
    // Preserve activity highlights after completion; startRun clears them for the next iteration.
    state.failedNodes.clear();
    state.rotationQueue.length = 0;
    state.current.tool = ""; state.current.model = ""; state.current.provider = ""; state.current.agent = "";
    if (result === "aborted") {
      setStatus("STOPPED"); addLog("Run stopped", "Execution aborted");
    } else {
      setStatus("COMPLETED"); addLog("Run completed", "All active operations finished");
    }
    updateHud();
  }

  async function loadMemory() {
    const pid = projectId();
    if (!pid) { state.memory = {nodes: [], edges: []}; rebuildData(); setStatus("NO PROJECT"); return; }
    try {
      const data = await authFetch("/api/v1/memory/graph-status/" + encodeURIComponent(pid));
      if (pid !== projectId()) return;
      state.memory = {nodes: data.nodes || [], edges: data.edges || []};
      rebuildData();
      if (!state.running) setStatus("IDLE");
    } catch (error) {
      setStatus("GRAPH OFFLINE");
      addLog("Memory graph unavailable", error.message || "Request failed", "warn");
    }
  }

  async function loadRegistry() {
    try {
      const data = await authFetch("/api/v1/memory/runtime-registry");
      state.registry = {roles: data.roles || [], tools: data.tools || []};
      rebuildData();
    } catch (_) {}
  }

  async function loadModels() {
    try {
      const data = await authFetch("/api/v1/keys/selected-models");
      state.selected = data.selected_models || {};
      rebuildData();
    } catch (_) {}
  }

  async function loadWorkspace() {
    const pid = projectId();
    if (!pid) { state.workspace = []; rebuildData(); return; }
    try {
      const data = await authFetch("/api/v1/workspaces/tree?project_id=" + encodeURIComponent(pid));
      if (pid !== projectId()) return;
      const tree = data.tree;
      const items = [];
      if (tree && tree.path) {
        items.push({name: tree.name || "workspace", path: tree.path, parent: "", kind: "workspace"});
        (tree.children || []).filter(item => item && item.path)
          .filter(item => ![".git", "node_modules", "venv", ".venv", "__pycache__"].includes(item.name))
          .slice(0, 80)
          .forEach(item => items.push({
            name: item.name, path: item.path, parent: tree.path,
            kind: item.type === "directory" ? "directory" : "file"
          }));
      }
      state.workspace = items;
      rebuildData();
    } catch (_) {}
  }

  function refreshAll() {
    loadMemory();
  }

  function initScene() {
    state.scene = new THREE.Scene();
    state.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    state.camera.position.set(4.1, 3.0, 5.1);
    try {
      state.renderer = new THREE.WebGLRenderer({alpha: true, antialias: true, powerPreference: "low-power"});
    } catch (error) {
      setStatus("3D UNAVAILABLE");
      addLog("WebGL unavailable", error.message || "3D rendering is not supported", "warn");
      return;
    }
    state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    state.renderer.outputColorSpace = THREE.SRGBColorSpace;
    state.renderer.setClearColor(0x020b08, 0);
    viewport.replaceChildren(state.renderer.domElement);
    state.renderer.domElement.className = "rf-cube-canvas";
    state.controls = new OrbitControls(state.camera, state.renderer.domElement);
    state.controls.enableDamping = true;
    state.controls.dampingFactor = 0.08;
    state.controls.enablePan = false;
    state.controls.minDistance = 3.0;
    state.controls.maxDistance = 10;
    state.controls.addEventListener("change", () => { state.dirty = true; });
    state.scene.add(new THREE.AmbientLight(0x6fffb5, 1.1));
    const keyLight = new THREE.PointLight(0x31ff9a, 18, 12);
    keyLight.position.set(3, 4, 5); state.scene.add(keyLight);
    const rimLight = new THREE.PointLight(0x0c9c62, 10, 10);
    rimLight.position.set(-4, -2, -3); state.scene.add(rimLight);
    state.cubeRoot = new THREE.Group();
    state.edgeRoot = new THREE.Group();
    state.scene.add(state.cubeRoot, state.edgeRoot);
    state.resizeObserver = new ResizeObserver(resize);
    state.resizeObserver.observe(viewport);
    resize();
    state.renderer.domElement.addEventListener("pointermove", onPointerMove);
    state.renderer.domElement.addEventListener("click", onPointerClick);
    state.raf = requestAnimationFrame(renderLoop);
  }

  function resize() {
    if (!state.renderer || !state.camera) return;
    const width = Math.max(1, viewport.clientWidth);
    const height = Math.max(1, viewport.clientHeight);
    state.camera.aspect = width / height;
    state.camera.updateProjectionMatrix();
    state.renderer.setSize(width, height, false);
    state.dirty = true;
  }

  function pick(event) {
    const rect = state.renderer.domElement.getBoundingClientRect();
    state.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    state.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    state.raycaster.setFromCamera(state.pointer, state.camera);
    const targets = [];
    state.nodes.forEach(node => {
      if (node.cell) targets.push(node.cell);
    });
    const hits = state.raycaster.intersectObjects(targets, true);
    const hit = hits.find(item => item.object.userData.nodeId || item.object.parent?.userData.nodeId);
    return hit ? (hit.object.userData.nodeId || hit.object.parent.userData.nodeId) : "";
  }

  function onPointerMove(event) {
    const id = pick(event);
    state.renderer.domElement.style.cursor = id ? "pointer" : "grab";
    if (id) inspect(id);
  }

  function onPointerClick(event) {
    const id = pick(event);
    if (id) inspect(id);
  }

  function renderLoop(now) {
    if (state.disposed) return;
    const active = state.running || state.rotation || state.rotationQueue.length || state.pulses.size || state.activeNodes.size || state.activeEdges.size;
    const interval = active ? 33 : 100;
    if (now - state.lastRender >= interval || state.dirty) {
      state.lastRender = now;
      if (state.controls) state.controls.update();
      state.nodes.forEach(node => {
        const cell = node.cell;
        if (!cell || !cell.userData.point || !cell.userData.halo) return;
        const activeNode = state.activeNodes.has(node.id);
        const failedNode = state.failedNodes.has(node.id);
        const pulse = activeNode ? (0.72 + Math.sin(now * 0.006) * 0.28) : 1;
        cell.userData.point.material.color.setHex(failedNode ? 0xff6258 : (activeNode ? 0xd9ffe8 : 0x39f5a0));
        cell.userData.point.material.emissive.setHex(failedNode ? 0x8a1717 : (activeNode ? 0x31ff9a : 0x0b6b3d));
        cell.userData.point.material.emissiveIntensity = activeNode ? 1.8 * pulse : 0.35;
        cell.userData.halo.material.opacity = activeNode ? 0.38 * pulse : 0.10;
      });
      if (state.rotation) {
        const turn = state.rotation;
        const t = Math.min(1, (now - turn.started) / turn.duration);
        const eased = 1 - Math.pow(1 - t, 3);
        turn.pivot.rotation[turn.axis] = eased * Math.PI / 2;
        if (t >= 1) finishTurn(turn);
      } else beginTurn();
      if (state.cubeRoot) {
        state.cubeRoot.rotation.y += 0.0014;
        state.cubeRoot.rotation.x = Math.sin(now * 0.00018) * 0.08;
      }
      updateLiveEdges();

      state.pulses.forEach((pulse, id) => {
        const t = Math.min(1, (now - pulse.started) / pulse.duration);
        pulse.mesh.position.lerpVectors(pulse.from, pulse.to, t);
        if (t >= 1) {
          state.scene.remove(pulse.mesh);
          pulse.mesh.geometry.dispose(); pulse.mesh.material.dispose();
          state.pulses.delete(id);
          // Keep the activated relationship highlighted.
        }
      });
      const glow = 0.78 + Math.sin(now * 0.004) * 0.18;
      state.edgeRoot.children.forEach(line => {
        const activeEdge = state.activeEdges.has(line.userData.edgeId);
        line.material.color.setHex(activeEdge ? 0xaaffce : 0x4dffad);
        line.material.opacity = activeEdge ? glow : 0.30;
      });
      state.renderer.render(state.scene, state.camera);
      state.dirty = false;
    }
    state.raf = requestAnimationFrame(renderLoop);
  }

  function disposeScene() {
    state.disposed = true;
    if (state.raf) cancelAnimationFrame(state.raf);
    state.resizeObserver?.disconnect();
    state.controls?.dispose();
    if (state.scene) clearGroup(state.scene);
    state.renderer?.dispose();
    state.renderer?.forceContextLoss?.();
  }

  window.addEventListener("pagehide", disposeScene, {once: true});

  function setCollapsed(value) {
    root.classList.toggle("is-collapsed", value);
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(!value));
      toggle.setAttribute("aria-label", value ? "Show runtime graph" : "Hide runtime graph");
    }
    try { localStorage.setItem(collapsedKey, value ? "1" : "0"); } catch (_) {}
    if (!value) resize();
  }

  if (toggle) toggle.addEventListener("click", () => setCollapsed(!root.classList.contains("is-collapsed")));
  eventBus.on("generation:state", event => {
    if (event?.active && !state.running) startRun();
    else if (!event?.active && state.running) finishRun("aborted");
  });
  eventBus.on("agent:graph_event", handleGraphEvent);
  eventBus.on("project.activated", project => {
    const id = typeof project === "string" ? project : (project && project.id) || "";
    if (id) localStorage.setItem("rf_active_project_id", id);
    else localStorage.removeItem("rf_active_project_id");
    state.project = id;
    state.memory = {nodes: [], edges: []}; state.registry = {roles: [], tools: []};
    state.selected = {}; state.workspace = [];
    state.activeNodes.clear(); state.activeEdges.clear(); state.events = [];
    if (feedEl) feedEl.replaceChildren();
    refreshAll();
  });
  eventBus.on("auth:success", refreshAll);
  eventBus.on("session:deleted", loadMemory);
  document.getElementById("strategy-select")?.addEventListener("change", event => {
    state.current.mode = event.target.value;
    updateHud();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshAll(); });
  try { setCollapsed(localStorage.getItem(collapsedKey) === "1"); } catch (_) { setCollapsed(false); }

  initScene();
  refreshAll();
})();