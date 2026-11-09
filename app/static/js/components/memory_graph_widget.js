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
    const restoreButton = document.createElement("button");
    restoreButton.id = "rf-memory-widget-restore";
    restoreButton.type = "button";
    restoreButton.className = "rf-memory-widget-restore";
    restoreButton.innerHTML = '<i data-lucide="brain-circuit" class="w-3 h-3"></i><span>MEMORY GRAPH</span><i data-lucide="chevron-up" class="w-3 h-3"></i>';
    root.insertAdjacentElement("afterend", restoreButton);
    const token = () => (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
    const projectId = () => localStorage.getItem("rf_active_project_id") || "";
    const collapsedKey = "rf_memory_graph_collapsed";

    let nodes = [], edges = [], activeIds = new Set(), lastProject = "";
    let renderer, scene, camera, graphGroup, raf = 0, refreshTimer = 0, resizeObserver = null;
    let lastFrame = 0, pulseClock = 0, rotationSpeed = 0.00035, pointerDown = false, pointerX = 0;

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
        const points = [];
        const goldenAngle = Math.PI * (3 - Math.sqrt(5));
        for (let i = 0; i < count; i++) {
            const y = 1 - (i / Math.max(1, count - 1)) * 2;
            const ring = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = goldenAngle * i;
            points.push(new THREE.Vector3(Math.cos(theta) * ring * radius, y * radius, Math.sin(theta) * ring * radius));
        }
        return points;
    }

    function initThree() {
        renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power", depth: true, stencil: false });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.setClearColor(0x000000, 0);
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
        camera.position.set(0, 0, 6.1);
        graphGroup = new THREE.Group();
        scene.add(graphGroup);

        const globe = new THREE.Mesh(
            new THREE.SphereGeometry(1.72, 28, 20),
            new THREE.MeshBasicMaterial({ color: 0x08e987, wireframe: true, transparent: true, opacity: 0.12 })
        );
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

    function disposeGraph() {
        const retained = graphGroup.children.filter(child => child.userData.staticGlobe);
        graphGroup.children.filter(child => !child.userData.staticGlobe).forEach(child => {
            graphGroup.remove(child);
            child.geometry?.dispose?.();
            if (Array.isArray(child.material)) child.material.forEach(m => m.dispose());
            else child.material?.dispose?.();
        });
        retained.forEach(child => { if (!graphGroup.children.includes(child)) graphGroup.add(child); });
    }

    function buildGraph() {
        if (!graphGroup) return;
        disposeGraph();
        const realNodes = nodes.slice(0, 300);
        const positions = fibonacciSphere(realNodes.length, 1.72);
        const byId = new Map();
        const normalPositions = [], normalColors = [], activePositions = [], activeColors = [];
        const edgePositions = [], edgeColors = [], hotEdgePositions = [], hotEdgeColors = [];
        const dim = new THREE.Color(0x168b61);
        const cyan = new THREE.Color(0x20e8ff);
        const purple = new THREE.Color(0xc56bff);
        const greenEdge = new THREE.Color(0x0cae76);
        const cyanEdge = new THREE.Color(0x6ceeff);

        realNodes.forEach((node, index) => {
            const id = String(node.id);
            const p = positions[index];
            byId.set(id, p);
            const active = activeIds.has(id);
            const color = active ? (index % 2 ? cyan : purple) : dim;
            const targetP = active ? activePositions : normalPositions;
            const targetC = active ? activeColors : normalColors;
            targetP.push(p.x, p.y, p.z);
            targetC.push(color.r, color.g, color.b);
        });

        edges.forEach(edge => {
            const source = String(edge.source), target = String(edge.target);
            const a = byId.get(source), b = byId.get(target);
            if (!a || !b) return;
            const hot = activeIds.has(source) || activeIds.has(target);
            const targetP = hot ? hotEdgePositions : edgePositions;
            const targetC = hot ? hotEdgeColors : edgeColors;
            const color = hot ? cyanEdge : greenEdge;
            targetP.push(a.x, a.y, a.z, b.x, b.y, b.z);
            targetC.push(color.r, color.g, color.b, color.r, color.g, color.b);
        });

        const addPoints = (values, colors, size, opacity) => {
            if (!values.length) return;
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3));
            geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
            const material = new THREE.PointsMaterial({ size, sizeAttenuation: true, vertexColors: true, transparent: true, opacity, depthWrite: false });
            graphGroup.add(new THREE.Points(geometry, material));
        };
        const addEdges = (values, colors, opacity) => {
            if (!values.length) return null;
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3));
            geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
            const material = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity, depthWrite: false });
            const lines = new THREE.LineSegments(geometry, material);
            graphGroup.add(lines);
            return lines;
        };

        addEdges(edgePositions, edgeColors, 0.22);
        const hotLines = addEdges(hotEdgePositions, hotEdgeColors, 0.95);
        addPoints(normalPositions, normalColors, 0.055, 0.68);
        let hotPoints = null;
        if (activePositions.length) {
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.Float32BufferAttribute(activePositions, 3));
            geometry.setAttribute("color", new THREE.Float32BufferAttribute(activeColors, 3));
            const material = new THREE.PointsMaterial({ size: 0.105, sizeAttenuation: true, vertexColors: true, transparent: true, opacity: 1, depthWrite: false });
            hotPoints = new THREE.Points(geometry, material);
            graphGroup.add(hotPoints);
        }
        graphGroup.userData.hotPoints = hotPoints;
        graphGroup.userData.hotLines = hotLines;

        if (countEl) countEl.textContent = realNodes.length + " NODES";
        if (edgeCountEl) edgeCountEl.textContent = edges.length + " EDGES";
        setStatus("SQLite graph · " + realNodes.length + " nodes");
    }

    async function loadGraph(pidOverride) {
        const pid = pidOverride || projectId();
        if (!pid) {
            nodes = []; edges = []; activeIds.clear();
            buildGraph();
            setStatus("Select a project to inspect memory");
            return;
        }
        try {
            const response = await fetch("/api/v1/memory/graph-status/" + encodeURIComponent(pid), {
                headers: token() ? { Authorization: "Bearer " + token() } : {},
                credentials: "same-origin", cache: "no-store"
            });
            if (!response.ok) throw new Error("HTTP " + response.status);
            const payload = await response.json();
            nodes = Array.isArray(payload.nodes) ? payload.nodes.slice(0, 300) : [];
            edges = Array.isArray(payload.edges) ? payload.edges : [];
            lastProject = pid;
            buildGraph();
            if (!nodes.length) setStatus("Waiting for saved memory");
        } catch (error) {
            setStatus("Memory graph unavailable · " + String(error.message || error).slice(0, 64));
            console.error("[MemoryGraph] SQLite graph fetch failed", error);
        }
    }

    function handleMemoryEvent(detail) {
        if (!detail) return;
        if (detail.project_id) lastProject = detail.project_id;
        if (detail.phase === "started") {
            rotationSpeed = 0.0018;
            setStatus("Memory query running · " + (detail.model || "orchestrator"));
            activity({ label: "Memory query started", detail: (detail.mode || "AUTO") + " · " + (detail.model || "model") });
            loadGraph(detail.project_id || lastProject);
        } else if (detail.phase === "activity" && detail.event) {
            const item = detail.event;
            activeIds = new Set((Array.isArray(item.active_node_ids) ? item.active_node_ids : []).map(String));
            activity({ label: (item.phase === "started" ? "Running · " : "Completed · ") + (item.label || item.operation || "Memory operation"), detail: item.detail || "", duration_ms: item.duration_ms });
            setStatus((item.label || "Memory operation") + " · " + activeIds.size + " active nodes");
            buildGraph();
        } else if (detail.phase === "completed") {
            activeIds = new Set((Array.isArray(detail.active_node_ids) ? detail.active_node_ids : []).map(String));
            rotationSpeed = 0.00035;
            setStatus("Context ready · " + activeIds.size + " matched nodes");
            activity({ label: "Memory context ready", detail: activeIds.size + " matched SQLite nodes" });
            loadGraph(detail.project_id || lastProject);
        } else if (detail.phase === "failed") {
            rotationSpeed = 0.00035;
            setStatus("Memory query failed");
            activity({ label: "Memory query failed", detail: detail.error || "See Agent Trace" });
        }
    }

    function animate(now) {
        raf = 0;
        if (document.hidden || root.classList.contains("is-collapsed")) return;
        if (now - lastFrame >= 16) {
            const delta = lastFrame ? Math.min(40, now - lastFrame) : 16;
            lastFrame = now;
            pulseClock += delta;
            graphGroup.rotation.y += rotationSpeed * delta;
            graphGroup.rotation.x = Math.sin(pulseClock * 0.00012) * 0.08;
            const hotPoints = graphGroup.userData.hotPoints;
            const hotLines = graphGroup.userData.hotLines;
            if (hotPoints) {
                hotPoints.material.opacity = 0.62 + (Math.sin(pulseClock * 0.008) + 1) * 0.19;
                hotPoints.material.size = 0.09 + (Math.sin(pulseClock * 0.008) + 1) * 0.018;
            }
            if (hotLines) hotLines.material.opacity = 0.62 + (Math.sin(pulseClock * 0.007) + 1) * 0.18;
            renderer.render(scene, camera);
        }
        raf = requestAnimationFrame(animate);
    }
    const start = () => { if (!raf && renderer && !document.hidden && !root.classList.contains("is-collapsed")) raf = requestAnimationFrame(animate); };
    const stop = () => { if (raf) cancelAnimationFrame(raf); raf = 0; };
    function setCollapsed(value) {
        root.classList.toggle("is-collapsed", value);
        root.style.display = value ? "none" : "";
        restoreButton.style.display = value ? "flex" : "none";
        if (toggle) {
            toggle.setAttribute("aria-expanded", String(!value));
            toggle.setAttribute("aria-label", value ? "Show memory graph" : "Hide memory graph");
            toggle.title = value ? "Show memory graph" : "Hide memory graph";
        }
        try { localStorage.setItem(collapsedKey, value ? "1" : "0"); } catch (_) {}
        if (value) stop(); else start();
    }

    try {
        initThree();
        const staticGlobe = graphGroup.children[0];
        staticGlobe.userData.staticGlobe = true;
        setCollapsed(localStorage.getItem(collapsedKey) === "1");
    } catch (error) {
        console.error("[MemoryGraph] Three.js initialization failed", error);
        setStatus("3D renderer unavailable");
        return;
    }
    toggle?.addEventListener("click", () => setCollapsed(true));
    restoreButton.addEventListener("click", () => setCollapsed(false));
    if (window.lucide) window.lucide.createIcons({ root: restoreButton });
    canvas.addEventListener("pointerdown", event => { pointerDown = true; pointerX = event.clientX; canvas.setPointerCapture?.(event.pointerId); });
    canvas.addEventListener("pointermove", event => {
        if (!pointerDown) return;
        graphGroup.rotation.y += (event.clientX - pointerX) * 0.008;
        pointerX = event.clientX;
        renderer.render(scene, camera);
    });
    canvas.addEventListener("pointerup", () => { pointerDown = false; });
    canvas.addEventListener("pointercancel", () => { pointerDown = false; });
    resizeObserver = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => { resize(); renderer.render(scene, camera); }) : null;
    resizeObserver?.observe(canvas);
    window.addEventListener("rf:memory-graph", event => { if (event.detail?.status === "memory_graph") handleMemoryEvent(event.detail); });
    eventBus.on("project.activated", project => {
        lastProject = project || projectId();
        nodes = []; edges = []; activeIds.clear();
        buildGraph();
        loadGraph(lastProject);
    });
    window.addEventListener("storage", event => { if (event.key === "rf_active_project_id") loadGraph(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else start(); });
    window.addEventListener("beforeunload", () => {
        stop();
        if (refreshTimer) clearInterval(refreshTimer);
        resizeObserver?.disconnect();
        disposeGraph();
        graphGroup?.traverse(object => {
            if (object.geometry) object.geometry.dispose();
            if (object.material) {
                if (Array.isArray(object.material)) object.material.forEach(m => m.dispose());
                else object.material.dispose();
            }
        });
        renderer?.dispose();
    }, { once: true });
    loadGraph().finally(() => { renderer.render(scene, camera); start(); });
    refreshTimer = window.setInterval(() => loadGraph(), 15000);
    start();
})();