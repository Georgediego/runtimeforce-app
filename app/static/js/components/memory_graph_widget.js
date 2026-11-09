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
    if (!canvas) return;

    let graphNodes = [], graphEdges = [], activeIds = new Set();
    let rotation = 0, lastFrame = 0, raf = 0, lastProjectId = "";
    let refreshTimer = null, eventTimer = null;
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
    async function loadGraph() {
        const currentProject = projectId();
        if (!currentProject) {
            setGraph({nodes: [], edges: []});
            if (statusEl) statusEl.textContent = "Select a project to inspect memory";
            lastProjectId = "";
            return;
        }
        try {
            const response = await fetch("/api/v1/memory/graph-status/" + encodeURIComponent(currentProject), {
                headers: token() ? {Authorization: "Bearer " + token()} : {}, cache: "no-store"
            });
            if (!response.ok) throw new Error("HTTP " + response.status);
            setGraph(await response.json());
            lastProjectId = currentProject;
        } catch (error) {
            if (statusEl) statusEl.textContent = "Memory graph unavailable";
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
        if (detail.project_id && detail.project_id !== projectId()) return;
        if (detail.phase === "started") {
            root.classList.add("is-querying");
            if (statusEl) statusEl.textContent = "Memory query running · " + (detail.model || "orchestrator");
            appendActivity({label: "Memory query started", detail: (detail.mode || "AUTO") + " · " + (detail.model || "model")});
            return;
        }
        if (detail.phase === "activity") {
            if (detail.event) {
                appendActivity(detail.event);
                if (detail.event.active_node_ids?.length) activeIds = new Set(detail.event.active_node_ids.map(String));
                if (statusEl) statusEl.textContent = (detail.event.label || "Memory operation") + " · " + (detail.event.duration_ms ?? 0) + " ms";
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
            const stats = detail.graph_stats || {};
            loadGraph().finally(() => {
                root.classList.remove("is-querying");
                if (statusEl) statusEl.textContent = "Used " + activeIds.size + " nodes · " + (stats.context_tokens || 0) + " tokens";
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
    function draw() {
        const ctx = canvas.getContext("2d", {alpha: true});
        if (!ctx) return;
        const rect = canvas.getBoundingClientRect();
        const width = Math.max(80, rect.width || 190), height = Math.max(80, rect.height || 150);
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.round(width * dpr), h = Math.round(height * dpr);
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);
        const cx = width / 2, cy = height / 2, radius = Math.min(width, height) * .39;
        const cos = Math.cos(rotation), sin = Math.sin(rotation), ct = Math.cos(.28), st = Math.sin(.28);
        const projected = new Map();
        ctx.save(); ctx.translate(cx, cy); ctx.strokeStyle = "rgba(75,205,190,.10)"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.ellipse(0, 0, radius, radius * .34, 0, 0, Math.PI * 2); ctx.stroke();
        ctx.beginPath(); ctx.ellipse(0, 0, radius * .58, radius, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
        for (const [id, p] of makePositions()) {
            const x = p.x * cos - p.z * sin, z0 = p.x * sin + p.z * cos;
            const y = p.y * ct - z0 * st, z = p.y * st + z0 * ct;
            const perspective = 1.35 / (1.35 - z * .20);
            projected.set(id, {x: cx + x * radius * perspective, y: cy + y * radius * perspective, z});
        }
        ctx.lineWidth = 1;
        for (const edge of graphEdges) {
            const a = projected.get(String(edge.source)), b = projected.get(String(edge.target));
            if (!a || !b || a.z + b.z < -.7) continue;
            const active = activeIds.has(String(edge.source)) || activeIds.has(String(edge.target));
            ctx.strokeStyle = active ? "rgba(75,231,255,.78)" : "rgba(54,190,170,.20)";
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
        for (const [id, p] of projected) {
            const depth = (p.z + 1) / 2, active = activeIds.has(id), size = (active ? 3.1 : 1.4) + depth * 1.7;
            ctx.beginPath(); ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
            ctx.fillStyle = active ? "#71efff" : "rgba(74,220,185," + (.35 + depth * .58) + ")";
            ctx.shadowColor = active ? "#43eaff" : "rgba(35,220,170,.25)";
            ctx.shadowBlur = active ? 15 : 4; ctx.fill();
        }
        ctx.shadowBlur = 0; ctx.textAlign = "center";
        ctx.fillStyle = "rgba(220,255,245,.88)"; ctx.font = "600 10px Inter, sans-serif";
        ctx.fillText(String(graphNodes.length), cx, cy + 3);
        ctx.fillStyle = "rgba(135,185,170,.75)"; ctx.font = "7px JetBrains Mono, monospace";
        ctx.fillText("MEMORY NODES", cx, cy + 15);
    }
    function animate(now) {
        raf = 0;
        if (document.hidden) return;
        if (now - lastFrame >= 33) {
            const delta = lastFrame ? Math.min(50, now - lastFrame) : 33;
            lastFrame = now;
            rotation += (root.classList.contains("is-querying") ? .009 : .0012) * (delta / 33);
            draw();
        }
        raf = requestAnimationFrame(animate);
    }
    function startAnimation() { if (!raf && !document.hidden) raf = requestAnimationFrame(animate); }
    function stopAnimation() { if (raf) cancelAnimationFrame(raf); raf = 0; }

    window.addEventListener("rf:memory-graph", event => handleMemoryEvent(event.detail || {}));
    window.addEventListener("storage", event => { if (event.key === "rf_active_project_id") loadGraph(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) stopAnimation(); else startAnimation(); });
    window.addEventListener("beforeunload", () => {
        stopAnimation();
        if (refreshTimer) clearInterval(refreshTimer);
        if (eventTimer) clearTimeout(eventTimer);
    });
    loadGraph(); startAnimation();
    refreshTimer = setInterval(loadGraph, 12000);
})();
