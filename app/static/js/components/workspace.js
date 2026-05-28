import { state, setState } from "../state.js";
import { workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons } from "../utils/icons.js";
import { showToast } from "./toast.js";
import { loadFileTree } from "./filetree.js";
import { loadGitStatus } from "./git.js";

function isActiveWorkspace(w) {
    if (!w) return false;
    var val = w.is_active;
    return val === 1 || val === true || val === "1" || val === "true";
}

function renderWorkspaceInfo(active) {
    var nameEl = document.getElementById("workspace-name");
    var pathEl = document.getElementById("workspace-path");
    if (active) {
        if (nameEl) nameEl.textContent = active.name;
        if (pathEl) {
            pathEl.textContent = active.type === "ssh"
                ? (active.username || "") + "@" + (active.host || "") + ":" + (active.path || "/")
                : (active.path || "~");
        }
    } else {
        if (nameEl) nameEl.textContent = "Workspace";
        if (pathEl) pathEl.textContent = "— не активен —";
    }
}

function setConnectionStatus(status) {
    var dot = document.getElementById("workspace-conn-dot");
    if (!dot) return;
    dot.className = "conn-dot " + status;
}

export async function loadActiveWorkspace() {
    try {
        var active = null;

        try {
            var activeRes = await fetch('/api/v1/workspaces/active');
            var activeData = await activeRes.json();
            if (activeData && activeData.active) {
                active = activeData.active;
            }
        } catch (err) {
            console.warn("Не удалось получить активный воркспейс напрямую:", err);
        }

        var data = await workspacesApi.list();
        var workspaces = data.workspaces || [];

        if (active) {
            for (var i = 0; i < workspaces.length; i++) {
                if (workspaces[i].id === active.id) {
                    workspaces[i].is_active = true;
                }
            }
        } else {
            for (var i = 0; i < workspaces.length; i++) {
                if (isActiveWorkspace(workspaces[i])) {
                    active = workspaces[i];
                    break;
                }
            }
        }

        setState("workspaces", workspaces);
        setState("activeWorkspace", active || null);
        renderWorkspaceInfo(active);

        if (active) {
            setConnectionStatus(active.type === "ssh" ? "connecting" : "local");
        } else {
            setConnectionStatus("disconnected");
        }
    } catch (e) {
        console.error("loadActiveWorkspace failed:", e);
        renderWorkspaceInfo(null);
        setConnectionStatus("error");
        throw e;
    }
}

// Абсолютно неблокирующий запуск фоновых процессов
export function startBackgroundWorkspaceSetup() {
    var active = state.activeWorkspace;

    if (!active) {
        console.info("No active workspace, skipping tree/git load");
        return;
    }

    if (active.type !== "ssh") {
        setConnectionStatus("local");
        loadFileTree().catch(function(e) { console.error("Tree:", e); });
        loadGitStatus().catch(function(e) { console.error("Git:", e); });
        return;
    }

    // Мгновенная загрузка дерева из кэша бэкенда
    setConnectionStatus("connecting");
    loadFileTree().catch(function(e) { 
        console.warn("Первичная фоновая загрузка дерева...", e); 
    });

    // Тяжелая сетевая проверка SSH уходит в фоновый промис (БЕЗ await)
    testWithRetry(active.id).then(function(connected) {
        if (connected) {
            setConnectionStatus("connected");
            loadFileTree().catch(function(e) { console.error("Tree reload failed:", e); });
            loadGitStatus().catch(function(e) { console.error("Git load failed:", e); });
        } else {
            setConnectionStatus("error");
        }
    }).catch(function(err) {
        setConnectionStatus("error");
    });
}

async function testWithRetry(workspaceId) {
    var maxRetries = 2; // Уменьшаем количество попыток для скорости отклика в фоне
    for (var attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            var result = await workspacesApi.test(workspaceId);
            if (result.status === "success") return true;
        } catch (e) {
            console.warn("SSH background test attempt " + attempt + " failed");
        }
        if (attempt < maxRetries) {
            await sleep(1000);
        }
    }
    return false;
}

function sleep(ms) {
    return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

export async function loadWorkspaces() {
    var list = document.getElementById("ws-list");
    if (!list) return;
    try {
        await loadActiveWorkspace();
        var workspaces = state.workspaces || [];
        renderWorkspaces(workspaces);
    } catch (e) {
        list.innerHTML = '<div class="text-center text-xs text-ide-error py-4">Ошибка загрузки</div>';
    }
}

function renderWorkspaces(ws) {
    var list = document.getElementById("ws-list");
    if (!list) return;
    if (!ws.length) {
        list.innerHTML = '<div class="text-center text-xs text-ide-muted py-4">Нет workspace</div>';
        return;
    }

    list.innerHTML = ws.map(function(w) {
        var isActive = isActiveWorkspace(w);
        var info = w.type === "ssh"
            ? escapeHtml(w.username || "") + "@" + escapeHtml(w.host || "") + ":" + (w.port || 22)
            : "Local: " + escapeHtml(w.path || "~");

        var statusBadge = isActive
            ? '<span class="text-[10px] bg-ide-accent/10 text-ide-accent px-2 py-0.5 rounded-full shrink-0">active</span>'
            : '<button class="activate-ws-btn text-[10px] text-ide-muted hover:text-ide-accent px-2 py-0.5 rounded border border-ide-border shrink-0" data-ws-id="' + w.id + '">Activate</button>';

        var testBtn = '<button class="test-ws-btn text-[10px] text-ide-muted hover:text-ide-accent px-2 py-0.5 rounded border border-ide-border shrink-0" data-ws-id="' + w.id + '">Test</button>';

        return '<div class="ws-card ' + (isActive ? 'active' : '') + '" data-ws-id="' + w.id + '">' +
            '<div class="conn-dot ' + (isActive ? 'connected' : 'disconnected') + '"></div>' +
            '<div class="flex-1 min-w-0">' +
                '<div class="text-xs font-medium text-ide-text truncate">' + escapeHtml(w.name) + '</div>' +
                '<div class="text-[11px] text-ide-muted">' + info + '</div>' +
            '</div>' +
            '<div class="flex items-center gap-1 shrink-0">' +
                testBtn + statusBadge +
                '<button class="delete-ws-btn text-ide-muted hover:text-ide-error p-1"><i data-lucide="trash-2" class="w-3 h-3"></i></button>' +
            '</div>' +
        '</div>';
    }).join("");

    refreshIcons(list);

    list.querySelectorAll(".activate-ws-btn").forEach(function(btn) {
        btn.addEventListener("click", function() { activateWorkspace(btn.dataset.wsId); });
    });
    list.querySelectorAll(".delete-ws-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var id = btn.closest(".ws-card").dataset.wsId;
            deleteWorkspace(id);
        });
    });
    list.querySelectorAll(".test-ws-btn").forEach(function(btn) {
        btn.addEventListener("click", function() { testWorkspaceConnection(btn.dataset.wsId, btn); });
    });
}

async function testWorkspaceConnection(id, btn) {
    var originalText = btn.textContent;
    btn.textContent = "...";
    btn.disabled = true;
    try {
        var result = await workspacesApi.test(id);
        if (result.status === "success") {
            btn.textContent = "✓ OK";
            showToast("Подключение успешно", "success");
        } else {
            btn.textContent = "✗ Fail";
            showToast("Ошибка: " + (result.message || "Unknown"), "error", 4000);
        }
    } catch (e) {
        btn.textContent = "✗ Err";
        showToast("Ошибка теста: " + e.message, "error");
    } finally {
        btn.disabled = false;
        setTimeout(function() { btn.textContent = originalText; }, 3000);
    }
}

export async function addLocalWorkspace() {
    var name = (document.getElementById("ws-local-name")?.value || "").trim() || "Local Project";
    var path = (document.getElementById("ws-path-input")?.value || "").trim();
    if (!path) { showToast("Укажите путь", "error"); return; }
    try {
        await workspacesApi.create({ name: name, type: "local", path: path, activate: true });
        document.getElementById("ws-path-input").value = "";
        showToast('Workspace "' + name + '" добавлен', "success");
        // Запускаем обновление параллельно, кнопки свободны мгновенно!
        loadWorkspaces().then(function() { startBackgroundWorkspaceSetup(); });
    } catch (e) {
        showToast("Ошибка: " + e.message, "error");
    }
}

export async function addSshWorkspace() {
    var payload = {
        name: (document.getElementById("ssh-name")?.value || "").trim() || ("SSH-" + Date.now()),
        type: "ssh",
        host: (document.getElementById("ssh-host")?.value || "").trim(),
        port: parseInt(document.getElementById("ssh-port").value) || 22,
        username: (document.getElementById("ssh-user")?.value || "").trim(),
        auth_type: document.getElementById("ssh-auth-type")?.value,
        password: document.getElementById("ssh-password").value || "",
        private_key: (document.getElementById("ssh-key")?.value || "").trim(),
        passphrase: document.getElementById("ssh-passphrase").value || "",
        path: (document.getElementById("ssh-path")?.value || "").trim(),
        activate: false,
    };
    if (!payload.host || !payload.username) { showToast("Укажите host и username", "error"); return; }

    var btn = document.getElementById("add-ssh-ws-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Подключение..."; }
    try {
        var data = await workspacesApi.create(payload);
        var testData = await workspacesApi.test(data.workspace_id);
        if (testData.status === "success") {
            await workspacesApi.activate(data.workspace_id);
            showToast("✓ " + payload.name + ": " + testData.message, "success");
            loadWorkspaces().then(function() { startBackgroundWorkspaceSetup(); });
        } else {
            await workspacesApi.delete(data.workspace_id);
            showToast("✗ " + testData.message, "error", 5000);
        }
    } catch (e) {
        showToast("Ошибка: " + e.message, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Подключить SSH"; }
    }
}

async function activateWorkspace(id) {
    try {
        await workspacesApi.activate(id);
        showToast("Активирован", "success");
        // Никаких await, мгновенная разблокировка кнопок
        loadWorkspaces().then(function() { startBackgroundWorkspaceSetup(); });
    } catch (e) {
        showToast("Ошибка активации", "error");
    }
}

async function deleteWorkspace(id) {
    if (!confirm("Удалить workspace?")) return;
    try {
        await workspacesApi.delete(id);
        showToast("Удалён", "success");
        loadWorkspaces().then(function() { startBackgroundWorkspaceSetup(); });
    } catch (e) {
        showToast("Ошибка удаления", "error");
    }
}

export function initSshAuthUI() {
    var authType = document.getElementById("ssh-auth-type");
    if (!authType) return;
    authType.addEventListener("change", function() {
        var t = authType.value;
        document.getElementById("ssh-password-row")?.classList.toggle("hidden", t !== "password");
        document.getElementById("ssh-key-row")?.classList.toggle("hidden", t !== "key");
    });
}