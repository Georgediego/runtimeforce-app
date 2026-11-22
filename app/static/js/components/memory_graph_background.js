/**
 * RuntimeForce Memory Graph — animated 3D sphere behind chat.
 * Renders every persisted project node; only stored relationships are drawn as edges.
 */
import { authFrontendService } from "../services/auth_frontend_service.js";

const canvas = document.getElementById("rf-memory-graph-background");
if (canvas) {
    const ctx = canvas.getContext("2d", { alpha: true });
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";
    const token = () => {
        const value = authFrontendService.getToken?.() || "";
        return value.replace(/^Bearer\\s+/i, "");
    };

    let nodes = [];
    let edges = [];
    let activeIds = new Set();
    let querying = false;
    let rotation = 0;
    let frame = 0;
    let lastFetch = 0;
    let resizeObserver = null;
    const pointById = new Map();

    function resize() {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.max(1, Math.round(rect.width * dpr));
        canvas.height = Math.max(1, Math.round(rect.height * dpr));
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function fibonacciSphere(count) {
        const points = [];
        const golden = Math.PI * (3 - Math.sqrt(5));
        for (let i = 0; i < count; i++) {
            const y = 1 - (i / Math.max(1, count - 1)) * 2;
            const radius = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = golden * i;
            points.push({ x: Math.cos(theta) * radius, y, z: Math.sin(theta) * radius });
        }
        return points;
    }

    function normalizeGraph(data) {
        const rawNodes = Array.isArray(data?.nodes) ? data.nodes : [];
        const rawEdges = Array.isArray(data?.edges) ? data.edges : [];
        const positions = fibonacciSphere(rawNodes.length);
        nodes = rawNodes.map((node, i) => ({
            ...node,
            x: positions[i].x, y: positions[i].y, z: positions[i].z
        }));
        pointById.clear();
        nodes.forEach(node => pointById.set(String(node.id), node));
        edges = rawEdges.filter(edge =>
            pointById.has(String(edge.source)) && pointById.has(String(edge.target))
        );
        activeIds = new Set((data?.active_node_ids || []).map(String));
    }

    async function loadGraph(force = false) {
        const pid = projectId();
        if (!pid || querying || (!force && Date.now() - lastFetch < 5000)) return;
        querying = true;
        lastFetch = Date.now();
        try {
            const auth = token();
            const response = await fetch(`/api/v1/memory/graph-status/${encodeURIComponent(pid)}`, {
                headers: auth ? { Authorization: `Bearer ${auth}` } : {}
            });
            if (!response.ok) return;
            normalizeGraph(await response.json());
        } catch (error) {
            console.debug("[Memory Graph] refresh skipped:", error);
        } finally {
            querying = false;
        }
    }

    function project(point, width, height, radius, cosY, sinY, cosX, sinX) {
        const x1 = point.x * cosY - point.z * sinY;
        const z1 = point.x * sinY + point.z * cosY;
        const y1 = point.y * cosX - z1 * sinX;
        const z2 = point.y * sinX + z1 * cosX;
        const perspective = 2.7 / (2.7 + z2);
        return {
            x: width / 2 + x1 * radius * perspective,
            y: height / 2 + y1 * radius * perspective,
            z: z2,
            scale: perspective
        };
    }

    function draw() {
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        if (!width || !height) return;
        ctx.clearRect(0, 0, width, height);
        const radius = Math.min(width, height) * .405;
        const cosY = Math.cos(rotation);
        const sinY = Math.sin(rotation);
        const cosX = Math.cos(.24 + Math.sin(rotation * .32) * .08);
        const sinX = Math.sin(.24 + Math.sin(rotation * .32) * .08);
        const projected = new Map();

        // Faint spherical latitude/longitude atmosphere, not fake graph relationships.
        const glow = ctx.createRadialGradient(width/2,height/2,radius*.12,width/2,height/2,radius*1.15);
        glow.addColorStop(0,"rgba(9,90,67,.09)");
        glow.addColorStop(.72,"rgba(7,54,43,.035)");
        glow.addColorStop(1,"rgba(0,0,0,0)");
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(width/2,height/2,radius*1.15,0,Math.PI*2); ctx.fill();

        for (const node of nodes) projected.set(String(node.id), project(node,width,height,radius,cosY,sinY,cosX,sinX));

        // Draw only relationships returned by the real SQLite graph endpoint.
        for (const edge of edges) {
            const a = projected.get(String(edge.source));
            const b = projected.get(String(edge.target));
            if (!a || !b) continue;
            const front = (a.z + b.z) / 2;
            const highlighted = activeIds.has(String(edge.source)) || activeIds.has(String(edge.target));
            const alpha = (front > 0 ? .22 : .075) + (highlighted ? .55 : 0);
            ctx.beginPath();
            ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
            ctx.strokeStyle = highlighted ? `rgba(38,245,190,${Math.min(.95,alpha)})` : `rgba(40,190,150,${alpha})`;
            ctx.lineWidth = highlighted ? 1.25 : .55;
            ctx.shadowBlur = highlighted ? 9 : 0;
            ctx.shadowColor = "rgba(32,245,190,.8)";
            ctx.stroke();
        }
        ctx.shadowBlur = 0;

        const ordered = [...nodes].sort((a,b) => (projected.get(String(a.id))?.z || 0) - (projected.get(String(b.id))?.z || 0));
        for (const node of ordered) {
            const p = projected.get(String(node.id));
            if (!p) continue;
            const active = activeIds.has(String(node.id));
            const front = p.z > -.05;
            const size = (active ? 2.4 : 1.05 + Math.min(1.3, Number(node.usage_count || 0) * .035)) * p.scale;
            const alpha = (front ? .9 : .25) * (active ? 1 : .82);
            ctx.beginPath(); ctx.arc(p.x,p.y,size,0,Math.PI*2);
            ctx.fillStyle = active ? `rgba(90,255,210,${alpha})` : `rgba(95,225,185,${alpha})`;
            ctx.shadowBlur = active ? 15 : (front ? 5 : 1);
            ctx.shadowColor = active ? "rgba(58,255,207,.95)" : "rgba(40,220,170,.45)";
            ctx.fill();
        }
        ctx.shadowBlur = 0;

        // A quiet luminous outer rim gives the sphere its dimensional silhouette.
        ctx.beginPath(); ctx.arc(width/2,height/2,radius,0,Math.PI*2);
        ctx.strokeStyle = "rgba(70,205,165,.12)"; ctx.lineWidth = .8; ctx.stroke();
        rotation += .0028;
        frame = requestAnimationFrame(draw);
    }

    window.addEventListener("rf:memory-graph", event => {
        const detail = event.detail || {};
        if (Array.isArray(detail.nodes)) normalizeGraph(detail);
        else if (Array.isArray(detail.active_node_ids)) activeIds = new Set(detail.active_node_ids.map(String));
        loadGraph(true);
    });
    window.addEventListener("rf:agent-stop-ack", () => { activeIds.clear(); });
    window.addEventListener("storage", event => {
        if (event.key === "rf_active_project_id") loadGraph(true);
    });
    window.addEventListener("resize", resize);
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    resize();
    loadGraph(true);
    setInterval(() => loadGraph(), 5000);
    frame = requestAnimationFrame(draw);
}
