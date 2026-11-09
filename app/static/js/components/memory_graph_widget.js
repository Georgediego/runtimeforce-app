/**
 * Local-first interactive 3D memory sphere.
 * Perspective-projected particles; no CDN, remote assets or heavy runtime dependency.
 */
const root = document.getElementById("rf-memory-widget");
if (root) {
    const toggle = document.getElementById("rf-memory-widget-toggle");
    const popover = document.getElementById("rf-memory-widget-popover");
    const statusEl = document.getElementById("rf-memory-widget-status");
    const countEl = document.getElementById("rf-memory-widget-count");
    const canvases = [document.getElementById("rf-memory-sphere-mini"), document.getElementById("rf-memory-sphere-large")].filter(Boolean);
    const PARTICLE_COUNT = 1120;
    const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
    const particles = Array.from({ length: PARTICLE_COUNT }, (_, index) => {
        const y = 1 - (index / (PARTICLE_COUNT - 1)) * 2;
        const radius = Math.sqrt(1 - y * y);
        const theta = GOLDEN_ANGLE * index;
        return { x: Math.cos(theta) * radius, y, z: Math.sin(theta) * radius };
    });
    const nodeIndex = new Map();
    let edges = [];
    let activeIds = new Set();
    let rotation = 0;
    let lastFrame = 0;
    let activeUntil = 0;
    let raf = 0;
    let lastProjectId = "";
    let refreshTimer = null;

    const hash = (value) => {
        let h = 2166136261;
        for (let i = 0; i < value.length; i++) { h ^= value.charCodeAt(i); h = Math.imul(h, 16777619); }
        return (h >>> 0) % PARTICLE_COUNT;
    };
    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";

    function setGraph(data) {
        nodeIndex.clear();
        (data.nodes || []).forEach((node) => { if (node.id) nodeIndex.set(String(node.id), hash(String(node.id))); });
        edges = (data.edges || []).map((edge) => ({ source: nodeIndex.get(String(edge.source)), target: nodeIndex.get(String(edge.target)) }))
            .filter((edge) => Number.isInteger(edge.source) && Number.isInteger(edge.target));
        if (countEl) countEl.textContent = (data.nodes || []).length + " NODES";
        if (statusEl) statusEl.textContent = "Idle · local SQLite";
    }
    async function loadGraph() {
        const currentProject = projectId();
        if (!currentProject) { setGraph({ nodes: [], edges: [] }); if (statusEl) statusEl.textContent = "No active project"; return; }
        try {
            const response = await fetch("/api/v1/memory/graph-status/" + encodeURIComponent(currentProject), {
                headers: token() ? { Authorization: "Bearer " + token() } : {}, cache: "no-store",
            });
            if (!response.ok) throw new Error("HTTP " + response.status);
            setGraph(await response.json());
            lastProjectId = currentProject;
        } catch (error) { if (statusEl) statusEl.textContent = "Memory graph unavailable"; }
    }
    function activateMemory(ids = []) {
        activeIds = new Set((ids || []).map(String));
        activeUntil = performance.now() + 5200;
        root.classList.add("is-active");
        if (statusEl) statusEl.textContent = activeIds.size ? "Query active · " + activeIds.size + " memory nodes" : "Query active · retrieving memory";
    }
    function drawCanvas(canvas, now) {
        const context = canvas.getContext("2d", { alpha: true });
        if (!context) return;
        const rect = canvas.getBoundingClientRect();
        const size = Math.max(24, Math.min(rect.width || canvas.width, rect.height || canvas.height));
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const pixels = Math.round(size * dpr);
        if (canvas.width !== pixels || canvas.height !== pixels) { canvas.width = pixels; canvas.height = pixels; }
        context.setTransform(dpr, 0, 0, dpr, 0, 0);
        context.clearRect(0, 0, size, size);
        const center = size / 2, radius = size * 0.405;
        const active = now < activeUntil, cos = Math.cos(rotation), sin = Math.sin(rotation);
        const ct = Math.cos(.22), st = Math.sin(.22);
        const projected = new Array(PARTICLE_COUNT);
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const p = particles[i], x = p.x * cos - p.z * sin, z0 = p.x * sin + p.z * cos;
            const y = p.y * ct - z0 * st, z = p.y * st + z0 * ct, perspective = 1.55 / (1.55 - z * .30);
            projected[i] = { x: center + x * radius * perspective, y: center + y * radius * perspective, z };
        }
        context.lineWidth = Math.max(.45, size / 280);
        for (const edge of edges) {
            const a = projected[edge.source], b = projected[edge.target];
            if (!a || !b || a.z + b.z < -.55) continue;
            const highlight = active && activeIds.size > 0 && [...activeIds].some((id) => nodeIndex.get(id) === edge.source || nodeIndex.get(id) === edge.target);
            context.strokeStyle = highlight ? "rgba(74,230,255,.42)" : "rgba(48,170,190,.075)";
            context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
        }
        const activeIndices = active ? new Set([...activeIds].map((id) => nodeIndex.get(id)).filter(Number.isInteger)) : new Set();
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const p = projected[i], selected = activeIndices.has(i), depth = (p.z + 1) / 2;
            const dot = (.45 + depth) * (size / 90);
            context.beginPath(); context.arc(p.x, p.y, selected ? dot * 2 : dot, 0, Math.PI * 2);
            context.fillStyle = selected ? "rgba(115,245,255,.98)" : `rgba(58,${145 + Math.round(depth * 75)},${190 + Math.round(depth * 55)},${.10 + depth * .58})`;
            context.shadowColor = selected ? "#36dcff" : "transparent";
            context.shadowBlur = selected ? size * .10 : 0;
            context.fill();
        }
        context.shadowBlur = 0;
    }
    function animate(now) {
        raf = 0;
        if (document.hidden) return;
        if (now - lastFrame >= 33) {
            const delta = lastFrame ? Math.min(50, now - lastFrame) : 33;
            lastFrame = now; rotation += (now < activeUntil ? .010 : .00085) * (delta / 33);
            canvases.forEach((canvas) => {
                if (canvas.id === "rf-memory-sphere-large" && popover?.classList.contains("hidden")) return;
                drawCanvas(canvas, now);
            });
            if (now >= activeUntil && root.classList.contains("is-active")) {
                root.classList.remove("is-active"); if (statusEl) statusEl.textContent = "Idle · local SQLite";
            }
        }
        raf = requestAnimationFrame(animate);
    }
    function startAnimation() { if (!raf && !document.hidden) raf = requestAnimationFrame(animate); }
    function stopAnimation() { if (raf) cancelAnimationFrame(raf); raf = 0; }

    toggle?.addEventListener("click", () => {
        const open = popover?.classList.toggle("hidden") === false;
        root.classList.toggle("is-open", open); toggle.setAttribute("aria-expanded", String(open));
        if (open) { loadGraph(); startAnimation(); }
    });
    document.addEventListener("click", (event) => {
        if (!root.contains(event.target) && !popover?.classList.contains("hidden")) {
            popover.classList.add("hidden"); root.classList.remove("is-open"); toggle?.setAttribute("aria-expanded", "false");
        }
    });
    window.addEventListener("rf:memory-graph", (event) => {
        const detail = event.detail || {};
        if (detail.project_id && detail.project_id !== projectId()) return;
        activateMemory(detail.active_node_ids || []); startAnimation();
    });
    window.addEventListener("storage", (event) => { if (event.key === "rf_active_project_id") loadGraph(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) stopAnimation(); else startAnimation(); });
    window.addEventListener("beforeunload", () => { stopAnimation(); if (refreshTimer) clearInterval(refreshTimer); });
    loadGraph(); startAnimation();
    refreshTimer = setInterval(() => {
        const currentProject = projectId();
        if (currentProject !== lastProjectId || !popover?.classList.contains("hidden")) loadGraph();
    }, 15000);
}
