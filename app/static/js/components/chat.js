import { state, setState } from "../state.js";
import { sessionsApi, workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons, getFileIcon } from "../utils/icons.js";
import { showToast } from "./toast.js";
import { loadSessions } from "./sessions.js";
import { loadGitStatus } from "./git.js";
import { loadFileTree } from "./filetree.js"; // <-- Успешно импортировано во избежание ReferenceError

var chatContainer = document.getElementById("chat-container");
var chatHistoryDOM = document.getElementById("chat-history");
var promptInput = document.getElementById("prompt-input");
var sendBtn = document.getElementById("send-btn");
var strategySelect = document.getElementById("strategy-select");
var modelLockSelect = document.getElementById("model-lock-select");

// AbortController для кнопки Stop
var currentAbortController = null;

// ═══════════════════════════════════════════════════════════════
// DEBUG TRACE PANEL
// ═══════════════════════════════════════════════════════════════

function getTraceLog() {
    return document.getElementById("debug-trace-log");
}

function appendTrace(badge, badgeClass, content) {
    var log = getTraceLog();
    if (!log) return;
    var time = new Date().toLocaleTimeString("ru", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    });

    var entry = document.createElement("div");
    entry.className = "trace-entry";
    entry.innerHTML =
        '<span class="trace-time">' + time + '</span>' +
        '<span class="trace-badge ' + badgeClass + '">' + badge + '</span>' +
        '<span class="trace-content"></span>';
    
    entry.querySelector(".trace-content").textContent = content;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;

    // Обновляем счетчик логов в шапке панели трейса
    var counter = document.getElementById("trace-counter");
    if (counter) {
        var count = log.querySelectorAll(".trace-entry").length;
        counter.textContent = "(" + count + ")";
    }
}

// Панель активных инструментов в статус-баре чата
var activeTools = {};

function updateActiveToolsUI() {
    var container = document.getElementById("active-tools-list");
    if (!container) return;
    
    var keys = Object.keys(activeTools);
    if (keys.length === 0) {
        container.innerHTML = '<div class="text-center text-[11px] text-ide-muted py-3">Нет активных инструментов</div>';
        
        var toolsCounter = document.getElementById("tools-count");
        if (toolsCounter) toolsCounter.textContent = "(0)";
        return;
    }
    
    var html = '';
    keys.forEach(function(id) {
        var t = activeTools[id];
        var statusClass = t.status === 'running' ? 'running' : (t.status === 'success' ? 'success' : 'error');
        var icon = t.status === 'running' ? 'loader' : (t.status === 'success' ? 'check-circle' : 'x-circle');
        var iconColor = t.status === 'running' ? 'text-yellow-500 animate-spin' : (t.status === 'success' ? 'text-green-500' : 'text-red-500');
        var elapsed = t.elapsedMs ? ' (' + (t.elapsedMs/1000).toFixed(1) + 's)' : '';
        
        html += '<div class="tool-execution-item ' + statusClass + '" data-tool-id="' + id + '">';
        html += '<i data-lucide="' + icon + '" class="w-3.5 h-3.5 ' + iconColor + ' shrink-0"></i>';
        html += '<span class="tool-name">' + escapeHtml(t.name) + '</span>';
        html += '<span class="tool-time">' + elapsed + '</span>';
        html += '</div>';
    });
    container.innerHTML = html;
    
    if (window.lucide) window.lucide.createIcons({ root: container });

    var toolsCounter = document.getElementById("tools-count");
    if (toolsCounter) {
        toolsCounter.textContent = "(" + keys.length + ")";
    }
}

function registerActiveTool(toolId, toolName) {
    activeTools[toolId] = {
        name: toolName,
        status: 'running',
        startTime: Date.now()
    };
    updateActiveToolsUI();
}

function updateActiveTool(toolId, status, elapsedMs) {
    if (activeTools[toolId]) {
        activeTools[toolId].status = status;
        activeTools[toolId].elapsedMs = elapsedMs;
        updateActiveToolsUI();
        
        // Скрываем инструмент через 3 секунды после завершения
        if (status !== 'running') {
            setTimeout(function() {
                delete activeTools[toolId];
                updateActiveToolsUI();
            }, 3000);
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// ОСНОВНЫЕ ФУНКЦИИ ЧАТА
// ═══════════════════════════════════════════════════════════════

export function initChat() {
    promptInput.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 200) + "px";
    });

    promptInput.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener("click", sendMessage);
    document.getElementById("new-chat-btn")?.addEventListener("click", newChat);
    document.getElementById("clear-trace-btn")?.addEventListener("click", function() {
        var log = getTraceLog();
        if (log) log.innerHTML = "";
    });

    // Обработка кнопки STOP
    document.getElementById("stop-gen-btn")?.addEventListener("click", function() {
        if (currentAbortController) {
            currentAbortController.abort();
            appendTrace("SYSTEM", "bg-red-900 text-red-200", "Генерация прервана пользователем.");
            showToast("Генерация остановлена", "info");
            setGenerating(false);
        }
    });

    // Кнопка прикрепления файлов контекста (вызов модалки)
    document.getElementById("attach-context-btn")?.addEventListener("click", function() {
        openContextPicker();
    });

    // Модалка контекста кнопки подтверждения/отмены
    document.getElementById("ctx-picker-cancel")?.addEventListener("click", closeContextPicker);
    document.getElementById("ctx-picker-confirm")?.addEventListener("click", confirmContextPicker);

    // Живой поиск в контекст-пикере
    document.getElementById("ctx-search-input")?.addEventListener("input", function(e) {
        filterContextPicker(e.target.value);
    });

    // Отрисовка пустого или дефолтного стрипа контекста
    renderContextStrip();
}

function setGenerating(val) {
    state.isGenerating = val;
    setState("isGenerating", val);
    
    var stopBtn = document.getElementById("stop-gen-btn");
    if (val) {
        sendBtn.disabled = true;
        sendBtn.classList.add("opacity-50");
        stopBtn?.classList.remove("hidden");
    } else {
        sendBtn.disabled = false;
        sendBtn.classList.remove("opacity-50");
        stopBtn?.classList.add("hidden");
        currentAbortController = null;
    }
}

export function newChat() {
    if (state.isGenerating) return;
    state.chatHistory = [];
    state.attachedContext = [];
    setState("currentSessionId", null);
    setState("attachedContext", []);
    chatHistoryDOM.innerHTML = "";
    renderContextStrip();
    promptInput.value = "";
    promptInput.style.height = "auto";
    showToast("Открыт новый чат", "info");
}

export async function loadChatSession(sessionId) {
    if (!sessionId) return;
    try {
        var data = await sessionsApi.messages(sessionId);
        var messageList = data.messages || [];
        
        state.chatHistory = messageList.filter(function(m) {
            return m.role === "user" || m.role === "assistant";
        });
        setState("currentSessionId", sessionId);
        renderChatHistory();
    } catch (e) {
        showToast("Не удалось загрузить сессию: " + e.message, "error");
    }
}

function renderChatHistory() {
    chatHistoryDOM.innerHTML = "";
    state.chatHistory.forEach(function(msg) {
        if (msg.role === "system") return;
        appendMessageDOM(msg.role, msg.content, msg.trace);
    });
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function appendMessageDOM(role, content, traceData = null) {
    var msgDiv = document.createElement("div");
    msgDiv.className = "message-fade-in flex w-full p-4 " + 
        (role === "user" ? "justify-end" : "justify-start bg-gray-900/20 border-y border-ide-border/50");

    var container = document.createElement("div");
    container.className = "flex space-x-3 max-w-3xl " + 
        (role === "user" ? "flex-row-reverse space-x-reverse max-w-[80%]" : "w-full");

    var avatar = document.createElement("div");
    avatar.className = "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold shadow-inner " + 
        (role === "user" ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30" : "bg-emerald-600/20 text-emerald-400 border border-emerald-500/30");
    avatar.textContent = role === "user" ? "U" : "AI";

    var body = document.createElement("div");
    if (role === "user") {
        body.className = "bg-indigo-950/20 border border-indigo-500/20 rounded-xl px-4 py-2.5 text-sm text-gray-200 leading-relaxed max-w-full font-sans";
        body.textContent = content;
    } else {
        body.className = "flex-1 space-y-2 overflow-hidden text-gray-200 leading-relaxed text-sm prose prose-invert font-sans";
        body.innerHTML = window.markdownUtils ? window.markdownUtils.render(content) : escapeHtml(content);
    }

    container.appendChild(avatar);
    container.appendChild(body);
    msgDiv.appendChild(container);

    if (role === "assistant" && traceData) {
        renderToolTraceBlock(body, traceData);
    }

    chatHistoryDOM.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    if (window.Prism) {
        msgDiv.querySelectorAll("pre code").forEach(function(block) {
            window.Prism.highlightElement(block);
        });
    }
}

function renderToolTraceBlock(parentDOM, trace) {
    if (!trace || !trace.calls || !trace.calls.length) return;
    
    var container = document.createElement("div");
    container.className = "mt-4 border border-gray-800 bg-gray-950/60 rounded-lg text-xs overflow-hidden shadow-sm";
    
    var header = document.createElement("div");
    header.className = "flex items-center justify-between px-3 py-2 bg-gray-900/80 cursor-pointer hover:bg-gray-900 text-gray-400 select-none border-b border-gray-800";
    header.innerHTML = '<span class="font-medium flex items-center space-x-2">⚙️ <span>Вызовы инструментов ИИ (' + trace.calls.length + ')</span></span><span class="toggle-icon text-[10px]">▼</span>';
    
    var content = document.createElement("div");
    content.className = "p-3 space-y-3 hidden bg-gray-950/40 max-h-60 overflow-y-auto font-mono";
    
    trace.calls.forEach(function(c) {
        var item = document.createElement("div");
        item.className = "space-y-1 border-l-2 border-gray-700 pl-2 py-0.5 text-gray-300";
        
        var title = document.createElement("div");
        title.className = "font-bold text-gray-400 text-[11px]";
        title.textContent = "Инструмент: " + c.name + " [" + (c.status || "done") + "]";
        
        var args = document.createElement("pre");
        args.className = "text-[10px] text-gray-500 bg-gray-900/50 p-1 rounded overflow-x-auto max-w-full";
        args.textContent = typeof c.args === 'string' ? c.args : JSON.stringify(c.args, null, 2);
        
        item.appendChild(title);
        item.appendChild(args);
        
        if (c.result) {
            var res = document.createElement("pre");
            res.className = "text-[10px] text-emerald-600/80 bg-emerald-950/10 p-1 rounded overflow-x-auto max-w-full max-h-24 overflow-y-auto";
            res.textContent = typeof c.result === 'string' ? c.result : JSON.stringify(c.result, null, 2);
            item.appendChild(res);
        }
        
        content.appendChild(item);
    });
    
    header.addEventListener("click", function() {
        var isHidden = content.classList.contains("hidden");
        if (isHidden) {
            content.classList.remove("hidden");
            header.querySelector(".toggle-icon").textContent = "▲";
        } else {
            content.classList.add("hidden");
            header.querySelector(".toggle-icon").textContent = "▼";
        }
    });
    
    container.appendChild(header);
    container.appendChild(content);
    parentDOM.appendChild(container);
}

// ═══════════════════════════════════════════════════════════════
// ОТПРАВКА СООБЩЕНИЙ И СТРИМИНГ ИИ
// ═══════════════════════════════════════════════════════════════

async function sendMessage() {
    var text = promptInput.value.trim();
    if (!text || state.isGenerating) return;

    var isNewSession = !state.currentSessionId;

    promptInput.value = "";
    promptInput.style.height = "auto";

    appendMessageDOM("user", text);
    
    state.chatHistory.push({ role: "user", content: text });
    
    var currentSessionId = state.currentSessionId;
    if (!currentSessionId) {
        currentSessionId = "session-" + Date.now() + "-" + Math.random().toString(36).slice(2, 11);
        setState("currentSessionId", currentSessionId);
        
        sessionsApi.create(text, currentSessionId)
            .then(function() {
                loadSessions();
            })
            .catch(function(err) {
                console.error("Не удалось зарегистрировать сессию в сайдбаре:", err);
            });
    }

    setGenerating(true);
    currentAbortController = new AbortController();

    var msgDiv = document.createElement("div");
    msgDiv.className = "message-fade-in flex space-x-4 p-4 bg-gray-900/20 border-y border-gray-800/30";
    
    var avatar = document.createElement("div");
    avatar.className = "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold shadow-inner bg-emerald-600/20 text-emerald-400 border border-emerald-500/30";
    avatar.textContent = "AI";

    var body = document.createElement("div");
    body.className = "flex-1 space-y-2 overflow-hidden text-gray-200 leading-relaxed";
    body.innerHTML = '<span class="text-gray-500 animate-pulse">Думает...</span>';

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(body);
    chatHistoryDOM.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    var messagesForLLM = [];
    
    if (state.attachedContext && state.attachedContext.length) {
        var contextPrompt = "Используй следующий контекст проекта для решения задачи:\n\n";
        state.attachedContext.forEach(function(ctx) {
            contextPrompt += "--- ФАЙЛ: " + ctx.path + " ---\n" + ctx.content + "\n\n";
        });
        messagesForLLM.push({ role: "system", content: contextPrompt });
    }
    
    state.chatHistory.forEach(function(h) {
        if (h.role === "user" || (h.role === "assistant" && h.content && !h.content.startsWith("[Tools:"))) {
            messagesForLLM.push({ role: h.role, content: h.content });
        }
    });

    var fullAssistantText = "";
    var currentToolCalls = {};
    var streamTraceData = { calls: [] };

    try {
        var response = await fetch("/api/v1/chat/stream", {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "Authorization": "Bearer " + (localStorage.getItem("jwt_token") || localStorage.getItem("rf_jwt_token") || "")
            },
            signal: currentAbortController.signal,
            body: JSON.stringify({
                session_id: currentSessionId,
                messages: messagesForLLM,
                strategy: (strategySelect && strategySelect.value) || "auto",
                model_lock: (modelLockSelect && modelLockSelect.value) || null,
                temperature: 0.2
            })
        });

        if (!response.ok) {
            throw new Error("Ошибка сервера: HTTP " + response.status);
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buffer = "";

        while (true) {
            var { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            var lines = buffer.split("\n");
            buffer = lines.pop();

            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                var trimmed = line.trim();
                if (!trimmed) continue;

                try {
                    if (trimmed.startsWith("SYSTEM_NOTICE:")) {
                        var msg = trimmed.substring("SYSTEM_NOTICE:".length);
                        appendTrace("SYSTEM", "error", msg);
                    }
                    else if (trimmed.startsWith("SYSTEM_ERROR:")) {
                        var err = trimmed.substring("SYSTEM_ERROR:".length);
                        appendTrace("ERROR", "error", err);
                    }
                    else if (trimmed.startsWith("MODEL_TRY:")) {
                        var meta = JSON.parse(trimmed.substring("MODEL_TRY:".length));
                        appendTrace("TRY", "try", meta.model.split("/").pop() + " (" + meta.provider + ")");
                        var rModelEl = document.getElementById("current-model-display");
                        if (rModelEl) rModelEl.textContent = meta.model.split("/").pop();
                    }
                    else if (trimmed.startsWith("MODEL_ERROR:")) {
                        var meta = JSON.parse(trimmed.substring("MODEL_ERROR:".length));
                        appendTrace("FAIL", "error", meta.model.split("/").pop() + " failed: " + meta.error);
                    }
                    else if (trimmed.startsWith("MODEL_SUCCESS:")) {
                        var meta = JSON.parse(trimmed.substring("MODEL_SUCCESS:".length));
                        appendTrace("SUCCESS", "success", meta.model.split("/").pop() + " in " + meta.elapsed_ms + "ms");
                    }
                    else if (trimmed.startsWith("ITERATION:")) {
                        var meta = JSON.parse(trimmed.substring("ITERATION:".length));
                        appendTrace("ITER", "iter", "Loop " + meta.iteration + "/" + meta.max);
                    }
                    else if (trimmed.startsWith("METADATA:")) {
                        var meta = JSON.parse(trimmed.substring("METADATA:".length));
                        var rModelEl = document.getElementById("current-model-display");
                        if (rModelEl) rModelEl.textContent = meta.model.split("/").pop();
                    }
                    else if (trimmed.startsWith("TOOL_START:")) {
                        var meta = JSON.parse(trimmed.substring("TOOL_START:".length));
                        appendTrace("TOOL", "tool", "Running: " + meta.tool_name);
                        registerActiveTool(meta.tool_id, meta.tool_name);
                    }
                    else if (trimmed.startsWith("TOOL_END:")) {
                        var meta = JSON.parse(trimmed.substring("TOOL_END:".length));
                        appendTrace("DONE", "done", "Finished: " + meta.tool_name);
                        updateActiveTool(meta.tool_id, meta.result?.error ? 'error' : 'success', 1000);
                        
                        streamTraceData.calls.push({
                            name: meta.tool_name,
                            args: meta.arguments || "",
                            result: meta.result || "",
                            status: meta.result?.error ? 'error' : 'success'
                        });
                        
                        if (["write_file", "apply_patch", "execute_command"].includes(meta.tool_name)) {
                            loadFileTree();
                            loadGitStatus();
                        }
                    }
                    else if (line.startsWith("CONTENT:")) {
                        var textToken = line.substring("CONTENT:".length);
                        if (fullAssistantText === "") {
                            body.innerHTML = "";
                        }
                        fullAssistantText += textToken;
                        body.innerHTML = window.markdownUtils ? window.markdownUtils.render(fullAssistantText) : escapeHtml(fullAssistantText);
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }
                    else {
                        if (fullAssistantText === "") {
                            body.innerHTML = "";
                        }
                        fullAssistantText += line + "\n";
                        body.innerHTML = window.markdownUtils ? window.markdownUtils.render(fullAssistantText) : escapeHtml(fullAssistantText);
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }
                } catch (err) {
                    console.error("Ошибка парсинга строки потока:", err, line);
                }
            }
        }

        state.chatHistory.push({ 
            role: "assistant", 
            content: fullAssistantText,
            trace: streamTraceData.calls.length ? streamTraceData : null
        });
        
        if (streamTraceData.calls.length) {
            renderToolTraceBlock(body, streamTraceData);
        }

    } catch (e) {
        if (e.name === "AbortError") {
            // Запрос был отменен пользователем
        } else {
            appendTrace("ERROR", "bg-red-900 text-red-200", "Ошибка стрима: " + e.message);
            body.innerHTML = '<span class="text-red-400 font-medium">⚠️ Ошибка отправки: ' + escapeHtml(e.message) + '</span>';
            showToast("Ошибка ИИ: " + e.message, "error");
        }
    } finally {
        setGenerating(false);
        state.attachedContext = [];
        setState("attachedContext", []);
        renderContextStrip();
        loadSessions(); // <-- Перезапрашиваем список сессий, чтобы заголовок обновился на ИИ-сгенерированный
    }
}

// ═══════════════════════════════════════════════════════════════
// КОНТЕКСТ-ПИКЕР И ФАЙЛОВЫЙ СТРИП (ATTACHMENTS)
// ═══════════════════════════════════════════════════════════════

var pickerSelection = new Set();
var allAvailablePaths = [];

export function initContextPicker(container) {
    if (!container) return;
}

function openContextPicker() {
    var modal = document.getElementById("context-picker-modal");
    if (!modal) return;

    modal.classList.remove("hidden");
    var listContainer = document.getElementById("ctx-picker-tree");
    if (!listContainer) return;

    listContainer.innerHTML = '<div class="p-4 text-center text-gray-500 animate-pulse text-xs">Сканирование дерева проекта...</div>';
    pickerSelection.clear();
    document.getElementById("ctx-picker-count").textContent = "Выбрано: 0";
    document.getElementById("ctx-picker-search").value = "";

    workspacesApi.list().then(async function() {
        try {
            var activeWs = state.activeWorkspace;
            if (!activeWs) {
                listContainer.innerHTML = '<div class="p-4 text-center text-gray-500 text-xs">Сначала активируйте воркспейс</div>';
                return;
            }
            
            var res = await fetch("/api/v1/workspaces/tree", {
                headers: { "Authorization": "Bearer " + (localStorage.getItem("jwt_token") || "") }
            });
            var treeData = await res.json();
            
            allAvailablePaths = [];
            buildFlatPathsFromTree(treeData.tree || [], "", allAvailablePaths);
            
            renderContextPickerList(allAvailablePaths);
        } catch (err) {
            listContainer.innerHTML = '<div class="p-4 text-center text-red-400 text-xs">Ошибка загрузки дерева: ' + err.message + '</div>';
        }
    });
}

function buildFlatPathsFromTree(nodes, currentPath, acc) {
    nodes.forEach(function(n) {
        var p = currentPath ? currentPath + "/" + n.name : n.name;
        if (n.type === "file") {
            acc.push({ name: n.name, path: p });
        } else if (n.type === "directory" && n.children) {
            buildFlatPathsFromTree(n.children, p, acc);
        }
    });
}

function renderContextPickerList(paths) {
    var container = document.getElementById("ctx-picker-tree");
    if (!container) return;
    container.innerHTML = "";

    if (!paths.length) {
        container.innerHTML = '<div class="p-4 text-center text-gray-500 text-xs">Файлы не найдены</div>';
        return;
    }

    paths.forEach(function(f) {
        var item = document.createElement("div");
        item.className = "flex items-center space-x-3 p-2 hover:bg-gray-800/60 rounded cursor-pointer border border-transparent transition text-xs text-gray-300";
        item.dataset.path = f.path;
        
        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "rounded border-gray-700 bg-gray-900 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 pointer-events-none";
        checkbox.checked = pickerSelection.has(f.path);

        var iconSpan = document.createElement("span");
        iconSpan.className = "text-gray-400 font-mono text-sm";
        iconSpan.innerHTML = getFileIcon(f.name);

        var nameInfo = document.createElement("div");
        nameInfo.className = "flex-1 overflow-hidden";
        nameInfo.innerHTML = '<div class="font-medium truncate text-gray-200">' + escapeHtml(f.name) + '</div>' +
                             '<div class="text-[10px] text-gray-500 truncate font-mono">' + escapeHtml(f.path) + '</div>';

        item.appendChild(checkbox);
        item.appendChild(iconSpan);
        item.appendChild(nameInfo);

        item.addEventListener("click", function() {
            if (pickerSelection.has(f.path)) {
                pickerSelection.delete(f.path);
                checkbox.checked = false;
                item.classList.remove("bg-indigo-950/20", "border-indigo-500/30");
            } else {
                pickerSelection.add(f.path);
                checkbox.checked = true;
                item.classList.add("bg-indigo-950/20", "border-indigo-500/30");
            }
            document.getElementById("ctx-picker-count").textContent = "Выбрано: " + pickerSelection.size;
        });

        container.appendChild(item);
    });
    refreshIcons(container);
}

function filterContextPicker(query) {
    var q = query.toLowerCase().trim();
    if (!q) {
        renderContextPickerList(allAvailablePaths);
        return;
    }
    var filtered = allAvailablePaths.filter(function(p) {
        return p.path.toLowerCase().includes(q) || p.name.toLowerCase().includes(q);
    });
    renderContextPickerList(filtered);
}

function closeContextPicker() {
    document.getElementById("context-picker-modal").classList.add("hidden");
}

async function confirmContextPicker() {
    var paths = Array.from(pickerSelection);
    if (!paths.length) { closeContextPicker(); return; }
    showToast("Загрузка " + paths.length + " файлов...", "info");

    for (var i = 0; i < paths.length; i++) {
        var path = paths[i];
        var name = path.split("/").pop();
        if (state.attachedContext.some(function(c) { return c.path === path; })) continue;
        
        try {
            var data = await workspacesApi.file(path);
            state.attachedContext.push({
                id: "ws-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7),
                type: "workspace", 
                name: name, 
                path: path, 
                content: data.content || ""
            });
        } catch (e) {}
    }

    setState("attachedContext", state.attachedContext);
    renderContextStrip();
    closeContextPicker();
    showToast("Добавлено " + paths.length + " файлов", "success");
}

function renderContextStrip() {
    var container = document.getElementById("attached-context-bar");
    if (!container) return;
    container.innerHTML = "";

    if (!state.attachedContext || !state.attachedContext.length) {
        container.classList.add("hidden");
        return;
    }

    container.classList.remove("hidden");
    state.attachedContext.forEach(function(ctx) {
        var badge = document.createElement("div");
        badge.className = "flex items-center space-x-1.5 bg-indigo-950/40 border border-indigo-500/30 px-2 py-1 rounded text-xs text-indigo-300 font-medium select-none";
        badge.innerHTML = '<span>' + getFileIcon(ctx.name) + '</span>' +
                          '<span class="max-w-[120px] truncate" title="' + escapeHtml(ctx.path) + '">' + escapeHtml(ctx.name) + '</span>' +
                          '<button class="text-indigo-400 hover:text-indigo-200 font-bold ml-1 text-[11px]">×</button>';
        
        badge.querySelector("button").addEventListener("click", function() {
            state.attachedContext = state.attachedContext.filter(function(c) { return c.id !== ctx.id; });
            setState("attachedContext", state.attachedContext);
            renderContextStrip();
        });

        container.appendChild(badge);
    });
    refreshIcons(container);
}

export function clearChat() {
    state.chatHistory = [];
    setState("currentSessionId", null);
    var history = document.getElementById("chat-history");
    if (history) history.innerHTML = "";
    renderContextStrip();
}