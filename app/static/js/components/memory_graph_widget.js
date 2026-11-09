import { eventBus } from "../core/event_bus.js";

/**
 * Persistent live SQLite knowledge-graph visualizer.
 * Every displayed node, edge and activity row comes from the real memory pipeline.
 */
(() => {
    const root = document.getElementById("rf-memory-widget");
    if (!root) return;
    const canvas = document.getElementById("rf-memory-sphere");
    const statusEl = document.getElementById("rf-memory-widget-status");
    const countEl = document.getElementById("rf-memory-widget-count");
    const edgeCountEl = document.getElementById("rf-memory-widget-edges");
    const feedEl = document.getElementById("rf-memory-activity");
    const toggle = document.getElementById("rf-memory-widget-toggle");
    const body = document.getElementById("rf-memory-widget-body");
    if (!canvas) return;

    let graphNodes = [], graphEdges = [], activeIds = new Set();
    let rotation = 0, lastFrame = 0, raf = 0, lastProjectId = "";
    let flowClock = 0, lastActivityAt = 0, currentOperation = "Idle";
    let pulseStartedAt = 0, pulseUntil = 0;
    let refreshTimer = null, eventTimer = null;
    let pointerDown = false, pointerX = 0;
    const collapsedKey = "rf_memory_graph_collapsed";
    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";
    const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));

    function setGraph(data) {
        graphNodes = Array.isArray(data.nodes) ? data.nodes : [];
        graphEdges = Array.isArray(data.edges) ? data.edges : [];
        if (countEl) countEl.textContent = graphNodes.length + " NODES";
        if (edgeCountEl) edgeCountEl.textContent = graphEdges.length + " EDGES";
        if (statusEl && !root.classList.contains("is-querying")) statusEl.textContent = "SQLite graph · " + graphNodes.length + " nodes";
    }
    async function loadGraph(projectOverride = "") {
        const currentProject = projectOverride || projectId();
        if (!currentProject) {
            setGraph({nodes: [], edges: []});
            if (statusEl) statusEl.textContent = "Select a project to inspect memory";
            lastProjectId = "";
            return;
        }
        try {
            const response = await fetch("/api/v1/memory/graph-status/" + encodeURIComponent(currentProject), {
                headers: token() ? {Authorization: "Bearer " + token()} : {},
                credentials: "same-origin",
                cache: "no-store"
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.detail || ("HTTP " + response.status));
            }
            const payload = await response.json();
            setGraph(payload);
            lastProjectId = currentProject;
            if (!graphNodes.length && statusEl && !root.classList.contains("is-querying")) {
                statusEl.textContent = "Graph ready · waiting for first saved interaction";
            }
        } catch (error) {
            console.error("[MemoryGraph] Snapshot request failed:", error);
            if (statusEl) statusEl.textContent = "Graph API error · " + String(error.message || error).slice(0, 90);
        }
    }
    function appendActivity(item) {
        if (!feedEl) return;
        feedEl.querySelector(".rf-memory-activity-empty")?.remove();
        const row = document.createElement("div");
        row.className = "rf-memory-activity-row";
        const label = esc(item.label || item.operation || "Memory operation");
        const detail = esc(item.detail || "");
        const duration = Number.isFinite(Number(item.duration_ms)) ? Math.max(0, Math.round(Number(item.duration_ms))) + " ms" : "";
        row.innerHTML = '<span class="rf-memory-activity-pulse"></span><div class="rf-memory-activity-copy"><b>' + label + '</b><small>' + detail + '</small></div><time>' + duration + '</time>';
        feedEl.prepend(row);
        while (feedEl.children.length > 5) feedEl.lastElementChild.remove();
    }
    function handleMemoryEvent(detail) {
        // The WebSocket event belongs to the active chat session. Trust its project scope;
        // localStorage can lag behind project activation and must not suppress live operations.
        if (detail.phase === "started") {
            root.classList.add("is-querying");
            if (detail.project_id) lastProjectId = detail.project_id;
            currentOperation = "Memory retrieval";
            lastActivityAt = performance.now();
            if (statusEl) statusEl.textContent = "Memory query running · " + (detail.model || "orchestrator");
            appendActivity({label: "Memory query started", detail: (detail.mode || "AUTO") + " · " + (detail.model || "model")});
            pulseStartedAt = performance.now();
            pulseUntil = pulseStartedAt + 900;
            loadGraph(detail.project_id || lastProjectId);
            startAnimation();
            return;
        }
        if (detail.phase === "activity") {
            if (detail.event) {
                const item = detail.event;
                appendActivity({
                    label: (item.phase === "started" ? "▶ " : "✓ ") + (item.label || "Memory operation"),
                    detail: item.detail || "",
                    duration_ms: item.phase === "started" ? undefined : item.duration_ms,
                });
                activeIds = new Set((Array.isArray(item.active_node_ids) ? item.active_node_ids : []).map(String));
                currentOperation = item.label || item.operation || "Memory operation";
                lastActivityAt = performance.now();
                if (statusEl) {
                    statusEl.textContent = (item.phase === "started" ? "Running: " : "Completed: ")
                        + (item.label || "Memory operation");
                }
                pulseStartedAt = performance.now();
                pulseUntil = pulseStartedAt + (item.operation === "graph_traversal" ? 4200 : 2400);
                if (item.operation === "graph_persist" && item.phase === "completed") {
                    loadGraph(detail.project_id || lastProjectId);
                }
            }
            startAnimation();
            return;
        }
        if (detail.phase === "failed") {
            root.classList.remove("is-querying");
            if (statusEl) statusEl.textContent = "Memory query failed";
            appendActivity({label: "Memory query failed", detail: detail.error || "See agent trace"});
            return;
        }
        if (detail.phase === "completed") {
            if (detail.active_node_ids) activeIds = new Set(detail.active_node_ids.map(String));
            currentOperation = "Memory context ready";
            const stats = detail.graph_stats || {};
            pulseStartedAt = performance.now();
            pulseUntil = pulseStartedAt + 3200;
            loadGraph(detail.project_id || lastProjectId).finally(() => {
                root.classList.remove("is-querying");
                if (statusEl) statusEl.textContent = "Used " + activeIds.size + " nodes · " + (stats.context_tokens || 0) + " tokens";
                draw();
            });
            startAnimation();
        }
    }
    function makePositions() {
        const positions = new Map(), count = graphNodes.length;
        if (!count) return positions;
        const golden = Math.PI * (3 - Math.sqrt(5));
        graphNodes.forEach((node, index) => {
            const y = 1 - (index / Math.max(1, count - 1)) * 2;
            const radius = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = golden * index;
            positions.set(String(node.id), {x: Math.cos(theta) * radius, y, z: Math.sin(theta) * radius});
        });
        return positions;
    }
    function nowSafe() { return typeof performance !== "undefined" ? performance.now() : Date.now(); }
    function draw() {
        const ctx = canvas.getContext("2d", {alpha: true});
        if (!ctx) return;
        const rect = canvas.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) return;
        const width = rect.width, height = rect.height;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.round(width * dpr), h = Math.round(height * dpr);
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);
        const cx = width / 2, cy = height / 2, radius = Math.min(width, height) * .48;
        const cos = Math.cos(rotation), sin = Math.sin(rotation), ct = Math.cos(.28), st = Math.sin(.28);
        const projected = new Map();
        const hasData = graphNodes.length > 0;
        // Always render a full rotating wireframe globe; only actual SQLite nodes are plotted on it.
        ctx.save();
        ctx.translate(cx, cy);
        const globeGlow = ctx.createRadialGradient(-radius * .28, -radius * .32, radius * .04, 0, 0, radius * 1.12);
        globeGlow.addColorStop(0, "rgba(7,247,122,.10)");
        globeGlow.addColorStop(.72, "rgba(7,247,122,.025)");
        globeGlow.addColorStop(1, "rgba(7,247,122,0)");
        ctx.beginPath();
        ctx.arc(0, 0, radius * 1.08, 0, Math.PI * 2);
        ctx.fillStyle = globeGlow;
        ctx.fill();
        ctx.strokeStyle = "rgba(7,247,122,.52)";
        ctx.lineWidth = 1.15;
        ctx.shadowColor = "#07f77a";
        ctx.shadowBlur = 13;
        ctx.beginPath();
        ctx.arc(0, 0, radius, 0, Math.PI * 2);
        ctx.stroke();
        ctx.shadowBlur = 0;
        // Curved latitude rings.
        for (const latitude of [-1.12, -.78, -.42, 0, .42, .78, 1.12]) {
            const y = Math.sin(latitude) * radius;
            const rx = Math.cos(latitude) * radius;
            const ry = Math.max(2, rx * .22);
            ctx.beginPath();
            ctx.ellipse(0, y, rx, ry, 0, 0, Math.PI * 2);
            ctx.strokeStyle = latitude === 0 ? "rgba(7,247,122,.38)" : "rgba(93,255,166,.23)";
            ctx.lineWidth = latitude === 0 ? .95 : .7;
            ctx.stroke();
        }
        // Rotating longitude meridians create a visible spherical volume even with only a few graph nodes.
        for (let meridian = 0; meridian < 8; meridian++) {
            const angle = rotation * .55 + meridian * Math.PI / 8;
            const rx = Math.abs(Math.cos(angle)) * radius;
            ctx.beginPath();
            ctx.ellipse(0, 0, Math.max(1.2, rx), radius, 0, 0, Math.PI * 2);
            ctx.strokeStyle = "rgba(93,255,166," + (.16 + Math.abs(Math.cos(angle)) * .17) + ")";
            ctx.lineWidth = .72;
            ctx.stroke();
        }
        ctx.restore();
        let positions;
        if (hasData) {
            positions = makePositions();
        } else {
            // A visual 3D wireframe placeholder only; never counted as SQLite memory.
            positions = new Map();
            const count = 42, golden = Math.PI * (3 - Math.sqrt(5));
            for (let i = 0; i < count; i++) {
                const y = 1 - (i / (count - 1)) * 2;
                const r = Math.sqrt(1 - y * y), theta = golden * i;
                positions.set("preview-" + i, {x: Math.cos(theta) * r, y, z: Math.sin(theta) * r});
            }
        }
        for (const [id, p] of positions) {
            const x = p.x * cos - p.z * sin, z0 = p.x * sin + p.z * cos;
            const y = p.y * ct - z0 * st, z = p.y * st + z0 * ct;
            const perspective = 1.35 / (1.35 - z * .20);
            projected.set(id, {x: cx + x * radius * perspective, y: cy + y * radius * perspective, z});
        }
        const operationLive = root.classList.contains("is-querying") || nowSafe() - lastActivityAt < 2600;
        if (hasData) {
            // Only stored SQLite relationships are drawn as graph edges.
            ctx.lineWidth = .72;
            for (const edge of graphEdges) {
                const a = projected.get(String(edge.source)), b = projected.get(String(edge.target));
                if (!a || !b || a.z + b.z < -.7) continue;
                const active = activeIds.has(String(edge.source)) || activeIds.has(String(edge.target));
                ctx.strokeStyle = active ? "rgba(7,247,122,.95)" : "rgba(7,247,122," + (.12 + ((a.z + b.z + 2) / 4) * .25) + ")";
                ctx.shadowColor = active ? "#07f77a" : "#07f77a";
                ctx.shadowBlur = active ? 9 : 2;
                ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
            }
            ctx.shadowBlur = 0;
        } else {
            const ids = Array.from(projected.values());
            const previewLinks = [];
            ctx.strokeStyle = "rgba(7,247,122,.28)"; ctx.lineWidth = .85;
            for (let i = 0; i < ids.length; i++) {
                const nearest = ids.map((p,j)=>({j,d:(p.x-ids[i].x)**2+(p.y-ids[i].y)**2})).filter(v=>v.j!==i).sort((a,b)=>a.d-b.d).slice(0,2);
                for (const n of nearest) if(n.j>i){
                    ctx.beginPath();ctx.moveTo(ids[i].x,ids[i].y);ctx.lineTo(ids[n.j].x,ids[n.j].y);ctx.stroke();
                    previewLinks.push([ids[i], ids[n.j]]);
                }
            }
            // Empty-state scaffold is explicitly a visualization, never counted as stored nodes.
            // While real memory operations run, animate packets over this scaffold so the
            // retrieval pipeline remains visible even before the project has persisted nodes.
            if (operationLive) {
                previewLinks.forEach(([a,b], index) => {
                    const t = (flowClock * .00042 + (index % 17) / 17) % 1;
                    const x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t;
                    ctx.beginPath(); ctx.arc(x, y, 1.7 + Math.sin(flowClock * .007 + index) * .6, 0, Math.PI * 2);
                    ctx.fillStyle = "#9affc4"; ctx.shadowColor = "#07f77a"; ctx.shadowBlur = 14; ctx.fill();
                });
            }
        }
        const pulseProgress = pulseUntil > performance.now()
            ? Math.max(0, Math.min(1, (performance.now() - pulseStartedAt) / Math.max(1, pulseUntil - pulseStartedAt)))
            : 1;
        if (hasData && operationLive) {
            // Highlight actual touched nodes. Operations without node IDs still animate the
            // real graph as a whole (intent analysis/cache lookup/context assembly).
            const ringIds = activeIds.size ? Array.from(activeIds) : Array.from(projected.keys());
            ringIds.forEach((id, index) => {
                const p = projected.get(id);
                if (!p) return;
                const wave = (nowSafe() * .0012 + index * .173) % 1;
                ctx.beginPath();
                ctx.arc(p.x, p.y, 4 + wave * 16, 0, Math.PI * 2);
                ctx.strokeStyle = "rgba(7,247,122," + (1 - wave) * .86 + ")";
                ctx.lineWidth = 1.6;
                ctx.shadowColor = "#07f77a"; ctx.shadowBlur = 10;
                ctx.stroke();
                ctx.shadowBlur = 0;
            });
            // Packets travel along real SQLite edges while retrieval is active.
            graphEdges.forEach((edge, index) => {
                const a = projected.get(String(edge.source)), b = projected.get(String(edge.target));
                if (!a || !b) return;
                if (activeIds.size && !activeIds.has(String(edge.source)) && !activeIds.has(String(edge.target))) return;
                const t = (flowClock * .00055 + (index % 11) / 11) % 1;
                const x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t;
                ctx.beginPath();
                ctx.arc(x, y, 2.0 + Math.sin(flowClock * .006 + index) * .65, 0, Math.PI * 2);
                ctx.fillStyle = "#caffdf"; ctx.shadowColor = "#07f77a"; ctx.shadowBlur = 15; ctx.fill();
            });
        }
        let nodeIndex = 0;
        for (const [id, p] of projected) {
            const depth = (p.z + 1) / 2, active = hasData && (activeIds.has(id) || (operationLive && activeIds.size === 0));
            const twinkle = .72 + .28 * Math.sin(flowClock * .003 + nodeIndex * 1.71);
            const size = hasData ? (active ? 2.8 : 1.15) + depth * (active ? 2.7 : 1.8) : 1.8 + depth * 1.5;
            ctx.beginPath(); ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
            ctx.fillStyle = active ? "#fff0fb" : "rgba(93,255,166," + ((hasData ? .40 + depth * .58 : .42 + depth * .48) * twinkle) + ")";
            ctx.shadowColor = active ? "#07f77a" : "#07f77a";
            ctx.shadowBlur = active ? 19 : 4 + depth * 5; ctx.fill();
            if (active) {
                ctx.beginPath(); ctx.arc(p.x, p.y, size + 4 + (Math.sin(flowClock * .009 + nodeIndex) + 1) * 2, 0, Math.PI * 2);
                ctx.strokeStyle = "rgba(7,247,122,.62)"; ctx.lineWidth = 1;
                ctx.shadowColor = "#07f77a"; ctx.shadowBlur = 12; ctx.stroke();
            }
            nodeIndex++;
        }
        ctx.shadowBlur = 0;
        ctx.shadowBlur = 0; ctx.textAlign = "center";
        ctx.fillStyle = "rgba(210,255,226,.96)"; ctx.font = "600 11px Inter, sans-serif";
        ctx.fillText(hasData ? String(graphNodes.length) : "◌", cx, cy + 3);
        ctx.fillStyle = "rgba(133,210,162,.86)"; ctx.font = "7px JetBrains Mono, monospace";
        ctx.fillText(hasData ? "SQLITE MEMORY" : "WAITING FOR MEMORY", cx, cy + 16);
    }
    function animate(now) {
        raf = 0;
        if (document.hidden || root.classList.contains("is-collapsed")) return;
        if (now - lastFrame >= 16) {
            const delta = lastFrame ? Math.min(50, now - lastFrame) : 16;
            lastFrame = now;
            const querying = root.classList.contains("is-querying");
            // Never freeze: slow idle orbit, visibly faster while the orchestrator accesses memory.
            rotation += (querying ? .0055 : .00075) * (delta / 16);
            flowClock += delta;
            draw();
        }
        raf = requestAnimationFrame(animate);
    }
    function startAnimation() { if (!raf && !document.hidden && !root.classList.contains("is-collapsed")) raf = requestAnimationFrame(animate); }
    function stopAnimation() { if (raf) cancelAnimationFrame(raf); raf = 0; }

    function setCollapsed(collapsed) {
        root.classList.toggle("is-collapsed", collapsed);
        if (toggle) {
            toggle.setAttribute("aria-expanded", String(!collapsed));
            toggle.setAttribute("aria-label", collapsed ? "Show memory graph" : "Hide memory graph");
            toggle.title = collapsed ? "Show memory graph" : "Hide memory graph";
        }
        try { localStorage.setItem(collapsedKey, collapsed ? "1" : "0"); } catch (_) {}
        if (!collapsed) startAnimation();
    }
    toggle?.addEventListener("click", () => setCollapsed(!root.classList.contains("is-collapsed")));
    try { setCollapsed(localStorage.getItem(collapsedKey) === "1"); } catch (_) { setCollapsed(false); }
    canvas.addEventListener("pointerdown", event => { pointerDown = true; pointerX = event.clientX; canvas.setPointerCapture?.(event.pointerId); });
    canvas.addEventListener("pointermove", event => {
        if (!pointerDown) return;
        rotation += (event.clientX - pointerX) * .008;
        pointerX = event.clientX;
        draw();
    });
    canvas.addEventListener("pointerup", () => { pointerDown = false; });
    canvas.addEventListener("pointercancel", () => { pointerDown = false; });
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => { draw(); startAnimation(); }).observe(canvas);
    // ChatWSClient dispatches this native event directly for every memory_graph WebSocket
    // frame. This avoids relying on the chat UI secondary EventBus callback.
    window.addEventListener("rf:memory-graph", event => {
        if (event.detail?.status === "memory_graph") handleMemoryEvent(event.detail);
    });
    eventBus.on("project.activated", project => {
        lastProjectId = project || projectId();
        graphNodes = [];
        graphEdges = [];
        setGraph({nodes: [], edges: []});
        loadGraph(lastProjectId);
    });
    window.addEventListener("storage", event => { if (event.key === "rf_active_project_id") loadGraph(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) stopAnimation(); else startAnimation(); });
    window.addEventListener("beforeunload", () => {
        stopAnimation();
        if (refreshTimer) clearInterval(refreshTimer);
        if (eventTimer) clearTimeout(eventTimer);
    });
    loadGraph().finally(() => { draw(); startAnimation(); });
    startAnimation();
    refreshTimer = setInterval(loadGraph, 12000);
})();
