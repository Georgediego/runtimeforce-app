import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
import { eventBus } from "../core/event_bus.js";

(() => {
    const root = document.getElementById("rf-memory-widget");
    const canvas = document.getElementById("rf-memory-sphere");
    if (!root || !canvas) return;

    const statusEl = document.getElementById("rf-memory-widget-status");
    const countEl = document.getElementById("rf-memory-widget-count");
    const edgeCountEl = document.getElementById("rf-memory-widget-edges");
    const feedEl = document.getElementById("rf-memory-activity");
    const toggle = document.getElementById("rf-memory-widget-toggle");
    const collapsedKey = "rf_memory_graph_collapsed";

    const restoreButton = document.createElement("button");
    restoreButton.id = "rf-memory-widget-restore";
    restoreButton.type = "button";
    restoreButton.className = "rf-memory-widget-restore";
    restoreButton.innerHTML = '<i data-lucide="brain-circuit" class="w-3 h-3"></i><span>MEMORY GRAPH</span><i data-lucide="chevron-up" class="w-3 h-3"></i>';
    root.insertAdjacentElement("afterend", restoreButton);

    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";

    // ---- Scene constants -------------------------------------------------
    const FOV = 38, CAM_Z = 5.8, RADIUS = 1.72, SHELL = 0.42;
    const SHELL3 = SHELL ** 3;
    const NODE_WORLD_SIZE = 0.15;
    const MIN_ACTIVE_MS = 2500;      // real activity stays on screen long enough to be seen
    const rotationSpeed = 0.00032;

    // ---- State -----------------------------------------------------------
    let nodes = [];
    let edges = [];
    let activeIds = new Set();
    let activeEdgeIds = new Set();
    let graphSignature = "";
    let lastProject = "";
    let requestVersion = 0;
    let renderer, scene, camera, graphGroup;
    let raf = 0, refreshTimer = 0, resizeObserver = null, endRunTimer = 0;
    let lastFrame = 0, pulseClock = 0;
    let processActive = false, runStartedAt = 0;
    let pointerDown = false, pointerX = 0;

    let points = null, pointMaterial = null;
    let edgeLines = null, edgeMaterial = null, edgeTarget = 0;
    let positionById = new Map();
    let indexById = new Map();
    let activeTarget = new Float32Array(0);

    const setStatus = value => { if (statusEl) statusEl.textContent = value; };

    function activity(item) {
        if (!feedEl) return;
        feedEl.querySelector(".rf-memory-activity-empty")?.remove();
        const row = document.createElement("div");
        row.className = "rf-memory-activity-row";
        const dot = document.createElement("span");
        dot.className = "rf-memory-activity-pulse";
        const copy = document.createElement("div");
        copy.className = "rf-memory-activity-copy";
        const label = document.createElement("b");
        label.textContent = String(item.label || item.operation || "Memory operation");
        const detail = document.createElement("small");
        detail.textContent = String(item.detail || "");
        copy.append(label, detail);
        const time = document.createElement("time");
        time.textContent = Number.isFinite(Number(item.duration_ms)) ? Math.round(Number(item.duration_ms)) + " ms" : "";
        row.append(dot, copy, time);
        feedEl.prepend(row);
        while (feedEl.children.length > 5) feedEl.lastElementChild.remove();
    }

    // ---- Stable placement ------------------------------------------------
    // Position depends only on the node id: adding, removing or reordering other nodes never moves it.
    function hash01(value, salt) {
        let h = (2166136261 ^ salt) >>> 0;
        for (let i = 0; i < value.length; i++) {
            h ^= value.charCodeAt(i);
            h = Math.imul(h, 16777619);
        }
        h ^= h >>> 15; h = Math.imul(h, 2246822519);
        h ^= h >>> 13; h = Math.imul(h, 3266489917);
        h ^= h >>> 16;
        return (h >>> 0) / 4294967296;
    }

    function stableSpherePosition(id) {
        const key = String(id);
        const y = 1 - 2 * hash01(key, 0x1b873593);
        const theta = 2 * Math.PI * hash01(key, 0x85ebca6b);
        const ring = Math.sqrt(Math.max(0, 1 - y * y));
        // Volume-uniform shell: points sit on the surface and inside it, which gives depth.
        const r = RADIUS * Math.cbrt(SHELL3 + hash01(key, 0xc2b2ae35) * (1 - SHELL3));
        return [Math.cos(theta) * ring * r, y * r, Math.sin(theta) * ring * r];
    }

    // sRGB values are written as-is (the custom shaders do no colour-space conversion).
    const rawColor = hex => new THREE.Color().setHex(hex, THREE.LinearSRGBColorSpace);
    const PALETTE = {
        project: 0x4cc2ff, conversation: 0x2ee6b6, decision: 0xf0bd55, file: 0xa99cff,
        code: 0xa99cff, symbol: 0x7fbfef, memory: 0x5fd1a4, memoryquery: 0x7f9a93
    };
    const nodeColor = (node, index) => {
        const type = String(node.type || "memory").toLowerCase();
        return rawColor(PALETTE[type] || PALETTE.memory);
    };

    // ---- Shaders ---------------------------------------------------------
    const DEPTH_GLSL = "float depth = clamp((-mv.z - 4.0) / 3.6, 0.0, 1.0);";

    function createPointMaterial() {
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: false, depthTest: false,
            uniforms: {
                uScale: { value: 300 },
                uSize: { value: NODE_WORLD_SIZE },
                uTime: { value: 0 },
                uHot1: { value: rawColor(0x20e8ff) },
                uHot2: { value: rawColor(0xc56bff) }
            },
            vertexShader: `
                attribute vec3 aColor;
                attribute float aActive;
                uniform float uScale, uSize, uTime;
                varying vec3 vColor;
                varying float vActive, vDepth, vSeed;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    ${DEPTH_GLSL}
                    float pulse = 1.0 + aActive * 0.22 * sin(uTime * 0.008 + position.x * 5.0);
                    gl_Position = projectionMatrix * mv;
                    gl_PointSize = max(2.0, uSize * (1.0 + aActive * 1.1) * pulse * uScale / -mv.z * (1.2 - 0.45 * depth));
                    vColor = aColor; vActive = aActive; vDepth = depth;
                    vSeed = fract(position.y * 3.7 + position.z * 1.9);
                }`,
            fragmentShader: `
                uniform vec3 uHot1, uHot2;
                varying vec3 vColor;
                varying float vActive, vDepth, vSeed;
                void main() {
                    float d = length(gl_PointCoord - 0.5) * 2.0;
                    if (d > 1.0) discard;
                    float core = 1.0 - smoothstep(0.0, 0.5, d);
                    float halo = pow(1.0 - d, 3.0) * 0.6;
                    vec3 hot = mix(uHot1, uHot2, step(0.5, vSeed));
                    vec3 base = mix(vColor, hot, vActive);
                    vec3 col = mix(base, vec3(1.0), core * (0.35 + 0.35 * vActive));
                    float a = clamp(core + halo * (1.0 + vActive), 0.0, 1.0) * mix(1.0, 0.4, vDepth);
                    gl_FragColor = vec4(col, a);
                }`
        });
    }

    function createEdgeMaterial() {
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: false, depthTest: false,
            uniforms: {
                uTime: { value: 0 }, uOpacity: { value: 0 }, uColor: { value: rawColor(0x62eaff) }
            },
            vertexShader: `
                attribute float aAlong;
                varying float vAlong, vDepth;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    ${DEPTH_GLSL}
                    vAlong = aAlong; vDepth = depth;
                    gl_Position = projectionMatrix * mv;
                }`,
            fragmentShader: `
                uniform float uTime, uOpacity;
                uniform vec3 uColor;
                varying float vAlong, vDepth;
                void main() {
                    float flow = fract(vAlong * 1.5 - uTime * 0.0009);
                    float spark = smoothstep(0.0, 0.18, flow) * (1.0 - smoothstep(0.18, 0.5, flow));
                    float a = (0.38 + 0.62 * spark) * uOpacity * mix(1.0, 0.45, vDepth);
                    gl_FragColor = vec4(uColor, a);
                }`
        });
    }

    // ---- Three.js setup --------------------------------------------------
    function initThree() {
        renderer = new THREE.WebGLRenderer({
            canvas, alpha: true, antialias: false,
            powerPreference: "low-power", depth: true, stencil: false
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.setClearColor(0x000000, 0);
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
        camera.position.set(0, 0, CAM_Z);
        graphGroup = new THREE.Group();
        scene.add(graphGroup);
        pointMaterial = createPointMaterial();
        edgeMaterial = createEdgeMaterial();
        resize();
    }

    function resize() {
        if (!renderer || !camera) return;
        const rect = canvas.getBoundingClientRect();
        const width = Math.max(1, Math.floor(rect.width));
        const height = Math.max(1, Math.floor(rect.height));
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        // World-size -> pixel-size factor for gl_PointSize.
        const bufferHeight = renderer.domElement.height || height;
        pointMaterial.uniforms.uScale.value = bufferHeight / (2 * Math.tan(THREE.MathUtils.degToRad(FOV / 2)));
    }

    function disposeLayer(object) {
        if (!object) return;
        graphGroup.remove(object);
        object.geometry?.dispose?.();
    }

    function disposeEdges() {
        disposeLayer(edgeLines);
        edgeLines = null;
    }

    function resetScene() {
        disposeLayer(points);
        points = null;
        disposeEdges();
        positionById = new Map();
        indexById = new Map();
        activeTarget = new Float32Array(0);
    }

    // ---- Graph layers ----------------------------------------------------
    function buildNodes() {
        if (!graphGroup) return;

        // Keep the current glow of existing nodes so a data refresh never makes highlights jump.
        const carry = new Map();
        if (points) {
            const old = points.geometry.attributes.aActive.array;
            indexById.forEach((i, id) => { if (old[i] > 0.01) carry.set(id, old[i]); });
        }
        disposeLayer(points);
        points = null;

        positionById = new Map();
        indexById = new Map();
        const count = nodes.length;
        activeTarget = new Float32Array(count);

        if (count) {
            const positions = new Float32Array(count * 3);
            const colors = new Float32Array(count * 3);
            const active = new Float32Array(count);
            nodes.forEach((node, i) => {
                const id = String(node.id);
                const pos = stableSpherePosition(id);
                const color = nodeColor(node, i);
                positions.set(pos, i * 3);
                colors.set([color.r, color.g, color.b], i * 3);
                active[i] = carry.get(id) || 0;
                positionById.set(id, pos);
                indexById.set(id, i);
            });
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute("aColor", new THREE.BufferAttribute(colors, 3));
            geometry.setAttribute("aActive", new THREE.BufferAttribute(active, 1));
            points = new THREE.Points(geometry, pointMaterial);
            points.frustumCulled = false;
            graphGroup.add(points);
        }

        applyActive(true);
        if (countEl) countEl.textContent = count + " NODES";
        if (edgeCountEl) edgeCountEl.textContent = edges.length + " EDGES";
        const activeText = processActive && activeIds.size ? " · " + activeIds.size + " ACTIVE" : "";
        setStatus("LIVE SQLITE GRAPH · " + count + " NODES · " + edges.length + " EDGES" + activeText);
    }

    // Only ids reported by the memory pipeline AND present in the loaded SQLite rows are shown.
    function applyActive(rebuildEdges) {
        activeTarget.fill(0);
        if (processActive) {
            activeIds.forEach(id => {
                const i = indexById.get(id);
                if (i !== undefined) activeTarget[i] = 1;
            });
        }
        edgeTarget = processActive ? 1 : 0;
        if (rebuildEdges && processActive) rebuildActiveEdges();
    }

    function rebuildActiveEdges() {
        disposeEdges();
        if (!activeEdgeIds.size) return;
        const pos = [], along = [];
        edges.forEach(edge => {
            if (!activeEdgeIds.has(String(edge.id))) return;
            const a = positionById.get(String(edge.source));
            const b = positionById.get(String(edge.target));
            if (!a || !b) return;
            pos.push(a[0], a[1], a[2], b[0], b[1], b[2]);
            along.push(0, 1);
        });
        if (!along.length) return;
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
        geometry.setAttribute("aAlong", new THREE.Float32BufferAttribute(along, 1));
        edgeLines = new THREE.LineSegments(geometry, edgeMaterial);
        edgeLines.frustumCulled = false;
        graphGroup.add(edgeLines);
    }

    // ---- Data loading ----------------------------------------------------
    async function loadGraph(pidOverride) {
        const pid = (typeof pidOverride === "string" ? pidOverride : "") || projectId() || lastProject;
        if (!pid) {
            requestVersion++;
            nodes = [];
            edges = [];
            graphSignature = "";
            activeIds.clear();
            activeEdgeIds.clear();
            resetScene();
            buildNodes();
            setStatus("Select a project to inspect its SQLite memory");
            return;
        }

        const version = ++requestVersion;
        try {
            const headers = {};
            const jwt = token();
            if (jwt) headers.Authorization = "Bearer " + jwt;
            const response = await fetch("/api/v1/memory/graph-status/" + encodeURIComponent(pid), {
                headers, credentials: "same-origin", cache: "no-store"
            });
            if (!response.ok) throw new Error("HTTP " + response.status);
            const payload = await response.json();
            if (version !== requestVersion) return;

            const nextNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
            const nextEdges = Array.isArray(payload.edges) ? payload.edges : [];
            const signature = nextNodes.length + ":" + nextEdges.length + ":" +
                nextNodes.map(node => node.id + "|" + node.type).join(",") + ":" +
                nextEdges.map(edge => edge.id).join(",");
            const projectChanged = pid !== lastProject;
            nodes = nextNodes;
            edges = nextEdges;
            lastProject = pid;
            if (signature !== graphSignature) {
                graphSignature = signature;
                if (projectChanged) resetScene();
                buildNodes();
            }

            if (!nodes.length) {
                setStatus("No saved SQLite memory nodes in this project yet");
            } else if (!edges.length) {
                setStatus("SQLite nodes loaded · no stored relationships yet");
            } else if (payload.truncated) {
                setStatus("Showing " + nodes.length + " of " + payload.total_nodes + " SQLite nodes");
            }
        } catch (error) {
            if (version !== requestVersion) return;
            // Keep the last good graph on screen; only report the failure.
            setStatus("Memory graph unavailable · " + String(error.message || error).slice(0, 64));
            console.error("[MemoryGraph] SQLite graph fetch failed", error);
        }
    }

    // ---- Memory events ---------------------------------------------------
    function endRun() {
        endRunTimer = 0;
        processActive = false;
        activeIds.clear();
        activeEdgeIds.clear();
        applyActive(false);   // targets fall to 0 -> smooth fade; nodes stay visible
        if (nodes.length) setStatus("LIVE SQLITE GRAPH · " + nodes.length + " NODES · " + edges.length + " EDGES");
    }

    function addActive(item) {
        if (Array.isArray(item.active_node_ids)) item.active_node_ids.forEach(id => activeIds.add(String(id)));
        if (Array.isArray(item.active_edge_ids)) item.active_edge_ids.forEach(id => activeEdgeIds.add(String(id)));
    }

    function handleMemoryEvent(detail) {
        if (!detail) return;
        const eventProject = typeof detail.project_id === "string" ? detail.project_id : "";
        if (eventProject) lastProject = eventProject;

        if (detail.phase === "started") {
            if (endRunTimer) { clearTimeout(endRunTimer); endRunTimer = 0; }
            processActive = true;
            runStartedAt = performance.now();
            activeIds.clear();
            activeEdgeIds.clear();
            applyActive(false);
            setStatus("Memory query running · reading SQLite graph");
            activity({ label: "Memory query started", detail: (detail.mode || "AUTO") + " · " + (detail.model || "orchestrator") });
            loadGraph(eventProject || lastProject);
            return;
        }

        if (detail.phase === "activity" && detail.event) {
            const item = detail.event;
            if (endRunTimer) { clearTimeout(endRunTimer); endRunTimer = 0; }
            processActive = true;
            addActive(item);
            activity({
                label: (item.phase === "started" ? "Running · " : "Completed · ") + (item.label || item.operation || "Memory operation"),
                detail: item.detail || "", duration_ms: item.duration_ms
            });
            const unknown = [...activeIds].some(id => !indexById.has(id));
            if (unknown) loadGraph(lastProject);   // buildNodes() re-applies the active state after loading
            else applyActive(true);
            return;
        }

        if (detail.phase === "completed") {
            processActive = true;
            addActive(detail);
            activity({ label: "Memory context ready", detail: "SQLite graph updated" });
            if ([...activeIds].some(id => !indexById.has(id))) loadGraph(eventProject || lastProject);
            else applyActive(true);
            // The memory pipeline takes milliseconds: keep the real activity visible, then fade it.
            const remaining = Math.max(1200, MIN_ACTIVE_MS - (performance.now() - runStartedAt));
            if (endRunTimer) clearTimeout(endRunTimer);
            endRunTimer = setTimeout(endRun, remaining);
            return;
        }

        if (detail.phase === "failed") {
            if (endRunTimer) { clearTimeout(endRunTimer); endRunTimer = 0; }
            endRun();
            setStatus("Memory query failed");
            activity({ label: "Memory query failed", detail: detail.error || "See Agent Trace" });
        }
    }

    // ---- Render loop -----------------------------------------------------
    function animate(now) {
        raf = 0;
        if (document.hidden || root.style.display === "none") return;

        const delta = lastFrame ? Math.min(40, now - lastFrame) : 16;
        lastFrame = now;
        pulseClock += delta;

        // Rotation is unconditional: it never depends on AI activity.
        graphGroup.rotation.y += rotationSpeed * delta;
        graphGroup.rotation.x = Math.sin(pulseClock * 0.00012) * 0.055;

        pointMaterial.uniforms.uTime.value = pulseClock;
        if (points) {
            const attr = points.geometry.attributes.aActive;
            const arr = attr.array;
            const k = 1 - Math.exp(-delta / 150);
            let dirty = false;
            for (let i = 0; i < arr.length; i++) {
                const diff = activeTarget[i] - arr[i];
                if (diff === 0) continue;
                arr[i] = Math.abs(diff) < 0.004 ? activeTarget[i] : arr[i] + diff * k;
                dirty = true;
            }
            if (dirty) attr.needsUpdate = true;
        }

        if (edgeLines) {
            const u = edgeMaterial.uniforms;
            u.uTime.value = pulseClock;
            u.uOpacity.value += (edgeTarget - u.uOpacity.value) * (1 - Math.exp(-delta / 260));
            if (edgeTarget === 0 && u.uOpacity.value < 0.02) { u.uOpacity.value = 0; disposeEdges(); }
        }

        renderer.render(scene, camera);
        raf = requestAnimationFrame(animate);
    }

    const start = () => {
        if (!raf && renderer && !document.hidden && root.style.display !== "none") {
            lastFrame = 0;
            raf = requestAnimationFrame(animate);
        }
    };
    const stop = () => {
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
    };

    function setCollapsed(value) {
        root.style.display = value ? "none" : "";
        restoreButton.style.display = value ? "flex" : "none";
        if (toggle) {
            toggle.setAttribute("aria-expanded", String(!value));
            toggle.setAttribute("aria-label", value ? "Show memory graph" : "Hide memory graph");
            toggle.title = value ? "Show memory graph" : "Hide memory graph";
        }
        try { localStorage.setItem(collapsedKey, value ? "1" : "0"); } catch (_) {}
        if (value) stop();
        else {
            resize();
            start();
        }
    }

    try {
        initThree();
        setCollapsed(localStorage.getItem(collapsedKey) === "1");
    } catch (error) {
        console.error("[MemoryGraph] Three.js initialization failed", error);
        setStatus("3D renderer unavailable");
        return;
    }

    toggle?.addEventListener("click", () => setCollapsed(true));
    restoreButton.addEventListener("click", () => setCollapsed(false));
    if (window.lucide) window.lucide.createIcons();

    canvas.addEventListener("pointerdown", event => {
        pointerDown = true;
        pointerX = event.clientX;
        canvas.setPointerCapture?.(event.pointerId);
    });
    canvas.addEventListener("pointermove", event => {
        if (!pointerDown) return;
        graphGroup.rotation.y += (event.clientX - pointerX) * 0.008;
        pointerX = event.clientX;
    });
    canvas.addEventListener("pointerup", () => { pointerDown = false; });
    canvas.addEventListener("pointercancel", () => { pointerDown = false; });
    canvas.addEventListener("webglcontextlost", event => {
        event.preventDefault();
        stop();
        setStatus("WebGL context lost");
    });
    canvas.addEventListener("webglcontextrestored", () => { resize(); start(); });

    resizeObserver = typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => { resize(); })
        : null;
    resizeObserver?.observe(canvas);

    window.addEventListener("rf:memory-graph", event => {
        if (event.detail?.status === "memory_graph") handleMemoryEvent(event.detail);
    });

    eventBus.on("project.activated", project => {
        const pid = typeof project === "string" ? project : project?.id;
        lastProject = pid || projectId();
        nodes = [];
        edges = [];
        graphSignature = "";
        activeIds.clear();
        activeEdgeIds.clear();
        resetScene();
        buildNodes();
        loadGraph(lastProject);
    });

    window.addEventListener("storage", event => {
        if (event.key === "rf_active_project_id") loadGraph();
    });
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) stop();
        else start();
    });

    window.addEventListener("beforeunload", () => {
        stop();
        if (refreshTimer) clearInterval(refreshTimer);
        if (endRunTimer) clearTimeout(endRunTimer);
        resizeObserver?.disconnect();
        resetScene();
        pointMaterial?.dispose();
        edgeMaterial?.dispose();
        renderer?.dispose();
    }, { once: true });

    // Debug hook: localStorage.rf_debug_graph = "1" -> window.__rfMemoryGraphDebug()
    if (localStorage.getItem("rf_debug_graph") === "1") {
        window.__rfMemoryGraphDebug = () => ({
            points: points ? points.geometry.attributes.position.count : 0,
            apiNodes: nodes.length,
            apiEdges: edges.length,
            activeNodes: points ? [...points.geometry.attributes.aActive.array].filter(v => v > 0.5).length : 0,
            activeEdges: edgeLines ? edgeLines.geometry.attributes.position.count / 2 : 0,
            rotationY: graphGroup.rotation.y,
            positions: Object.fromEntries([...positionById].map(([id, p]) => [id, p.map(v => +v.toFixed(5))]))
        });
    }

    loadGraph().finally(() => start());
    refreshTimer = window.setInterval(() => loadGraph(), 15000);
    start();
})();