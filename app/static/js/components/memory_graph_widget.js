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
    const FOV = 38, CAM_Z = 4.85, RADIUS = 1.82;
    const AMBIENT_SHELL_POINTS = 100;
    const MIN_ACTIVE_MS = 2500;        // real activity stays visible long enough to be seen
    const EDGE_IDLE_ALPHA = 0.16;      // faint always-on web of real edges (0 = show edges only while active)
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

    // Deterministic seed: type cluster centre + id-hashed offset inside a blob.
    function seedPosition(node, radius) {
        const id = String(node.id);
        const anchor = typeAnchor(node.type, radius);
        const dir = unitVector(id, 0x1b873593);
        const blob = radius * 0.78 * Math.cbrt(hash01(id, 0xc2b2ae35));
        return [anchor[0] + dir[0] * blob, anchor[1] + dir[1] * blob, anchor[2] + dir[2] * blob];
    }

    // Relax ONLY nodes without a cached position; cached nodes are pinned, so existing points never move.
    function layoutGraph(nodeList, edgeList, cache, radius) {
        const fresh = new Set();
        nodeList.forEach(node => {
            const id = String(node.id);
            if (!cache.has(id)) { cache.set(id, seedPosition(node, radius)); fresh.add(id); }
        });
        if (!fresh.size) return;

        const ids = nodeList.map(node => String(node.id)).sort();
        const index = new Map(ids.map((id, i) => [id, i]));
        const pos = ids.map(id => cache.get(id));
        const free = ids.map(id => fresh.has(id));
        const links = [];
        edgeList.forEach(edge => {
            const a = index.get(String(edge.source)), b = index.get(String(edge.target));
            if (a !== undefined && b !== undefined && a !== b && (free[a] || free[b])) links.push([a, b]);
        });
        const iterations = ids.length <= 400 ? 40 : ids.length <= 1200 ? 12 : 0;
        const REP = 0.32, REST = 0.42;
        for (let it = 0; it < iterations; it++) {
            const force = ids.map(() => [0, 0, 0]);
            for (let i = 0; i < ids.length; i++) {
                for (let j = i + 1; j < ids.length; j++) {
                    if (!free[i] && !free[j]) continue;
                    const dx = pos[i][0] - pos[j][0], dy = pos[i][1] - pos[j][1], dz = pos[i][2] - pos[j][2];
                    const d2 = dx * dx + dy * dy + dz * dz;
                    if (d2 >= REP * REP || d2 === 0) continue;
                    const d = Math.sqrt(d2), f = (REP - d) / REP * 0.03 / d;
                    force[i][0] += dx * f; force[i][1] += dy * f; force[i][2] += dz * f;
                    force[j][0] -= dx * f; force[j][1] -= dy * f; force[j][2] -= dz * f;
                }
            }
            links.forEach(([a, b]) => {
                const dx = pos[b][0] - pos[a][0], dy = pos[b][1] - pos[a][1], dz = pos[b][2] - pos[a][2];
                const d = Math.hypot(dx, dy, dz) || 1, f = (d - REST) * 0.012 / d;
                force[a][0] += dx * f; force[a][1] += dy * f; force[a][2] += dz * f;
                force[b][0] -= dx * f; force[b][1] -= dy * f; force[b][2] -= dz * f;
            });
            for (let i = 0; i < ids.length; i++) {
                if (!free[i]) continue;
                const p = pos[i], f = force[i];
                const step = Math.min(0.06, Math.hypot(f[0], f[1], f[2])) / (Math.hypot(f[0], f[1], f[2]) || 1);
                p[0] += f[0] * step; p[1] += f[1] * step; p[2] += f[2] * step;
                const len = Math.hypot(p[0], p[1], p[2]);
                if (len > radius) { p[0] *= radius / len; p[1] *= radius / len; p[2] *= radius / len; }
            }
        }
    }
    // LAYOUT-END

    // Shaders do no colour-space conversion, so sRGB values are written as-is.
    const rawColor = hex => new THREE.Color().setHex(hex, THREE.LinearSRGBColorSpace);
    const PALETTE = {
        project: 0xbfe9ff, conversation: 0x8f6bff, memoryquery: 0x9b94c9, decision: 0xf0bd55,
        file: 0x4fe0c0, code: 0x4fe0c0, symbol: 0x6aa8ff, memory: 0x9a74ff
    };
    const nodeColor = node => rawColor(PALETTE[String(node.type || "memory").toLowerCase()] || PALETTE.memory);

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

        // 100 ambient shell particles form the outer globe. Visual only:
        // they are not SQLite nodes and are never connected by graph edges.
        const shellPositions = new Float32Array(AMBIENT_SHELL_POINTS * 3);
        const goldenAngle = Math.PI * (3 - Math.sqrt(5));
        for (let i = 0; i < AMBIENT_SHELL_POINTS; i++) {
            const y = 1 - (i / (AMBIENT_SHELL_POINTS - 1)) * 2;
            const ring = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = goldenAngle * i;
            const radius = RADIUS * 1.035;
            shellPositions.set([
                Math.cos(theta) * ring * radius,
                y * radius,
                Math.sin(theta) * ring * radius
            ], i * 3);
        }
        // Build a spherical lattice: each surface point joins its three
        // nearest neighbours. These struts are shell geometry, not memory edges.
        const shellLinks = [];
        const linked = new Set();
        for (let i = 0; i < AMBIENT_SHELL_POINTS; i++) {
            const nearest = [];
            for (let j = 0; j < AMBIENT_SHELL_POINTS; j++) {
                if (i === j) continue;
                const dx = shellPositions[i * 3] - shellPositions[j * 3];
                const dy = shellPositions[i * 3 + 1] - shellPositions[j * 3 + 1];
                const dz = shellPositions[i * 3 + 2] - shellPositions[j * 3 + 2];
                nearest.push({ j, d: dx * dx + dy * dy + dz * dz });
            }
            nearest.sort((a, b) => a.d - b.d);
            for (const item of nearest.slice(0, 3)) {
                const lo = Math.min(i, item.j), hi = Math.max(i, item.j);
                const key = lo + ":" + hi;
                if (linked.has(key)) continue;
                linked.add(key);
                shellLinks.push(
                    shellPositions[lo * 3], shellPositions[lo * 3 + 1], shellPositions[lo * 3 + 2],
                    shellPositions[hi * 3], shellPositions[hi * 3 + 1], shellPositions[hi * 3 + 2]
                );
            }
        }
        const shellLineGeometry = new THREE.BufferGeometry();
        shellLineGeometry.setAttribute("position", new THREE.Float32BufferAttribute(shellLinks, 3));
        const shellLineMaterial = new THREE.LineBasicMaterial({
            color: 0x6685a8, transparent: true, opacity: 0.28,
            depthTest: true, depthWrite: true
        });
        shellMesh = new THREE.LineSegments(shellLineGeometry, shellLineMaterial);
        shellMesh.frustumCulled = false;
        shellMesh.renderOrder = 0;
        graphGroup.add(shellMesh);

        const shellGeometry = new THREE.BufferGeometry();
        shellGeometry.setAttribute("position", new THREE.BufferAttribute(shellPositions, 3));
        const shellMaterial = new THREE.PointsMaterial({
            color: 0xb5c9e6, size: 0.052, sizeAttenuation: true,
            transparent: true, opacity: 0.96, depthTest: true, depthWrite: true
        });
        ambientPoints = new THREE.Points(shellGeometry, shellMaterial);
        ambientPoints.frustumCulled = false;
        ambientPoints.renderOrder = 1;
        graphGroup.add(ambientPoints);
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
        setStatus("LIVE SQLITE GRAPH · " + count + " NODES · " + edges.length + " EDGES" + activeText);
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
            buildGraph();
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
                buildGraph();
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
        applyActive();     // targets fall to 0 -> smooth fade; every node and edge stays on screen
        if (nodes.length) setStatus("LIVE SQLITE GRAPH · " + nodes.length + " NODES · " + edges.length + " EDGES");
    }

    function addActive(item) {
        if (Array.isArray(item.active_node_ids)) item.active_node_ids.forEach(id => activeIds.add(String(id)));
        if (Array.isArray(item.active_edge_ids)) item.active_edge_ids.forEach(id => activeEdgeIds.add(String(id)));
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
            applyActive();
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
        ambientPoints?.geometry.dispose();
        ambientPoints?.material.dispose();
        if (shellMesh) { graphGroup.remove(shellMesh); shellMesh.geometry.dispose(); shellMesh.material.dispose(); shellMesh = null; }
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