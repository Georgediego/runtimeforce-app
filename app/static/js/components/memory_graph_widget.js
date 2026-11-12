import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
import { eventBus } from "../core/event_bus.js";

(() => {
    const root = document.getElementById("rf-memory-widget");
    const canvas = document.getElementById("rf-memory-sphere");
    if (!root || !canvas) return;

    const statusEl = document.getElementById("rf-memory-widget-status");
    const countEl = document.getElementById("rf-memory-widget-count");
    const edgeCountEl = document.getElementById("rf-memory-widget-edges");
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
    const FOV = 38, CAM_Z = 4.85, RADIUS = 1.48;
    const MIN_ACTIVE_MS = 2500;        // real activity stays visible long enough to be seen
    const EDGE_IDLE_ALPHA = 0.18;        // visible, but subdued, real graph relationships
    const HOT = 0x62ff83;

    // ---- State -----------------------------------------------------------
    let nodes = [];
    let edges = [];
    let activeIds = new Set();
    const everActiveIds = new Set();
    let activeEdgeIds = new Set();
    let generationActive = false;
    let graphSignature = "";
    let lastProject = "";
    let requestVersion = 0;
    let renderer, scene, camera, graphGroup;
    let raf = 0, refreshTimer = 0, resizeObserver = null, endRunTimer = 0;
    let lastFrame = 0, pulseClock = 0;
    let processActive = false, runStartedAt = 0;
    let pointerDown = false, pointerX = 0;
    let focusedNodeId = "";
    let focusPending = false;
    let tumbleVelocity = new THREE.Vector3(0.0011, 0.0017, 0.0008);
    let tumbleChangeAt = 0;

    let nodePoints = null, glowPoints = null, edgeLines = null;
    let nodeMaterial = null, glowMaterial = null, edgeMaterial = null;
    let positionById = new Map();      // id -> [x, y, z]
    let indexById = new Map();         // node id -> buffer index
    let edgeIndexById = new Map();     // edge id -> segment index
    let nodeTarget = new Float32Array(0);
    let edgeTarget = new Float32Array(0);
    const layoutCache = new Map();     // id -> [x, y, z], survives data refreshes

    const setStatus = value => { if (statusEl) statusEl.textContent = value; };

    // ---- Distributed graph layout ---------------------------------------
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

    // Distributed 3D layout: node positions are derived from real graph relationships.
    // Organic 3D force layout: no core, no radial spokes, no type-based center.
    // Real edges gently pull their endpoints together; repulsion distributes every node.
    function layoutGraph(nodeList, edgeList, cache, radius) {
        const count = nodeList.length;
        if (!count) return;

        // Every real entity occupies a point on one spherical shell.
        // Fibonacci distribution avoids a fake core, spokes, or decorative geometry.
        const goldenAngle = Math.PI * (3 - Math.sqrt(5));
        const shellRadius = radius * 0.82;
        const jitter = radius * 0.012;
        nodeList.forEach((node, i) => {
            const id = String(node.id);
            const y = 1 - 2 * ((i + 0.5) / count);
            const ring = Math.sqrt(Math.max(0, 1 - y * y));
            const angle = goldenAngle * i;
            const depth = (hash01(id, 0x73a91d) - 0.5) * 2 * jitter;
            const r = shellRadius + depth;
            cache.set(id, [
                Math.cos(angle) * ring * r,
                y * r,
                Math.sin(angle) * ring * r
            ]);
        });
    }
    // LAYOUT-END

    // Shaders do no colour-space conversion, so sRGB values are written as-is.
    const rawColor = hex => new THREE.Color().setHex(hex, THREE.LinearSRGBColorSpace);
    const PALETTE = {
        project: 0x69ff91, conversation: 0x45e978, memoryquery: 0x8affaa, decision: 0xb0ffc2,
        file: 0x50f080, code: 0x72ff9a, symbol: 0x3fe875, memory: 0x9bffb2,
        workspace: 0x64f58a, directory: 0x38d96c, provider: 0x72ff9a, model: 0x9affb3,
        role: 0x55ed7d, tool: 0x83ffa2, mode: 0x6bf58f
    };
    const INACTIVE_NODE_COLOR = 0x42d96e;
    const nodeColor = node => rawColor(PALETTE[String(node?.type || "memory").toLowerCase()] || PALETTE.memory);

    // ---- Shaders ---------------------------------------------------------
    const DEPTH_GLSL = "float depth = clamp((-mv.z - 4.0) / 3.6, 0.0, 1.0);";

    const ICON_INDEX = {
        model: 0, provider: 0, file: 1, code: 1, memory: 2, memoryquery: 2,
        project: 3, workspace: 3, directory: 3, conversation: 4, decision: 5,
        symbol: 6, role: 7, tool: 8, mode: 9, summary: 10
    };

    function createIconAtlas() {
        const cell = 32, columns = 4;
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = cell * columns;
        const ctx = canvas.getContext("2d");
        const types = ["model", "file", "memory", "project", "conversation", "decision", "symbol", "role", "tool", "mode", "summary"];
        types.forEach((type, index) => {
            const x = (index % columns) * cell, y = Math.floor(index / columns) * cell;
            ctx.save();
            ctx.translate(x, y);
            ctx.strokeStyle = "#ffffff";
            ctx.fillStyle = "#ffffff";
            ctx.lineWidth = 2.3;
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            if (type === "model") {
                ctx.strokeRect(9, 9, 14, 14);
                for (let k = 0; k < 4; k++) {
                    const q = 11 + k * 3.4;
                    ctx.beginPath(); ctx.moveTo(q, 5); ctx.lineTo(q, 9); ctx.moveTo(q, 23); ctx.lineTo(q, 27);
                    ctx.moveTo(5, q); ctx.lineTo(9, q); ctx.moveTo(23, q); ctx.lineTo(27, q); ctx.stroke();
                }
                ctx.strokeRect(13, 13, 6, 6);
            } else if (type === "file") {
                ctx.beginPath(); ctx.moveTo(9, 5); ctx.lineTo(19, 5); ctx.lineTo(24, 10); ctx.lineTo(24, 27);
                ctx.lineTo(9, 27); ctx.closePath(); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(19, 5); ctx.lineTo(19, 10); ctx.lineTo(24, 10);
                ctx.moveTo(12, 16); ctx.lineTo(21, 16); ctx.moveTo(12, 21); ctx.lineTo(21, 21); ctx.stroke();
            } else if (type === "memory") {
                ctx.beginPath(); ctx.moveTo(16, 26);
                ctx.bezierCurveTo(12, 29, 8, 25, 9, 21); ctx.bezierCurveTo(5, 18, 7, 12, 11, 11);
                ctx.bezierCurveTo(11, 6, 16, 5, 18, 9); ctx.bezierCurveTo(23, 6, 27, 11, 25, 15);
                ctx.bezierCurveTo(29, 19, 26, 25, 22, 25); ctx.bezierCurveTo(20, 28, 17, 27, 16, 26); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(16, 9); ctx.lineTo(16, 26); ctx.moveTo(11, 14); ctx.lineTo(14, 16);
                ctx.moveTo(21, 13); ctx.lineTo(18, 16); ctx.moveTo(11, 21); ctx.lineTo(14, 20);
                ctx.moveTo(21, 20); ctx.lineTo(18, 22); ctx.stroke();
            } else if (type === "project") {
                ctx.beginPath(); ctx.moveTo(5, 11); ctx.lineTo(13, 11); ctx.lineTo(16, 14); ctx.lineTo(27, 14);
                ctx.lineTo(25, 26); ctx.lineTo(6, 26); ctx.closePath(); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(5, 11); ctx.lineTo(7, 7); ctx.lineTo(15, 7); ctx.lineTo(18, 11); ctx.stroke();
            } else if (type === "conversation") {
                ctx.beginPath(); ctx.moveTo(7, 8); ctx.lineTo(25, 8); ctx.lineTo(25, 21); ctx.lineTo(16, 21);
                ctx.lineTo(10, 26); ctx.lineTo(10, 21); ctx.lineTo(7, 21); ctx.closePath(); ctx.stroke();
                [12, 16, 20].forEach(q => { ctx.beginPath(); ctx.arc(q, 14.5, 0.8, 0, Math.PI * 2); ctx.fill(); });
            } else if (type === "decision") {
                ctx.beginPath(); ctx.arc(16, 16, 10, 0, Math.PI * 2); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(10, 16); ctx.lineTo(14, 20); ctx.lineTo(22, 11); ctx.stroke();
            } else if (type === "symbol") {
                ctx.font = "bold 23px monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("{ }", 16, 16);
            } else if (type === "summary") {
                ctx.beginPath(); ctx.moveTo(8, 6); ctx.lineTo(24, 6); ctx.lineTo(24, 26); ctx.lineTo(8, 26); ctx.closePath(); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(12, 12); ctx.lineTo(20, 12); ctx.moveTo(12, 17); ctx.lineTo(20, 17); ctx.moveTo(12, 22); ctx.lineTo(18, 22); ctx.stroke();
            } else if (type === "role") {
                ctx.beginPath(); ctx.arc(16, 11, 4, 0, Math.PI * 2); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(7, 26); ctx.bezierCurveTo(7, 17, 25, 17, 25, 26); ctx.stroke();
            } else if (type === "tool") {
                ctx.beginPath(); ctx.arc(10, 10, 4, 0, Math.PI * 2); ctx.moveTo(13, 13); ctx.lineTo(24, 24);
                ctx.moveTo(19, 23); ctx.lineTo(23, 19); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(7, 7); ctx.lineTo(11, 11); ctx.stroke();
            } else if (type === "mode") {
                [10, 16, 22].forEach((q, i) => {
                    ctx.beginPath(); ctx.moveTo(6, q); ctx.lineTo(26, q); ctx.stroke();
                    ctx.beginPath(); ctx.arc([12, 21, 15][i], q, 2, 0, Math.PI * 2); ctx.fill();
                });
            }
            ctx.restore();
        });
        const texture = new THREE.CanvasTexture(canvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.magFilter = THREE.LinearFilter;
        texture.minFilter = THREE.LinearFilter;
        texture.generateMipmaps = false;
        return texture;
    }
    const iconAtlas = createIconAtlas();

    function createNodeMaterial() {
        // Tiny luminous particles represent actual runtime entities.
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: false, depthTest: true,
            uniforms: { uScale: { value: 300 } },
            vertexShader: `
                attribute vec3 aColor;
                attribute float aSize, aActive, aMarked;
                uniform float uScale;
                varying vec3 vColor;
                varying float vActive, vMarked, vDepth;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    ${DEPTH_GLSL}
                    gl_Position = projectionMatrix * mv;
                    gl_PointSize = max(1.4, aSize * (1.0 + aActive * 0.10) * uScale / -mv.z);
                    vColor = aColor; vActive = aActive; vMarked = aMarked; vDepth = depth;
                }`,
            fragmentShader: `
                varying vec3 vColor;
                varying float vActive, vMarked, vDepth;
                void main() {
                    vec2 p = gl_PointCoord - 0.5;
                    float d = length(p);
                    if (d > 0.5) discard;
                    float core = 1.0 - smoothstep(0.06, 0.5, d);
                    float alpha = mix(0.32, 0.68, vMarked);
                    alpha = mix(alpha, 1.0, vActive);
                    vec3 col = mix(vColor, vec3(0.38, 1.0, 0.55), vActive * 0.86);
                    col *= mix(1.0, 0.38, vDepth);
                    gl_FragColor = vec4(col, core * alpha);
                }`
        });
    }

    function createGlowMaterial() {
        // Soft local bloom, drawn only for nodes with aActive > 0.
        return new THREE.ShaderMaterial({
            transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
            uniforms: { uScale: { value: 300 }, uTime: { value: 0 }, uHot: { value: rawColor(HOT) } },
            vertexShader: `
                attribute vec3 aColor;
                attribute float aSize, aActive, aMarked;
                uniform float uScale;
                varying vec3 vColor;
                varying float vActive, vMarked;
                void main() {
                    vec4 mv = modelViewMatrix * vec4(position, 1.0);
                    gl_Position = projectionMatrix * mv;
                    gl_PointSize = aSize * (1.6 + aActive * 1.0) * uScale / -mv.z;
                    if (aActive < 0.02) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); gl_PointSize = 0.0; }
                    vColor = aColor; vActive = aActive; vMarked = aMarked;
                }`,
            fragmentShader: `
                varying vec3 vColor;
                varying float vActive, vMarked;
                void main() {
                    vec2 p = (gl_PointCoord - 0.5) * 2.0;
                    float d = length(p);
                    if (d > 1.0) discard;
                    float glow = exp(-d * d * 4.2);
                    float core = 1.0 - smoothstep(0.0, 0.42, d);
                    float a = glow * 0.22 * vActive;
                    gl_FragColor = vec4(mix(vColor, vec3(0.72, 1.0, 0.80), core * 0.22), a);
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
                    float idleFlow = spark * (0.025 + 0.035 * (0.5 + 0.5 * sin(uTime * 0.001 + vAlong * 6.283)));
                    float activeFlow = 0.48 + 0.50 * spark;
                    float a = mix(uIdle + idleFlow, activeFlow, vAct) * mix(1.0, 0.68, vDepth);
                    vec3 col = mix(vColor * 1.35 + 0.20, uHot, vAct);
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
        "padding:1px 5px;border-radius:3px;color: #aaffbd;background:rgba(3,18,9,.90);border:1px solid rgba(75,255,125,.32);" +
        "transition:opacity .15s;will-change:transform}" +
        ".rf-memory-label.hot{font-size:10px;font-weight:700;color:#eaffef;background:rgba(5,54,22,.95);border-color:#65ff8b;" +
        "box-shadow:0 0 12px rgba(75,255,125,.38)}";
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
            }
        }
        const w = canvas.clientWidth, h = canvas.clientHeight;
        graphGroup.updateMatrixWorld(true);
        let used = 0;
        picks.forEach(({ i, hot }) => {
            const node = nodes[i];
            const pos = positionById.get(String(node.id));
            if (!node || !pos) return;
            labelVec.set(pos[0], pos[1], pos[2]).applyMatrix4(graphGroup.matrixWorld);
            if (labelVec.z < -0.15 * RADIUS) return;                       // avoid labels behind the camera
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
            const text = String(node.label || node.id || node.type || "").trim();
            if (el.textContent !== text) el.textContent = text;
            el.style.opacity = "1";
            el.style.transform = "translate(" + Math.round(x + 7) + "px," + Math.round(y - 8) + "px)";
            used++;
        });
        for (let k = used; k < labelPool.length; k++) labelPool[k].style.opacity = "0";
    }

    // Runtime visualization contains only real graph entities and relationships.

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
        nodePoints?.geometry.dispose();
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
        const presentEdges = new Set(edges.map(edge => String(edge.id)));
        [...layoutCache.keys()].forEach(id => { if (!present.has(id)) layoutCache.delete(id); });
        [...everActiveIds].forEach(id => { if (!present.has(id)) everActiveIds.delete(id); });
        [...activeIds].forEach(id => { if (!present.has(id)) activeIds.delete(id); });
        [...activeEdgeIds].forEach(id => { if (!presentEdges.has(id)) activeEdgeIds.delete(id); });
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
            const marked = new Float32Array(count);
            const icons = new Float32Array(count);
            const colorById = new Map();
            nodes.forEach((node, i) => {
                const id = String(node.id);
                const pos = layoutCache.get(id);
                const color = nodeColor(node);
                positions.set(pos, i * 3);
                colors.set([color.r, color.g, color.b], i * 3);
                const deg = degree.get(id) || 0;
                sizes[i] = 0.055;
                icons[i] = ICON_INDEX[String(node.type || "").toLowerCase()] ?? ICON_INDEX.symbol;
                active[i] = carryNodes.get(id) || 0;
                marked[i] = everActiveIds.has(id) ? 1 : 0;
                positionById.set(id, pos);
                indexById.set(id, i);
                colorById.set(id, color);
            });
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute("aColor", new THREE.BufferAttribute(colors, 3));
            geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
            geometry.setAttribute("aActive", new THREE.BufferAttribute(active, 1));
            geometry.setAttribute("aMarked", new THREE.BufferAttribute(marked, 1));
            geometry.setAttribute("aIcon", new THREE.BufferAttribute(icons, 1));

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

        } else {
            edgeTarget = new Float32Array(0);

        }

        rememberActiveNodes(); // Include events received before an async graph refresh completed.
        applyActive();
        if (countEl) countEl.textContent = count + " NODES";
        if (edgeCountEl) edgeCountEl.textContent = edges.length + " EDGES";
        const activeText = processActive && activeIds.size ? " · " + activeIds.size + " ACTIVE" : "";
        setStatus("RUNTIME GRAPH · " + count + " OBJECTS · " + edges.length + " LINKS" + activeText);
    }

    function clearPersistentHighlights() {
        activeIds.clear();
        activeEdgeIds.clear();
        everActiveIds.clear();
        focusedNodeId = "";
        focusPending = false;
        const marked = nodePoints?.geometry.attributes.aMarked;
        if (marked) {
            marked.array.fill(0);
            marked.needsUpdate = true;
        }
    }

    // Targets come only from ids reported by the memory pipeline that exist in the loaded SQLite rows.
    function applyActive() {
        nodeTarget.fill(0);
        edgeTarget.fill(0);
        const activeSet = new Set(activeIds);

        if (processActive) {
            // Reveal only real stored relationships attached to an active entity.
            edges.forEach(edge => {
                const source = String(edge.source), target = String(edge.target);
                if (!activeSet.has(source) && !activeSet.has(target)) return;
                activeEdgeIds.add(String(edge.id));
                activeSet.add(source);
                activeSet.add(target);
            });
        }

        if (edgeLines) edgeLines.visible = true;
        activeSet.forEach(nodeId => {
            const i = indexById.get(nodeId);
            if (i === undefined) return;
            everActiveIds.add(nodeId);
            nodeTarget[i] = processActive ? 1 : 0;
            const marked = nodePoints?.geometry.attributes.aMarked;
            if (marked && marked.array[i] !== 1) {
                marked.array[i] = 1;
                marked.needsUpdate = true;
            }
        });
        activeEdgeIds.forEach(edgeId => {
            const k = edgeIndexById.get(edgeId);
            // Keep discovered links bright and pulsing until the next iteration clears them.
            if (k !== undefined) edgeTarget[k] = processActive ? 1 : 0.72;
        });
    }

    // ---- Runtime topology sources ---------------------------------------
    // Cached separately because model discovery is more expensive than the memory graph query.
    let topologyNodes = [];
    let topologyEdges = [];
    let topologyLoadedAt = 0;
    let modelsLoadedAt = 0;
    const SKIP_TREE_NAMES = new Set([".git", "__pycache__", "node_modules", "venv", ".venv", ".pytest_cache", "staticfiles", "media", ".cache", ".DS_Store"]);
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
        const maxNodes = 800;
        const maxDepth = 6;

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
                (Array.isArray(models) ? models : []).forEach(model => {
                    const modelId = "model:" + provider + ":" + String(model.id || model.name);
                    outNodes.push({ id: modelId, label: String(model.name || model.id), type: "model", source: "models" });
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
            // Only entities returned by live workspace/model APIs are added here.
            topologyNodes = workspace.nodes.concat(models.nodes);
            topologyEdges = workspace.edges.concat(models.edges);
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
        if (generationActive) return;
        processActive = false;
        activeIds.clear();
        applyActive();     // keep completed real relationships visible and pulsing
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
            if (roleNode) {
                focusedNodeId = String(roleNode.id);
                focusPending = true;
                activeIds.add(focusedNodeId);
            }
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
                focusedNodeId = String(modelNode.id);
                focusPending = true;
                activeIds.add(focusedNodeId);
            }
        }
    }

    function rememberActiveNodes() {
        activeIds.forEach(id => {
            if (!indexById.has(id)) return;
            everActiveIds.add(id);
            const attribute = nodePoints?.geometry.attributes.aMarked;
            const index = indexById.get(id);
            if (attribute && attribute.array[index] !== 1) {
                attribute.array[index] = 1;
                attribute.needsUpdate = true;
            }
        });
    }

    function addActive(item) {
        if (Array.isArray(item.active_node_ids)) {
            item.active_node_ids.forEach(id => {
                const value = String(id);
                activeIds.add(value);
                if (indexById.has(value)) { focusedNodeId = value; focusPending = true; }
            });
        }
        if (Array.isArray(item.active_edge_ids)) item.active_edge_ids.forEach(id => activeEdgeIds.add(String(id)));
        addContextActive(item);
        const toolName = String(item.tool_name || item.tool || "").trim();
        if (toolName) {
            const toolId = "agent-tool:" + toolName;
            if (indexById.has(toolId)) {
                activeIds.add(toolId);
                focusedNodeId = toolId;
                focusPending = true;
            }
        }
        rememberActiveNodes();
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
            clearPersistentHighlights();
            addContextActive(detail);
            rememberActiveNodes();
            applyActive();
            setStatus("Runtime operation running · tracing active graph objects");
            loadGraph(eventProject || lastProject);
            return;
        }

        if (detail.phase === "activity" && detail.event) {
            const item = detail.event;
            if (endRunTimer) { clearTimeout(endRunTimer); endRunTimer = 0; }
            processActive = true;
            addActive(item);
            if (hasUnknown()) loadGraph(lastProject);   // buildGraph() re-applies the active state after loading
            else applyActive();
            return;
        }

        if (detail.phase === "completed") {
            processActive = true;
            addActive(detail);
            if (hasUnknown()) loadGraph(eventProject || lastProject);
            else applyActive();
            // Keep the graph alive for the full assistant generation, not just the memory event.
            if (!generationActive) {
                const remaining = Math.max(1200, MIN_ACTIVE_MS - (performance.now() - runStartedAt));
                if (endRunTimer) clearTimeout(endRunTimer);
                endRunTimer = setTimeout(endRun, remaining);
            }
            return;
        }

        if (detail.phase === "failed") {
            if (endRunTimer) { clearTimeout(endRunTimer); endRunTimer = 0; }
            endRun();
            setStatus("Memory query failed");
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

        // Continuous free tumbling across all three axes.
        // A real active entity is smoothly brought to the camera-facing side first.
        if (focusPending && focusedNodeId && positionById.has(focusedNodeId)) {
            const p = positionById.get(focusedNodeId);
            const direction = new THREE.Vector3(p[0], p[1], p[2]).normalize();
            const target = new THREE.Quaternion().setFromUnitVectors(direction, new THREE.Vector3(0, 0, 1));
            graphGroup.quaternion.slerp(target, 1 - Math.exp(-delta / 430));
            if (graphGroup.quaternion.angleTo(target) < 0.012) {
                graphGroup.quaternion.copy(target);
                focusPending = false;
                tumbleChangeAt = pulseClock + 700;
            }
        } else {
            if (pulseClock >= tumbleChangeAt) {
                const sign = () => Math.random() < 0.5 ? -1 : 1;
                tumbleVelocity.set(
                    sign() * (0.00045 + Math.random() * 0.00135),
                    sign() * (0.00055 + Math.random() * 0.00155),
                    sign() * (0.00035 + Math.random() * 0.00125)
                );
                tumbleChangeAt = pulseClock + 1800 + Math.random() * 2600;
            }
            graphGroup.rotateX(tumbleVelocity.x * delta);
            graphGroup.rotateY(tumbleVelocity.y * delta);
            graphGroup.rotateZ(tumbleVelocity.z * delta);
        }
        const breathe = 1 + Math.sin(pulseClock * 0.0007) * (processActive ? 0.004 : 0.002);
        graphGroup.scale.setScalar(breathe);

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

    eventBus.on("session:deleted", () => {
        // A deleted chat must leave no visual activity residue in the runtime graph.
        activeIds.clear();
        everActiveIds.clear();
        activeEdgeIds.clear();
        if (!generationActive) processActive = false;
        graphSignature = "";
        loadGraph(lastProject);
    });

    eventBus.on("generation:state", state => {
        generationActive = Boolean(state?.active);
        if (endRunTimer) { clearTimeout(endRunTimer); endRunTimer = 0; }
        if (generationActive) {
            if (!processActive) clearPersistentHighlights();
            processActive = true;
            const strategy = document.getElementById("strategy-select")?.value || "auto";
            addActive({ mode: strategy });
            setStatus("Assistant generating · runtime graph active");
            applyActive();
        } else {
            endRun();
        }
    });

    eventBus.on("agent:graph_event", event => {
        if (!event || !generationActive) return;
        processActive = true;
        addActive(event);
        const phaseLabel = event.label || event.tool_name || event.model || event.status;
        if (phaseLabel) setStatus("LIVE · " + String(phaseLabel).slice(0, 72));
        if (hasUnknown()) loadGraph(lastProject);
        else applyActive();
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
        iconAtlas?.dispose();
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
            rotation: { x: graphGroup.rotation.x, y: graphGroup.rotation.y, z: graphGroup.rotation.z },
            focusedNodeId,
            focusPending,
            highlightedEdgeIds: [...activeEdgeIds],
            positions: Object.fromEntries([...positionById].map(([id, p]) => [id, p.map(v => +v.toFixed(5))]))
        });
    }

    loadGraph().finally(() => start());
    refreshTimer = window.setInterval(() => loadGraph(), 15000);
    start();
})();