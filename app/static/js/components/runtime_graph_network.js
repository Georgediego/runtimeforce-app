import { eventBus } from "../core/event_bus.js";

(() => {
    const root = document.getElementById("rf-memory-widget");
    const canvas = document.getElementById("rf-network-canvas");
    if (!root || !canvas) return;

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    const token = () => (
        localStorage.getItem("rf_jwt_token") ||
        localStorage.getItem("access_token") ||
        ""
    ).replace(/^Bearer\\s+/i, "");

    const projectId = () => localStorage.getItem("rf_active_project_id") || "";

    const state = {
        nodes: new Map(),
        edges: new Map(),
        positions: new Map(),
        activeNodes: new Map(),
        activeEdges: new Map(),
        rotation: 0,
        frame: 0,
        width: 1,
        height: 1,
        dpr: 1,
        lastFrame: 0,
        running: false,
        disposed: false
    };

    function api(url) {
        const headers = {};
        const jwt = token();
        if (jwt) headers.Authorization = "Bearer " + jwt;

        return fetch(url, {
            headers,
            credentials: "same-origin",
            cache: "no-store"
        }).then(response => {
            if (!response.ok) throw new Error("HTTP " + response.status);
            return response.json();
        });
    }

    function setTopology(data) {
        state.nodes.clear();
        state.edges.clear();
        state.positions.clear();

        (data.nodes || []).forEach(node => {
            if (!node || node.id == null) return;
            const id = String(node.id);
            state.nodes.set(id, node);
        });

        (data.edges || []).forEach(edge => {
            if (!edge || edge.id == null || edge.source == null || edge.target == null) return;
            const id = String(edge.id);
            const source = String(edge.source);
            const target = String(edge.target);
            if (!state.nodes.has(source) || !state.nodes.has(target) || source === target) return;
            state.edges.set(id, { id, source, target });
        });

        const nodes = Array.from(state.nodes.keys()).sort();
        const count = Math.max(1, nodes.length);

        nodes.forEach((id, index) => {
            const y = 1 - (2 * (index + 0.5)) / count;
            const radius = Math.sqrt(Math.max(0, 1 - y * y));
            const angle = index * 2.399963229728653;
            state.positions.set(id, {
                x: Math.cos(angle) * radius,
                y,
                z: Math.sin(angle) * radius
            });
        });

        schedule();
    }

    async function loadGraph() {
        const id = projectId();
        if (!id) {
            setTopology({ nodes: [], edges: [] });
            return;
        }

        try {
            const data = await api("/api/v1/memory/graph-status/" + encodeURIComponent(id));
            if (id !== projectId()) return;
            setTopology(data);
        } catch (error) {
            // Keep the last valid graph; never fabricate replacement topology.
        }
    }

    function activateMemoryEvent(event) {
        if (!event || typeof event !== "object") return;

        (event.active_node_ids || []).forEach(value => {
            const id = String(value);
            if (state.nodes.has(id)) state.activeNodes.set(id, performance.now());
        });

        (event.active_edge_ids || []).forEach(value => {
            const id = String(value);
            if (state.edges.has(id)) state.activeEdges.set(id, performance.now());
        });

        schedule();
    }

    function onGraphEvent(event) {
        if (!event || event.status !== "memory_graph") return;

        const payload = event.event && typeof event.event === "object"
            ? event.event
            : event;

        if (event.phase === "activity" || event.phase === "completed") {
            activateMemoryEvent(payload);
        }
    }

    function project(point, centerX, centerY, radius) {
        const cosine = Math.cos(state.rotation);
        const sine = Math.sin(state.rotation);
        const x = point.x * cosine - point.z * sine;
        const z = point.x * sine + point.z * cosine;
        const perspective = 3.5 / (3.5 + z * 0.34);

        return {
            x: centerX + x * radius * perspective,
            y: centerY - point.y * radius * perspective,
            z,
            perspective
        };
    }

    function draw(timestamp) {
        const width = state.width;
        const height = state.height;
        const centerX = width * 0.5;
        const centerY = height * 0.5;
        const radius = Math.max(1, Math.min(width * 0.43, height * 0.43));

        ctx.fillStyle = "#050912";
        ctx.fillRect(0, 0, width, height);

        const projected = new Map();
        state.nodes.forEach((node, id) => {
            const position = state.positions.get(id);
            if (position) projected.set(id, project(position, centerX, centerY, radius));
        });

        // Only backend-reported graph edges are rendered, and only while active.
        state.activeEdges.forEach((startedAt, edgeId) => {
            const edge = state.edges.get(edgeId);
            if (!edge) return;

            const from = projected.get(edge.source);
            const to = projected.get(edge.target);
            if (!from || !to) return;

            const age = Math.max(0, timestamp - startedAt);
            const opacity = Math.max(0.18, 1 - age / 2200);

            ctx.beginPath();
            ctx.moveTo(from.x, from.y);
            ctx.lineTo(to.x, to.y);
            ctx.strokeStyle = "rgba(255, 207, 119, " + (0.78 * opacity) + ")";
            ctx.lineWidth = 1.15;
            ctx.shadowColor = "rgba(255, 196, 92, " + (0.65 * opacity) + ")";
            ctx.shadowBlur = 8;
            ctx.stroke();
            ctx.shadowBlur = 0;

            const progress = (age % 900) / 900;
            const pulseX = from.x + (to.x - from.x) * progress;
            const pulseY = from.y + (to.y - from.y) * progress;

            ctx.beginPath();
            ctx.arc(pulseX, pulseY, 2.1, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(255, 235, 190, " + opacity + ")";
            ctx.shadowColor = "#ffd17a";
            ctx.shadowBlur = 10;
            ctx.fill();
            ctx.shadowBlur = 0;
        });

        const ordered = Array.from(state.nodes.keys())
            .map(id => ({ id, point: projected.get(id) }))
            .filter(item => item.point)
            .sort((a, b) => a.point.z - b.point.z);

        ordered.forEach(({ id, point }) => {
            const activeAt = state.activeNodes.get(id);
            const age = activeAt == null ? Infinity : Math.max(0, timestamp - activeAt);
            const intensity = Math.max(0, 1 - age / 2200);
            const depth = Math.max(0, Math.min(1, (point.z + 1) / 2));
            const size = 1.05 + depth * 0.75 + intensity * 0.85;

            ctx.beginPath();
            ctx.arc(point.x, point.y, size, 0, Math.PI * 2);
            ctx.fillStyle = intensity > 0
                ? "rgba(255, 222, 157, " + Math.max(0.35, intensity) + ")"
                : "rgba(151, 190, 226, " + (0.38 + depth * 0.48) + ")";

            if (intensity > 0) {
                ctx.shadowColor = "#ffd17a";
                ctx.shadowBlur = 5 + intensity * 10;
            }
            ctx.fill();
            ctx.shadowBlur = 0;
        });

        state.activeNodes.forEach((startedAt, id) => {
            if (timestamp - startedAt > 2200) state.activeNodes.delete(id);
        });
        state.activeEdges.forEach((startedAt, id) => {
            if (timestamp - startedAt > 2200) state.activeEdges.delete(id);
        });
    }

    function schedule() {
        if (!state.frame && !document.hidden && !state.disposed) {
            state.frame = requestAnimationFrame(frame);
        }
    }

    function frame(timestamp) {
        state.frame = 0;
        if (state.disposed || document.hidden) return;

        const delta = state.lastFrame ? Math.min(40, timestamp - state.lastFrame) : 16;
        state.lastFrame = timestamp;
        state.rotation += 0.00011 * delta;

        draw(timestamp);
        state.frame = requestAnimationFrame(frame);
    }

    function resize() {
        const bounds = canvas.getBoundingClientRect();
        state.dpr = Math.min(window.devicePixelRatio || 1, 1.5);
        state.width = Math.max(1, bounds.width);
        state.height = Math.max(1, bounds.height);

        canvas.width = Math.round(state.width * state.dpr);
        canvas.height = Math.round(state.height * state.dpr);
        ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
        schedule();
    }

    function collapse(value) {
        root.classList.toggle("is-collapsed", value);
        const button = document.getElementById("rf-memory-widget-toggle");
        if (button) {
            button.setAttribute("aria-expanded", String(!value));
            button.setAttribute("aria-label", value ? "Show Runtime Graph" : "Hide Runtime Graph");
        }

        try {
            localStorage.setItem("rf_runtime_graph_collapsed", value ? "1" : "0");
        } catch (error) {}

        if (!value) resize();
    }

    document.getElementById("rf-memory-widget-toggle")?.addEventListener("click", () => {
        collapse(!root.classList.contains("is-collapsed"));
    });

    eventBus.on("agent:graph_event", onGraphEvent);

    eventBus.on("generation:state", value => {
        const active = Boolean(value && value.active);
        if (active && !state.running) {
            state.activeNodes.clear();
            state.activeEdges.clear();
        }
        state.running = active;
        schedule();
    });

    eventBus.on("project.activated", project => {
        const id = typeof project === "string" ? project : (project && project.id) || "";
        if (id) localStorage.setItem("rf_active_project_id", id);
        else localStorage.removeItem("rf_active_project_id");

        state.activeNodes.clear();
        state.activeEdges.clear();
        setTopology({ nodes: [], edges: [] });
        loadGraph();
    });

    eventBus.on("auth:success", loadGraph);
    eventBus.on("session:selected", () => {
        state.activeNodes.clear();
        state.activeEdges.clear();
        schedule();
    });

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    document.addEventListener("visibilitychange", () => {
        if (document.hidden && state.frame) {
            cancelAnimationFrame(state.frame);
            state.frame = 0;
        } else if (!document.hidden) {
            loadGraph();
            schedule();
        }
    });

    window.addEventListener("pagehide", () => {
        state.disposed = true;
        observer.disconnect();
        if (state.frame) cancelAnimationFrame(state.frame);
    }, { once: true });

    try {
        collapse(localStorage.getItem("rf_runtime_graph_collapsed") === "1");
    } catch (error) {
        collapse(false);
    }

    resize();
    loadGraph();
    schedule();
})();
