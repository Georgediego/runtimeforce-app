import { state, setState, subscribe } from "../state.js";
import { sessionsApi, workspacesApi } from "../api.js";
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
var currentAbortController = null;
var runningAgentCommands = {};

function injectCodeCopyButtons(container) {
    if (!document.getElementById('rf-thin-scrollbar-style')) {
        var style = document.createElement('style');
        style.id = 'rf-thin-scrollbar-style';
        style.innerHTML = '.custom-thin-scrollbar::-webkit-scrollbar { height: 6px; width: 6px; } .custom-thin-scrollbar::-webkit-scrollbar-track { background: transparent; } .custom-thin-scrollbar::-webkit-scrollbar-thumb { background-color: var(--ide-elevated-2); border-radius: 4px; } .custom-thin-scrollbar::-webkit-scrollbar-thumb:hover { background-color: var(--ide-text-muted); }';
        document.head.appendChild(style);
    }
    container.querySelectorAll("pre").forEach(function(pre) {
        if (pre.querySelector(".code-copy-btn")) return;
        pre.style.position = "relative";
        pre.style.scrollbarWidth = "thin";
        pre.classList.add("rounded-md", "custom-thin-scrollbar");

        var copyBtn = document.createElement("button");
        copyBtn.className = "code-copy-btn flex items-center justify-center cursor-pointer";
        copyBtn.title = "Copy code";
        copyBtn.innerHTML = '<i data-lucide="copy" class="w-3.5 h-3.5"></i>';
        pre.appendChild(copyBtn);

        if (window.lucide) window.lucide.createIcons({ root: copyBtn });

        copyBtn.addEventListener("click", function(e) {
            e.stopPropagation();
            var codeText = pre.querySelector("code")?.textContent || pre.textContent;
            navigator.clipboard.writeText(codeText).then(function() {
                showToast("Code copied", "success", 1500);
                copyBtn.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i>';
                if (window.lucide) window.lucide.createIcons({ root: copyBtn });
                setTimeout(function() {
                    copyBtn.innerHTML = '<i data-lucide="copy" class="w-3.5 h-3.5"></i>';
                    if (window.lucide) window.lucide.createIcons({ root: copyBtn });
                }, 2000);
            }).catch(function() {
                showToast("Copy failed", "error");
            });
        });
    });
}

function getTraceLog() {
    return document.getElementById("debug-trace-log");
}

function appendTrace(badge, badgeClass, content) {
    var log = getTraceLog();
    if (!log) return;

    var time = new Date().toLocaleTimeString("ru", {
        hour: "2-digit", minute: "2-digit", second: "2-digit"
    });

    var traceStyles = {
        SUCCESS: { dotColor: 'bg-[var(--ide-success)]', dotIcon: '<i data-lucide="check" class="w-2 h-2 text-white"></i>', badgeClass: 'bg-emerald-500/20 text-emerald-400' },
        FAIL: { dotColor: 'bg-[var(--ide-error)]', dotIcon: '<i data-lucide="x" class="w-2 h-2 text-white"></i>', badgeClass: 'bg-rose-500/20 text-rose-400' },
        ERROR: { dotColor: 'bg-[var(--ide-error)]', dotIcon: '<i data-lucide="x" class="w-2 h-2 text-white"></i>', badgeClass: 'bg-rose-500/20 text-rose-400' },
        TRY: { dotColor: 'bg-[var(--ide-accent)]', dotIcon: '', badgeClass: 'bg-blue-500/20 text-blue-400' },
        SYSTEM: { dotColor: 'bg-[var(--ide-warning)]', dotIcon: '', badgeClass: 'bg-amber-500/20 text-amber-400' },
        ITER: { dotColor: 'bg-purple-500', dotIcon: '', badgeClass: 'bg-purple-500/20 text-purple-400' },
        DONE: { dotColor: 'bg-[var(--ide-success)]', dotIcon: '<i data-lucide="check" class="w-2 h-2 text-white"></i>', badgeClass: 'bg-emerald-500/20 text-emerald-400' },
        TOOL: { dotColor: 'bg-cyan-500', dotIcon: '', badgeClass: 'bg-cyan-500/20 text-cyan-400' },
        STOPPED: { dotColor: 'bg-[var(--ide-error)]', dotIcon: '<i data-lucide="square" class="w-2 h-2 text-white"></i>', badgeClass: 'bg-rose-500/20 text-rose-400' },
        LOOP: { dotColor: 'bg-[var(--ide-error)]', dotIcon: '<i data-lucide="alert-circle" class="w-2 h-2 text-white"></i>', badgeClass: 'bg-rose-500/20 text-rose-400' }
    };

    var style = traceStyles[badge] || { dotColor: 'bg-gray-500', dotIcon: '', badgeClass: 'bg-gray-500/20 text-gray-400' };
    var isActive = ['TRY', 'ITER', 'TOOL'].includes(badge);
    var dotClasses = style.dotColor + ' border-4 border-[var(--ide-elevated)] z-10 flex items-center justify-center';
    if (isActive) dotClasses += ' animate-pulse';

    var entry = document.createElement("div");
    entry.className = "trace-entry relative flex items-center justify-between py-2";
    entry.innerHTML =
        '<div class="absolute -left-6 w-4 h-4 rounded-full ' + dotClasses + '">' + style.dotIcon + '</div>' +
        '<div class="flex items-center gap-2 flex-1 min-w-0">' +
            '<span class="' + style.badgeClass + ' px-1.5 py-0.5 rounded text-[10px] font-bold uppercase shrink-0">' + badge + '</span>' +
            '<span class="trace-content text-[var(--ide-text-primary)] text-xs break-all"></span>' +
        '</div>' +
        '<span class="text-[10px] text-[var(--ide-text-muted)] bg-[var(--ide-elevated-2)] px-1.5 py-0.5 rounded shrink-0 ml-2">' + time + '</span>';

    entry.querySelector(".trace-content").textContent = content;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
    if (window.lucide) window.lucide.createIcons({ root: entry });
}

var activeTools = {};

function updateActiveToolsUI() {
    var container = document.getElementById("active-tools-list");
    if (!container) return;
    var keys = Object.keys(activeTools);
    if (keys.length === 0) {
        container.innerHTML = '<div class="text-center text-[11px] text-ide-muted py-3">No active tools</div>';
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
}

function registerActiveTool(toolId, toolName, args) {
    activeTools[toolId] = { name: toolName, arguments: args || "", status: 'running', startTime: Date.now() };
    updateActiveToolsUI();
}

function updateActiveTool(toolId, status, elapsedMs) {
    if (activeTools[toolId]) {
        activeTools[toolId].status = status;
        activeTools[toolId].elapsedMs = elapsedMs;
        updateActiveToolsUI();
        if (status !== 'running') {
            setTimeout(function() { delete activeTools[toolId]; updateActiveToolsUI(); }, 3000);
        }
    }
}

function renderMarkdown(text) {
    if (window.marked) {
        if (typeof window.marked.parse === "function") return window.marked.parse(text);
        else if (typeof window.marked === "function") return window.marked(text);
    }
    return escapeHtml(text).replace(/\n/g, "<br>");
}

export function initChat() {
    if (!promptInput || !sendBtn) return;
    promptInput.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 200) + "px";
    });
    promptInput.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!state.isGenerating) sendMessage();
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
            appendTrace("STOPPED", "error", "Stopped by user");
            showToast("Generation stopped", "warning");
            setGenerating(false);
        }
    };
    stopBtnTrace?.addEventListener("click", handleStopAction);
    stopBtnChat?.addEventListener("click", handleStopAction);

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

    subscribe("models", function() { filterAllDropdowns(); });

    var attachBtn = document.getElementById("attach-btn");
    var fileInput = document.getElementById("attach-file-input");
    if (attachBtn && fileInput) {
        attachBtn.addEventListener("click", function(e) { e.preventDefault(); e.stopPropagation(); fileInput.click(); });
        fileInput.addEventListener("change", function(e) {
            var files = e.target.files;
            if (!files || !files.length) return;
            Array.from(files).forEach(function(file) {
                if (file.size > 5 * 1024 * 1024) { showToast(file.name + " > 5MB, skipped", "error"); return; }
                var chipId = "up-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);
                state.attachedContext.push({ id: chipId, type: "upload", name: file.name, size: file.size, content: null, loading: true });
                setState("attachedContext", state.attachedContext);
                renderContextStrip();
                var reader = new FileReader();
                reader.onload = function(ev) {
                    var found = state.attachedContext.find(function(c) { return c.id === chipId; });
                    if (found) { found.content = ev.target.result; found.loading = false; renderContextStrip(); }
                };
                reader.onerror = function() {
                    setState("attachedContext", state.attachedContext.filter(function(c) { return c.id !== chipId; }));
                    renderContextStrip();
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
        if (stopBtnTrace) { stopBtnTrace.disabled = false; stopBtnTrace.classList.remove("opacity-50", "cursor-not-allowed"); }
    } else {
        sendBtn.disabled = false;
        sendBtn.classList.remove("opacity-50");
        stopBtn?.classList.add("hidden");
        if (stopBtnTrace) { stopBtnTrace.disabled = true; stopBtnTrace.classList.add("opacity-50", "cursor-not-allowed"); }
        currentAbortController = null;
    }
}

export function newChat() {
    if (state.isGenerating) return;
    state.chatHistory = [];
    state.attachedContext = [];
    setState("currentSessionId", null);
    setState("attachedContext", []);
    if (chatHistoryDOM) chatHistoryDOM.innerHTML = "";
    renderContextStrip();
    if (promptInput) { promptInput.value = ""; promptInput.style.height = "auto"; }
    showToast("New chat opened", "info");
}

export async function loadChatSession(sessionId) {
    if (!sessionId) return;
    try {
        var data = await sessionsApi.messages(sessionId);
        state.chatHistory = (data.messages || []).filter(function(m) { return m.role === "user" || m.role === "assistant"; });
        setState("currentSessionId", sessionId);
        renderChatHistory();
    } catch (e) {
        showToast("Failed to load session: " + e.message, "error");
    }
}

function renderChatHistory() {
    if (!chatHistoryDOM) return;
    chatHistoryDOM.innerHTML = "";
    state.chatHistory.forEach(function(msg) {
        if (msg.role === "system" || msg.role === "tool" || (msg.role === "assistant" && msg.tool_calls && !msg.content)) return;
        appendMessageDOM(msg.role, msg.content, msg.trace);
    });
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
}

export function appendMessageDOM(role, content, traceData) {
    if (traceData === undefined) traceData = null;
    var msgDiv = document.createElement("div");

    if (role === "user") {
        msgDiv.className = "message-card bg-[var(--ide-elevated-2)] rounded-xl p-3 self-end max-w-[80%] relative shadow-sm";
        msgDiv.innerHTML = '<div class="text-[var(--ide-accent)] font-bold text-[11px] mb-1">You</div>' +
            '<div class="text-[var(--ide-text-primary)] text-sm font-sans whitespace-pre-wrap">' + escapeHtml(content || "") + '</div>' +
            '<div class="text-[var(--ide-text-muted)] text-[10px] text-right mt-1">' + new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) + '</div>';
    } else {
        msgDiv.className = "message-card bg-[var(--ide-elevated)] rounded-xl pt-3 px-3 pb-8 self-start max-w-[95%] sm:max-w-[85%] border-l-[3px] border-[var(--ide-accent)] relative shadow-sm";
        var headerHTML = '<div class="flex items-center justify-between mb-2"><div class="flex items-center gap-2"><span class="font-bold text-[11px] text-[var(--ide-text-secondary)] uppercase tracking-wider">Agent</span><span class="w-1.5 h-1.5 rounded-full bg-[var(--ide-success)]"></span></div></div>' +
            '<button class="copy-msg-btn absolute bottom-2 left-3 p-1 rounded hover:bg-[var(--ide-hover)] text-[var(--ide-text-muted)] hover:text-[var(--ide-text-primary)] transition-colors flex items-center justify-center cursor-pointer" title="Copy"><i data-lucide="copy" class="w-3.5 h-3.5"></i></button>';
        var bodyDiv = document.createElement("div");
        bodyDiv.className = "text-[var(--ide-text-primary)] leading-relaxed text-sm prose prose-invert font-sans content-div overflow-hidden";
        bodyDiv.innerHTML = renderMarkdown(content || "");
        msgDiv.innerHTML = headerHTML;
        msgDiv.appendChild(bodyDiv);

        var copyBtn = msgDiv.querySelector(".copy-msg-btn");
        if (copyBtn) {
            copyBtn.addEventListener("click", function() {
                navigator.clipboard.writeText(bodyDiv.textContent);
                showToast("Response copied", "success", 1500);
            });
        }
        if (traceData) renderToolTraceBlock(bodyDiv, traceData);
    }

    injectCodeCopyButtons(msgDiv);
    if (chatHistoryDOM) chatHistoryDOM.appendChild(msgDiv);
    refreshIcons(msgDiv);
    if (chatContainer) setTimeout(function() { chatContainer.scrollTop = chatContainer.scrollHeight; }, 10);
    if (window.Prism && role !== "user") {
        msgDiv.querySelectorAll("pre code").forEach(function(block) { window.Prism.highlightElement(block); });
    }
    return role === "user" ? msgDiv : msgDiv.querySelector('.content-div');
}

function renderToolTraceBlock(parentDOM, trace) {
    if (!trace || !trace.calls || !trace.calls.length) return;
    var container = document.createElement("div");
    container.className = "mt-4 border border-gray-800 bg-gray-950/60 rounded-lg text-xs overflow-hidden shadow-sm";
    var header = document.createElement("div");
    header.className = "flex items-center justify-between px-3 py-2 bg-gray-900/80 cursor-pointer hover:bg-gray-900 text-gray-400 select-none border-b border-gray-800";
    header.innerHTML = '<span class="font-medium flex items-center space-x-2">⚙️ <span>Tool calls (' + trace.calls.length + ')</span></span><span class="toggle-icon text-[10px]">▼</span>';
    var content = document.createElement("div");
    content.className = "p-3 space-y-3 hidden bg-gray-950/40 max-h-60 overflow-y-auto font-mono";
    trace.calls.forEach(function(c) {
        var item = document.createElement("div");
        item.className = "space-y-1 border-l-2 border-gray-700 pl-2 py-0.5 text-gray-300";
        var title = document.createElement("div");
        title.className = "font-bold text-gray-400 text-[11px]";
        title.textContent = "Tool: " + c.name + " [" + (c.status || "done") + "]";
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
        content.classList.toggle("hidden");
        header.querySelector(".toggle-icon").textContent = isHidden ? "▲" : "▼";
    });
    container.appendChild(header);
    container.appendChild(content);
    parentDOM.appendChild(container);
}

// ═══════════════════════════════════════════════════════════
// Прямой запрос к локальной модели (OpenAI-compatible API)
// ═══════════════════════════════════════════════════════════
async function sendLocalStream(aiContentDiv, localModel, messages) {
    appendTrace("TRY", "try", localModel.name + " (local)");
    var modelDisplay = document.getElementById("current-model-display");
    if (modelDisplay) modelDisplay.textContent = localModel.name;

    var response = await fetch(localModel.url + '/chat/completions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + (localModel.api_key || 'not-needed')
        },
        signal: currentAbortController.signal,
        body: JSON.stringify({
            model: localModel.model_name,
            messages: messages,
            stream: true,
            temperature: 0.2
        })
    });

    if (!response.ok) {
        var errText = '';
        try { errText = (await response.json()).error?.message || ''; } catch(e) {}
        throw new Error('HTTP ' + response.status + (errText ? ': ' + errText : ''));
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder("utf-8");
    var buffer = "";
    var fullText = "";
    var startTime = Date.now();

    while (true) {
        var result = await reader.read();
        if (result.done) break;

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split("\n");
        buffer = lines.pop();

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (!line || !line.startsWith("data: ")) continue;

            var dataStr = line.slice(6).trim();
            if (dataStr === "[DONE]") {
                var elapsed = Date.now() - startTime;
                appendTrace("SUCCESS", "success", localModel.name + " in " + elapsed + "ms");
                break;
            }

            try {
                var parsed = JSON.parse(dataStr);
                var delta = parsed.choices?.[0]?.delta;
                if (delta && delta.content) {
                    if (fullText === "") aiContentDiv.innerHTML = "";
                    fullText += delta.content;
                    aiContentDiv.innerHTML = renderMarkdown(fullText);
                    injectCodeCopyButtons(aiContentDiv);
                    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            } catch (e) { /* skip malformed chunks */ }
        }
    }

    return fullText;
}

// ═══════════════════════════════════════════════════════════
// Основная отправка сообщения
// ═══════════════════════════════════════════════════════════
async function sendMessage() {
    var text = promptInput.value.trim();
    if (!text && !state.attachedContext.length) return;
    promptInput.value = "";
    promptInput.style.height = "auto";

    appendMessageDOM("user", text);
    var aiContentDiv = appendMessageDOM("assistant", "");
    state.chatHistory.push({ role: "user", content: text });

    var currentSessionId = state.currentSessionId;
    if (!currentSessionId) {
        currentSessionId = "session-" + Date.now() + "-" + Math.random().toString(36).slice(2, 11);
        setState("currentSessionId", currentSessionId);
        sessionsApi.create(text, currentSessionId)
            .then(function() { loadSessions(); })
            .catch(function(err) { console.error("Session registration failed:", err); });
    }

    setGenerating(true);
    currentAbortController = new AbortController();

    var messagesForLLM = [];
    if (state.attachedContext && state.attachedContext.length) {
        var contextPrompt = "Use the following project context:\n\n";
        state.attachedContext.forEach(function(ctx) {
            contextPrompt += "--- FILE: " + ctx.path + " ---\n" + ctx.content + "\n\n";
        });
        messagesForLLM.push({ role: "system", content: contextPrompt });
    }
    state.chatHistory.forEach(function(h) {
        if (h.role === "user") {
            messagesForLLM.push({ role: "user", content: h.content || "" });
        } else if (h.role === "assistant" && !h.tool_calls) {
            var content = h.content || "";
            if (content && !content.startsWith("[Tools: ")) {
                messagesForLLM.push({ role: "assistant", content: content });
            }
        }
    });

    var fullAssistantText = "";
    var streamTraceData = { calls: [] };

    var strategyVal = (strategySelect && strategySelect.value) || "auto";
    var modelLockVal = null;
    if (strategySelect && strategySelect.value === "manual" && modelLockSelect) {
        modelLockVal = modelLockSelect.value || null;
    }

    // ═══════════════════════════════════════════════════════════
    // Проверка: локальная модель?
    // ═══════════════════════════════════════════════════════════
    var isLocalModel = modelLockVal && modelLockVal.startsWith('local:');
    var localModel = isLocalModel ? (typeof window.getLocalModelById === 'function' ? window.getLocalModelById(modelLockVal) : null) : null;

    try {
        if (isLocalModel && localModel) {
            // ─── ЛОКАЛЬНАЯ МОДЕЛЬ: прямой запрос ───
            fullAssistantText = await sendLocalStream(aiContentDiv, localModel, messagesForLLM);
        } else {
            // ─── ОБЛАЧНАЯ МОДЕЛЬ: запрос через backend ───
            if (isLocalModel && !localModel) {
                throw new Error('Local model not found. Re-add it in Settings → Providers.');
            }

            var response = await fetch("/api/v1/chat/stream", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + (localStorage.getItem("rf_jwt_token") || localStorage.getItem("jwt_token") || "")
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

            if (!response.ok) throw new Error("Server error: HTTP " + response.status);

            var reader = response.body.getReader();
            var decoder = new TextDecoder("utf-8");
            var buffer = "";

            while (true) {
                var result = await reader.read();
                if (result.done) break;
                buffer += decoder.decode(result.value, { stream: true });
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
                        } else if (status === "failed") {
                            appendTrace("ERROR", "error", event.error || "Unknown error");
                            aiContentDiv.innerHTML = '<span class="text-ide-error font-medium">⚠️ ' + escapeHtml(event.error) + '</span>';
                        } else if (status === "loop_detected") {
                            appendTrace("LOOP", "error", event.message || "Loop detected");
                            showToast(event.message || "Loop detected!", "error");
                        } else if (status === "model_try") {
                            appendTrace("TRY", "try", event.model.split("/").pop() + " (" + event.provider + ")");
                            var rModelEl = document.getElementById("current-model-display");
                            if (rModelEl) rModelEl.textContent = event.model.split("/").pop();
                        } else if (status === "model_error") {
                            appendTrace("FAIL", "error", event.model.split("/").pop() + " failed: " + event.error);
                        } else if (status === "model_success") {
                            appendTrace("SUCCESS", "success", event.model.split("/").pop() + " in " + event.elapsed_ms + "ms");
                        } else if (status === "iteration_start") {
                            appendTrace("ITER", "iter", "Loop " + event.iteration + "/" + event.max_iterations);
                        } else if (status === "title_generated") {
                            loadSessions();
                        } else if (status === "tool_start") {
                            appendTrace("TOOL", "tool", "Running: " + event.tool_name);
                            registerActiveTool(event.tool_id, event.tool_name, event.arguments);
                        } else if (status === "tool_end") {
                            appendTrace("DONE", "done", "Finished: " + event.tool_name);
                            updateActiveTool(event.tool_id, event.result?.error ? 'error' : 'success', 1000);
                            streamTraceData.calls.push({ name: event.tool_name, args: event.arguments || "", result: event.result || "", status: event.result?.error ? 'error' : 'success' });
                            if (["write_file", "apply_patch", "execute_command"].includes(event.tool_name)) { loadFileTree(); loadGitStatus(); }
                            if (event.tool_name === "execute_command" && event.result && typeof window.appendAgentTerminalOutput === "function") {
                                var activeTool = activeTools[event.tool_id];
                                var rawArgs = activeTool ? activeTool.arguments : "";
                                var argsObj = rawArgs;
                                if (typeof argsObj === "string") { try { argsObj = JSON.parse(argsObj); } catch(e) {} }
                                window.appendAgentTerminalOutput(argsObj?.command || argsObj || "", event.result);
                            }
                        } else if (status === "streaming") {
                            if (event.model) {
                                var rModelEl2 = document.getElementById("current-model-display");
                                if (rModelEl2) rModelEl2.textContent = event.model.split("/").pop();
                            }
                            if (event.content) {
                                if (fullAssistantText === "") aiContentDiv.innerHTML = "";
                                fullAssistantText += event.content;
                                aiContentDiv.innerHTML = renderMarkdown(fullAssistantText);
                                injectCodeCopyButtons(aiContentDiv);
                                if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
                            }
                        }
                    } catch (err) {
                        console.error("Stream parse error:", err, dataStr);
                    }
                }
            }
        }
    } catch (e) {
        if (e.name === "AbortError") {
            // cancelled
        } else {
            appendTrace("ERROR", "error", "Stream error: " + e.message);
            aiContentDiv.innerHTML = '<span class="text-red-400 font-medium">⚠️ ' + escapeHtml(e.message) + '</span>';
            showToast("AI error: " + e.message, "error");
        }
    } finally {
        if (fullAssistantText) {
            var lastMsg = state.chatHistory[state.chatHistory.length - 1];
            if (!lastMsg || lastMsg.role !== "assistant") {
                state.chatHistory.push({ role: "assistant", content: fullAssistantText, trace: streamTraceData.calls.length ? streamTraceData : null });
            } else {
                lastMsg.content = fullAssistantText;
                lastMsg.trace = streamTraceData.calls.length ? streamTraceData : null;
            }
        }
        setGenerating(false);
        state.attachedContext = [];
        setState("attachedContext", []);
        renderContextStrip();
        loadSessions();
    }
}

function handleStrategyChange() {
    var val = strategySelect.value;
    var settingsPanel = document.getElementById("orchestrator-settings");
    var filterPanel = document.getElementById("model-filters-container");
    var manualPanel = document.getElementById("settings-manual-panel");
    var consiliumPanel = document.getElementById("settings-consilium-panel");
    if (!settingsPanel) return;
    [settingsPanel, filterPanel, manualPanel, consiliumPanel].forEach(function(el) { if (el) el.classList.add("hidden"); });

    if (val === "manual") {
        settingsPanel.classList.remove("hidden");
        if (filterPanel) filterPanel.classList.remove("hidden");
        if (manualPanel) manualPanel.classList.remove("hidden");
        filterAllDropdowns();
    } else if (val === "consilium") {
        settingsPanel.classList.remove("hidden");
        if (filterPanel) filterPanel.classList.remove("hidden");
        if (consiliumPanel) consiliumPanel.classList.remove("hidden");
        filterAllDropdowns();
    }
}

// ═══════════════════════════════════════════════════════════
// ЕДИНСТВЕННАЯ версия filterAllDropdowns + populateDropdown
// ═══════════════════════════════════════════════════════════
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

    var selectedModels = {};
    if (typeof window.getAllSelectedModels === "function") {
        selectedModels = window.getAllSelectedModels();
    }

    populateDropdown("model-lock-select", models, filters, selectedModels);
    populateDropdown("consilium-draft-select", models, filters, selectedModels);
    populateDropdown("consilium-critic-select", models, filters, selectedModels);
    populateDropdown("consilium-synth-select", models, filters, selectedModels);
}

function populateDropdown(selectId, models, filters, selectedModels) {
    var select = document.getElementById(selectId);
    if (!select) return;
    var currentValue = select.value;
    var isManualSelect = (selectId === "model-lock-select");
    select.innerHTML = isManualSelect ? '<option value="">-- select model --</option>' : '<option value="">-- Auto --</option>';

    var providers = Object.keys(models || {});
    if (providers.length === 0) {
        select.innerHTML = '<option value="">No models (add API keys)</option>';
        return;
    }

    var hasAnyModels = false;

    // ═══════════════════════════════════════════════════════════
    // Локальные модели — ТОЛЬКО в manual (model-lock-select)
    // ═══════════════════════════════════════════════════════════
    if (isManualSelect && models['local'] && models['local'].length > 0) {
        var localGroup = document.createElement("optgroup");
        localGroup.label = "LOCAL";
        models['local'].forEach(function(m) {
            var opt = document.createElement("option");
            opt.value = m.id;
            opt.textContent = '🖥 ' + m.name;
            if (m.id === currentValue) opt.selected = true;
            localGroup.appendChild(opt);
            hasAnyModels = true;
        });
        select.appendChild(localGroup);
    }

    // Облачные провайдеры
    providers.forEach(function(provider) {
        // Локальные уже обработаны выше
        if (provider === 'local') return;
        // Локальные НЕ показываем в consilium
        if (filters.providers && filters.providers.length > 0 && !filters.providers.includes(provider)) return;

        var providerModels = models[provider] || [];
        var selectedForProvider = (selectedModels && selectedModels[provider]) || [];

        var filteredModels = providerModels.filter(function(m) {
            if (selectedForProvider.length > 0 && !selectedForProvider.includes(m.id)) return false;
            if (!filters.free && m.tier === "free") return false;
            if (!filters.pro && m.tier !== "free") return false;
            if (filters.code && !m.capabilities?.includes("code")) return false;
            if (filters.reason && !m.capabilities?.includes("reasoning")) return false;
            return true;
        });

        if (filteredModels.length === 0) return;

        var group = document.createElement("optgroup");
        group.label = provider.toUpperCase();
        filteredModels.forEach(function(m) {
            var opt = document.createElement("option");
            opt.value = m.id;
            opt.textContent = m.name + " (" + m.tier + ")";
            if (m.id === currentValue) opt.selected = true;
            group.appendChild(opt);
            hasAnyModels = true;
        });
        select.appendChild(group);
    });

    if (!hasAnyModels) {
        select.innerHTML = '<option value="">No models available</option>';
    }
}

// ═══════════════════════════════════════════════════════════
// Context Picker
// ═══════════════════════════════════════════════════════════
var pickerSelection = new Set();
var allAvailablePaths = [];

function openContextPicker() {
    var modal = document.getElementById("context-picker-modal");
    if (!modal) return;
    modal.classList.add("active");
    modal.classList.remove("hidden");
    var listContainer = document.getElementById("ctx-picker-tree");
    if (!listContainer) return;
    listContainer.innerHTML = '<div class="p-4 text-center text-gray-500 animate-pulse text-xs">Scanning project tree...</div>';
    pickerSelection.clear();
    var countEl = document.getElementById("ctx-picker-count");
    if (countEl) countEl.textContent = "Selected: 0";
    var searchEl = document.getElementById("ctx-picker-search");
    if (searchEl) searchEl.value = "";

    workspacesApi.list().then(async function() {
        try {
            if (!state.activeWorkspace) {
                listContainer.innerHTML = '<div class="p-4 text-center text-gray-500 text-xs">Activate workspace first</div>';
                return;
            }
            var res = await fetch("/api/v1/workspaces/tree", {
                headers: { "Authorization": "Bearer " + (localStorage.getItem("rf_jwt_token") || localStorage.getItem("jwt_token") || "") }
            });
            var treeData = await res.json();
            allAvailablePaths = [];
            buildFlatPathsFromTree(treeData.tree || [], "", allAvailablePaths);
            renderContextPickerList(allAvailablePaths);
        } catch (err) {
            listContainer.innerHTML = '<div class="p-4 text-center text-red-400 text-xs">Error: ' + err.message + '</div>';
        }
    });
}

function closeContextPicker() {
    var modal = document.getElementById("context-picker-modal");
    if (modal) { modal.classList.remove("active"); modal.classList.add("hidden"); }
}

function buildFlatPathsFromTree(nodes, currentPath, acc) {
    nodes.forEach(function(n) {
        var p = currentPath ? currentPath + "/" + n.name : n.name;
        if (n.type === "file") { acc.push({ name: n.name, path: p }); }
        else if (n.type === "directory" && n.children) { buildFlatPathsFromTree(n.children, p, acc); }
    });
}

function renderContextPickerList(paths) {
    var container = document.getElementById("ctx-picker-tree");
    if (!container) return;
    container.innerHTML = "";
    if (!paths.length) { container.innerHTML = '<div class="p-4 text-center text-gray-500 text-xs">No files found</div>'; return; }
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
        nameInfo.innerHTML = '<div class="font-medium truncate text-gray-200">' + escapeHtml(f.name) + '</div><div class="text-[10px] text-gray-500 truncate font-mono">' + escapeHtml(f.path) + '</div>';
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
            var countEl = document.getElementById("ctx-picker-count");
            if (countEl) countEl.textContent = "Selected: " + pickerSelection.size;
        });
        container.appendChild(item);
    });
    refreshIcons(container);
}

function filterContextPicker(query) {
    var q = query.toLowerCase().trim();
    if (!q) { renderContextPickerList(allAvailablePaths); return; }
    renderContextPickerList(allAvailablePaths.filter(function(p) { return p.path.toLowerCase().includes(q) || p.name.toLowerCase().includes(q); }));
}

async function confirmContextPicker() {
    var paths = Array.from(pickerSelection);
    if (!paths.length) { closeContextPicker(); return; }
    showToast("Loading " + paths.length + " files...", "info");
    for (var i = 0; i < paths.length; i++) {
        var path = paths[i];
        var name = path.split("/").pop();
        if (state.attachedContext.some(function(c) { return c.path === path; })) continue;
        try {
            var data = await workspacesApi.file(path);
            state.attachedContext.push({ id: "ws-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7), type: "workspace", name: name, path: path, content: data.content || "" });
        } catch (e) {}
    }
    setState("attachedContext", state.attachedContext);
    renderContextStrip();
    closeContextPicker();
    showToast("Added " + paths.length + " files", "success");
}

function renderContextStrip() {
    var container = document.getElementById("attached-context-bar");
    if (!container) return;
    container.innerHTML = "";
    if (!state.attachedContext || !state.attachedContext.length) { container.classList.add("hidden"); return; }
    container.classList.remove("hidden");
    state.attachedContext.forEach(function(ctx) {
        var badge = document.createElement("div");
        badge.className = "flex items-center space-x-1.5 bg-gray-200 dark:bg-gray-800 px-2 py-1 rounded-lg text-xs font-medium";
        badge.innerHTML = '<span>' + getFileIcon(ctx.name) + '</span><span class="max-w-[120px] truncate" title="' + escapeHtml(ctx.path) + '">' + escapeHtml(ctx.name) + '</span><button class="text-indigo-400 hover:text-indigo-200 font-bold ml-1 text-[11px]">×</button>';
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

// Глобальный экспорт
window.filterAllDropdowns = filterAllDropdowns;