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
    const MAX_NODES = 300;
    const MAX_EDGES = 1200;

    const restoreButton = document.createElement("button");
    restoreButton.id = "rf-memory-widget-restore";
    restoreButton.type = "button";
    restoreButton.className = "rf-memory-widget-restore";
    restoreButton.innerHTML = '<i data-lucide="brain-circuit" class="w-3 h-3"></i><span>MEMORY GRAPH</span><i data-lucide="chevron-up" class="w-3 h-3"></i>';
    root.insertAdjacentElement("afterend", restoreButton);

    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";

    let nodes = [];
    let edges = [];
    let activeIds = new Set();
    let lastProject = "";
    let requestVersion = 0;
    let renderer, scene, camera, graphGroup, globe;
    let raf = 0, refreshTimer = 0, resizeObserver = null;
    let lastFrame = 0, pulseClock = 0, rotationSpeed = 0.00032;
    let pointerDown = false, pointerX = 0;
    let activeMesh = null, activeLines = null, activeInstanceCount = 0;

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

    function fibonacciSphere(count, radius) {
        if (!count) return [];
        const points = [];
        const goldenAngle = Math.PI * (3 - Math.sqrt(5));
        for (let i = 0; i < count; i++) {
            const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2;
            const ring = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = goldenAngle * i;
            points.push(new THREE.Vector3(Math.cos(theta) * ring * radius, y * radius, Math.sin(theta) * ring * radius));
        }
        return points;
    }

    function initThree() {
        renderer = new THREE.WebGLRenderer({
            canvas, alpha: true, antialias: false,
            powerPreference: "low-power", depth: true, stencil: false
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
        renderer.setClearColor(0x000000, 0);
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
        camera.position.set(0, 0, 5.8);
        graphGroup = new THREE.Group();
        scene.add(graphGroup);

        globe = new THREE.Mesh(
            new THREE.SphereGeometry(1.72, 24, 18),
            new THREE.MeshBasicMaterial({
                color: 0x147b68, wireframe: true,
                transparent: true, opacity: 0.075,
                depthWrite: false
            })
        );
        globe.userData.staticGlobe = true;
        graphGroup.add(globe);
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
    }

    function disposeObject(object) {
        if (!object) return;
        graphGroup.remove(object);
        object.geometry?.dispose?.();
        if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
        else object.material?.dispose?.();
    }

    function clearGraphObjects() {
        [...graphGroup.children].forEach(child => {
            if (!child.userData.staticGlobe) disposeObject(child);
        });
        activeMesh = null;
        activeLines = null;
        activeInstanceCount = 0;
    }

    function nodeColor(node, active, index) {
        if (active) return new THREE.Color(index % 2 ? 0x20e8ff : 0xc56bff);
        const type = String(node.type || "memory").toLowerCase();
        const palette = {
            project: 0x38a8ff,
            conversation: 0x21c9a0,
            decision: 0xd7a64a,
            file: 0x9a8cff,
            code: 0x9a8cff,
            symbol: 0x6aa8d9,
            memory: 0x4b9f83
        };
        return new THREE.Color(palette[type] || 0x4b9f83);
    }

    function buildGraph() {
        if (!graphGroup) return;
        clearGraphObjects();

        const visibleNodes = nodes.slice(0, MAX_NODES);
        const visibleEdges = edges.slice(0, MAX_EDGES);
        const positions = fibonacciSphere(visibleNodes.length, 1.72);
        const positionById = new Map();
        const normalNodes = [];
        const hotNodes = [];
        const normalEdgePositions = [];
        const hotEdgePositions = [];

        visibleNodes.forEach((node, index) => {
            const id = String(node.id);
            const position = positions[index];
            positionById.set(id, position);
            const record = { position, color: nodeColor(node, activeIds.has(id), index) };
            if (activeIds.has(id)) hotNodes.push(record);
            else normalNodes.push(record);
        });

        visibleEdges.forEach(edge => {
            const source = positionById.get(String(edge.source));
            const target = positionById.get(String(edge.target));
            if (!source || !target) return;
            const targetArray = activeIds.has(String(edge.source)) || activeIds.has(String(edge.target))
                ? hotEdgePositions : normalEdgePositions;
            targetArray.push(source.x, source.y, source.z, target.x, target.y, target.z);
        });

        const makeNodeMesh = (records, radius, opacity) => {
            if (!records.length) return null;
            const geometry = new THREE.SphereGeometry(radius, 8, 6);
            const material = new THREE.MeshBasicMaterial({
                color: 0xffffff, vertexColors: true,
                transparent: true, opacity, depthWrite: false
            });
            const mesh = new THREE.InstancedMesh(geometry, material, records.length);
            const dummy = new THREE.Object3D();
            records.forEach((record, index) => {
                dummy.position.copy(record.position);
                dummy.scale.setScalar(1);
                dummy.updateMatrix();
                mesh.setMatrixAt(index, dummy.matrix);
                mesh.setColorAt(index, record.color);
            });
            mesh.instanceMatrix.needsUpdate = true;
            if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
            graphGroup.add(mesh);
            return mesh;
        };

        const makeLines = (values, color, opacity) => {
            if (!values.length) return null;
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3));
            const material = new THREE.LineBasicMaterial({
                color, transparent: true, opacity, depthWrite: false
            });
            const lines = new THREE.LineSegments(geometry, material);
            graphGroup.add(lines);
            return lines;
        };

        makeLines(normalEdgePositions, 0x168b68, 0.34);
        activeLines = makeLines(hotEdgePositions, 0x62eaff, 0.96);
        makeNodeMesh(normalNodes, 0.043, 0.94);
        activeMesh = makeNodeMesh(hotNodes, 0.068, 1);
        activeInstanceCount = hotNodes.length;

        if (countEl) countEl.textContent = visibleNodes.length + " NODES";
        if (edgeCountEl) edgeCountEl.textContent = visibleEdges.length + " EDGES";
        const activeText = activeIds.size ? " · " + activeIds.size + " ACTIVE" : "";
        setStatus("LIVE SQLITE GRAPH · " + visibleNodes.length + " NODES · " + visibleEdges.length + " EDGES" + activeText);
        renderer?.render(scene, camera);
    }

    async function loadGraph(pidOverride) {
        const pid = (typeof pidOverride === "string" ? pidOverride : "") || projectId() || lastProject;
        if (!pid) {
            requestVersion++;
            nodes = [];
            edges = [];
            activeIds.clear();
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

            nodes = Array.isArray(payload.nodes) ? payload.nodes.slice(0, MAX_NODES) : [];
            edges = Array.isArray(payload.edges) ? payload.edges.slice(0, MAX_EDGES) : [];
            lastProject = pid;
            buildGraph();

            if (!nodes.length) {
                setStatus("No saved SQLite memory nodes in this project yet");
            } else if (!edges.length) {
                setStatus("SQLite nodes loaded · no stored relationships yet");
            } else if (payload.truncated) {
                setStatus("Showing " + nodes.length + " of " + payload.total_nodes + " SQLite nodes");
            }
        } catch (error) {
            if (version !== requestVersion) return;
            setStatus("Memory graph unavailable · " + String(error.message || error).slice(0, 64));
            console.error("[MemoryGraph] SQLite graph fetch failed", error);
        }
    }

    function handleMemoryEvent(detail) {
        if (!detail) return;
        const eventProject = typeof detail.project_id === "string" ? detail.project_id : "";
        if (eventProject) lastProject = eventProject;

        if (detail.phase === "started") {
            rotationSpeed = 0.0015;
            setStatus("Memory query running · reading SQLite graph");
            activity({ label: "Memory query started", detail: (detail.mode || "AUTO") + " · " + (detail.model || "orchestrator") });
            loadGraph(eventProject || lastProject);
            return;
        }

        if (detail.phase === "activity" && detail.event) {
            const item = detail.event;
            activeIds = new Set((Array.isArray(item.active_node_ids) ? item.active_node_ids : []).map(String));
            activity({
                label: (item.phase === "started" ? "Running · " : "Completed · ") + (item.label || item.operation || "Memory operation"),
                detail: item.detail || "", duration_ms: item.duration_ms
            });
            buildGraph();
            return;
        }

        if (detail.phase === "completed") {
            activeIds = new Set((Array.isArray(detail.active_node_ids) ? detail.active_node_ids : []).map(String));
            rotationSpeed = 0.00032;
            activity({ label: "Memory context ready", detail: activeIds.size + " matched SQLite nodes" });
            buildGraph();
            loadGraph(eventProject || lastProject);
            return;
        }

        if (detail.phase === "failed") {
            rotationSpeed = 0.00032;
            setStatus("Memory query failed");
            activity({ label: "Memory query failed", detail: detail.error || "See Agent Trace" });
        }
    }

    function animate(now) {
        raf = 0;
        if (document.hidden || root.style.display === "none") return;

        const delta = lastFrame ? Math.min(40, now - lastFrame) : 16;
        lastFrame = now;
        pulseClock += delta;
        graphGroup.rotation.y += rotationSpeed * delta;
        graphGroup.rotation.x = Math.sin(pulseClock * 0.00012) * 0.055;

        if (activeMesh && activeInstanceCount) {
            const scale = 1.12 + (Math.sin(pulseClock * 0.008) + 1) * 0.24;
            const dummy = new THREE.Object3D();
            for (let i = 0; i < activeInstanceCount; i++) {
                activeMesh.getMatrixAt(i, dummy.matrix);
                dummy.matrix.decompose(dummy.position, dummy.quaternion, dummy.scale);
                dummy.scale.setScalar(scale);
                dummy.updateMatrix();
                activeMesh.setMatrixAt(i, dummy.matrix);
            }
            activeMesh.instanceMatrix.needsUpdate = true;
            activeMesh.material.opacity = 0.72 + (Math.sin(pulseClock * 0.008) + 1) * 0.14;
        }
        if (activeLines) activeLines.material.opacity = 0.58 + (Math.sin(pulseClock * 0.007) + 1) * 0.2;

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
        renderer.render(scene, camera);
    });
    canvas.addEventListener("pointerup", () => { pointerDown = false; });
    canvas.addEventListener("pointercancel", () => { pointerDown = false; });

    resizeObserver = typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => { resize(); renderer?.render(scene, camera); })
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
        activeIds.clear();
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
        resizeObserver?.disconnect();
        clearGraphObjects();
        globe?.geometry?.dispose();
        globe?.material?.dispose();
        renderer?.dispose();
    }, { once: true });

    loadGraph().finally(() => start());
    refreshTimer = window.setInterval(() => loadGraph(), 15000);
    start();
})();
