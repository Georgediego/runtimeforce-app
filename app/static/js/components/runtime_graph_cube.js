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
  const palette = {
    memory: 0x39f5a0, project: 0x52e8b2, conversation: 0x50dca5, file: 0x5ad8b7,
    code: 0x65e9c4, workspace: 0x43c8e8, directory: 0x40bda7, role: 0x9bff69,
    agent: 0x9bff69, provider: 0x65e6a9, model: 0x9cff48, tool: 0x70f0c0, mode: 0xb5ff8a
  };
  const glyph = {
    memory: "▤", project: "⌂", conversation: "◌", file: "▧", code: "</>",
    workspace: "⌂", directory: "▦", role: "✦", agent: "✦",
    provider: "◈", model: "⌘", tool: "⚙", mode: "◎"
  };
  const state = {
    nodes: new Map(), edges: new Map(), cells: [], memory: {nodes: [], edges: []},
    registry: {roles: [], tools: []}, selected: {}, workspace: [],
    activeNodes: new Set(), activeEdges: new Set(), events: [],
    current: {model: "", provider: "", agent: "", tool: "", mode: ""},
    status: "IDLE", running: false, failed: false, project: "",
    side: 2, cubeSize: 0.78, spacing: 0.9, selectedNode: "",
    rotationQueue: [], rotation: null, lastTurn: new Map(),
    pulses: new Map(), dirty: true, lastRender: 0, raf: 0,
    renderer: null, scene: null, camera: null, controls: null,
    cubeRoot: null, edgeRoot: null, raycaster: new THREE.Raycaster(),
    pointer: new THREE.Vector2(), resizeObserver: null, disposed: false
  };

  const restore = document.createElement("button");
  restore.id = "rf-memory-widget-restore";
  restore.type = "button";
  restore.className = "rf-memory-widget-restore";
  restore.textContent = "RUNTIME GRAPH  ↑";
  root.insertAdjacentElement("afterend", restore);

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

    state.memory.nodes.forEach(node => {
      addNode("mem:" + node.id, node.type || "memory", node.label || node.id,
        "SQLite graph node · " + node.id, "graph_nodes");
    });
    state.memory.edges.forEach(edge => {
      addEdge("memory:" + edge.id, "mem:" + edge.source, "mem:" + edge.target,
        "memory", edge.relation || "RELATED_TO");
    });

    state.registry.roles.forEach(role => {
      const id = "role:" + String(role.name).toLowerCase();
      addNode(id, "role", role.name, "Agent role · allowed tools: " + (role.allowed_tools || []).join(", "), "ROLE_PROFILES");
      (role.allowed_tools || []).forEach(toolName => {
        const toolId = "tool:" + toolName;
        if (state.registry.tools.some(tool => tool.name === toolName)) {
          addEdge("role-tool:" + role.name + ":" + toolName, id, toolId, "declared", "Role tool permission");
        }
      });
    });
    state.registry.tools.forEach(tool => {
      addNode("tool:" + tool.name, "tool", tool.name, tool.description || "Registered orchestrator tool", "AGENT_TOOLS_MANIFEST");
    });

    Object.entries(state.selected).forEach(([provider, models]) => {
      const providerId = "provider:" + provider.toLowerCase();
      addNode(providerId, "provider", provider, "Provider with selected models", "provider_keys");
      (models || []).forEach(modelId => {
        const id = "model:" + modelId;
        addNode(id, "model", String(modelId).split("/").pop(), String(modelId), "selected_models");
        addEdge("provider-model:" + provider.toLowerCase() + ":" + modelId,
          providerId, id, "configured", "Selected model for provider");
      });
    });

    const strategy = document.getElementById("strategy-select");
    if (strategy) Array.from(strategy.options).forEach(option => {
      addNode("mode:" + option.value, "mode", option.textContent.trim(), "Chat mode", "strategy-select");
    });

    state.workspace.forEach(item => {
      addNode("ws:" + item.path, item.kind || "workspace", item.name, item.path, "workspace_tree");
      if (item.parent) addEdge("contains:" + item.path, "ws:" + item.parent, "ws:" + item.path, "filesystem", "Contains");
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

  function makeIconTexture(kind) {
    const canvas = document.createElement("canvas");
    canvas.width = 96; canvas.height = 96;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, 96, 96);
    ctx.beginPath(); ctx.arc(48, 48, 43, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(2,18,12,.92)"; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = "#4bffad"; ctx.stroke();
    ctx.fillStyle = "#caffdf"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = kind === "code" ? "bold 22px monospace" : "bold 43px sans-serif";
    ctx.fillText(glyph[kind] || "•", 48, 49);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  function makeCell(node, coord) {
    const group = new THREE.Group();
    group.position.set(coord.x * state.spacing, coord.y * state.spacing, coord.z * state.spacing);
    group.userData.coord = {...coord};
    group.userData.nodeId = node ? node.id : "";
    const baseGeometry = new THREE.BoxGeometry(state.cubeSize, state.cubeSize, state.cubeSize);
    const edges = new THREE.EdgesGeometry(baseGeometry);
    baseGeometry.dispose();
    const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({
      color: node ? (palette[node.kind] || 0x39f5a0) : 0x174a35,
      transparent: true, opacity: node ? 0.9 : 0.16
    }));
    group.add(line);
    if (node) {
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(state.cubeSize * 0.94, state.cubeSize * 0.94, state.cubeSize * 0.94),
        new THREE.MeshPhongMaterial({
          color: palette[node.kind] || 0x39f5a0, transparent: true,
          opacity: 0.13, shininess: 90, specular: 0x72ffba
        })
      );
      body.userData.nodeId = node.id;
      group.add(body);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: makeIconTexture(node.kind), transparent: true, depthWrite: false
      }));
      sprite.scale.set(0.34, 0.34, 1);
      sprite.position.z = state.cubeSize * 0.53;
      sprite.userData.nodeId = node.id;
      group.add(sprite);
      group.userData.body = body;
      group.userData.outline = line;
      group.userData.sprite = sprite;
    }
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

    const count = state.nodes.size;
    state.side = count <= 8 ? 2 : Math.max(3, Math.ceil(Math.cbrt(count)));
    state.spacing = Math.min(0.9, 2.5 / state.side);
    state.cubeSize = state.spacing * 0.84;
    const ordered = Array.from(state.nodes.values()).sort((a, b) =>
      a.kind.localeCompare(b.kind) || a.label.localeCompare(b.label)
    );
    const nodeAt = new Map();
    ordered.forEach((node, index) => {
      const x = index % state.side;
      const y = Math.floor(index / state.side) % state.side;
      const z = Math.floor(index / (state.side * state.side));
      nodeAt.set(x + ":" + y + ":" + z, node);
    });
    const center = (state.side - 1) / 2;
    for (let z = 0; z < state.side; z++) {
      for (let y = 0; y < state.side; y++) {
        for (let x = 0; x < state.side; x++) {
          const node = nodeAt.get(x + ":" + y + ":" + z) || null;
          const coord = {x: x - center, y: y - center, z: z - center};
          const cell = makeCell(node, coord);
          if (node) state.nodes.get(node.id).cell = cell;
          state.cells.push(cell);
          state.cubeRoot.add(cell);
        }
      }
    }
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
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: edge.kind === "memory" ? 0x4dffad : 0x238e63,
        transparent: true, opacity: edge.kind === "memory" ? 0.68 : 0.38
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
      new THREE.SphereGeometry(0.045, 8, 8),
      new THREE.MeshBasicMaterial({color: tone === "error" ? 0xff5d52 : 0x9dffbd})
    );
    state.scene.add(mesh);
    state.pulses.set(edgeId, {mesh, from: source.position.clone(), to: target.position.clone(), started: performance.now(), duration: 1150});
    state.activeEdges.add(edgeId);
    const line = state.edgeRoot.children.find(item => item.userData.edgeId === edgeId);
    if (line) { line.material.color.setHex(tone === "error" ? 0xff6258 : 0x9dffbd); line.material.opacity = 0.98; }
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
    if ((item.active_node_ids || []).length) {
      const first = state.nodes.get("mem:" + item.active_node_ids[0]);
      if (first) enqueueTurn(first.id, "memory");
    }
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
        setStatus("MEMORY FAILED"); addLog("Memory access failed", event.error || "", "error");
        return;
      }
      if (event.phase === "activity" || event.phase === "completed") {
        setStatus("MEMORY ACCESS");
        activateMemoryEvent(item);
        if (event.phase === "activity") addLog(item.label || item.operation || "Memory activity", item.detail || item.phase || "");
        if (event.phase === "completed") {
          const completedIds = (item.active_node_ids || []).map(id => "mem:" + id);
          addLog("Memory context ready", completedIds.length + " nodes selected");
          window.setTimeout(() => {
            completedIds.forEach(id => state.activeNodes.delete(id));
            state.dirty = true;
          }, 850);
          window.setTimeout(async () => {
            await loadMemory();
            (item.active_edge_ids || []).forEach(id => pulseEdge("memory:" + id));
          }, 1300);
        }
      }
    } else if (status === "phase") {
      if (event.role) {
        const agent = String(event.role);
        state.activeNodes.forEach(id => { if (id.startsWith("role:")) state.activeNodes.delete(id); });
        state.current.agent = agent;
        const id = "role:" + agent.toLowerCase();
        if (!state.nodes.has(id)) {
          addNode(id, "role", agent, "Observed active agent role", "agent_event");
          buildCube();
        }
        state.activeNodes.add(id);
        enqueueTurn(id, "role");
      }
      setStatus(event.label || "PROCESSING");
      addLog("Agent phase", event.label || event.role || "");
    } else if (status === "model_try") {
      state.activeNodes.forEach(id => { if (id.startsWith("model:") || id.startsWith("provider:")) state.activeNodes.delete(id); });
      const model = String(event.model || "");
      const provider = String(event.provider || model.split("/")[0] || "");
      state.current.model = model;
      state.current.provider = provider;
      if (event.role) state.current.agent = String(event.role);
      let modelId = resolveModelNode(model);
      const providerId = "provider:" + provider.toLowerCase();
      const roleId = "role:" + String(state.current.agent || "").toLowerCase();
      let needsBuild = false;
      if (!state.nodes.has(providerId)) {
        addNode(providerId, "provider", provider, "Observed active provider", "model_try");
        needsBuild = true;
      }
      if (roleId && !state.nodes.has(roleId)) {
        addNode(roleId, "role", state.current.agent, "Observed active agent role", "model_try");
        needsBuild = true;
      }
      if (!modelId) {
        modelId = "model:runtime:" + model;
        addNode(modelId, "model", model.split("/").pop(), model, "model_try");
        needsBuild = true;
      }
      if (needsBuild) buildCube();
      state.activeNodes.add(modelId); state.activeNodes.add(providerId);
      if (state.nodes.has(roleId)) state.activeNodes.add(roleId);
      let relation = Array.from(state.edges.values()).find(edge => edge.source === providerId && edge.target === modelId);
      if (!relation && state.nodes.has(providerId) && state.nodes.has(modelId)) {
        const relationId = "observed-model:" + provider.toLowerCase() + ":" + model;
        addEdge(relationId, providerId, modelId, "runtime", "Observed model selection event");
        relation = state.edges.get(relationId);
        rebuildEdges();
      }
      if (relation) pulseEdge(relation.id);
      enqueueTurn(modelId, "model");
      setStatus("INFERENCE");
      addLog("Model selected", model + " · " + provider);
    } else if (status === "tool_start") {
      const name = String(event.tool_name || "");
      state.current.tool = name;
      const toolId = "tool:" + name;
      const role = String(event.role || state.current.agent || "");
      let needsBuild = false;
      if (!state.nodes.has(toolId)) {
        addNode(toolId, "tool", name, "Observed active orchestrator tool", "tool_start");
        needsBuild = true;
      }
      const roleId = role ? "role:" + role.toLowerCase() : "";
      if (role && !state.nodes.has(roleId)) {
        addNode(roleId, "role", role, "Observed active agent role", "tool_start");
        needsBuild = true;
      }
      if (needsBuild) buildCube();
      state.activeNodes.add(toolId);
      if (role) {
        state.current.agent = role;
        let relation = Array.from(state.edges.values()).find(edge => edge.source === roleId && edge.target === toolId);
        if (!relation) {
          const relationId = "observed-tool:" + role.toLowerCase() + ":" + name;
          addEdge(relationId, roleId, toolId, "runtime", "Observed tool invocation event");
          relation = state.edges.get(relationId);
          if (relation) rebuildEdges();
        }
        if (relation) pulseEdge(relation.id);
      }
      enqueueTurn(toolId, "tool");
      setStatus("TOOL EXECUTION");
      addLog("Tool invoked", name);
    } else if (status === "tool_end") {
      state.activeNodes.delete("tool:" + String(event.tool_name || state.current.tool || ""));
      state.current.tool = "";
      setStatus("TOOL COMPLETED");
      addLog("Tool completed", event.tool_name || "");
    } else if (status === "reasoning" || status === "streaming") {
      setStatus(status === "streaming" ? "GENERATING" : "REASONING");
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
    setStatus("FAILED");
    addLog("Execution failed", message, "error");
    state.activeNodes.forEach(id => {
      const node = state.nodes.get(id);
      if (node?.cell?.userData.outline) node.cell.userData.outline.material.color.setHex(0xff6258);
      if (node?.cell?.userData.body) node.cell.userData.body.material.color.setHex(0xff6258);
    });
    state.pulses.forEach(pulse => pulse.mesh.material.color.setHex(0xff6258));
    state.edgeRoot.children.forEach(line => {
      if (state.activeEdges.has(line.userData.edgeId)) {
        line.material.color.setHex(0xff6258);
        line.material.opacity = 1;
      }
    });
    state.dirty = true;
    window.setTimeout(() => {
      state.failed = false;
      state.activeNodes.clear(); state.activeEdges.clear();
      state.current.tool = ""; state.current.model = ""; state.current.provider = ""; state.current.agent = "";
      buildCube(); setStatus("IDLE"); updateHud();
    }, 1800);
  }

  function startRun() {
    state.running = true; state.failed = false;
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
    state.activeNodes.clear(); state.activeEdges.clear();
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
    loadRegistry();
    loadModels();
    loadWorkspace();
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
    const active = state.running || state.rotation || state.rotationQueue.length || state.pulses.size;
    const interval = active ? 33 : 100;
    if (now - state.lastRender >= interval || state.dirty) {
      state.lastRender = now;
      if (state.controls) state.controls.update();
      state.nodes.forEach(node => {
        const cell = node.cell;
        if (!cell || !cell.userData.body || !cell.userData.outline) return;
        const activeNode = state.activeNodes.has(node.id);
        cell.userData.body.material.opacity = activeNode ? 0.42 : 0.13;
        cell.userData.outline.material.color.setHex(state.failed ? 0xff6258 : (activeNode ? 0xa6ffc9 : (palette[node.kind] || 0x39f5a0)));
        cell.userData.outline.material.opacity = activeNode ? 1 : 0.9;
      });
      if (state.rotation) {
        const turn = state.rotation;
        const t = Math.min(1, (now - turn.started) / turn.duration);
        const eased = 1 - Math.pow(1 - t, 3);
        turn.pivot.rotation[turn.axis] = eased * Math.PI / 2;
        if (t >= 1) finishTurn(turn);
      } else beginTurn();
      if (state.rotation) updateLiveEdges();

      state.pulses.forEach((pulse, id) => {
        const t = Math.min(1, (now - pulse.started) / pulse.duration);
        pulse.mesh.position.lerpVectors(pulse.from, pulse.to, t);
        if (t >= 1) {
          state.scene.remove(pulse.mesh);
          pulse.mesh.geometry.dispose(); pulse.mesh.material.dispose();
          state.pulses.delete(id); state.activeEdges.delete(id);
          const edge = state.edges.get(id);
          const line = state.edgeRoot.children.find(item => item.userData.edgeId === id);
          if (line && edge) {
            line.material.color.setHex(edge.kind === "memory" ? 0x4dffad : 0x238e63);
            line.material.opacity = edge.kind === "memory" ? 0.68 : 0.38;
          }
        }
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
  restore.addEventListener("click", () => setCollapsed(false));
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