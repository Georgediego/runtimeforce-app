/**
 * RuntimeForce Memory Graph — cinematic particle sphere behind chat.
 * The spherical shell is visual atmosphere; highlighted graph edges are
 * exclusively the real relationships returned by the project's SQLite graph.
 */
import { authFrontendService } from "../services/auth_frontend_service.js";
import { eventBus } from "../core/event_bus.js";

const canvas = document.getElementById("rf-memory-graph-background");
if (canvas) {
    const ctx = canvas.getContext("2d", { alpha: true });
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";
    const token = () => String(authFrontendService.getToken?.() || "").replace(/^Bearer\\s+/i, "");

    let nodes = [], edges = [], activeIds = new Set();
    let busy = false, rotation = 0, raf = 0, lastFetch = 0, activityUntil = 0;
    let width = 0, height = 0, dpr = 1;
    const particles = [];
    const golden = Math.PI * (3 - Math.sqrt(5));

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
        if (!pid || busy || (!force && Date.now() - lastFetch < 7000)) return;
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
        if (!width || !height) { raf = requestAnimationFrame(draw); return; }
        ctx.clearRect(0, 0, width, height);
        const tilt = .30 + Math.sin(rotation * .23) * .075;
        const cx = width/2, cy = height/2, radius = Math.min(width,height)*.435;
        const glow = ctx.createRadialGradient(cx,cy,radius*.05,cx,cy,radius*1.2);
        glow.addColorStop(0,"rgba(0,255,170,.105)");
        glow.addColorStop(.48,"rgba(0,180,125,.055)");
        glow.addColorStop(1,"rgba(0,0,0,0)");
        ctx.fillStyle=glow; ctx.beginPath(); ctx.arc(cx,cy,radius*1.2,0,Math.PI*2); ctx.fill();

        // Fine point cloud, all points remain on the rotating 3D shell.
        for (const particle of particles) {
            const p = rotate(particle, rotation, tilt);
            const front = p.z > -.05;
            const twinkle = .72 + Math.sin(rotation*1.7 + particle.phase)*.22;
            ctx.beginPath();
            ctx.arc(p.x,p.y,particle.size*p.scale*(front?1:.82),0,Math.PI*2);
            ctx.fillStyle = front ? `rgba(80,255,195,${.30*twinkle})` : `rgba(45,180,140,${.10*twinkle})`;
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
        for (const edge of edges) {
            const a=projected.get(edge.source), b=projected.get(edge.target);
            if (!a || !b) continue;
            const hot=activeIds.has(edge.source)||activeIds.has(edge.target);
            const pulse=hot ? .65 + (Math.sin(rotation*5 + (Number(edge.weight)||1)*3)+1)*.16 : .10;
            ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
            ctx.strokeStyle=hot ? `rgba(50,255,190,${pulse})` : "rgba(55,205,155,.13)";
            ctx.lineWidth=hot?1.35:.55;
            ctx.shadowBlur=hot?14:0; ctx.shadowColor="rgba(35,255,185,.9)"; ctx.stroke();
        }
        ctx.shadowBlur=0;

        // Actual memory entities sit on the surface as brighter identifiable nodes.
        for (const node of nodes) {
            const p=projected.get(node.id); if(!p) continue;
            const active=activeIds.has(node.id);
            const front=p.z>-.1;
            const size=(active?2.5:1.35)*p.scale;
            ctx.beginPath(); ctx.arc(p.x,p.y,size,0,Math.PI*2);
            ctx.fillStyle=active?"rgba(190,255,230,.98)":(front?"rgba(90,255,195,.82)":"rgba(55,185,145,.28)");
            ctx.shadowBlur=active?18:(front?7:1);
            ctx.shadowColor="rgba(35,255,185,.9)"; ctx.fill();
            if(active){
                ctx.beginPath(); ctx.arc(p.x,p.y,size+4+Math.sin(rotation*6)*1.5,0,Math.PI*2);
                ctx.strokeStyle="rgba(75,255,200,.42)"; ctx.lineWidth=.8; ctx.stroke();
            }
        }
        ctx.shadowBlur=0;

        // Short orbital streaks give the shell a living, dimensional motion.
        if (Date.now() < activityUntil) {
            const sweep=(rotation*1.7)%(Math.PI*2);
            ctx.beginPath(); ctx.ellipse(cx,cy,radius*1.02,radius*.34,sweep,Math.PI*1.12,Math.PI*1.72);
            ctx.strokeStyle="rgba(65,255,195,.26)"; ctx.lineWidth=1.1;
            ctx.shadowBlur=12; ctx.shadowColor="rgba(40,255,190,.8)"; ctx.stroke(); ctx.shadowBlur=0;
        }
        ctx.beginPath(); ctx.arc(cx,cy,radius,0,Math.PI*2);
        ctx.strokeStyle="rgba(75,225,175,.18)"; ctx.lineWidth=.8; ctx.stroke();

        rotation += .0032;
        raf=requestAnimationFrame(draw);
    }

    // Subscribe to the real orchestrator event bus; no synthetic activity events.
    eventBus.on("agent:graph_event", event => {
        const e=event||{};
        const phase=String(e.label||"").toLowerCase();
        if (/memory|retriev|context/.test(phase) || ["tool_start","tool_end"].includes(e.status)) {
            activityUntil=Date.now()+1800;
            activeIds = new Set(edges.flatMap(edge => [edge.source,edge.target]));
            loadGraph(true);
        }
    });
    eventBus.on("agent:trace_event", event => {
        if (/memory|retriev|context/i.test(String(event?.text||""))) {
            activityUntil=Date.now()+2200;
            activeIds = new Set(edges.flatMap(edge => [edge.source,edge.target]));
            loadGraph(true);
        }
    });
    eventBus.on("session:selected", () => { activeIds.clear(); loadGraph(true); });
    window.addEventListener("storage", e => { if(e.key==="rf_active_project_id") loadGraph(true); });
    window.addEventListener("resize",resize);
    const observer=new ResizeObserver(resize); observer.observe(canvas);
    resize(); loadGraph(true); raf=requestAnimationFrame(draw);
}
