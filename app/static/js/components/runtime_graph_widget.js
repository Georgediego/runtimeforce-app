/**
 * RuntimeForce Runtime Graph — real entities and observed runtime relationships.
 * Canvas 2D, event-driven rendering; no synthetic hub or decorative graph edges.
 */
import { eventBus } from "../core/event_bus.js";

(() => {
    const host = document.getElementById("rf-rg");
    if (!host) return;

    const $ = (tag, cls, value) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (value !== undefined) node.textContent = value;
        return node;
    };
    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const hash = (s, salt = 0) => {
        let h = (2166136261 ^ salt) >>> 0;
        for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
        h ^= h >>> 15; h = Math.imul(h, 2246822519); h ^= h >>> 13;
        return (h >>> 0) / 4294967296;
    };
    const color = kind => ({
        memory: "#64e8a1", provider: "#55d9c5", model: "#9bf58a",
        role: "#b69cff", tool: "#f0c77a", mode: "#8fc8ff",
        workspace: "#82aaff"
    })[kind] || "#64e8a1";

    const S = {
        nodes: new Map(), edges: new Map(), positions: new Map(),
        memory: { nodes: [], edges: [], totalNodes: 0, totalEdges: 0 },
        registry: { roles: [], tools: [] }, selected: {}, workspace: [],
        run: false, state: "IDLE", current: {}, activeNodes: new Set(),
        activeEdges: new Set(), events: [], hover: "", dirty: true,
        health: { memory: "wait", workspace: "wait", models: "wait", registry: "wait" },
        animUntil: 0, project: ""
    };

    const canvas = $("canvas", "rf-rg-canvas");
    const ctx = canvas.getContext("2d");
    const stage = $("div", "rf-rg-stage");
    const tip = $("div", "rf-rg-tip");
    stage.append(canvas, tip);
    const header = $("div", "rf-rg-head");
    const title = $("div", "rf-rg-title");
    const pulse = $("i", "rf-rg-pulse");
    const titleCopy = $("div", "rf-rg-title-copy");
    titleCopy.append($("b", "", "RUNTIME GRAPH"), $("small", "", "REAL ENTITIES · LIVE ORCHESTRATION"));
    title.append(pulse, titleCopy);
    const controls = $("div", "rf-rg-actions");
    const expand = $("button", "rf-rg-btn", "Expand");
    expand.type = "button";
    controls.append(expand);
    const collapse = $("button", "rf-rg-btn", "Hide");
    collapse.type = "button";
    controls.append(collapse);
    header.append(title, controls);

    const readout = $("div", "rf-rg-readout");
    const cells = {};
    [["state","STATE"],["mode","MODE"],["role","AGENT"],["provider","PROVIDER"],["model","MODEL"],["tool","TOOL"]].forEach(([key,label]) => {
        const cell = $("div", "rf-rg-cell");
        cells[key] = $("strong", "", "—");
        cell.append(cells[key], $("span", "", label));
        readout.append(cell);
    });
    const footer = $("div", "rf-rg-footer");
    const metrics = $("span", "rf-rg-metrics-text", "0 OBJECTS · 0 LINKS");
    const health = $("span", "rf-rg-health");
    Object.keys(S.health).forEach(key => {
        const dot = $("i", "rf-rg-dot");
        dot.title = key;
        health.append(dot);
        S.health[key] = "wait";
    });
    footer.append(metrics, health);
    const logBox = $("div", "rf-rg-log");
    logBox.append($("div", "rf-rg-log-head", "PROCESS EVENTS"));
    const log = $("div", "rf-rg-log-list");
    logBox.append(log);
    const body = $("div", "rf-rg-body");
    body.append(stage, readout, footer, logBox);
    host.replaceChildren(header, body);

    const authFetch = async url => {
        const headers = {};
        const jwt = token();
        if (jwt) headers.Authorization = "Bearer " + jwt;
        const response = await fetch(url, { headers, credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
    };

    function addNode(id, kind, label, detail = "") {
        if (!id) return;
        const old = S.nodes.get(id);
        S.nodes.set(id, { id, kind, label: String(label || id), detail: String(detail || "") });
    }
    function addEdge(id, a, b, kind = "relation", detail = "") {
        if (!id || !S.nodes.has(a) || !S.nodes.has(b) || a === b) return;
        S.edges.set(id, { id, a, b, kind, detail });
    }
    function rebuild() {
        S.nodes.clear(); S.edges.clear();
        S.positions.clear();
        S.registry.roles.forEach(r => addNode("role:" + r.name.toLowerCase(), "role", r.name, (r.allowed_tools || []).join(", ")));
        S.registry.tools.forEach(t => addNode("tool:" + t.name, "tool", t.name, t.description));
        const select = document.getElementById("strategy-select");
        if (select) Array.from(select.options).forEach(o => addNode("mode:" + o.value, "mode", (o.textContent || o.value).trim(), "chat mode"));
        Object.entries(S.selected).forEach(([provider, ids]) => {
            addNode("provider:" + provider, "provider", provider, "selected provider");
            ids.forEach(id => {
                addNode("model:" + id, "model", id.split("/").pop(), id);
                addEdge("provides:" + provider + ":" + id, "provider:" + provider, "model:" + id, "provides");
            });
        });
        S.memory.nodes.forEach(n => addNode("mem:" + n.id, "memory", n.label || n.id, n.type));
        S.memory.edges.forEach(e => addEdge("memory:" + e.id, "mem:" + e.source, "mem:" + e.target, "memory", e.relation));
        S.workspace.forEach(w => {
            addNode("ws:" + w.path, "workspace", w.name, w.path);
            if (w.parent) addEdge("contains:" + w.path, "ws:" + w.parent, "ws:" + w.path, "workspace");
        });
        // Place entities in a deterministic, distributed field; no invented center or links.
        const list = Array.from(S.nodes.values());
        list.forEach((n, i) => {
            const a = hash(n.id, 31) * Math.PI * 2;
            const r = 0.16 + Math.sqrt(hash(n.id, 73)) * 0.72;
            S.positions.set(n.id, { x: 0.5 + Math.cos(a) * r * 0.47, y: 0.5 + Math.sin(a) * r * 0.43, depth: hash(n.id, 19) });
        });
        S.dirty = true;
        renderMetrics();
        draw();
    }

    async function loadMemory() {
        const pid = projectId();
        if (!pid) { S.memory = { nodes: [], edges: [], totalNodes: 0, totalEdges: 0 }; S.health.memory = "off"; rebuild(); return; }
        try {
            const p = await authFetch("/api/v1/memory/graph-status/" + encodeURIComponent(pid));
            if (pid !== projectId()) return;
            S.memory = { nodes: p.nodes || [], edges: p.edges || [], totalNodes: p.total_nodes || 0, totalEdges: p.total_edges || 0 };
            S.health.memory = "ok"; rebuild();
        } catch (_) { S.health.memory = "err"; renderMetrics(); }
    }
    async function loadWorkspace() {
        const pid = projectId();
        if (!pid) { S.workspace = []; S.health.workspace = "off"; rebuild(); return; }
        try {
            const p = await authFetch("/api/v1/workspaces/tree?project_id=" + encodeURIComponent(pid));
            if (pid !== projectId()) return;
            const tree = p.tree;
            const items = [];
            if (tree && tree.path) {
                items.push({ name: tree.name || "workspace", path: tree.path, parent: "" });
                (tree.children || []).filter(x => x && x.path).slice(0, 80).forEach(x => {
                    if ([".git","node_modules","venv",".venv","__pycache__"].includes(x.name)) return;
                    items.push({ name: x.name, path: x.path, parent: tree.path });
                });
            }
            S.workspace = items; S.health.workspace = "ok"; rebuild();
        } catch (_) { S.health.workspace = "err"; renderMetrics(); }
    }
    async function loadModels() {
        try {
            const p = await authFetch("/api/v1/keys/selected-models");
            S.selected = p.selected_models || {}; S.health.models = "ok"; rebuild();
        } catch (_) { S.health.models = "err"; renderMetrics(); }
    }
    async function loadRegistry() {
        try {
            const p = await authFetch("/api/v1/memory/runtime-registry");
            S.registry = { roles: p.roles || [], tools: p.tools || [] }; S.health.registry = "ok"; rebuild();
        } catch (_) { S.health.registry = "err"; renderMetrics(); }
    }
    function refreshAll() { loadMemory(); loadWorkspace(); loadModels(); loadRegistry(); }

    function addEvent(text, meta = "", tone = "") {
        S.events.unshift({ time: new Date().toLocaleTimeString(), text: String(text).slice(0, 90), meta: String(meta).slice(0, 60), tone });
        S.events.length = Math.min(S.events.length, 40);
        renderLog();
    }
    function runtimeEdge(a, b, id) {
        if (S.nodes.has(a) && S.nodes.has(b)) {
            S.activeEdges.add(id);
            S.edges.set(id, { id, a, b, kind: "runtime" });
        }
    }
    function onGraphEvent(ev) {
        if (!ev || typeof ev !== "object" || !S.run) return;
        if (ev.status === "phase") {
            S.state = String(ev.label || "PROCESSING").toUpperCase();
            if (ev.role) {
                const id = "role:" + ev.role.toLowerCase();
                if (S.nodes.has(id)) { S.current.role = ev.role; S.activeNodes.add(id); }
            }
            addEvent(ev.label || "Agent phase", ev.role || "");
        } else if (ev.status === "model_try") {
            const id = "model:" + ev.model;
            const provider = "provider:" + String(ev.provider || ev.model.split("/")[0]).toLowerCase();
            if (!S.nodes.has(id)) { addNode(id, "model", ev.model.split("/").pop(), ev.model); }
            if (!S.nodes.has(provider)) addNode(provider, "provider", ev.provider || ev.model.split("/")[0]);
            const role = S.current.role ? "role:" + S.current.role.toLowerCase() : "";
            runtimeEdge(role, provider, "runtime:role-provider");
            runtimeEdge(provider, id, "runtime:provider-model");
            S.current.provider = ev.provider || "";
            S.current.model = ev.model || "";
            S.activeNodes.add(provider); S.activeNodes.add(id);
            S.state = "MODEL";
            addEvent("Model attempt", ev.model + " · " + (ev.provider || ""));
        } else if (ev.status === "tool_start") {
            const id = "tool:" + ev.tool_name;
            if (!S.nodes.has(id)) addNode(id, "tool", ev.tool_name, "observed runtime tool");
            const role = S.current.role ? "role:" + S.current.role.toLowerCase() : "";
            runtimeEdge(role, id, "runtime:role-tool:" + ev.tool_name);
            S.current.tool = ev.tool_name; S.activeNodes.add(id); S.state = "TOOL";
            addEvent("Tool started", ev.tool_name);
        } else if (ev.status === "tool_end") {
            S.current.tool = ""; S.state = "MODEL";
            addEvent("Tool completed", ev.tool_name || "");
        } else if (ev.status === "memory_graph") {
            S.state = "MEMORY";
            const item = ev.event || ev;
            (item.active_node_ids || []).forEach(id => {
                const key = "mem:" + id;
                if (S.nodes.has(key)) S.activeNodes.add(key);
            });
            (item.active_edge_ids || []).forEach(id => {
                const key = "memory:" + id;
                if (S.edges.has(key)) S.activeEdges.add(key);
            });
            if (ev.phase === "completed") { addEvent("Memory context ready"); loadMemory(); }
        } else if (ev.status === "reasoning" || ev.status === "streaming") {
            S.state = "GENERATING";
            if (ev.status === "streaming") addEvent("Response streaming");
        } else if (ev.status === "warning") addEvent("Warning", ev.warning || "", "warn");
        else if (ev.status === "error" || ev.status === "failed") { S.state = "FAILED"; addEvent("Execution failed", ev.error || "", "err"); }
        else if (ev.status === "done" || ev.status === "aborted") { finishRun(ev.status); return; }
        S.animUntil = performance.now() + 1800; renderReadout(); draw();
    }
    function startRun() {
        S.run = true; S.state = "STARTING"; S.current = {}; S.activeNodes.clear(); S.activeEdges.clear();
        const mode = document.getElementById("strategy-select")?.value || "";
        S.current.mode = mode;
        if (mode) S.activeNodes.add("mode:" + mode);
        addEvent("Run started", mode); renderReadout(); draw();
    }
    function finishRun(status = "completed") {
        S.run = false; S.state = status.toUpperCase();
        S.activeNodes.clear();
        S.animUntil = performance.now() + 1800;
        addEvent("Run " + status, "", status === "failed" ? "err" : "");
        renderReadout(); draw();
    }

    function renderMetrics() {
        metrics.textContent = S.nodes.size + " OBJECTS · " + S.edges.size + " LINKS · " + S.memory.totalNodes + " MEMORY";
        health.replaceChildren();
        Object.entries(S.health).forEach(([key,value]) => {
            const dot = $("i", "rf-rg-dot is-" + value); dot.title = key + ": " + value; health.append(dot);
        });
    }
    function renderReadout() {
        const values = { state: S.state, mode: S.current.mode, role: S.current.role, provider: S.current.provider, model: S.current.model, tool: S.current.tool };
        Object.entries(cells).forEach(([key,node]) => {
            node.textContent = values[key] || "—";
            node.classList.toggle("is-on", Boolean(S.run && values[key]));
        });
        host.classList.toggle("is-running", S.run);
    }
    function renderLog() {
        log.replaceChildren();
        if (!S.events.length) { log.append($("div", "rf-rg-empty", "Waiting for runtime events")); return; }
        S.events.slice(0, 5).forEach(item => {
            const row = $("div", "rf-rg-event" + (item.tone ? " is-" + item.tone : ""));
            row.append($("i", "rf-rg-event-dot"), $("span", "rf-rg-event-title", item.text), $("span", "rf-rg-event-meta", [item.time,item.meta].filter(Boolean).join(" · ")));
            log.append(row);
        });
    }
    function resize() {
        const rect = stage.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 1.5);
        canvas.width = Math.max(1, Math.round(rect.width * dpr));
        canvas.height = Math.max(1, Math.round(rect.height * dpr));
        canvas.style.width = rect.width + "px"; canvas.style.height = rect.height + "px";
        ctx.setTransform(dpr,0,0,dpr,0,0); S.dirty = true; draw();
    }
    let width = 0, height = 0;
    function draw() {
        if (document.hidden || collapsed) return;
        const rect = stage.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        if (canvas.width === 0 || width !== rect.width || height !== rect.height) {
            width = rect.width; height = rect.height; resize();
        }
        const w = width, h = height, t = performance.now();
        ctx.clearRect(0,0,w,h);
        // Only actual stored or observed runtime relationships are drawn.
        S.edges.forEach(edge => {
            const a = S.positions.get(edge.a), b = S.positions.get(edge.b);
            if (!a || !b) return;
            const active = S.activeEdges.has(edge.id);
            ctx.beginPath(); ctx.moveTo(a.x*w,a.y*h); ctx.lineTo(b.x*w,b.y*h);
            ctx.strokeStyle = active ? "rgba(7,247,122,.9)" : edge.kind === "memory" ? "rgba(100,232,161,.20)" : "rgba(130,170,210,.18)";
            ctx.lineWidth = active ? 1.6 : 0.7; ctx.stroke();
            if (active && S.run) {
                const q = (t * .00045 + hash(edge.id)) % 1;
                const x = (a.x + (b.x-a.x)*q)*w, y = (a.y + (b.y-a.y)*q)*h;
                ctx.beginPath(); ctx.arc(x,y,2.3,0,Math.PI*2); ctx.fillStyle = "#b9ffd1"; ctx.fill();
            }
        });
        S.nodes.forEach(n => {
            const p = S.positions.get(n.id); if (!p) return;
            const active = S.activeNodes.has(n.id) && S.run;
            const hovered = S.hover === n.id;
            const x = p.x*w, y = p.y*h, r = active ? 3.8 : n.kind === "memory" ? 2 : 2.7;
            if (active) { ctx.beginPath(); ctx.arc(x,y,10,0,Math.PI*2); ctx.fillStyle = "rgba(7,247,122,.12)"; ctx.fill(); }
            ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fillStyle = color(n.kind); ctx.fill();
            if (hovered || active) {
                ctx.font = "10px 'JetBrains Mono',monospace"; ctx.fillStyle = "#d8f5e7";
                ctx.fillText(n.label.slice(0,24), x+7, y-7);
            }
        });
        if (S.run || t < S.animUntil) requestAnimationFrame(draw);
    }

    let collapsed = false;
    try { collapsed = localStorage.getItem("rf_runtime_graph_collapsed") === "1"; } catch (_) {}
    function setCollapsed(value) {
        collapsed = value; host.classList.toggle("is-collapsed", value);
        collapse.textContent = value ? "Show" : "Hide";
        try { localStorage.setItem("rf_runtime_graph_collapsed", value ? "1" : "0"); } catch (_) {}
        if (!value) { width = 0; draw(); }
    }
    collapse.addEventListener("click", () => setCollapsed(!collapsed));
    expand.addEventListener("click", () => {
        const overlay = $("div", "rf-rg-overlay");
        const panel = $("section", "rf-rg rf-rg-expanded");
        const close = $("button", "rf-rg-btn", "Close");
        close.addEventListener("click", () => overlay.remove());
        const clone = canvas.cloneNode(false);
        clone.width = canvas.width; clone.height = canvas.height;
        panel.append($("div", "rf-rg-expanded-head", "RUNTIME GRAPH"), close, clone);
        overlay.append(panel); document.body.append(overlay);
        const c = clone.getContext("2d");
        const render = () => {
            if (!overlay.isConnected) return;
            c.clearRect(0,0,clone.width,clone.height);
            c.drawImage(canvas,0,0,clone.width,clone.height);
            requestAnimationFrame(render);
        };
        render();
    });
    canvas.addEventListener("pointermove", e => {
        const r = canvas.getBoundingClientRect(), x=(e.clientX-r.left)/r.width, y=(e.clientY-r.top)/r.height;
        let best="", d=0.0009;
        S.nodes.forEach(n => { const p=S.positions.get(n.id); if (!p) return; const q=(p.x-x)**2+(p.y-y)**2; if(q<d){d=q;best=n.id;} });
        S.hover=best;
        if (best) {
            const n=S.nodes.get(best); tip.textContent="";
            tip.append($("b","",n.label),$("span","",n.detail || n.kind));
            tip.style.display="flex"; tip.style.left=clamp(x*r.width+10,4,r.width-160)+"px"; tip.style.top=clamp(y*r.height+10,4,r.height-45)+"px";
        } else tip.style.display="none";
        draw();
    });
    canvas.addEventListener("pointerleave", () => { S.hover=""; tip.style.display="none"; draw(); });
    new ResizeObserver(resize).observe(stage);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { width=0; draw(); } });
    eventBus.on("generation:state", state => {
        if (state?.active && !S.run) startRun();
        else if (!state?.active && S.run) finishRun("aborted");
    });
    eventBus.on("agent:graph_event", onGraphEvent);
    eventBus.on("project.activated", () => {
        S.project=projectId(); S.run=false; S.current={}; S.activeNodes.clear(); S.activeEdges.clear(); S.events=[];
        S.memory={nodes:[],edges:[],totalNodes:0,totalEdges:0}; S.workspace=[]; S.selected={}; S.registry={roles:[],tools:[]};
        refreshAll(); renderLog(); renderReadout();
    });
    eventBus.on("auth:success", refreshAll);
    eventBus.on("session:deleted", loadMemory);
    document.getElementById("strategy-select")?.addEventListener("change", () => {
        if (!S.run) { S.current.mode=document.getElementById("strategy-select").value; renderReadout(); }
    });
    setCollapsed(collapsed); renderLog(); renderReadout(); refreshAll();
    setInterval(() => { if (!document.hidden && !S.run && !collapsed) refreshAll(); }, 30000);
})();
