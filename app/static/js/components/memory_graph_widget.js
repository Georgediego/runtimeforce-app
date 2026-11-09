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
    restoreButton.innerHTML = '<i data-lucide="brain-circuit" class="w-3 h-3"></i><span>RUNTIME GRAPH</span><i data-lucide="chevron-up" class="w-3 h-3"></i>';
    root.insertAdjacentElement("afterend", restoreButton);

    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";

    // ---- Scene constants -------------------------------------------------
    const FOV = 38, CAM_Z = 4.85, RADIUS = 1.42;
    const MIN_ACTIVE_MS = 2500;        // real activity stays visible long enough to be seen
    const EDGE_IDLE_ALPHA = 0;           // real edges are visible only during actual memory activity
    const MAX_ACTIVE_LABELS = 5, IDLE_LABELS = 3;
    const rotationSpeed = 0.00032;
    const HOT = 0xff3fa4;

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

    let nodePoints = null, glowPoints = null, edgeLines = null, ambientPoints = null, shellMesh = null;
    let nodeMaterial = null, glowMaterial = null, edgeMaterial = null;
    let positionById = new Map();      // id -> [x, y, z]
    let indexById = new Map();         // node id -> buffer index
    let edgeIndexById = new Map();     // edge id -> segment index
    let nodeTarget = new Float32Array(0);
    let edgeTarget = new Float32Array(0);
    let hubIndexes = [];
    const layoutCache = new Map();     // id -> [x, y, z], survives data refreshes

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

    // ---- Stable clustered layout (pure functions) ------------------------
    // LAYOUT-BEGIN
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

    function unitVector(key, salt) {
        const y = 1 - 2 * hash01(key, salt);
        const theta = 2 * Math.PI * hash01(key, salt + 1);
        const ring = Math.sqrt(Math.max(0, 1 - y * y));
        return [Math.cos(theta) * ring, y, Math.sin(theta) * ring];
    }

    const KNOWN_ANCHORS = {
        project: [0, 1, 0.1], conversation: [-0.9, 0.2, 0.4], memoryquery: [0.85, -0.15, 0.5],
        decision: [0.1, -0.95, -0.3], file: [0.65, 0.5, -0.7], code: [0.65, 0.5, -0.7],
        symbol: [-0.55, -0.6, -0.65], memory: [-0.2, 0.15, 0.95]
    };

    function typeAnchor(type, radius) {
        const key = String(type || "memory").toLowerCase();
        const raw = KNOWN_ANCHORS[key] || unitVector(key, 0x51ed27);
        const len = Math.hypot(raw[0], raw[1], raw[2]) || 1;
        return raw.map(v => (v / len) * radius * 0.55);
    }

    // All real SQLite nodes share one spherical surface.
    // Fibonacci distribution spreads the existing points evenly over the globe.
    // Hash-shuffle IDs before Fibonacci placement. This prevents sorted ID prefixes
    // (workspace files, models, roles) from occupying separate latitude bands.
    // Every real object receives a stable, evenly distributed position on the sphere.
    function layoutGraph(nodeList, edgeList, cache, radius) {
        const ordered = nodeList
            .map(node => String(node.id))
            .sort((a, b) => {
                const ha = hash01(a, 0x6d2b79f5);
                const hb = hash01(b, 0x6d2b79f5);
                return ha - hb || a.localeCompare(b);
            });
        const total = ordered.length;
        const goldenAngle = Math.PI * (3 - Math.sqrt(5));
        ordered.forEach((id, i) => {
            const y = total <= 1 ? 0 : 1 - 2 * (i + 0.5) / total;
            const ring = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = goldenAngle * i;
            cache.set(id, [
                Math.cos(theta) * ring * radius,
                y * radius,
                Math.sin(theta) * ring * radius
            ]);
        });
    }
        // LAYOUT-END

    // Shaders do no colour-space conversion, so sRGB values are written as-is.
    const rawColor = hex => new THREE.Color().setHex(hex, THREE.LinearSRGBColorSpace);
    const PALETTE = {
        project: 0xbfe9ff, conversation: 0x8f6bff, memoryquery: 0x9b94c9, decision: 0xf0bd55,
        file: 0x4fe0c0, code: 0x4fe0c0, symbol: 0x6aa8ff, memory: 0x9a74ff,
        workspace: 0x73d9ff, directory: 0x36c9a8, provider: 0xffc36b, model: 0xff9a56,
        role: 0xf47fb2, tool: 0xd78cff, mode: 0x9bafff
    };
    // Inactive objects follow the IDE's green accent; active objects are highlighted HOT by the shader.
    const INACTIVE_NODE_COLOR = 0x42d99a;
    const nodeColor = () => rawColor(INACTIVE_NODE_COLOR);

    // ---- Shaders ---------------------------------------------------------
    const DEPTH_GLSL = "float depth = clamp((-mv.z - 4.0) / 3.6, 0.0, 1.0);";

    function createNodeMaterial() {
        // Point-sprite impostor: each point is shaded as a lit 3D ball.
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: true, depthTest: true,
            uniforms: { uScale: { value: 300 }, uTime: { value: 0 }, uHot: { value: rawColor(HOT) } },
            vertexShader: `
                attribute vec3 aColor;
                attribute float aSize, aActive;
                uniform float uScale, uTime;
                varying vec3 vColor;
                varying float vActive, vDepth;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    ${DEPTH_GLSL}
                    float pulse = 1.0 + aActive * 0.18 * sin(uTime * 0.009 + position.x * 5.0);
                    gl_Position = projectionMatrix * mv;
                    gl_PointSize = max(3.0, aSize * (1.0 + aActive * 0.9) * pulse * uScale / -mv.z);
                    vColor = aColor; vActive = aActive; vDepth = depth;
                }`,
            fragmentShader: `
                uniform vec3 uHot;
                varying vec3 vColor;
                varying float vActive, vDepth;
                void main() {
                    vec2 p = (gl_PointCoord - 0.5) * 2.0;
                    p.y = -p.y;
                    float r2 = dot(p, p);
                    if (r2 > 1.0) discard;
                    vec3 n = vec3(p, sqrt(1.0 - r2));
                    vec3 L = normalize(vec3(-0.45, 0.55, 0.7));
                    float diff = max(dot(n, L), 0.0);
                    float rim = pow(1.0 - n.z, 2.5);
                    float spec = pow(max(dot(n, normalize(L + vec3(0.0, 0.0, 1.0))), 0.0), 28.0);
                    vec3 base = mix(vColor, uHot, vActive);
                    vec3 col = base * (0.30 + 0.85 * diff) + base * rim * 0.35;
                    col += vec3(1.0) * spec * (0.55 + 0.4 * vActive);
                    col += uHot * vActive * 0.45;
                    col *= mix(1.0, 0.42, vDepth);
                    gl_FragColor = vec4(col, 1.0);
                }`
        });
    }

    function createGlowMaterial() {
        // Bloom + star rays, drawn only for nodes with aActive > 0.
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
            uniforms: { uScale: { value: 300 }, uTime: { value: 0 }, uHot: { value: rawColor(HOT) } },
            vertexShader: `
                attribute float aSize, aActive;
                uniform float uScale;
                varying float vActive;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    gl_Position = projectionMatrix * mv;
                    gl_PointSize = aSize * (3.2 + aActive * 4.8) * uScale / -mv.z;
                    if (aActive < 0.02) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); gl_PointSize = 0.0; }
                    vActive = aActive;
                }`,
            fragmentShader: `
                uniform vec3 uHot;
                varying float vActive;
                void main() {
                    vec2 p = (gl_PointCoord - 0.5) * 2.0;
                    float d = length(p);
                    if (d > 1.0) discard;
                    float glow = exp(-d * d * 5.0);
                    float star = exp(-abs(p.x) * 14.0) * exp(-abs(p.y) * 3.0)
                               + exp(-abs(p.y) * 14.0) * exp(-abs(p.x) * 3.0);
                    float a = clamp(glow * 0.85 + star * 0.6, 0.0, 1.0) * vActive;
                    gl_FragColor = vec4(mix(uHot, vec3(1.0), glow * 0.35), a);
                }`
        });
    }

    function createEdgeMaterial() {
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: false, depthTest: false,
            uniforms: { uTime: { value: 0 }, uIdle: { value: EDGE_IDLE_ALPHA }, uHot: { value: rawColor(HOT) } },
            vertexShader: `
                attribute vec3 aColor;
                attribute float aAlong, aAct;
                varying vec3 vColor;
                varying float vAlong, vAct, vDepth;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    ${DEPTH_GLSL}
                    vColor = aColor; vAlong = aAlong; vAct = aAct; vDepth = depth;
                    gl_Position = projectionMatrix * mv;
                }`,
            fragmentShader: `
                uniform float uTime, uIdle;
                uniform vec3 uHot;
                varying vec3 vColor;
                varying float vAlong, vAct, vDepth;
                void main() {
                    float flow = fract(vAlong * 1.5 - uTime * 0.0011);
                    float spark = smoothstep(0.0, 0.15, flow) * (1.0 - smoothstep(0.15, 0.45, flow));
                    float a = mix(uIdle, 0.45 + 0.55 * spark, vAct) * mix(1.0, 0.4, vDepth);
                    vec3 col = mix(vColor * 1.1 + 0.15, uHot, vAct);
                    gl_FragColor = vec4(col, a);
                }`
        });
    }

    // ---- Labels (DOM overlay over the canvas) ----------------------------
    const labelLayer = document.createElement("div");
    labelLayer.className = "rf-memory-labels";
    labelLayer.style.cssText = "position:absolute;pointer-events:none;overflow:hidden;z-index:3";
    const labelStyle = document.createElement("style");
    labelStyle.textContent =
        ".rf-memory-label{position:absolute;left:0;top:0;white-space:nowrap;font:600 8px 'JetBrains Mono',monospace;" +
        "padding:1px 5px;border-radius:3px;color:#e9e4ff;background:rgba(10,8,22,.72);border:1px solid rgba(160,140,255,.25);" +
        "transition:opacity .15s;will-change:transform}" +
        ".rf-memory-label.hot{font-size:10px;font-weight:700;color:#fff;background:#ff3fa4;border-color:#ff8fcb;" +
        "box-shadow:0 0 12px rgba(255,63,164,.65)}";
    document.head.appendChild(labelStyle);
    const labelPool = [];
    const labelVec = new THREE.Vector3();

    function placeLabelLayer() {
        const parent = canvas.parentElement;
        if (!parent) return;
        if (getComputedStyle(parent).position === "static") parent.style.position = "relative";
        if (labelLayer.parentElement !== parent) parent.appendChild(labelLayer);
        labelLayer.style.left = canvas.offsetLeft + "px";
        labelLayer.style.top = canvas.offsetTop + "px";
        labelLayer.style.width = canvas.clientWidth + "px";
        labelLayer.style.height = canvas.clientHeight + "px";
    }

    function updateLabels() {
        const picks = [];
        if (processActive) {
            for (const id of activeIds) {
                const i = indexById.get(id);
                if (i !== undefined) picks.push({ i, hot: true });
                if (picks.length >= MAX_ACTIVE_LABELS) break;
            }
        }
        for (const i of hubIndexes) {
            if (picks.length >= MAX_ACTIVE_LABELS + IDLE_LABELS) break;
            if (!picks.some(p => p.i === i)) picks.push({ i, hot: false });
        }
        const w = canvas.clientWidth, h = canvas.clientHeight;
        graphGroup.updateMatrixWorld(true);
        let used = 0;
        picks.forEach(({ i, hot }) => {
            const node = nodes[i];
            const pos = positionById.get(String(node.id));
            if (!node || !pos) return;
            labelVec.set(pos[0], pos[1], pos[2]).applyMatrix4(graphGroup.matrixWorld);
            if (labelVec.z < -0.15 * RADIUS) return;                       // far half of the sphere
            labelVec.project(camera);
            const x = (labelVec.x * 0.5 + 0.5) * w, y = (-labelVec.y * 0.5 + 0.5) * h;
            if (x < 0 || y < 0 || x > w || y > h) return;
            let el = labelPool[used];
            if (!el) {
                el = document.createElement("div");
                labelPool.push(el);
                labelLayer.appendChild(el);
            }
            el.className = "rf-memory-label" + (hot ? " hot" : "");
            const text = String(node.label || node.type || "").trim().slice(0, hot ? 30 : 22);
            if (el.textContent !== text) el.textContent = text;
            el.style.opacity = "1";
            el.style.transform = "translate(" + Math.round(x + 7) + "px," + Math.round(y - 8) + "px)";
            used++;
        });
        for (let k = used; k < labelPool.length; k++) labelPool[k].style.opacity = "0";
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

        nodeMaterial = createNodeMaterial();
        glowMaterial = createGlowMaterial();
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
        const bufferHeight = renderer.domElement.height || height;
        const scale = bufferHeight / (2 * Math.tan(THREE.MathUtils.degToRad(FOV / 2)));
        nodeMaterial.uniforms.uScale.value = scale;
        glowMaterial.uniforms.uScale.value = scale;
        placeLabelLayer();
    }

    function disposeLayers() {
        [nodePoints, glowPoints, edgeLines].forEach(object => { if (object) graphGroup.remove(object); });
        nodePoints?.geometry.dispose();          // glowPoints shares this geometry
        edgeLines?.geometry.dispose();
        nodePoints = glowPoints = edgeLines = null;
    }

    function resetScene() {
        disposeLayers();
        layoutCache.clear();
        positionById = new Map();
        indexById = new Map();
        edgeIndexById = new Map();
        nodeTarget = new Float32Array(0);
        edgeTarget = new Float32Array(0);
        hubIndexes = [];
    }

    // ---- Graph build -----------------------------------------------------
    function buildGraph() {
        if (!graphGroup) return;

        // Keep current glow so a data refresh never makes highlights jump.
        const carryNodes = new Map(), carryEdges = new Map();
        if (nodePoints) {
            const arr = nodePoints.geometry.attributes.aActive.array;
            indexById.forEach((i, id) => { if (arr[i] > 0.01) carryNodes.set(id, arr[i]); });
        }
        if (edgeLines) {
            const arr = edgeLines.geometry.attributes.aAct.array;
            edgeIndexById.forEach((i, id) => { if (arr[i * 2] > 0.01) carryEdges.set(id, arr[i * 2]); });
        }
        disposeLayers();

        // Drop cached positions of nodes that no longer exist.
        const present = new Set(nodes.map(node => String(node.id)));
        [...layoutCache.keys()].forEach(id => { if (!present.has(id)) layoutCache.delete(id); });
        layoutGraph(nodes, edges, layoutCache, RADIUS);

        positionById = new Map();
        indexById = new Map();
        edgeIndexById = new Map();
        const count = nodes.length;
        nodeTarget = new Float32Array(count);

        const degree = new Map();
        edges.forEach(edge => {
            degree.set(String(edge.source), (degree.get(String(edge.source)) || 0) + 1);
            degree.set(String(edge.target), (degree.get(String(edge.target)) || 0) + 1);
        });

        if (count) {
            const positions = new Float32Array(count * 3);
            const colors = new Float32Array(count * 3);
            const sizes = new Float32Array(count);
            const active = new Float32Array(count);
            const colorById = new Map();
            nodes.forEach((node, i) => {
                const id = String(node.id);
                const pos = layoutCache.get(id);
                const color = nodeColor(node);
                positions.set(pos, i * 3);
                colors.set([color.r, color.g, color.b], i * 3);
                const deg = degree.get(id) || 0;
                sizes[i] = 0.10 + 0.12 * Math.min(1, Math.log1p(deg) / Math.log(14));
                active[i] = carryNodes.get(id) || 0;
                positionById.set(id, pos);
                indexById.set(id, i);
                colorById.set(id, color);
            });
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute("aColor", new THREE.BufferAttribute(colors, 3));
            geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
            geometry.setAttribute("aActive", new THREE.BufferAttribute(active, 1));

            // Real SQLite edges only: both endpoints must exist in the loaded node set.
            const rows = edges.filter(edge => positionById.has(String(edge.source)) && positionById.has(String(edge.target)));
            const ePos = new Float32Array(rows.length * 6);
            const eColor = new Float32Array(rows.length * 6);
            const eAlong = new Float32Array(rows.length * 2);
            const eAct = new Float32Array(rows.length * 2);
            rows.forEach((edge, k) => {
                const a = String(edge.source), b = String(edge.target);
                ePos.set(positionById.get(a), k * 6);
                ePos.set(positionById.get(b), k * 6 + 3);
                const ca = colorById.get(a), cb = colorById.get(b);
                eColor.set([ca.r, ca.g, ca.b, cb.r, cb.g, cb.b], k * 6);
                eAlong[k * 2] = 0; eAlong[k * 2 + 1] = 1;
                const carry = carryEdges.get(String(edge.id)) || 0;
                eAct[k * 2] = carry; eAct[k * 2 + 1] = carry;
                edgeIndexById.set(String(edge.id), k);
            });
            edgeTarget = new Float32Array(rows.length);
            if (rows.length) {
                const edgeGeometry = new THREE.BufferGeometry();
                edgeGeometry.setAttribute("position", new THREE.BufferAttribute(ePos, 3));
                edgeGeometry.setAttribute("aColor", new THREE.BufferAttribute(eColor, 3));
                edgeGeometry.setAttribute("aAlong", new THREE.BufferAttribute(eAlong, 1));
                edgeGeometry.setAttribute("aAct", new THREE.BufferAttribute(eAct, 1));
                edgeLines = new THREE.LineSegments(edgeGeometry, edgeMaterial);
                edgeLines.frustumCulled = false;
                edgeLines.renderOrder = 1;
                graphGroup.add(edgeLines);
            }

            nodePoints = new THREE.Points(geometry, nodeMaterial);
            nodePoints.frustumCulled = false;
            nodePoints.renderOrder = 2;
            glowPoints = new THREE.Points(geometry, glowMaterial);
            glowPoints.frustumCulled = false;
            glowPoints.renderOrder = 3;
            graphGroup.add(nodePoints, glowPoints);

            hubIndexes = nodes
                .map((node, i) => ({ i, deg: degree.get(String(node.id)) || 0, id: String(node.id) }))
                .filter(item => item.deg > 0)
                .sort((a, b) => b.deg - a.deg || (a.id < b.id ? -1 : 1))
                .slice(0, IDLE_LABELS).map(item => item.i);
        } else {
            edgeTarget = new Float32Array(0);
            hubIndexes = [];
        }

        applyActive();
        if (countEl) countEl.textContent = count + " NODES";
        if (edgeCountEl) edgeCountEl.textContent = edges.length + " EDGES";
        const activeText = processActive && activeIds.size ? " · " + activeIds.size + " ACTIVE" : "";
        setStatus("RUNTIME GRAPH · " + count + " OBJECTS · " + edges.length + " LINKS" + activeText);
    }

    // Targets come only from ids reported by the memory pipeline that exist in the loaded SQLite rows.
    function applyActive() {
        nodeTarget.fill(0);
        edgeTarget.fill(0);
        if (!processActive) return;
        activeIds.forEach(id => {
            const i = indexById.get(id);
            if (i !== undefined) nodeTarget[i] = 1;
        });
        activeEdgeIds.forEach(id => {
            const k = edgeIndexById.get(id);
            if (k !== undefined) edgeTarget[k] = 1;
        });
        // Real relationships connected to an active object light up during its operation.
        // Illuminate only real stored/configured relationships that touch an active object.
        // This keeps the network meaningful: no synthetic all-to-all links are drawn.
        edges.forEach(edge => {
            const source = String(edge.source);
            const target = String(edge.target);
            if (!activeIds.has(source) && !activeIds.has(target)) return;
            const k = edgeIndexById.get(String(edge.id));
            if (k !== undefined) edgeTarget[k] = 1;
        });
    }

    // ---- Runtime topology sources ---------------------------------------
    // Cached separately because model discovery is more expensive than the memory graph query.
    let topologyNodes = [];
    let topologyEdges = [];
    let topologyLoadedAt = 0;
    let modelsLoadedAt = 0;
    const SKIP_TREE_NAMES = new Set([".git", "__pycache__", "node_modules", "venv", ".venv", ".pytest_cache", "staticfiles", "media", ".cache", ".DS_Store"]);
    const CHAT_MODES = [
        { id: "auto", label: "Auto" },
        { id: "coding", label: "Autonomous Team" },
        { id: "local", label: "Local" },
        { id: "manual", label: "Manual" }
    ];
    const ROLE_TOOLS = {
        Engineer: ["read_workspace_file", "write_workspace_file", "run_shell_command", "grep_search"],
        Implementer: ["read_workspace_file", "write_workspace_file", "patch_file", "run_shell_command"],
        Designer: ["read_workspace_file", "write_workspace_file", "patch_file"],
        Architect: ["read_workspace_file", "grep_search", "search_graph"]
    };

    async function authenticatedJson(url) {
        const headers = {};
        const jwt = token();
        if (jwt) headers.Authorization = "Bearer " + jwt;
        const response = await fetch(url, { headers, credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status + " · " + url);
        return response.json();
    }

    async function loadWorkspaceTopology(pid) {
        const payload = await authenticatedJson("/api/v1/workspaces/tree?project_id=" + encodeURIComponent(pid));
        const tree = payload?.tree;
        if (!tree || !tree.path) return { nodes: [], edges: [] };

        const outNodes = [];
        const outEdges = [];
        const rootId = "workspace:root:" + pid;
        outNodes.push({ id: rootId, label: tree.name || "Workspace", type: "workspace", source: "workspace" });
        const queue = [{ item: tree, parentId: rootId, depth: 0 }];
        const seen = new Set([String(tree.path)]);
        const maxNodes = 320;
        const maxDepth = 4;

        while (queue.length && outNodes.length < maxNodes) {
            const current = queue.shift();
            const children = Array.isArray(current.item.children) ? current.item.children : (
                current.depth === 0 && Array.isArray(tree.children) ? tree.children : []
            );
            for (const child of children) {
                if (outNodes.length >= maxNodes) break;
                if (!child?.path || SKIP_TREE_NAMES.has(child.name)) continue;
                const path = String(child.path);
                if (seen.has(path)) continue;
                seen.add(path);
                const isDir = child.is_dir === true || child.type === "directory";
                const id = "workspace:" + (isDir ? "dir:" : "file:") + path;
                outNodes.push({
                    id,
                    label: String(child.name || path.split("/").pop() || path),
                    type: isDir ? "directory" : "file",
                    source: "workspace"
                });
                outEdges.push({
                    id: "workspace-edge:" + current.parentId + "->" + id,
                    source: current.parentId,
                    target: id,
                    relation: isDir ? "contains directory" : "contains file",
                    weight: 1
                });
                if (isDir && current.depth + 1 < maxDepth) {
                    queue.push({ item: { ...child, children: null }, parentId: id, depth: current.depth + 1 });
                }
            }

            // The tree endpoint returns one level. Load children for directories as needed.
            if (current.depth > 0 || current.item === tree) {
                for (const child of children) {
                    if (outNodes.length >= maxNodes) break;
                    if (!(child?.is_dir === true || child?.type === "directory") || current.depth + 1 >= maxDepth) continue;
                    const childId = "workspace:dir:" + String(child.path);
                    const queued = queue.find(entry => entry.parentId === childId);
                    if (!queued) continue;
                    try {
                        const nested = await authenticatedJson(
                            "/api/v1/workspaces/tree/children?project_id=" + encodeURIComponent(pid) +
                            "&path=" + encodeURIComponent(child.path)
                        );
                        queued.item.children = Array.isArray(nested.children) ? nested.children : [];
                    } catch (_) {
                        // Keep the real directory node even if its listing is inaccessible.
                        queued.item.children = [];
                    }
                }
            }
        }
        return { nodes: outNodes, edges: outEdges };
    }

    let modelsLoadPromise = null;
    async function loadModelTopology(force = false) {
        if (!force && Date.now() - modelsLoadedAt < 180000) {
            return {
                nodes: topologyNodes.filter(n => n.source === "models"),
                edges: topologyEdges.filter(e => e.sourceType === "models")
            };
        }
        if (modelsLoadPromise) return modelsLoadPromise;
        modelsLoadPromise = (async () => {
            const payload = await authenticatedJson("/api/v1/models");
            const outNodes = [];
            const outEdges = [];
            Object.entries(payload.models || {}).forEach(([provider, models]) => {
                const providerId = "provider:" + provider;
                outNodes.push({ id: providerId, label: provider, type: "provider", source: "models" });
                (Array.isArray(models) ? models : []).forEach(model => {
                    const modelId = "model:" + provider + ":" + String(model.id || model.name);
                    outNodes.push({ id: modelId, label: String(model.name || model.id), type: "model", source: "models" });
                    outEdges.push({
                        id: "model-edge:" + provider + "->" + modelId,
                        source: providerId, target: modelId, relation: "provides model", weight: 1,
                        sourceType: "models"
                    });
                });
            });
            modelsLoadedAt = Date.now();
            return { nodes: outNodes, edges: outEdges };
        })();
        try {
            return await modelsLoadPromise;
        } finally {
            modelsLoadPromise = null;
        }
    }

    function buildStaticTopology() {
        const outNodes = [];
        const outEdges = [];
        Object.entries(ROLE_TOOLS).forEach(([role, tools]) => {
            const roleId = "agent-role:" + role.toLowerCase();
            outNodes.push({ id: roleId, label: role, type: "role", source: "agents" });
            tools.forEach(tool => {
                const toolId = "agent-tool:" + tool;
                if (!outNodes.some(node => node.id === toolId)) {
                    outNodes.push({ id: toolId, label: tool, type: "tool", source: "agents" });
                }
                outEdges.push({
                    id: "role-tool:" + roleId + "->" + toolId,
                    source: roleId, target: toolId, relation: "allowed tool", weight: 1
                });
            });
        });
        CHAT_MODES.forEach(mode => {
            outNodes.push({ id: "chat-mode:" + mode.id, label: mode.label, type: "mode", source: "chat" });
        });
        return { nodes: outNodes, edges: outEdges };
    }

    let topologyLoadPromise = null;
    async function loadRuntimeTopology(pid, force = false) {
        const now = Date.now();
        if (!force && now - topologyLoadedAt < 60000 && topologyNodes.length) {
            const models = await loadModelTopology(false).catch(() => ({ nodes: [], edges: [] }));
            const cachedBase = topologyNodes.filter(node => node.source !== "models");
            const cachedBaseEdges = topologyEdges.filter(edge => edge.sourceType !== "models");
            return { nodes: cachedBase.concat(models.nodes), edges: cachedBaseEdges.concat(models.edges) };
        }
        if (topologyLoadPromise) return topologyLoadPromise;
        topologyLoadPromise = (async () => {
            const [workspace, models] = await Promise.all([
                loadWorkspaceTopology(pid).catch(error => {
                    console.warn("[MemoryGraph] Workspace topology unavailable", error);
                    return { nodes: [], edges: [] };
                }),
                loadModelTopology(force).catch(error => {
                    console.warn("[MemoryGraph] Model topology unavailable", error);
                    return {
                        nodes: topologyNodes.filter(n => n.source === "models"),
                        edges: topologyEdges.filter(e => e.sourceType === "models")
                    };
                })
            ]);
            const staticGraph = buildStaticTopology();
            topologyNodes = workspace.nodes.concat(models.nodes, staticGraph.nodes);
            topologyEdges = workspace.edges.concat(models.edges, staticGraph.edges);
            topologyLoadedAt = Date.now();
            return { nodes: topologyNodes, edges: topologyEdges };
        })();
        try {
            return await topologyLoadPromise;
        } finally {
            topologyLoadPromise = null;
        }
    }

    // ---- Data loading ----------------------------------------------------
    async function loadGraph(pidOverride, forceTopology = false) {
        const pid = (typeof pidOverride === "string" ? pidOverride : "") || projectId() || lastProject;
        if (!pid) {
            requestVersion++;
            nodes = [];
            edges = [];
            graphSignature = "";
            activeIds.clear();
            activeEdgeIds.clear();
            resetScene();
            buildGraph();
            setStatus("Select a project to inspect its runtime graph");
            return;
        }

        const version = ++requestVersion;
        try {
            const [payload, topology] = await Promise.all([
                authenticatedJson("/api/v1/memory/graph-status/" + encodeURIComponent(pid)),
                loadRuntimeTopology(pid, forceTopology)
            ]);
            if (version !== requestVersion) return;

            const memoryNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
            const memoryEdges = Array.isArray(payload.edges) ? payload.edges : [];
            const combinedNodes = memoryNodes.concat(topology.nodes);
            const combinedEdges = memoryEdges.concat(topology.edges);
            const signature = combinedNodes.length + ":" + combinedEdges.length + ":" +
                combinedNodes.map(node => node.id + "|" + node.type).join(",") + ":" +
                combinedEdges.map(edge => edge.id).join(",");
            const projectChanged = pid !== lastProject;
            nodes = combinedNodes;
            edges = combinedEdges;
            lastProject = pid;
            if (signature !== graphSignature) {
                graphSignature = signature;
                if (projectChanged) resetScene();
                buildGraph();
            }

            const memoryCount = memoryNodes.length;
            setStatus("RUNTIME GRAPH · " + nodes.length + " OBJECTS · " + edges.length + " LINKS · " + memoryCount + " MEMORY");
        } catch (error) {
            if (version !== requestVersion) return;
            setStatus("Runtime graph unavailable · " + String(error.message || error).slice(0, 64));
            console.error("[MemoryGraph] Runtime graph fetch failed", error);
        }
    }

    // ---- Memory events ---------------------------------------------------
    function endRun() {
        endRunTimer = 0;
        processActive = false;
        activeIds.clear();
        activeEdgeIds.clear();
        applyActive();     // targets fall to 0 -> smooth fade; every node and edge stays on screen
        if (nodes.length) setStatus("RUNTIME GRAPH · " + nodes.length + " OBJECTS · " + edges.length + " LINKS");
    }

    function addContextActive(item) {
        if (!item || typeof item !== "object") return;
        const modeValue = String(item.mode || item.strategy || "").toLowerCase().replace(/[^a-z]/g, "");
        const modeAliases = { auto: "auto", automatic: "auto", coding: "coding", atm: "coding", local: "local", manual: "manual" };
        const modeId = modeAliases[modeValue];
        if (modeId) activeIds.add("chat-mode:" + modeId);

        const roleValue = String(item.role || item.agent_role || item.agent || "").toLowerCase();
        if (roleValue) {
            const roleNode = nodes.find(node => node.type === "role" && String(node.label).toLowerCase() === roleValue);
            if (roleNode) activeIds.add(String(roleNode.id));
        }

        const modelValue = String(item.model || item.model_id || "").toLowerCase().trim();
        if (modelValue) {
            const modelNode = nodes.find(node =>
                node.type === "model" &&
                (String(node.label).toLowerCase() === modelValue ||
                 String(node.id).toLowerCase().endsWith(":" + modelValue) ||
                 modelValue.includes(String(node.label).toLowerCase()))
            );
            if (modelNode) {
                activeIds.add(String(modelNode.id));
                const providerName = String(modelNode.id).split(":")[1];
                const providerId = "provider:" + providerName;
                if (nodes.some(node => String(node.id) === providerId)) activeIds.add(providerId);
            }
        }
    }

    function addActive(item) {
        if (Array.isArray(item.active_node_ids)) item.active_node_ids.forEach(id => activeIds.add(String(id)));
        if (Array.isArray(item.active_edge_ids)) item.active_edge_ids.forEach(id => activeEdgeIds.add(String(id)));
        addContextActive(item);
    }

    const hasUnknown = () => [...activeIds].some(id => !indexById.has(id));

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
            addContextActive(detail);
            applyActive();
            setStatus("Runtime operation running · tracing active graph objects");
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
            if (hasUnknown()) loadGraph(lastProject);   // buildGraph() re-applies the active state after loading
            else applyActive();
            return;
        }

        if (detail.phase === "completed") {
            processActive = true;
            addActive(detail);
            activity({ label: "Memory context ready", detail: "SQLite graph updated" });
            if (hasUnknown()) loadGraph(eventProject || lastProject);
            else applyActive();
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
    function easeBuffer(attribute, target, factor, perItem) {
        const arr = attribute.array;
        let dirty = false;
        for (let i = 0; i < target.length; i++) {
            const current = arr[i * perItem];
            const diff = target[i] - current;
            if (diff === 0) continue;
            const next = Math.abs(diff) < 0.004 ? target[i] : current + diff * factor;
            for (let v = 0; v < perItem; v++) arr[i * perItem + v] = next;
            dirty = true;
        }
        if (dirty) attribute.needsUpdate = true;
    }

    function animate(now) {
        raf = 0;
        if (document.hidden || root.style.display === "none") return;

        const delta = lastFrame ? Math.min(40, now - lastFrame) : 16;
        lastFrame = now;
        pulseClock += delta;

        // Rotation is unconditional: it never depends on AI activity.
        graphGroup.rotation.y += rotationSpeed * delta;
        graphGroup.rotation.x = Math.sin(pulseClock * 0.00012) * 0.055;

        nodeMaterial.uniforms.uTime.value = pulseClock;
        edgeMaterial.uniforms.uTime.value = pulseClock;
        if (nodePoints) easeBuffer(nodePoints.geometry.attributes.aActive, nodeTarget, 1 - Math.exp(-delta / 150), 1);
        if (edgeLines) easeBuffer(edgeLines.geometry.attributes.aAct, edgeTarget, 1 - Math.exp(-delta / 220), 2);

        updateLabels();
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
        labelLayer.style.display = value ? "none" : "";
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

    resizeObserver = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => resize()) : null;
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
        buildGraph();
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
        nodeMaterial?.dispose();
        glowMaterial?.dispose();
        edgeMaterial?.dispose();
        labelLayer.remove();
        renderer?.dispose();
    }, { once: true });

    // Debug hook: localStorage.rf_debug_graph = "1" -> window.__rfMemoryGraphDebug()
    if (localStorage.getItem("rf_debug_graph") === "1") {
        window.__rfMemoryGraphDebug = () => ({
            points: nodePoints ? nodePoints.geometry.attributes.position.count : 0,
            apiNodes: nodes.length,
            apiEdges: edges.length,
            drawnEdges: edgeLines ? edgeLines.geometry.attributes.position.count / 2 : 0,
            activeNodes: nodePoints ? [...nodePoints.geometry.attributes.aActive.array].filter(v => v > 0.5).length : 0,
            activeEdges: edgeLines ? [...edgeLines.geometry.attributes.aAct.array].filter(v => v > 0.5).length / 2 : 0,
            rotationY: graphGroup.rotation.y,
            positions: Object.fromEntries([...positionById].map(([id, p]) => [id, p.map(v => +v.toFixed(5))]))
        });
    }

    loadGraph().finally(() => start());
    refreshTimer = window.setInterval(() => loadGraph(), 15000);
    start();
})();