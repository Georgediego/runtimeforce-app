import { state, setState } from "../state.js";
import { sessionsApi, workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons, getFileIcon } from "../utils/icons.js";
import { showToast } from "./toast.js";
import { loadSessions } from "./sessions.js";
import { loadGitStatus } from "./git.js";

var chatContainer = document.getElementById("chat-container");
var chatHistoryDOM = document.getElementById("chat-history");
var promptInput = document.getElementById("prompt-input");
var sendBtn = document.getElementById("send-btn");
var strategySelect = document.getElementById("strategy-select");
var modelLockSelect = document.getElementById("model-lock-select");

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
    window.addEventListener("new-chat", newChat);
    window.addEventListener("render-message", function(e) { appendMessage(e.detail.role, e.detail.content); });
    window.addEventListener("agent-status", function(e) { setAgentStatus(e.detail.status, e.detail.model); });
}

export function newChat() {
    setState("chatHistory", []);
    setState("currentSessionId", null);
    setState("attachedContext", []);
    chatHistoryDOM.innerHTML = "";
    setAgentStatus("Idle");
    document.querySelectorAll(".session-item").forEach(function(el) { el.classList.remove("active"); });
    renderContextStrip();
}

export function clearChat() {
    newChat();
    showToast("История очищена", "success");
}

function updateLiveOrchestratorBadge(provider, model, isFallback = false) {
    var display = document.getElementById("current-model-display");
    var activeDisplay = document.getElementById("active-model-display");
    var statusText = document.getElementById("agent-status-text");
    var statusIndicator = document.getElementById("status-indicator");

    if (!display) return;

    var shortModel = model.split("/").pop();
    var displayText = provider.toUpperCase() + ": " + shortModel;
    
    display.innerText = displayText;
    if (activeDisplay) activeDisplay.innerText = displayText;

    if (isFallback) {
        if (statusText) statusText.innerText = "Fallback";
        if (statusIndicator) statusIndicator.className = "w-2 h-2 rounded-full bg-ide-warning status-active animate-pulse";
    }
}

async function sendMessage() {
    if (state.isGenerating) return;
    var text = promptInput.value.trim();
    if (!text && !state.attachedContext.length) return;

    var loadingFiles = state.attachedContext.filter(function(c) { return c.loading; });
    if (loadingFiles.length > 0) {
        showToast("Ожидаем загрузку " + loadingFiles.length + " файл(ов)...", "info", 1500);
        var start = Date.now();
        while (state.attachedContext.some(function(c) { return c.loading; }) && Date.now() - start < 10000) {
            await new Promise(function(r) { setTimeout(r, 100); });
        }
    }

    var contextSnapshot = state.attachedContext.slice();
    var llmContextBlock = "";
    if (contextSnapshot.length) {
        llmContextBlock = "\n\n---\n## Attached Context (for AI only)\n" +
            contextSnapshot.map(function(c) {
                var label = c.type === "workspace" ? "Workspace file" : "Attached file";
                return "### " + label + ": `" + c.name + "`\n```\n" + (c.content || "").slice(0, 50000) + "\n```";
            }).join("\n\n");
    }

    var displayText = text || "";
    var fullText = displayText + llmContextBlock;

    promptInput.value = "";
    promptInput.style.height = "auto";

    if (!state.currentSessionId) {
        var sid = "session-" + Date.now();
        setState("currentSessionId", sid);
        try {
            await sessionsApi.create(displayText.slice(0, 50) || "New chat", sid);
            setTimeout(loadSessions, 500);
        } catch (e) {}
    }

    state.chatHistory.push({ role: "user", content: displayText });
    appendMessage("user", displayText, contextSnapshot);
    setState("attachedContext", []);
    renderContextStrip();

    setState("isGenerating", true);
    setAgentStatus("Generating");

    var aiContentDiv = appendMessage("assistant", "");
    var currentResponse = "";
    var toolElements = {};

    var messagesForLLM = state.chatHistory.slice(0, -1).concat([{ role: "user", content: fullText }]);

    try {
        var response = await fetch("/api/v1/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: state.currentSessionId,
                messages: messagesForLLM,
                strategy: strategySelect.value,
                model_lock: modelLockSelect.value || null,
                temperature: 0.2
            })
        });

        if (!response.ok) throw new Error("Network response error: " + response.status);

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            var { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            var lines = buffer.split("\n");
            buffer = lines.pop(); 

            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (!line) continue;

                if (line.indexOf("METADATA:") === 0) {
                    try {
                        var meta = JSON.parse(line.substring(9));
                        updateLiveOrchestratorBadge(meta.provider, meta.model, meta.fallback);
                    } catch (e) {
                        console.error("Meta parse error", e);
                    }
                } 
                else if (line.indexOf("SYSTEM_NOTICE:") === 0) {
                    var noticeText = line.substring(14);
                    var noticeDiv = document.createElement("div");
                    noticeDiv.className = "my-2 text-xs font-mono text-amber-500 bg-amber-950/20 border border-amber-900/40 rounded p-2 text-center animate-pulse";
                    noticeDiv.innerHTML = "⚡ " + escapeHtml(noticeText);
                    aiContentDiv.appendChild(noticeDiv);
                    scrollToBottom();
                }
                else if (line.indexOf("SYSTEM_ERROR:") === 0) {
                    var errText = line.substring(13);
                    aiContentDiv.innerHTML += "<div class=\"p-3 my-2 text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-lg font-mono\"><strong>🔴 Ошибка оркестратора:</strong> " + escapeHtml(errText) + "</div>";
                    scrollToBottom();
                }
                else if (line.indexOf("TOOL_START:") === 0) {
                    try {
                        var toolData = JSON.parse(line.substring(11));
                        setAgentStatus("Tool", toolData.model);
                        var w = document.createElement("div");
                        w.className = "my-3 border border-ide-border rounded-lg p-3 bg-ide-panel/50 font-sans";
                        w.innerHTML = "<div class=\"tool-badge running\"><span class=\"animate-ping w-1.5 h-1.5 rounded-full bg-yellow-400 mr-1.5\"></span>Running: " + escapeHtml(toolData.tool_name) + "</div><div class=\"text-[11px] font-mono text-ide-muted mb-2 truncate\">Args: " + escapeHtml(String(toolData.arguments)) + "</div><div class=\"tool-output text-yellow-500/80 font-mono text-xs\">Executing...</div>";
                        aiContentDiv.appendChild(w);
                        toolElements[toolData.tool_id] = w;
                        scrollToBottom();
                    } catch (e) {}
                }
                else if (line.indexOf("TOOL_END:") === 0) {
                    try {
                        var toolData = JSON.parse(line.substring(9));
                        setAgentStatus("Generating", toolData.model);
                        var w2 = toolElements[toolData.tool_id];
                        if (w2) {
                            var outDiv = w2.querySelector(".tool-output");
                            var badge = w2.querySelector(".tool-badge");
                            var r = toolData.result;
                            if (r.error) {
                                badge.className = "tool-badge error";
                                badge.innerHTML = "❌ Error: " + escapeHtml(toolData.tool_name);
                                outDiv.textContent = r.error;
                                outDiv.className = "tool-output text-ide-error font-mono text-xs";
                            } else {
                                badge.className = "tool-badge success";
                                badge.innerHTML = "✅ Done: " + escapeHtml(toolData.tool_name);
                                outDiv.textContent = toolData.tool_name === "execute_command"
                                    ? "[Exit: " + r.exit_code + "]\n" + r.stdout + "\n" + r.stderr
                                    : JSON.stringify(r, null, 2);
                            }
                            refreshIcons(badge);
                        }
                        scrollToBottom();
                        loadGitStatus();
                    } catch (e) {}
                }
                else {
                    currentResponse += line + "\n";
                    aiContentDiv.innerHTML = marked.parse(currentResponse);
                    scrollToBottom();
                }
            }
        }

        state.chatHistory.push({ role: "assistant", content: currentResponse });
        setAgentStatus("Idle");
        loadSessions();
    } catch (err) {
        aiContentDiv.innerHTML += "<div class=\"text-xs text-ide-error my-2 font-mono bg-ide-error/10 p-2 border border-ide-error/20 rounded\">Ошибка сессии маршрутизации: " + escapeHtml(err.message) + "</div>";
        setAgentStatus("Error");
    } finally {
        setState("isGenerating", false);
    }
}

export function appendMessage(role, content, attachedFiles) {
    attachedFiles = attachedFiles || [];
    var div = document.createElement("div");
    div.className = "flex gap-3 group";
    var isUser = role === "user";
    var icon = isUser ? "user" : "cpu";
    var iconColor = isUser ? "text-ide-muted" : "text-ide-accent";
    var bg = isUser ? "bg-ide-hover" : "bg-ide-panel border border-ide-border";
    var name = isUser ? "You" : "Runtime Agent";
    var ts = new Date().toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });

    var chipsHTML = "";
    if (isUser && attachedFiles.length > 0) {
        chipsHTML = "<div class=\"flex flex-wrap gap-1.5 mb-2\">" +
            attachedFiles.map(function(c) {
                var ico = c.type === "workspace" ? "folder" : "file";
                return "<span class=\"ctx-chip\"><i data-lucide=\"" + ico + "\" class=\"w-3 h-3 shrink-0\"></i><span class=\"chip-name\">" + escapeHtml(c.name) + "</span></span>";
            }).join("") + "</div>";
    }

    div.innerHTML = "<div class=\"w-7 h-7 rounded-lg " + bg + " flex items-center justify-center shrink-0 mt-0.5\"><i data-lucide=\"" + icon + "\" class=\"w-3.5 h-3.5 " + iconColor + "\"></i></div>" +
        "<div class=\"flex-1 min-w-0 pt-0.5\">" +
        "<div class=\"flex items-center gap-2 mb-1.5\"><span class=\"font-semibold text-xs text-ide-text\">" + name + "</span>" +
        "<span class=\"text-[10px] text-ide-muted font-mono\">" + ts + "</span></div>" +
        chipsHTML +
        "<div class=\"prose prose-invert max-w-none text-sm text-ide-text content-div\"></div>" +
        "</div>" +
        "<div class=\"msg-actions flex items-start gap-1 pt-0.5\">" +
        "<button class=\"copy-msg-btn p-1 rounded hover:bg-ide-hover text-ide-muted\"><i data-lucide=\"copy\" class=\"w-3 h-3\"></i></button>" +
        "</div>";

    chatHistoryDOM.appendChild(div);
    refreshIcons(div);
    var cd = div.querySelector(".content-div");
    if (isUser) {
        cd.innerText = content;
    } else {
        cd.innerHTML = marked.parse(content || "");
    }
    var copyBtn = div.querySelector(".copy-msg-btn");
    if (copyBtn) {
        copyBtn.addEventListener("click", function() {
            navigator.clipboard.writeText(cd.textContent);
            showToast("Скопировано", "success", 1500);
        });
    }
    scrollToBottom();
    return cd;
}

function scrollToBottom() {
    chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "smooth" });
}

export function setAgentStatus(status, model) {
    var statusText = document.getElementById("agent-status-text");
    var statusIndicator = document.getElementById("status-indicator");
    if (statusText) statusText.innerText = status;
    
    if (statusIndicator) {
        if (status === "Generating" || status === "Fallback" || status === "Tool") {
            statusIndicator.className = "w-2 h-2 rounded-full bg-ide-warning status-active";
        } else if (status === "Idle") {
            statusIndicator.className = "w-2 h-2 rounded-full bg-ide-success status-idle";
        } else if (status === "Error") {
            statusIndicator.className = "w-2 h-2 rounded-full bg-ide-error";
        }
    }
    if (model) {
        var short = model.split("/").pop();
        var currentDisp = document.getElementById("current-model-display");
        var activeDisp = document.getElementById("active-model-display");
        if (currentDisp) currentDisp.innerText = short;
        if (activeDisp) activeDisp.innerText = short;
    }
}

export function renderContextStrip() {
    var strip = document.getElementById("context-strip");
    if (!state.attachedContext.length) {
        strip.innerHTML = "";
        return;
    }
    strip.innerHTML = state.attachedContext.map(function(c) {
        if (c.loading) {
            return "<span class=\"ctx-chip\" style=\"opacity:0.6\"><i data-lucide=\"loader\" class=\"w-3 h-3 animate-spin\"></i><span class=\"chip-name\">" + escapeHtml(c.name) + "</span></span>";
        }
        var ico = c.type === "workspace" ? "folder" : "upload";
        return "<span class=\"ctx-chip\"><i data-lucide=\"" + ico + "\" class=\"w-3 h-3\"></i><span class=\"chip-name\">" + escapeHtml(c.name) + "</span><button data-remove-id=\"" + c.id + "\">×</button></span>";
    }).join("");
    refreshIcons(strip);
    strip.querySelectorAll("[data-remove-id]").forEach(function(btn) {
        btn.addEventListener("click", function() {
            setState("attachedContext", state.attachedContext.filter(function(c) { return c.id !== btn.dataset.removeId; }));
            renderContextStrip();
        });
    });
}

export function initFileAttach() {
    var attachBtn = document.getElementById("attach-btn");
    var fileInput = document.getElementById("attach-file-input");
    if (!attachBtn || !fileInput) return;

    attachBtn.addEventListener("click", function() { fileInput.click(); });
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

export function initContextPicker() {
    document.getElementById("context-btn")?.addEventListener("click", openContextPicker);
    document.getElementById("close-context-picker-btn")?.addEventListener("click", closeContextPicker);
    document.getElementById("cancel-context-picker-btn")?.addEventListener("click", closeContextPicker);
    document.getElementById("confirm-context-picker-btn")?.addEventListener("click", confirmContextPicker);
    document.getElementById("context-picker-modal")?.addEventListener("click", function(e) {
        if (e.target === e.currentTarget) closeContextPicker();
    });
}

var pickerTreeData = null;
var pickerSelection = new Set();

async function openContextPicker() {
    document.getElementById("context-picker-modal").classList.remove("hidden");
    pickerSelection = new Set();
    document.getElementById("ctx-picker-count").textContent = "Выбрано: 0";
    var container = document.getElementById("ctx-picker-tree");
    container.innerHTML = "<div class=\"text-center text-xs text-ide-muted py-4\">Загрузка...</div>";

    if (!state.cachedFileTree) {
        try {
            var data = await workspacesApi.tree();
            state.cachedFileTree = data.tree;
        } catch (e) {
            container.innerHTML = "<div class=\"text-center text-xs text-ide-error py-4\">Нет workspace</div>";
            return;
        }
    }
    pickerTreeData = state.cachedFileTree;
    renderPickerTree(pickerTreeData);
}

function renderPickerTree(tree, filter) {
    filter = filter || "";
    var container = document.getElementById("ctx-picker-tree");
    if (!tree) return;
    var lower = filter.toLowerCase();

    function render(node, depth) {
        depth = depth || 0;
        var isDir = !!node.children;
        var pad = "padding-left: " + (depth * 12) + "px";
        if (isDir) {
            var children = (node.children || []).map(function(c) { return render(c, depth + 1); }).join("");
            if (!children && lower) return "";
            return "<div style=\"" + pad + "\"><label class=\"picker-tree-item\"><input type=\"checkbox\" value=\"" + escapeHtml(node.path) + "\" data-type=\"dir\"><i data-lucide=\"folder\" class=\"w-3.5 h-3.5 text-ide-warning\"></i><span>" + escapeHtml(node.name) + "</span></label>" + children + "</div>";
        }
        if (lower && !node.name.toLowerCase().includes(lower)) return "";
        return "<div style=\"" + pad + "\"><label class=\"picker-tree-item\"><input type=\"checkbox\" value=\"" + escapeHtml(node.path) + "\" data-type=\"file\" data-name=\"" + escapeHtml(node.name) + "\"><i data-lucide=\"" + getFileIcon(node.name) + "\" class=\"w-3.5 h-3.5\"></i><span>" + escapeHtml(node.name) + "</span></label></div>";
    }

    container.innerHTML = (tree.children || []).map(function(c) { return render(c, 0); }).join("") || "<div class=\"text-center text-xs text-ide-muted py-4\">Пусто</div>";
    container.querySelectorAll("input[type=\"checkbox\"]").forEach(function(cb) {
        cb.checked = pickerSelection.has(cb.value);
        cb.addEventListener("change", function() {
            if (cb.checked) pickerSelection.add(cb.value);
            else pickerSelection.delete(cb.value);
            document.getElementById("ctx-picker-count").textContent = "Выбрано: " + pickerSelection.size;
        });
    });
    refreshIcons(container);
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