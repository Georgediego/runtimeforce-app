/**
 * RuntimeForce Memory Graph — cinematic particle sphere behind chat.
 * The spherical shell is visual atmosphere; highlighted graph edges are
 * exclusively the real relationships returned by the project's SQLite graph.
 */
import { authFrontendService } from "../services/auth_frontend_service.js";
import { eventBus } from "../core/event_bus.js";

const canvas = document.getElementById("rf-memory-graph-background");
const widget = document.getElementById("rf-memory-widget");
const widgetToggle = document.getElementById("rf-memory-widget-toggle");
const widgetRestore = document.getElementById("rf-memory-widget-restore");
const widgetStatus = document.getElementById("rf-memory-widget-status");
if (canvas && widget && widgetToggle && widgetRestore) {
    const ctx = canvas.getContext("2d", { alpha: true });
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";
    const token = () => String(authFrontendService.getToken?.() || "").replace(/^Bearer\\s+/i, "");

    let nodes = [], edges = [], activeIds = new Set();
    let busy = false, rotation = 0, raf = 0, lastFetch = 0, activityUntil = 0;
    let width = 0, height = 0, dpr = 1;
    const particles = [];
    const isVisible = () => !widget.classList.contains("is-collapsed");
    const stopRendering = () => { if (raf) cancelAnimationFrame(raf); raf = 0; };
    const startRendering = () => {
        if (!isVisible() || raf) return;
        resize();
        loadGraph(true);
        loadTopology();
        raf = requestAnimationFrame(draw);
    };
    const setCollapsed = collapsed => {
        widget.classList.toggle("is-collapsed", collapsed);
        widgetRestore.classList.toggle("hidden", !collapsed);
        widgetToggle.setAttribute("aria-expanded", String(!collapsed));
        widgetToggle.setAttribute("aria-label", collapsed ? "Show memory graph" : "Hide memory graph");
        widgetToggle.title = collapsed ? "Show memory graph" : "Hide memory graph";
        try { localStorage.setItem("rf_memory_graph_collapsed", collapsed ? "1" : "0"); } catch (_) {}
        if (collapsed) {
            stopRendering();
            ctx.clearRect(0, 0, width, height);
        } else startRendering();
    };
    try { setCollapsed(localStorage.getItem("rf_memory_graph_collapsed") === "1"); } catch (_) {}

    const golden = Math.PI * (3 - Math.sqrt(5));
    let runtimeRegistry = { roles: [], tools: [] };
    let selectedModels = {};
    let liveContext = { role: "", tool: "", model: "", mode: "" };
    const topology = { nodes: [], edges: [] };

    async function loadTopology() {
        const auth = token();
        const headers = auth ? { Authorization: `Bearer ${auth}` } : {};
        try {
            const [registryResponse, modelsResponse] = await Promise.all([
                fetch("/api/v1/memory/runtime-registry", { headers }),
                fetch("/api/v1/keys/selected-models", { headers })
            ]);
            if (registryResponse.ok) runtimeRegistry = await registryResponse.json();
            if (modelsResponse.ok) selectedModels = (await modelsResponse.json()).selected_models || {};
            rebuildTopology();
        } catch (error) {
            console.debug("[Memory Graph] topology refresh skipped:", error);
        }
    }

    function rebuildTopology() {
        const items = [];
        const addRing = (kind, values, radius, phase, color) => {
            // Distribute every category over the full spherical shell (Fibonacci sphere),
            // instead of placing each category on a flat circular orbit.
            const count = Math.max(1, values.length);
            values.forEach((item, index) => {
                const y = 1 - 2 * ((index + 0.5) / count);
                const radial = Math.sqrt(Math.max(0, 1 - y * y));
                const angle = (golden * index) + phase;
                items.push({
                    id: item.id, ring: kind,
                    kind: item.id.startsWith("provider:") ? "provider" : item.id.startsWith("model:") ? "model" : kind,
                    label: item.label, detail: item.detail || kind,
                    x: Math.cos(angle) * radial * radius,
                    y: y * radius,
                    z: Math.sin(angle) * radial * radius,
                    color, angle
                });
            });
        };
        const modeSelect = document.getElementById("strategy-select");
        const modes = modeSelect ? Array.from(modeSelect.options).map(o => ({
            id: "mode:" + o.value, label: (o.textContent || o.value).replace(/[^\p{L}\p{N} ]/gu, "").trim().toUpperCase(),
            detail: "Chat mode"
        })) : [];
        const roles = (runtimeRegistry.roles || []).map(r => ({ id: "role:" + r.name, label: r.name, detail: "Agent role" }));
        const tools = (runtimeRegistry.tools || []).map(t => ({ id: "tool:" + t.name, label: t.name, detail: t.description || "Agent tool" }));
        const providers = Object.entries(selectedModels || {}).filter(([, ids]) => Array.isArray(ids) && ids.length);
        const ai = [];
        providers.forEach(([provider, ids]) => {
            ai.push({ id: "provider:" + provider, label: provider.toUpperCase(), detail: "AI provider" });
            ids.forEach(id => ai.push({ id: "model:" + id, label: String(id).split("/").pop(), detail: provider + " · " + id }));
        });
        addRing("mode", modes, 1.02, .15, "#8fc8ff");
        addRing("role", roles, 1.10, -.55, "#bd9aff");
        addRing("tool", tools, 1.19, .78, "#ffd27b");
        addRing("ai", ai, 1.28, -.28, "#67eaff");
        topology.nodes = items;
        topology.edges = [];
        providers.forEach(([provider, ids]) => ids.forEach(id => topology.edges.push(["provider:" + provider, "model:" + id])));
    }


    function resize() {
        const rect = canvas.getBoundingClientRect();
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = Math.max(1, rect.width); height = Math.max(1, rect.height);
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        buildParticles();
    }

    // Fine-grained points form the continuous spherical silhouette even when
    // a new project has only a handful of stored memory entities.
    function buildParticles() {
        particles.length = 0;
        const count = Math.max(240, Math.min(520, Math.round(Math.min(width, height) * .82)));
        for (let i = 0; i < count; i++) {
            const y = 1 - (i / (count - 1)) * 2;
            const r = Math.sqrt(1 - y * y);
            const a = golden * i;
            particles.push({
                x: Math.cos(a) * r, y, z: Math.sin(a) * r,
                size: .45 + ((i * 17) % 9) * .075,
                phase: (i * 2.399) % (Math.PI * 2)
            });
        }
    }

    function normalize(data) {
        const raw = Array.isArray(data?.nodes) ? data.nodes : [];
        nodes = raw.map(node => ({ ...node, id: String(node.id) }));
        const ids = new Set(nodes.map(n => n.id));
        edges = (Array.isArray(data?.edges) ? data.edges : []).filter(e =>
            ids.has(String(e.source)) && ids.has(String(e.target))
        ).map(e => ({ ...e, source: String(e.source), target: String(e.target) }));
        activeIds = new Set((data?.active_node_ids || []).map(String).filter(id => ids.has(id)));
    }

    async function loadGraph(force = false) {
        const pid = projectId();
        if (!isVisible() || !pid || busy || (!force && Date.now() - lastFetch < 7000)) return;
        busy = true; lastFetch = Date.now();
        try {
            const auth = token();
            const response = await fetch(`/api/v1/memory/graph-status/${encodeURIComponent(pid)}`, {
                headers: auth ? { Authorization: `Bearer ${auth}` } : {}
            });
            if (response.ok) normalize(await response.json());
        } catch (error) {
            console.debug("[Memory Graph] refresh skipped:", error);
        } finally { busy = false; }
    }

    function rotate(p, angle, tilt) {
        const cy = Math.cos(angle), sy = Math.sin(angle);
        const cx = Math.cos(tilt), sx = Math.sin(tilt);
        const x = p.x * cy - p.z * sy;
        const z = p.x * sy + p.z * cy;
        const y = p.y * cx - z * sx;
        const depth = p.y * sx + z * cx;
        const perspective = 2.65 / (2.65 + depth);
        const radius = Math.min(width, height) * .435;
        return { x: width/2 + x*radius*perspective, y: height/2 + y*radius*perspective, z: depth, scale: perspective };
    }

    function draw() {
        if (!isVisible()) { raf = 0; return; }
        if (!width || !height) { raf = requestAnimationFrame(draw); return; }
        ctx.clearRect(0, 0, width, height);
        const tilt = .30 + Math.sin(rotation * .23) * .075;
        const cx = width/2, cy = height/2, radius = Math.min(width,height)*.435;
        const glow = ctx.createRadialGradient(cx,cy,radius*.05,cx,cy,radius*1.2);
        glow.addColorStop(0,"rgba(90,120,255,.13)");
        glow.addColorStop(.48,"rgba(110,95,220,.065)");
        glow.addColorStop(1,"rgba(0,0,0,0)");
        ctx.fillStyle=glow; ctx.beginPath(); ctx.arc(cx,cy,radius*1.2,0,Math.PI*2); ctx.fill();

        // Fine point cloud, all points remain on the rotating 3D shell.
        for (const particle of particles) {
            const p = rotate(particle, rotation, tilt);
            const front = p.z > -.05;
            const twinkle = .72 + Math.sin(rotation*1.7 + particle.phase)*.22;
            ctx.beginPath();
            ctx.arc(p.x,p.y,particle.size*p.scale*(front?1:.82),0,Math.PI*2);
            ctx.fillStyle = front ? `rgba(150,180,255,${.30*twinkle})` : `rgba(100,105,205,${.10*twinkle})`;
            ctx.fill();
        }

        // Real project-memory relationships only — active edges get a bright pulse.
        const byId = new Map(nodes.map(n => [n.id,n]));
        const projected = new Map(nodes.map((n,i) => {
            const y = 1 - 2 * ((i + .5) / Math.max(1,nodes.length));
            const r = Math.sqrt(Math.max(0,1-y*y));
            const a = golden * i;
            return [n.id, rotate({ x:Math.cos(a)*r, y, z:Math.sin(a)*r },rotation,tilt)];
        }));
        // Memory links are hidden at rest. During a real graph interaction,
        // show only connected active edges as barely visible threads with a travelling pulse.
        if (Date.now() < activityUntil) {
            const now = Date.now();
            edges.forEach((edge, index) => {
                if (!activeIds.has(edge.source) && !activeIds.has(edge.target)) return;
                const a = projected.get(edge.source), b = projected.get(edge.target);
                if (!a || !b || (a.z < -.15 && b.z < -.15)) return;
                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                ctx.strokeStyle = "rgba(125,165,235,.095)";
                ctx.lineWidth = .42;
                ctx.shadowBlur = 0;
                ctx.stroke();
                const progress = ((now / 1050) + index * .173) % 1;
                const px = a.x + (b.x - a.x) * progress;
                const py = a.y + (b.y - a.y) * progress;
                const pulse = ctx.createRadialGradient(px, py, 0, px, py, 5.5);
                pulse.addColorStop(0, "rgba(205,235,255,.92)");
                pulse.addColorStop(.22, "rgba(125,195,255,.48)");
                pulse.addColorStop(1, "rgba(105,165,255,0)");
                ctx.beginPath();
                ctx.arc(px, py, 5.5, 0, Math.PI * 2);
                ctx.fillStyle = pulse;
                ctx.fill();
            });
        }
        ctx.shadowBlur = 0;

        // Actual memory entities sit on the surface as brighter identifiable nodes.
        for (const node of nodes) {
            const p=projected.get(node.id); if(!p) continue;
            const active=activeIds.has(node.id);
            const front=p.z>-.1;
            const size=(active?2.5:1.35)*p.scale;
            ctx.beginPath(); ctx.arc(p.x,p.y,size,0,Math.PI*2);
            ctx.fillStyle=active?"rgba(225,235,255,.98)":(front?"rgba(145,175,255,.84)":"rgba(100,115,205,.30)");
            ctx.shadowBlur=active?18:(front?7:1);
            ctx.shadowColor="rgba(35,255,185,.9)"; ctx.fill();
            if(active){
                ctx.beginPath(); ctx.arc(p.x,p.y,size+4+Math.sin(rotation*6)*1.5,0,Math.PI*2);
                ctx.strokeStyle="rgba(155,145,255,.48)"; ctx.lineWidth=.8; ctx.stroke();
            }
        }
        ctx.shadowBlur=0;




        // Runtime topology: real modes, registered roles/tools and saved provider/model selections.
        // These are separate orbital layers, not fabricated Memory Graph relationships.
        const orbitColors = { mode: "#8fc8ff", role: "#bd9aff", tool: "#ffd27b", ai: "#67eaff" };
        const orbitPoints = new Map();
        for (const item of topology.nodes) {
            const p = rotate(item, rotation * .72, .42);
            orbitPoints.set(item.id, p);
        }
        // No decorative orbit rails or configuration links: the shell is made of points only.
        for (const item of topology.nodes) {
            const p = orbitPoints.get(item.id);
            if (!p) continue;
            const active = (item.kind === "role" && liveContext.role && item.label.toLowerCase() === liveContext.role.toLowerCase())
                || (item.kind === "tool" && liveContext.tool && item.label.toLowerCase() === liveContext.tool.toLowerCase())
                || (item.kind === "model" && liveContext.model && item.detail.toLowerCase().includes(liveContext.model.toLowerCase()))
                || (item.kind === "mode" && liveContext.mode && item.id.endsWith(liveContext.mode.toLowerCase()));
            const color = active ? "#ffffff" : item.color;
            const size = active ? 3.2 : (item.kind === "model" ? 2.0 : item.kind === "provider" ? 3.0 : 2.6);
            ctx.beginPath(); ctx.arc(p.x, p.y, size * p.scale, 0, Math.PI * 2);
            ctx.fillStyle = color; ctx.shadowBlur = active ? 18 : 8; ctx.shadowColor = item.color;
            ctx.fill(); ctx.shadowBlur = 0;
            if (active || p.z > .25) {
                ctx.font = "600 8px 'JetBrains Mono',monospace";
                ctx.textAlign = p.x >= width / 2 ? "left" : "right";
                ctx.fillStyle = active ? "#f4f7ff" : "rgba(205,220,255,.72)";
                ctx.fillText(item.label.slice(0, 18), p.x + (p.x >= width / 2 ? 6 : -6), p.y);
            }
        }
        // Central coordinator: a visual anchor, not a synthetic memory node.
        const corePulse = busy ? 1 : .45 + Math.sin(rotation * 2) * .08;
        ctx.beginPath(); ctx.arc(width / 2, height / 2, 5.5 + corePulse * 2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(225,238,255,.95)"; ctx.shadowBlur = 22 * corePulse;
        ctx.shadowColor = "#6daeff"; ctx.fill(); ctx.shadowBlur = 0;
        ctx.font = "700 8px 'JetBrains Mono',monospace"; ctx.textAlign = "center";
        ctx.fillStyle = "rgba(225,238,255,.88)"; ctx.fillText("ORCHESTRATOR", width / 2, height / 2 + 19);

        rotation += .0032;
        if (widgetStatus) widgetStatus.textContent = nodes.length + " nodes · " + edges.length + " links";
        raf=requestAnimationFrame(draw);
    }

    // Subscribe to the real orchestrator event bus; no synthetic activity events.
    eventBus.on("agent:graph_event", event => {
        const e = event || {};
        liveContext = {
            role: String(e.role || liveContext.role || ""),
            tool: String(e.tool_name || liveContext.tool || ""),
            model: String(e.model || liveContext.model || ""),
            mode: String(e.mode || liveContext.mode || "")
        };
        const phase=String(e.label||"").toLowerCase();
        if (/memory|retriev|context/.test(phase) || ["tool_start","tool_end"].includes(e.status)) {
            activityUntil=Date.now()+1800;
            if (isVisible()) loadGraph(true);
        }
    });
    eventBus.on("agent:trace_event", event => {
        if (/memory|retriev|context/i.test(String(event?.text||""))) {
            activityUntil=Date.now()+2200;
            if (isVisible()) loadGraph(true);
        }
    });
    eventBus.on("session:selected", () => { activeIds.clear(); if (isVisible()) loadGraph(true); });
    window.addEventListener("storage", e => { if(e.key==="rf_active_project_id" && isVisible()) loadGraph(true); });
    window.addEventListener("resize", () => { if (isVisible()) resize(); });
    const observer=new ResizeObserver(() => { if (isVisible()) resize(); }); observer.observe(canvas);
    widgetToggle.addEventListener("click", () => setCollapsed(true));
    widgetRestore.addEventListener("click", () => setCollapsed(false));
    if (isVisible()) startRendering();
}
