/**
 * Chat UI Controller with Interactive Section 15.5 Dangerous Command Approval & Terminal Stream.
 */
import { ChatWSClient } from "../core/chat_ws_client.js";
import { sessionsApi, keysApi } from "../core/api_http_client.js";
import { showToast, showConfirm, showPrompt, showMultiLinePrompt, showCommandApprovalModal } from "./toast_ui_controller.js";
import { terminalUIController } from "./terminal.js";
import { eventBus } from "../core/event_bus.js";
import { fileTreeUIController } from "./file_tree_ui_controller.js";

let wsClient = null;
let currentSessionId = null;
let fullResponseText = "";
let fullReasoningText = "";
let currentPhaseLabel = "Processing request...";
let currentAgentRole = "Agent";
let currentAgentModel = "";
let attachedFiles = [];
let lastUserPrompt = "";
let isGenerating = false;
let isFirstMessageOfSession = true;
let executionTimer = null;
let elapsedSeconds = 0;
let currentPendingMessageId = null;
let treeReloadTimer = null;
let pendingStreamError = "";
let generationFinalized = false;
let userAbortedGeneration = false;
const approvedCommandsCache = new Set();

const ALL_PROVIDERS = ["gemini", "openrouter", "groq", "sambanova", "cerebras", "ollama", "lm_studio", "openai", "anthropic", "deepseek", "xai"];
const FREE_PROVIDERS_SET = new Set(["gemini", "groq", "sambanova", "cerebras", "ollama", "lm_studio"]);

function debouncedTreeReload() {
    if (treeReloadTimer) clearTimeout(treeReloadTimer);
    treeReloadTimer = setTimeout(() => {
        fileTreeUIController.loadTree();
        treeReloadTimer = null;
    }, 300);
}

function isDangerousCommand(cmd) {
    if (!cmd) return false;
    const c = cmd.toLowerCase().trim();
    const risky = [
        "rm -", "rm --", "chmod 777", "git reset --hard", 
        "git clean -f", "sudo ", "apt install", "apt-get install", 
        "pip install", "npm install", "dd if=", "mkfs"
    ];
    return risky.some(pattern => c.includes(pattern));
}

export const chatUIController = {
    init() {
        const sendBtn = document.getElementById("send-btn");
        const promptInput = document.getElementById("prompt-input");
        const attachBtn = document.getElementById("attach-btn");
        const fileInput = document.getElementById("attach-file-input");
        const scrollBtn = document.getElementById("scroll-to-bottom-btn");
        const chatContainer = document.getElementById("chat-container");

        attachBtn?.addEventListener("click", () => fileInput?.click());
        fileInput?.addEventListener("change", (e) => this.handleFileAttachments(e));
        
        promptInput?.addEventListener("input", () => {
            this.autoResizeTextarea(promptInput);
        });

        promptInput?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!isGenerating) this.sendMessage();
            }
        });

        sendBtn?.addEventListener("click", () => {
            if (isGenerating) this.abortGeneration();
            else this.sendMessage();
        });

        document.getElementById("stop-gen-btn")?.addEventListener("click", () => this.abortGeneration());
        document.getElementById("new-chat-btn")?.addEventListener("click", () => this.newChat());
        document.getElementById("refresh-sessions-btn")?.addEventListener("click", () => this.loadSessionsList());

        chatContainer?.addEventListener("scroll", () => {
            const dist = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
            if (scrollBtn) scrollBtn.classList.toggle("hidden", dist <= 120);
        });
        scrollBtn?.addEventListener("click", () => this.scrollToBottom(true));

        eventBus.on("project.activated", (projectId) => {
            if (projectId) {
                localStorage.setItem("rf_active_project_id", projectId);
                this.loadSessionsList();
            }
        });
        eventBus.on("workspace:changed", () => this.loadSessionsList());

        eventBus.on("orchestrator.model_degraded", (data) => {
            showToast(`Model ${data.model_id} degraded. Switching candidate...`, "warning");
        });
        eventBus.on("orchestrator.billing_error", (data) => {
            showToast(`Provider quota/billing error on ${data.provider}. Key update required.`, "error");
        });
        eventBus.on("orchestrator.provider_rate_limited", (data) => {
            showToast(`Provider ${data.provider} rate limited. Rotating...`, "warning");
        });
    },

    autoResizeTextarea(el) {
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 250)}px`;
    },

    getUserAvatarInfo() {
        let avatarUrl = localStorage.getItem("rf_user_avatar") || "";
        let userEmail = localStorage.getItem("rf_user_email") || "";
        if (!avatarUrl || !userEmail) {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            if (token) {
                try {
                    const payload = JSON.parse(atob(token.split(".")[1]));
                    if (payload.avatar) {
                        avatarUrl = payload.avatar;
                        localStorage.setItem("rf_user_avatar", avatarUrl);
                    }
                    if (payload.email) {
                        userEmail = payload.email;
                        localStorage.setItem("rf_user_email", userEmail);
                    }
                } catch (e) {}
            }
        }
        return { avatarUrl, userEmail: userEmail || "User" };
    },

    getActiveProjectId() {
        return localStorage.getItem("rf_active_project_id") || "";
    },

    startExecutionTimer(placeholderMsgId) {
        this.stopExecutionTimer();
        elapsedSeconds = 0;
        executionTimer = setInterval(() => {
            elapsedSeconds++;
            if (placeholderMsgId) {
                const card = document.querySelector(`[data-message-id="${placeholderMsgId}"]`);
                const timerEl = card?.querySelector(".live-exec-timer");
                if (timerEl) timerEl.textContent = `${elapsedSeconds}s`;
            }
        }, 1000);
    },

    stopExecutionTimer() {
        if (executionTimer) {
            clearInterval(executionTimer);
            executionTimer = null;
        }
    },

    async getEnabledModelsList() {
        const allowFree = localStorage.getItem("rf_filter_tier_free") !== "false";
        const allowPro = localStorage.getItem("rf_filter_tier_pro") !== "false";

        const enabled = [];
        let hasAnySavedConfig = false;
        try {
            const data = await keysApi.getSelectedModels();
            const selectedMap = data.selected_models || {};
            Object.entries(selectedMap).forEach(([p, modelIds]) => {
                const isFreeProv = FREE_PROVIDERS_SET.has(p);
                if (!allowFree && isFreeProv) return;
                if (!allowPro && !isFreeProv) return;
                if (Array.isArray(modelIds) && modelIds.length > 0) {
                    hasAnySavedConfig = true;
                    enabled.push(...modelIds);
                }
            });
        } catch (e) {
            console.warn("Failed to get enabled models list:", e);
        }
        return hasAnySavedConfig ? enabled : null;
    },

    getATMModels() {
        return {
            architect: document.getElementById("atm-architect-select")?.value || null,
            engineer: document.getElementById("atm-engineer-select")?.value || null,
            designer: document.getElementById("atm-designer-select")?.value || null,
            tester: document.getElementById("atm-tester-select")?.value || null,
            critic: document.getElementById("atm-critic-select")?.value || null,
        };
    },

    setOrchestratorProgress(percent) {
        const bar = document.getElementById("orchestrator-progress-bar");
        if (bar) bar.style.width = `${percent}%`;
    },

    handleFileAttachments(e) {
        const files = Array.from(e.target.files || []);
        files.forEach((file) => {
            const reader = new FileReader();
            reader.onload = (event) => {
                attachedFiles.push({ name: file.name, content: event.target.result });
                this.renderAttachedContextBar();
            };
            reader.readAsText(file);
        });
        e.target.value = "";
    },

    renderAttachedContextBar() {
        const bar = document.getElementById("attached-context-bar");
        if (!bar) return;
        if (!attachedFiles.length) {
            bar.classList.add("hidden");
            bar.innerHTML = "";
            return;
        }
        bar.classList.remove("hidden");
        bar.innerHTML = attachedFiles
            .map(
                (f, idx) => `
            <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[var(--ide-elevated)] border border-[var(--ide-border-subtle)] text-[11px] font-mono text-[var(--ide-accent)]">
                <i data-lucide="file-text" class="w-3 h-3"></i>
                <span class="truncate max-w-[140px]">${f.name}</span>
                <button class="remove-attachment-btn text-[var(--ide-text-muted)] hover:text-red-400 cursor-pointer ml-1" data-index="${idx}"><i data-lucide="x" class="w-3 h-3"></i></button>
            </div>`
            )
            .join("");
        if (window.lucide) window.lucide.createIcons({ root: bar });
        bar.querySelectorAll(".remove-attachment-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                attachedFiles.splice(parseInt(btn.dataset.index, 10), 1);
                this.renderAttachedContextBar();
            });
        });
    },

    setGeneratingState(active) {
        isGenerating = active;
        const sendBtn = document.getElementById("send-btn");
        const stopBtn = document.getElementById("stop-gen-btn");
        const statusBadge = document.getElementById("orchestrator-status-badge");

        if (active) {
            if (sendBtn) {
                sendBtn.className = "bg-red-500 hover:bg-red-600 text-white w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer shadow-lg";
                sendBtn.innerHTML = `<i data-lucide="square" class="w-4 h-4"></i>`;
                sendBtn.title = "Stop Generation";
            }
            if (stopBtn) stopBtn.classList.remove("hidden");
            if (statusBadge) statusBadge.classList.remove("hidden");
        } else {
            this.stopExecutionTimer();
            if (sendBtn) {
                sendBtn.className = "bg-[var(--ide-accent)] hover:bg-[var(--ide-accent-hover)] text-white w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer";
                sendBtn.innerHTML = `<i data-lucide="arrow-up" class="w-4 h-4"></i>`;
                sendBtn.title = "Send Message";
            }
            if (stopBtn) stopBtn.classList.add("hidden");
            if (statusBadge) statusBadge.classList.add("hidden");
            setTimeout(() => this.setOrchestratorProgress(0), 1000);
        }
        if (window.lucide) window.lucide.createIcons({ root: sendBtn });
    },

    abortGeneration() {
        userAbortedGeneration = true;
        generationFinalized = true;
        if (wsClient) {
            wsClient.abort();
            wsClient.close();
            wsClient = null;
        }
        this.stopExecutionTimer();
        showToast("Generation aborted", "info");
        this.setGeneratingState(false);
    },

    scrollToBottom(smooth = false) {
        const chatContainer = document.getElementById("chat-container");
        if (chatContainer) chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    },

    async loadSessionsList() {
        const container = document.getElementById("sessions-list");
        if (!container) return;
        try {
            const activeProjectId = this.getActiveProjectId();
            const data = await sessionsApi.list(activeProjectId);
            let sessions = data.sessions || [];
            if (!sessions.length) {
                container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-4">No sessions for this project</div>';
                return;
            }

            container.innerHTML = sessions
                .map((s) => {
                    const isActive = s.id === currentSessionId;
                    const borderStyle = isActive ? "border: 1px solid var(--ide-accent) !important;" : "border: 1px solid var(--ide-border-subtle) !important;";
                    const bgStyle = isActive ? "background: rgba(7, 247, 122, 0.08) !important;" : "background: var(--ide-elevated) !important;";
                    return `
                <div class="session-item flex items-center justify-between w-full gap-2 p-2 mb-1 rounded-lg transition-colors cursor-pointer" style="${borderStyle} ${bgStyle}" data-id="${s.id}">
                    <div class="flex items-center gap-1.5 min-w-0 flex-1">
                        <span class="session-title text-left whitespace-nowrap overflow-hidden text-ellipsis text-xs font-medium text-[var(--ide-text-primary)]" title="${s.title}">${s.title || "New Chat"}</span>
                    </div>
                    <div class="flex items-center gap-1 shrink-0">
                        <button class="edit-session-btn text-[var(--ide-text-muted)] hover:text-emerald-400 p-1 rounded-md cursor-pointer" data-id="${s.id}" data-title="${s.title || ""}" title="Rename">
                            <i data-lucide="pencil" class="w-3.5 h-3.5"></i>
                        </button>
                        <button class="delete-session-btn text-[var(--ide-text-muted)] hover:text-red-400 p-1 rounded-md cursor-pointer" data-id="${s.id}" title="Delete">
                            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                        </button>
                    </div>
                </div>`;
                })
                .join("");

            if (window.lucide) window.lucide.createIcons({ root: container });

            container.querySelectorAll(".session-item").forEach((item) => {
                item.addEventListener("click", (e) => {
                    if (e.target.closest(".delete-session-btn") || e.target.closest(".edit-session-btn")) return;
                    this.openSession(item.dataset.id);
                });
            });

            container.querySelectorAll(".edit-session-btn").forEach((btn) => {
                btn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    const newTitle = await showPrompt("Rename Session", "", btn.dataset.title || "", "Save", "Cancel");
                    if (newTitle && newTitle.trim()) {
                        await sessionsApi.create(newTitle.trim(), btn.dataset.id);
                        showToast("Session renamed", "success");
                        this.loadSessionsList();
                    }
                });
            });

            container.querySelectorAll(".delete-session-btn").forEach((btn) => {
                btn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    const confirmed = await showConfirm("Delete Session", "Delete this chat?", "Delete", "Cancel");
                    if (confirmed) {
                        await sessionsApi.delete(btn.dataset.id);
                        showToast("Session deleted", "info");
                        if (currentSessionId === btn.dataset.id) this.newChat();
                        else this.loadSessionsList();
                    }
                });
            });

            if (!currentSessionId && sessions.length > 0) {
                const savedSessionId = localStorage.getItem(`rf_last_session_${activeProjectId}`);
                const targetSession = sessions.find(s => s.id === savedSessionId) || sessions[0];
                if (targetSession) {
                    this.openSession(targetSession.id);
                }
            }

        } catch (e) {
            container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-2">Failed to load sessions</div>';
        }
    },

    async openSession(sessionId) {
        if (isGenerating) this.abortGeneration();
        currentSessionId = sessionId;
        isFirstMessageOfSession = false;
        
        const activeProjectId = this.getActiveProjectId();
        if (activeProjectId) {
            localStorage.setItem(`rf_last_session_${activeProjectId}`, sessionId);
        }

        eventBus.emit("session:selected", sessionId);
        const chatHistory = document.getElementById("chat-history");
        const traceLog = document.getElementById("debug-trace-log");
        const toolsList = document.getElementById("active-tools-list");
        if (chatHistory) chatHistory.innerHTML = "";
        if (traceLog) traceLog.innerHTML = "";
        if (toolsList) toolsList.innerHTML = "";
        try {
            await terminalUIController.setSession(sessionId);
            const data = await sessionsApi.messages(sessionId);
            (data.messages || []).forEach((m) => this.appendMessage(m.role, m.content, m.id));
            const traceData = await sessionsApi.traces(sessionId).catch(() => ({ traces: [] }));
            (traceData.traces || []).forEach((t) => this.renderTraceEntry(t.badge, t.text, t.timestamp));
            const toolData = await sessionsApi.tools(sessionId).catch(() => ({ tools: [] }));
            (toolData.tools || []).forEach((tl) => this.appendActiveTool(tl.tool_id, tl.tool_name, tl.status));
            
            document.querySelectorAll(".session-item").forEach(el => {
                const isThis = el.dataset.id === sessionId;
                el.style.border = isThis ? "1px solid var(--ide-accent) !important" : "1px solid var(--ide-border-subtle) !important";
                el.style.background = isThis ? "rgba(7, 247, 122, 0.08) !important" : "var(--ide-elevated) !important";
            });
        } catch (e) {
            showToast("Failed to load session history", "error");
        }
    },

    async newChat(silent = false) {
        if (isGenerating) this.abortGeneration();
        currentSessionId = `session-${Date.now()}`;
        fullResponseText = "";
        fullReasoningText = "";
        attachedFiles = [];
        isFirstMessageOfSession = true;
        currentPendingMessageId = null;

        const activeProjectId = this.getActiveProjectId();
        if (activeProjectId) {
            localStorage.setItem(`rf_last_session_${activeProjectId}`, currentSessionId);
            try {
                await sessionsApi.create("New Chat", currentSessionId, activeProjectId);
                await this.loadSessionsList();
            } catch (e) {
                console.warn("Failed to create initial session entry:", e);
            }
        }

        this.renderAttachedContextBar();
        terminalUIController.clear();
        terminalUIController.setSession(currentSessionId);
        eventBus.emit("session:selected", currentSessionId);
        const chatHistory = document.getElementById("chat-history");
        const traceLog = document.getElementById("debug-trace-log");
        const toolsList = document.getElementById("active-tools-list");
        if (chatHistory) chatHistory.innerHTML = "";
        if (traceLog) traceLog.innerHTML = "";
        if (toolsList) toolsList.innerHTML = "";
        this.setOrchestratorProgress(0);
        if (!silent) showToast("New chat started", "info");
    },

    async triggerSmartAutoTitling(userPrompt) {
        try {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            const activeProjectId = this.getActiveProjectId();
            const res = await fetch("/api/v1/sessions/auto-title", {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ 
                    text: userPrompt, 
                    session_id: currentSessionId,
                    project_id: activeProjectId
                }),
            });
            const data = await res.json();
            const smartTitle = data.title || "Code Analysis";
            
            const activeItem = document.querySelector(`.session-item[data-id="${currentSessionId}"] .session-title`);
            if (activeItem) {
                activeItem.textContent = smartTitle;
                activeItem.title = smartTitle;
            }
            
            this.loadSessionsList();
        } catch (e) {
            console.debug("Smart auto-titling warning:", e);
        }
    },

    async sendMessage(overrideText = null, isEditing = false) {
        if (isGenerating && overrideText === null) return;
        const input = document.getElementById("prompt-input");
        const rawUserPrompt = overrideText !== null ? overrideText : input?.value.trim() || "";
        if (!rawUserPrompt && !attachedFiles.length) return;
        lastUserPrompt = rawUserPrompt;

        let agentPayloadPrompt = rawUserPrompt;
        if (attachedFiles.length) {
            const fileContexts = attachedFiles.map((f) => `### Attached File: ${f.name}\n\`\`\`\n${f.content}\n\`\`\``).join("\n");
            agentPayloadPrompt = rawUserPrompt ? `${fileContexts}\n\n${rawUserPrompt}` : fileContexts;
            attachedFiles = [];
            this.renderAttachedContextBar();
        }
        if (input && overrideText === null) {
            input.value = "";
            this.autoResizeTextarea(input);
        }

        if (!isEditing) this.appendMessage("user", rawUserPrompt);

        currentPendingMessageId = `msg-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
        const requestPendingId = currentPendingMessageId;
        pendingStreamError = "";
        generationFinalized = false;
        userAbortedGeneration = false;
        const assistantContentDiv = this.appendMessage("assistant", "", currentPendingMessageId);

        this.startExecutionTimer(currentPendingMessageId);
        fullResponseText = "";
        fullReasoningText = "";
        currentPhaseLabel = "Routing task...";
        currentAgentRole = "Agent";
        assistantContentDiv.parentElement?.classList.add("assistant-bubble-generating");
        this.setGeneratingState(true);
        this.renderAssistantBubble(assistantContentDiv, fullResponseText, fullReasoningText);
        this.setOrchestratorProgress(15);

        if (isFirstMessageOfSession) {
            isFirstMessageOfSession = false;
            this.triggerSmartAutoTitling(rawUserPrompt);
        }

        if (wsClient) {
            wsClient.close();
            wsClient = null;
        }
        wsClient = new ChatWSClient(currentSessionId, {
            onEvent: (event) => {
                if (requestPendingId !== currentPendingMessageId) return;
                this.handleStreamEvent(event, requestPendingId);
            },
            onError: (err) => {
                if (requestPendingId !== currentPendingMessageId) return;
                // Wait for the terminal close/error outcome; transient transport errors are not final.
                pendingStreamError = err?.message || "WebSocket transport error.";
            },
            onClose: (closeEvent) => {
                if (requestPendingId !== currentPendingMessageId || generationFinalized || userAbortedGeneration) return;
                generationFinalized = true;
                const targetDiv = this.getPendingMessageContentDiv(requestPendingId);
                const closeDetails = closeEvent?.reason
                    ? "WebSocket closed (code " + (closeEvent.code || "unknown") + "): " + closeEvent.reason
                    : "WebSocket closed (code " + (closeEvent?.code || "unknown") + ").";
                const errorText = pendingStreamError
                    ? "The connection ended before a final answer was received.\n" + pendingStreamError + "\n" + closeDetails
                    : "Connection closed before the final answer was received.\n" + closeDetails;
                targetDiv?.parentElement?.classList.remove("assistant-bubble-generating");
                this.setGeneratingState(false);
                if (targetDiv) {
                    const details = fullResponseText
                        ? errorText + "\n\nPartial response:\n" + fullResponseText
                        : errorText;
                    this.renderErrorBox(targetDiv, details);
                }
            },
        });

        try {
            await wsClient.connect();
            const strategy = document.getElementById("strategy-select")?.value || "auto";
            const modelLock = strategy === "manual" ? (document.getElementById("model-lock-select")?.value || null) : null;
            const explicitEnabled = await this.getEnabledModelsList();
            const atmModels = this.getATMModels();
            wsClient.send(agentPayloadPrompt, {
                strategy,
                model_lock: modelLock,
                enabled_models: explicitEnabled,
                atm_architect_model: atmModels.architect,
                atm_engineer_model: atmModels.engineer,
                atm_designer_model: atmModels.designer,
                atm_tester_model: atmModels.tester,
                atm_critic_model: atmModels.critic,
            });
        } catch (err) {
            if (requestPendingId !== currentPendingMessageId || generationFinalized) return;
            generationFinalized = true;
            const targetDiv = this.getPendingMessageContentDiv(requestPendingId);
            this.renderErrorBox(targetDiv, err.message || "Failed to establish WebSocket connection.");
            targetDiv?.parentElement?.classList.remove("assistant-bubble-generating");
            this.setGeneratingState(false);
        }
    },

    getPendingMessageContentDiv(pendingId) {
        if (!pendingId) return null;
        const msgCard = document.querySelector(`[data-message-id="${pendingId}"]`);
        if (!msgCard) return null;
        return msgCard.querySelector(".assistant-content-div") || msgCard.querySelector("div");
    },

    escapeHtml(str) {
        return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    },

    renderErrorBox(container, errText) {
        if (!container) return;
        container.innerHTML = '<div class="assistant-error-box p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 font-mono text-xs flex flex-col gap-2 my-2">' +
            '<div class="font-bold flex items-center gap-2 text-red-300"><i data-lucide="alert-octagon" class="w-4 h-4 text-red-400"></i>Generation Failed or Interrupted</div>' +
            '<div class="text-[11px] leading-relaxed text-red-300/90 whitespace-pre-wrap">' + this.escapeHtml(errText) + '</div>' +
            '<div class="pt-2 border-t border-red-500/20 flex flex-wrap justify-end items-center gap-2">' +
                '<button type="button" class="change-model-provider-btn px-3 py-1.5 rounded bg-[var(--ide-accent)] text-white font-bold text-[11px] hover:brightness-110 transition-colors inline-flex items-center gap-1.5 shadow-md"><i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i> Change model / provider</button>' +
                '<button type="button" class="send-error-report-btn px-3 py-1.5 rounded bg-red-500 text-white font-bold text-[11px] hover:bg-red-600 transition-colors inline-flex items-center gap-1.5 shadow-md"><i data-lucide="send" class="w-3.5 h-3.5"></i> Send to developer</button>' +
                '<span class="error-report-status text-[10px] text-[var(--ide-text-secondary)]" aria-live="polite"></span>' +
            '</div></div>';
        if (window.lucide) window.lucide.createIcons({ root: container });
        container.querySelector(".change-model-provider-btn")?.addEventListener("click", () => {
            const strategySelect = document.getElementById("strategy-select");
            if (strategySelect) {
                strategySelect.value = "manual";
                strategySelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
            document.getElementById("settings-manual-panel")?.scrollIntoView({ behavior: "smooth", block: "center" });
            document.getElementById("model-lock-trigger")?.click();
        });
        container.querySelector(".send-error-report-btn")?.addEventListener("click", (event) => {
            this.sendErrorReport(event.currentTarget, errText);
        });
    },

    async sendErrorReport(button, errText) {
        const box = button.closest(".assistant-error-box");
        const status = box?.querySelector(".error-report-status");
        const originalLabel = button.textContent.trim();
        button.disabled = true;
        button.textContent = "Sending...";
        if (status) status.textContent = "";
        try {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            if (!token) throw new Error("Authentication token is missing. Please sign in again.");
            const response = await fetch("https://runtimeforce.dev/api/v1/mail/report", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + token.replace(/^Bearer\s+/i, "")
                },
                body: JSON.stringify({
                    error: errText,
                    session_id: currentSessionId || "",
                    prompt: lastUserPrompt || "",
                    partial_response: fullResponseText || "",
                    model: currentAgentModel || "",
                    strategy: document.getElementById("strategy-select")?.value || "",
                    app_version: document.getElementById("active-project-ver-display")?.textContent?.trim() || "",
                    user_agent: navigator.userAgent || ""
                })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
            button.textContent = "Report sent";
            if (status) status.textContent = "Отчёт отправлен на errors@runtimeforce.dev";
        } catch (error) {
            button.disabled = false;
            button.textContent = originalLabel || "Send to developer";
            if (status) status.textContent = "Не удалось отправить: " + error.message;
        }
    },

    async handleStreamEvent(event, pendingId) {
        const assistantDiv = this.getPendingMessageContentDiv(pendingId);

        if (event.status === "phase" && event.label) {
            currentPhaseLabel = event.label;
            if (event.role) currentAgentRole = event.role;
            if (event.model) currentAgentModel = event.model;
            this.updateActiveRoleUI();
            this.appendTrace("PHASE", event.label);
            if (assistantDiv) this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
        } else if (event.status === "model_try") {
            pendingStreamError = "";
            const modelName = (event.model || "auto").split("/").pop();
            const providerName = event.provider || "auto";
            currentAgentModel = `${modelName} (${providerName})`;
            if (event.role) currentAgentRole = event.role;
            this.updateActiveRoleUI();
            this.appendTrace("TRY", `Attempting: ${modelName} (${providerName})`);
            currentPhaseLabel = `Processing with ${modelName}...`;
            if (assistantDiv) this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
            this.setOrchestratorProgress(40);
        } else if (event.status === "reasoning" && event.reasoning) {
            currentPhaseLabel = "Model is processing the request...";
            if (assistantDiv) {
                this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
                this.scrollToBottom();
            }
            this.setOrchestratorProgress(50);
        } else if (event.status === "streaming" && event.content) {
            pendingStreamError = "";
            currentPhaseLabel = "Generating response...";
            fullResponseText += event.content;
            if (assistantDiv) {
                this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
                this.scrollToBottom();
            }
            this.setOrchestratorProgress(75);
        } else if (event.status === "tool_start") {
            this.appendTrace("TOOL", `Running: ${event.tool_name}`);
            this.appendActiveTool(event.tool_id || `tool-${Date.now()}`, event.tool_name, "running");
            currentPhaseLabel = `Running tool: ${event.tool_name}...`;
            if (event.role) currentAgentRole = event.role;
            this.updateActiveRoleUI();

            // Intercept dangerous command according to Section 15.5
            try {
                const args = JSON.parse(event.arguments || "{}");
                if (event.tool_name === "execute_command" && args.command) {
                    const cmd = args.command;
                    if (isDangerousCommand(cmd) && !approvedCommandsCache.has(cmd)) {
                        const approvalRes = await showCommandApprovalModal(cmd, "Elevated / Destructive Operation");
                        if (!approvalRes.approved) {
                            showToast("Execution denied by user", "warning");
                            this.abortGeneration();
                            return;
                        }
                        if (approvalRes.duration === "always" || approvalRes.duration === "today") {
                            approvedCommandsCache.add(cmd);
                        }
                        if (approvalRes.password) {
                            args.password = approvalRes.password;
                            event.arguments = JSON.stringify(args);
                        }
                    }
                    terminalUIController.appendPromptLine(args.command, true);
                } else if (event.tool_name === "read_workspace_file") {
                    terminalUIController.appendPromptLine(`cat ${args.filepath || ''}`, true);
                } else if (event.tool_name === "write_workspace_file" || event.tool_name === "apply_code_patch") {
                    terminalUIController.appendPromptLine(`write ${args.filepath || ''}`, true);
                } else if (event.tool_name === "scan_workspace") {
                    terminalUIController.appendPromptLine(`find ${args.pattern || '**/*'}`, true);
                } else if (event.tool_name === "search_grep") {
                    terminalUIController.appendPromptLine(`grep -rn "${args.query || ''}"`, true);
                } else if (event.tool_name.startsWith("git_")) {
                    terminalUIController.appendPromptLine(`git ${event.tool_name.replace('git_', '')}`, true);
                }
            } catch (e) {}

            if (assistantDiv) this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
            this.setOrchestratorProgress(60);
        } else if (event.status === "tool_end") {
            this.appendTrace("DONE", `Completed: ${event.tool_name}`);
            this.updateActiveToolStatus(event.tool_id, event.tool_name, "success");

            try {
                const result = JSON.parse(event.result || "{}");
                if (event.tool_name === "execute_command") {
                    if (result.stdout) terminalUIController.appendOutput(result.stdout, "text-slate-200", true);
                    if (result.stderr) terminalUIController.appendOutput(result.stderr, "text-red-400", true);
                } else if (event.tool_name === "write_workspace_file" || event.tool_name === "apply_code_patch") {
                    debouncedTreeReload();
                    terminalUIController.appendOutput(`[✓ Saved: ${result.path || 'file'} (${result.bytes_written || 0} bytes)]`, "text-emerald-400", true);
                } else if (event.tool_name === "read_workspace_file") {
                    const charCount = (result.content || "").length;
                    terminalUIController.appendOutput(`[Read ${charCount} chars from ${result.path || 'file'}]`, "text-slate-400", true);
                } else if (event.tool_name === "scan_workspace") {
                    const count = result.count || (result.files || []).length;
                    terminalUIController.appendOutput(`[Found ${count} workspace files]`, "text-slate-400", true);
                } else if (event.tool_name === "search_grep") {
                    const count = result.count || (result.matches || []).length;
                    terminalUIController.appendOutput(`[Found ${count} code matches for "${result.query || ''}"]`, "text-slate-400", true);
                } else {
                    terminalUIController.appendOutput(`[${event.tool_name} completed]`, "text-slate-400", true);
                }
            } catch (e) {}

            this.setOrchestratorProgress(85);
        } else if (event.status === "aborted") {
            generationFinalized = true;
            userAbortedGeneration = true;
            currentPhaseLabel = "Stopped";
            this.appendTrace("ABORT", "Generation aborted by user");
            if (assistantDiv) {
                if (fullResponseText) this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
                else assistantDiv.textContent = "Generation stopped by user.";
            }
            assistantDiv?.parentElement?.classList.remove("assistant-bubble-generating");
            this.setGeneratingState(false);
        } else if (event.status === "error" || event.status === "failed") {
            currentPhaseLabel = "Request failed";
            pendingStreamError = event.error || "Execution error";
            this.appendTrace("ERROR", pendingStreamError);
            // A candidate may fail while orchestration is still trying another model.
            // Display the error only if the stream ends without a final answer.
        } else if (event.status === "done") {
            generationFinalized = true;
            assistantDiv?.parentElement?.classList.remove("assistant-bubble-generating");
            this.setGeneratingState(false);
            if (pendingStreamError || (!fullResponseText && !fullReasoningText)) {
                this.renderErrorBox(assistantDiv, pendingStreamError || "Generation completed without returning an answer.");
                return;
            }
            currentPhaseLabel = "Completed";
            this.setOrchestratorProgress(100);
            if (assistantDiv) this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
            this.loadSessionsList();
        }
    },

    updateActiveRoleUI() {
        const display = document.getElementById("current-model-display");
        if (display) {
            const roleClass = `agent-role-${currentAgentRole.toLowerCase()}`;
            display.innerHTML = `<span class="agent-role-badge ${roleClass}">${currentAgentRole}</span> <span class="font-mono text-[var(--ide-text-primary)]">${currentAgentModel || 'Auto'}</span>`;
        }
    },

    renderAssistantBubble(container, responseText, reasoningText) {
        if (!container) return;
        let textToRender = responseText || "";
        // Keep hidden model reasoning private; show operational phases below instead.
        textToRender = textToRender
            .replace(/<think>[\s\S]*?<\/think>/gi, "")
            .replace(/<think>[\s\S]*$/gi, "")
            .trim();

        const isBusy = isGenerating && container.parentElement?.classList.contains("assistant-bubble-generating");

        let html = `
<div class="assistant-status-compact inline-flex items-center gap-2 text-xs font-mono p-1.5 px-2.5 bg-[var(--ide-elevated)] rounded-lg border border-[var(--ide-border-subtle)] mb-2 mr-2 float-left select-none">
    <div class="ai-thinking-indicator ${isBusy ? 'active' : ''} flex items-center justify-center">
        <div class="ai-thinking-orbit"></div>
        <img
            src="/static/animated-spin.png"
            class="ai-thinking-logo w-4 h-4"
            alt="AI"
        />
    </div>
    <span class="live-phase-label text-[10px] text-[var(--ide-text-secondary)] truncate max-w-[260px]">${this.escapeHtml(currentPhaseLabel || "Processing request...")}</span>
    <span class="live-exec-timer font-bold text-[var(--ide-accent)] ml-auto font-mono text-[10px]">
        ${elapsedSeconds ? elapsedSeconds + 's' : ''}
    </span>
</div>`;

        if (textToRender) {
            const parsedText = window.marked ? window.marked.parse(textToRender) : textToRender;
            html += parsedText;
        }

        container.innerHTML = html;

        container.querySelectorAll("pre").forEach((preBlock) => {
            if (!preBlock.querySelector(".code-copy-btn")) {
                preBlock.style.position = "relative";
                const copyBtn = document.createElement("button");
                copyBtn.className = "code-copy-btn text-[10px] px-2 py-1 rounded bg-[var(--ide-surface)] border border-[var(--ide-border-subtle)] text-[var(--ide-text-secondary)] hover:text-emerald-400 transition-colors absolute top-2 right-2 cursor-pointer";
                copyBtn.innerHTML = `<i data-lucide="copy" class="w-3.5 h-3.5"></i>`;
                copyBtn.addEventListener("click", () => {
                    const code = preBlock.querySelector("code")?.innerText || preBlock.innerText;
                    navigator.clipboard.writeText(code);
                    showToast("Code copied", "success");
                });
                preBlock.appendChild(copyBtn);
                if (window.lucide) window.lucide.createIcons({ root: copyBtn });
            }
        });
    },

    appendActiveTool(toolId, toolName, status) {
        const container = document.getElementById("active-tools-list");
        if (!container) return;
        let existing = container.querySelector(`[data-tool-id="${toolId}"]`);
        if (!existing) {
            existing = document.createElement("div");
            existing.dataset.toolId = toolId;
            existing.className = "flex items-center justify-between p-1.5 border-b border-[var(--ide-border-subtle)] text-[10px]";
            container.appendChild(existing);
        }
        const isRunning = status === "running";
        const textColor = isRunning ? "text-amber-400" : "text-emerald-400";
        const time = new Date().toLocaleTimeString();
        const checkmarkHTML = !isRunning && status === "success" ? `<span class="text-emerald-400 font-bold mr-1">&#10004;</span>` : "";
        existing.innerHTML = `
            <div class="flex items-center min-w-0 flex-1">
                ${checkmarkHTML}
                <span class="truncate ${textColor} font-mono font-medium">${toolName}</span>
            </div>
            <span class="text-[var(--ide-text-muted)] text-[9px] shrink-0 ml-2">${time}</span>`;
        container.scrollTop = container.scrollHeight;
    },

    updateActiveToolStatus(toolId, toolName, status) {
        this.appendActiveTool(toolId || `tool-${Date.now()}`, toolName, status);
    },

    appendTrace(badge, text) {
        this.renderTraceEntry(badge, text, new Date().toISOString());
    },

    renderTraceEntry(badge, text, isoTimestamp) {
        const log = document.getElementById("debug-trace-log");
        if (!log) return;
        const time = isoTimestamp ? new Date(isoTimestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
        let badgeBg = "bg-amber-500/20";
        let textColor = "text-amber-400";
        if (badge === "ERROR" || badge === "FAILED") {
            badgeBg = "bg-red-500/20";
            textColor = "text-red-400";
        } else if (badge === "DONE" || badge === "SUCCESS") {
            badgeBg = "bg-emerald-500/20";
            textColor = "text-emerald-400";
        }
        const entry = document.createElement("div");
        entry.className = "flex items-center gap-2 text-[10px] py-1 border-b border-[var(--ide-border-subtle)]";
        entry.innerHTML = `
            <span class="px-1.5 py-0.5 rounded ${badgeBg} ${textColor} font-bold uppercase shrink-0">${badge}</span>
            <span class="truncate flex-1 ${textColor} font-medium">${text}</span>
            <span class="text-[var(--ide-text-muted)] text-[9px] shrink-0">${time}</span>`;
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight;
    },

    appendMessage(role, rawText, msgId = null) {
        const history = document.getElementById("chat-history");
        if (!history) return null;
        const msgWrapper = document.createElement("div");
        const isUser = role === "user";
        
        const messageId = msgId || (isUser ? `user-${Date.now()}` : `asst-${Date.now()}`);
        msgWrapper.dataset.messageId = messageId;
        msgWrapper.className = `p-3 rounded-xl max-w-[90%] text-[0.80rem] leading-relaxed flex flex-col gap-2 relative ${isUser ? "bg-[var(--ide-elevated-2)] self-end border-r-2 border-[var(--ide-accent)]" : "bg-[var(--ide-elevated)] self-start border-l-2 border-[var(--ide-accent)]"}`;

        if (isUser) {
            const { avatarUrl, userEmail } = this.getUserAvatarInfo();
            const userHeader = document.createElement("div");
            userHeader.className = "user-avatar-header flex items-center justify-end mb-1 pb-1 border-b border-[var(--ide-border-subtle)]";
            
            const avatarHtml = avatarUrl
                ? `<img src="${this.escapeHtml(avatarUrl)}" class="w-5 h-5 rounded-full object-cover border border-[var(--ide-accent)]" alt="User Avatar" />`
                : `<div class="w-5 h-5 rounded-full bg-[var(--ide-accent)] text-black font-bold flex items-center justify-center text-[10px]">${this.escapeHtml(userEmail.charAt(0).toUpperCase())}</div>`;

            userHeader.innerHTML = avatarHtml;
            msgWrapper.appendChild(userHeader);
        }

        const contentDiv = document.createElement("div");
        contentDiv.className = isUser ? "user-content-div" : "assistant-content-div";
        
        if (isUser) {
            contentDiv.innerHTML = window.marked ? window.marked.parse(rawText) : rawText;
        } else {
            this.renderAssistantBubble(contentDiv, rawText, "");
        }
        msgWrapper.appendChild(contentDiv);

        const actionsBar = document.createElement("div");
        actionsBar.className = `flex items-center gap-2 pt-1 border-t border-[var(--ide-border-subtle)] text-[10px] opacity-70 hover:opacity-100 transition-opacity ${isUser ? "justify-end" : "justify-start"}`;

        if (isUser) {
            actionsBar.innerHTML = `
                <button class="copy-msg-btn hover:text-emerald-400 p-1 cursor-pointer" title="Copy"><i data-lucide="copy" class="w-3.5 h-3.5"></i></button>
                <button class="edit-msg-btn hover:text-emerald-400 p-1 cursor-pointer" title="Edit"><i data-lucide="pencil" class="w-3.5 h-3.5"></i></button>
                <button class="delete-msg-btn hover:text-red-400 p-1 cursor-pointer" title="Delete"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>`;
            actionsBar.querySelector(".copy-msg-btn")?.addEventListener("click", () => {
                navigator.clipboard.writeText(contentDiv.innerText || rawText);
                showToast("Copied", "success");
            });
            actionsBar.querySelector(".edit-msg-btn")?.addEventListener("click", async () => {
                const edited = await showMultiLinePrompt("Edit Prompt", "", rawText, "Resend", "Cancel");
                if (edited && edited.trim() && messageId) {
                    const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
                    await fetch(`/api/v1/messages/${messageId}/truncate-from`, { 
                        method: "POST", 
                        headers: { Authorization: `Bearer ${token}` } 
                    });
                    await this.openSession(currentSessionId);
                    this.sendMessage(edited.trim(), false);
                }
            });
            actionsBar.querySelector(".delete-msg-btn")?.addEventListener("click", async () => {
                const confirmed = await showConfirm("Delete Message", "Delete this and subsequent messages?", "Delete", "Cancel");
                if (confirmed && messageId) {
                    const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
                    await fetch(`/api/v1/messages/${messageId}/truncate-from`, { 
                        method: "POST", 
                        headers: { Authorization: `Bearer ${token}` } 
                    });
                    await this.openSession(currentSessionId);
                }
            });
        } else {
            actionsBar.innerHTML = `
                <button class="copy-msg-btn hover:text-emerald-400 p-1 cursor-pointer" title="Copy"><i data-lucide="copy" class="w-3.5 h-3.5"></i></button>
                <button class="retry-msg-btn hover:text-emerald-400 p-1 cursor-pointer" title="Regenerate"><i data-lucide="rotate-cw" class="w-3.5 h-3.5"></i></button>`;
            actionsBar.querySelector(".copy-msg-btn")?.addEventListener("click", () => {
                navigator.clipboard.writeText(contentDiv.innerText || rawText);
                showToast("Copied", "success");
            });
            actionsBar.querySelector(".retry-msg-btn")?.addEventListener("click", () => {
                if (lastUserPrompt) {
                    showToast("Regenerating...", "info");
                    this.sendMessage(lastUserPrompt);
                }
            });
        }
        msgWrapper.appendChild(actionsBar);
        if (window.lucide) window.lucide.createIcons({ root: actionsBar });
        history.appendChild(msgWrapper);
        this.scrollToBottom(true);
        return contentDiv;
    },
};
