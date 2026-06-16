import { state, setState, subscribe } from "../state.js";
import { streamChat, sessionsApi, workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons, getFileIcon } from "../utils/icons.js";
import { showToast } from "./toast.js";
import { loadSessions } from "./sessions.js";
import { loadGitStatus } from "./git.js";
import { loadFileTree } from "./filetree.js";

var chatContainer = document.getElementById("chat-container");
var chatHistoryDOM = document.getElementById("chat-history");
var promptInput = document.getElementById("prompt-input");
var sendBtn = document.getElementById("send-btn");
var strategySelect = document.getElementById("strategy-select");
var modelLockSelect = document.getElementById("model-lock-select");

// AbortController для кнопки Stop
var currentAbortController = null;

// Локальный кэш запущенных инструментов агента
var runningAgentCommands = {};

// Внедрение контрастных кнопок копирования кода в pre
function injectCodeCopyButtons(container) {
    container.querySelectorAll("pre").forEach(function(pre) {
        if (pre.querySelector(".code-copy-btn")) return; // Защита от дубликатов
        pre.style.position = "relative";
        
        var copyBtn = document.createElement("button");
        copyBtn.className = "code-copy-btn absolute top-2 right-2 p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition z-10 cursor-pointer flex items-center justify-center shadow-lg";
        copyBtn.title = "Копировать код";
        copyBtn.innerHTML = '<i data-lucide="copy" class="w-3.5 h-3.5"></i>';
        
        pre.appendChild(copyBtn);
        
        copyBtn.addEventListener("click", function(e) {
            e.stopPropagation();
            var codeText = pre.querySelector("code")?.textContent || pre.textContent;
            navigator.clipboard.writeText(codeText).then(function() {
                showToast("Код скопирован", "success", 1500);
                copyBtn.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i>';
                setTimeout(function() {
                    copyBtn.innerHTML = '<i data-lucide="copy" class="w-3.5 h-3.5"></i>';
                    refreshIcons(copyBtn);
                }, 2000);
            }).catch(function() {
                showToast("Ошибка копирования", "error");
            });
        });
    });
}

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

// Панель активных инструментов
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

function registerActiveTool(toolId, toolName, args) {
    activeTools[toolId] = {
        name: toolName,
        arguments: args || "",
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

// Откатоустойчивый рендерер Markdown
function renderMarkdown(text) {
    if (window.marked) {
        if (typeof window.marked.parse === "function") {
            return window.marked.parse(text);
        } else if (typeof window.marked === "function") {
            return window.marked(text);
        }
    }
    return escapeHtml(text).replace(/\n/g, "<br>");
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
            if (!state.isGenerating) {
                sendMessage();
            }
        }
    });

    sendBtn.addEventListener("click", sendMessage);
    document.getElementById("new-chat-btn")?.addEventListener("click", newChat);
    document.getElementById("clear-trace-btn")?.addEventListener("click", function() {
        var log = getTraceLog();
        if (log) log.innerHTML = "";
    });

    var stopBtnTrace = document.getElementById("stop-generation-btn");
    var stopBtnChat = document.getElementById("stop-gen-btn");
    
    var handleStopAction = function() {
        if (currentAbortController) {
            currentAbortController.abort();
            appendTrace("STOPPED", "error", "Процесс принудительно остановлен пользователем.");
            showToast("Генерация прервана", "warning");
            
            if (stopBtnTrace) {
                stopBtnTrace.innerHTML = '<i data-lucide="square" class="w-3 h-3"></i> Останавливаю...';
                setTimeout(() => {
                    stopBtnTrace.innerHTML = '<i data-lucide="square" class="w-3 h-3"></i> Stop';
                    refreshIcons(stopBtnTrace);
                }, 1000);
            }
            
            setGenerating(false);
        }
    };

    stopBtnTrace?.addEventListener("click", handleStopAction);
    stopBtnChat?.addEventListener("click", handleStopAction);

    document.getElementById("attach-context-btn")?.addEventListener("click", function() {
        openContextPicker();
    });

    document.getElementById("ctx-picker-cancel")?.addEventListener("click", closeContextPicker);
    document.getElementById("ctx-picker-confirm")?.addEventListener("click", confirmContextPicker);

    document.getElementById("ctx-picker-search")?.addEventListener("input", function(e) {
        filterContextPicker(e.target.value);
    });

    if (strategySelect) {
        strategySelect.addEventListener("change", handleStrategyChange);
        handleStrategyChange();
    }

    document.querySelectorAll(".model-filter-checkbox, .model-filter-provider").forEach(function(el) {
        el.addEventListener("change", filterAllDropdowns);
    });

    subscribe("models", function(models) {
        filterAllDropdowns();
    });

    var attachBtn = document.getElementById("attach-btn");
    var fileInput = document.getElementById("attach-file-input");
    if (attachBtn && fileInput) {
        attachBtn.addEventListener("click", function(e) {
            e.preventDefault();
            e.stopPropagation();
            fileInput.click();
        });
        
        fileInput.addEventListener("change", function(e) {
            var files = e.target.files;
            if (!files || !files.length) return;
            Array.from(files).forEach(function(file) {
                if (file.size > 5 * 1024 * 1024) {
                    showToast(file.name + " > 5MB, пропущен", "error");
                    return;
                }
                var chipId = "up-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);
                var chip = { id: chipId, type: "upload", name: file.name, size: file.size, content: null, loading: true };
                state.attachedContext.push(chip);
                setState("attachedContext", state.attachedContext);
                renderContextStrip();

                var reader = new FileReader();
                reader.onload = function(ev) {
                    var found = state.attachedContext.find(function(c) { return c.id === chipId; });
                    if (found) {
                        found.content = ev.target.result;
                        found.loading = false;
                        renderContextStrip();
                    }
                };
                reader.onerror = function() {
                    setState("attachedContext", state.attachedContext.filter(function(c) { return c.id !== chipId; }));
                    renderContextStrip();
                    showToast("Ошибка чтения " + file.name, "error");
                };
                reader.readAsText(file);
            });
            fileInput.value = "";
        });
    }

    renderContextStrip();
}

function setGenerating(val) {
    state.isGenerating = val;
    setState("isGenerating", val);
    
    var stopBtn = document.getElementById("stop-gen-btn");
    var stopBtnTrace = document.getElementById("stop-generation-btn");
    
    if (val) {
        sendBtn.disabled = true;
        sendBtn.classList.add("opacity-50");
        stopBtn?.classList.remove("hidden");
        
        if (stopBtnTrace) {
            stopBtnTrace.disabled = false;
            stopBtnTrace.classList.remove("opacity-50", "cursor-not-allowed");
        }
    } else {
        sendBtn.disabled = false;
        sendBtn.classList.remove("opacity-50");
        stopBtn?.classList.add("hidden");
        
        if (stopBtnTrace) {
            stopBtnTrace.disabled = true;
            stopBtnTrace.classList.add("opacity-50", "cursor-not-allowed");
        }
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
    if (typeof setAgentStatus === "function") setAgentStatus("Idle");
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

export function appendMessageDOM(role, content, traceData = null) {
    var msgDiv = document.createElement("div");
    msgDiv.className = "message-fade-in flex w-full p-4 group " + 
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
        body.className = "bg-indigo-950/20 border border-indigo-500/20 rounded-xl px-4 py-2.5 text-sm text-gray-200 leading-relaxed max-w-full font-sans relative";
        
        if (content.length > 300) {
            var shortText = content.slice(0, 300);
            var longText = content.slice(300);
            
            body.innerHTML = 
                '<span class="user-text-short">' + escapeHtml(shortText) + '</span>' +
                '<span class="user-text-dots">... </span>' +
                '<span class="user-text-long hidden">' + escapeHtml(longText) + '</span>' +
                '<button class="user-text-toggle-btn text-indigo-400 hover:text-indigo-300 font-semibold ml-1.5 cursor-pointer transition text-xs select-none">Показать всё</button>';
            
            var btn = body.querySelector(".user-text-toggle-btn");
            var longSpan = body.querySelector(".user-text-long");
            var dotsSpan = body.querySelector(".user-text-dots");
            
            btn.addEventListener("click", function() {
                var isHidden = longSpan.classList.contains("hidden");
                if (isHidden) {
                    longSpan.classList.remove("hidden");
                    dotsSpan.classList.add("hidden");
                    btn.textContent = "Свернуть";
                } else {
                    longSpan.classList.add("hidden");
                    dotsSpan.classList.remove("hidden");
                    btn.textContent = "Показать всё";
                }
                chatContainer.scrollTop = chatContainer.scrollHeight;
            });
        } else {
            body.textContent = content;
        }
    } else {
        body.className = "flex-1 space-y-2 overflow-hidden text-gray-200 leading-relaxed text-sm prose prose-invert font-sans content-div";
        body.innerHTML = renderMarkdown(content);
    }

    container.appendChild(avatar);
    container.appendChild(body);
    msgDiv.appendChild(container);

    if (role === "assistant") {
        var actionsDiv = document.createElement("div");
        actionsDiv.className = "msg-actions flex items-start gap-1 pt-0.5 shrink-0";
        actionsDiv.innerHTML = '<button class="copy-msg-btn p-1 rounded hover:bg-ide-hover text-ide-muted" title="Скопировать весь ответ"><i data-lucide="copy" class="w-3 h-3"></i></button>';
        msgDiv.appendChild(actionsDiv);
        
        var copyBtn = actionsDiv.querySelector(".copy-msg-btn");
        if (copyBtn) {
            copyBtn.addEventListener("click", function() {
                navigator.clipboard.writeText(body.textContent);
                showToast("Весь ответ скопирован", "success", 1500);
            });
        }
    }

    if (role === "assistant" && traceData) {
        renderToolTraceBlock(body, traceData);
    }

    injectCodeCopyButtons(msgDiv);

    chatHistoryDOM.appendChild(msgDiv);
    refreshIcons(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    if (window.Prism) {
        msgDiv.querySelectorAll("pre code").forEach(function(block) {
            window.Prism.highlightElement(block);
        });
    }
    return body;
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
// ОТПРАВКА СООБЩЕНИЙ И СТРИМИНГ ИИ (JSON SSE PARSER)
// ═══════════════════════════════════════════════════════════════

async function sendMessage() {
    var text = promptInput.value.trim();
    if (!text && !state.attachedContext.length) return;

    var isNewSession = !state.currentSessionId;

    promptInput.value = "";
    promptInput.style.height = "auto";

    var aiContentDiv = appendMessageDOM("assistant", "");
    var avatarEl = aiContentDiv.closest(".group")?.querySelector(".shadow-inner");
    if (avatarEl) {
        avatarEl.classList.add("avatar-thinking");
    }

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
    var streamTraceData = { calls: [] };

    var strategyVal = (strategySelect && strategySelect.value) || "auto";
    if (strategyVal === "combined") {
        var checked = [];
        document.querySelectorAll(".combined-strategy-checkbox:checked").forEach(function(cb) {
            checked.push(cb.value);
        });
        strategyVal = checked.length > 0 ? checked.join(",") : "auto";
    }

    var modelLockVal = null;
    if (strategySelect && strategySelect.value === "manual" && modelLockSelect) {
        modelLockVal = modelLockSelect.value || null;
    }

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
                strategy: strategyVal,
                model_lock: modelLockVal,
                temperature: 0.2,
                consilium_draft_model: (strategySelect && strategySelect.value === "consilium") ? (document.getElementById("consilium-draft-select")?.value || null) : null,
                consilium_critic_model: (strategySelect && strategySelect.value === "consilium") ? (document.getElementById("consilium-critic-select")?.value || null) : null,
                consilium_synth_model: (strategySelect && strategySelect.value === "consilium") ? (document.getElementById("consilium-synth-select")?.value || null) : null,
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
            var lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (var i = 0; i < lines.length; i++) {
                var line = lines[i].trim();
                if (!line || !line.startsWith("data: ")) continue;

                var dataStr = line.slice(6).trim();
                if (dataStr === "[DONE]") continue;

                try {
                    var event = JSON.parse(dataStr);
                    var status = event.status;

                    if (status === "fallback") {
                        appendTrace("SYSTEM", "error", event.message || "Switching...");
                    }
                    else if (status === "failed") {
                        appendTrace("ERROR", "error", event.error || "Unknown error");
                        aiContentDiv.innerHTML = "<span class=\"text-ide-error font-medium\">⚠️ " + escapeHtml(event.error) + "</span>";
                    }
                    else if (status === "model_try") {
                        appendTrace("TRY", "try", event.model.split("/").pop() + " (" + event.provider + ")");
                        var rModelEl = document.getElementById("current-model-display");
                        if (rModelEl) rModelEl.textContent = event.model.split("/").pop();
                    }
                    else if (status === "model_error") {
                        appendTrace("FAIL", "error", event.model.split("/").pop() + " failed: " + event.error);
                    }
                    else if (status === "model_success") {
                        appendTrace("SUCCESS", "success", event.model.split("/").pop() + " in " + event.elapsed_ms + "ms");
                    }
                    else if (status === "iteration_start") {
                        appendTrace("ITER", "iter", "Loop " + event.iteration + "/" + event.max_iterations);
                    }
                    else if (status === "title_generated") {
                        loadSessions();
                    }
                    else if (status === "tool_start") {
                        appendTrace("TOOL", "tool", "Running: " + event.tool_name);
                        registerActiveTool(event.tool_id, event.tool_name, event.arguments);
                    }
                    else if (status === "tool_end") {
                        appendTrace("DONE", "done", "Finished: " + event.tool_name);
                        updateActiveTool(event.tool_id, event.result?.error ? 'error' : 'success', 1000);
                        
                        streamTraceData.calls.push({
                            name: event.tool_name,
                            args: event.arguments || "",
                            result: event.result || "",
                            status: event.result?.error ? 'error' : 'success'
                        });
                        
                        if (["write_file", "apply_patch", "execute_command"].includes(event.tool_name)) {
                            loadFileTree();
                            loadGitStatus();
                        }

                        if (event.tool_name === "execute_command" && event.result) {
                            if (typeof window.appendAgentTerminalOutput === "function") {
                                var activeTool = activeTools[event.tool_id];
                                var rawArgs = activeTool ? activeTool.arguments : "";
                                var argsObj = rawArgs;
                                if (typeof argsObj === "string") {
                                    try { argsObj = JSON.parse(argsObj); } catch(e) {}
                                }
                                var cmdText = argsObj?.command || argsObj || "";
                                window.appendAgentTerminalOutput(cmdText, event.result);
                            }
                        }
                    }
                    else if (status === "streaming") {
                        if (event.model) {
                            var rModelEl = document.getElementById("current-model-display");
                            if (rModelEl) rModelEl.textContent = event.model.split("/").pop();
                        }
                        
                        if (event.content) {
                            if (fullAssistantText === "") {
                                aiContentDiv.innerHTML = "";
                            }
                            fullAssistantText += event.content;
                            aiContentDiv.innerHTML = renderMarkdown(fullAssistantText);
                            injectCodeCopyButtons(aiContentDiv);
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        }
                    }
                } catch (err) {
                    console.error("Ошибка парсинга строки потока:", err, dataStr);
                }
            }
        }

    } catch (e) {
        if (e.name === "AbortError") {
            // Запрос отменен
        } else {
            appendTrace("ERROR", "bg-red-900 text-red-200", "Ошибка стрима: " + e.message);
            aiContentDiv.innerHTML = '<span class="text-red-400 font-medium">⚠️ Ошибка отправки: ' + escapeHtml(e.message) + '</span>';
            showToast("Ошибка ИИ: " + e.message, "error");
        }
    } finally {
        setGenerating(false);
        state.attachedContext = [];
        setState("attachedContext", []);
        renderContextStrip();
        loadSessions();
        
        if (avatarEl) {
            avatarEl.classList.remove("avatar-thinking");
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// ВСПУ ПАНЕЛИ ОРКЕСТРАТОРА И НАСТРОЙКИ С ФИЛЬТРАМИ
// ═══════════════════════════════════════════════════════════════

function handleStrategyChange() {
    var val = strategySelect.value;
    var settingsPanel = document.getElementById("orchestrator-settings");
    var filterPanel = document.getElementById("model-filters-container");
    var manualPanel = document.getElementById("settings-manual-panel");
    var combinedPanel = document.getElementById("settings-combined-panel");
    var consiliumPanel = document.getElementById("settings-consilium-panel");
    
    if (!settingsPanel) return;
    
    settingsPanel.classList.add("hidden");
    filterPanel?.classList.add("hidden");
    manualPanel?.classList.add("hidden");
    combinedPanel?.classList.add("hidden");
    consiliumPanel?.classList.add("hidden");
    
    if (val === "manual") {
        settingsPanel.classList.remove("hidden");
        filterPanel?.classList.remove("hidden");
        manualPanel?.classList.remove("hidden");
        filterAllDropdowns();
    } else if (val === "combined") {
        settingsPanel.classList.remove("hidden");
        combinedPanel?.classList.remove("hidden");
    } else if (val === "consilium") {
        settingsPanel.classList.remove("hidden");
        filterPanel?.classList.remove("hidden");
        consiliumPanel?.classList.remove("hidden");
        filterAllDropdowns();
    }
}

function filterAllDropdowns() {
    var models = state.models || {};
    
    var filters = {
        free: document.getElementById("filter-tier-free")?.checked ?? true,
        pro: document.getElementById("filter-tier-pro")?.checked ?? true,
        code: document.getElementById("filter-cap-code")?.checked ?? false,
        reason: document.getElementById("filter-cap-reason")?.checked ?? false,
        providers: []
    };
    
    document.querySelectorAll(".model-filter-provider:checked").forEach(function(cb) {
        filters.providers.push(cb.value);
    });
    
    populateDropdown("model-lock-select", models, filters);
    populateDropdown("consilium-draft-select", models, filters);
    populateDropdown("consilium-critic-select", models, filters);
    populateDropdown("consilium-synth-select", models, filters);
}

function populateDropdown(selectId, models, filters) {
    var select = document.getElementById(selectId);
    if (!select) return;
    
    var currentValue = select.value;
    select.innerHTML = selectId === "model-lock-select" ? '<option value="">-- выберите модель --</option>' : '<option value="">-- Авто-подбор --</option>';
    
    var providers = Object.keys(models || {});
    if (providers.length === 0) {
        select.innerHTML = '<option value="">Нет доступных моделей (введите ключи)</option>';
        return;
    }
    
    providers.forEach(function(provider) {
        if (filters.providers && filters.providers.length > 0 && !filters.providers.includes(provider)) return;
        
        var group = document.createElement("optgroup");
        group.label = provider.toUpperCase();
        
        var addedCount = 0;
        models[provider].forEach(function(m) {
            if (!filters.free && m.tier === "free") return;
            if (!filters.pro && m.tier !== "free") return;
            
            if (filters.code && !m.capabilities?.includes("code")) return;
            if (filters.reason && !m.capabilities?.includes("reasoning")) return;
            
            var opt = document.createElement("option");
            opt.value = m.id;
            opt.textContent = m.name + " (" + m.tier + ")";
            if (m.id === currentValue) {
                opt.selected = true;
            }
            group.appendChild(opt);
            addedCount++;
        });
        
        if (addedCount > 0) {
            select.appendChild(group);
        }
    });
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
                type: "workspace", name: name, path: path, content: data.content || ""
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