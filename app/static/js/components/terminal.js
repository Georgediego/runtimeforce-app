/**
 * Terminal UI Controller with Real-Time Agent Execution Stream & Persistent Storage.
 */
import { workspacesApi, sessionsApi, approvalsApi, projectsApi } from "../core/api_http_client.js";
import { showCommandApprovalModal, showToast } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

let currentSessionId = null;
let saveQueue = [];
let isSaving = false;
let terminalIdentity = { username: "user", hostname: "localhost" };
let terminalIdentityPromise = Promise.resolve();
let approvalPollTimer = null;
let approvalPollRunning = false;
let approvalDialogOpen = false;
const activeApprovalDialogs = new Set();

async function flushSaveQueue() {
    if (isSaving || !currentSessionId || saveQueue.length === 0) return;
    isSaving = true;
    const entry = saveQueue.shift();
    try {
        await sessionsApi.saveTerminalEntry(currentSessionId, entry.type, entry.content);
    } catch (e) {
        console.warn("Failed to persist terminal entry:", e);
    } finally {
        isSaving = false;
        if (saveQueue.length > 0) flushSaveQueue();
    }
}

function queueSave(entryType, content) {
    if (!currentSessionId || !content) return;
    saveQueue.push({ type: entryType, content });
    flushSaveQueue();
}

export const terminalUIController = {
    init() {
        if (!approvalPollTimer) {
            approvalPollTimer = setInterval(() => this.pollCommandApprovals(), 700);
            this.pollCommandApprovals();
        }
        terminalIdentityPromise = workspacesApi.environment().then((environment) => {
            terminalIdentity = {
                username: environment.username || "user",
                hostname: environment.hostname || "localhost",
            };
        }).catch((error) => console.warn("Could not detect terminal identity:", error));
        const cmdInput = document.getElementById("terminal-cmd-input");
        cmdInput?.addEventListener("keydown", async (e) => {
            if (e.key === "Enter") {
                const cmd = cmdInput.value.trim();
                if (!cmd) return;
                cmdInput.value = "";
                await terminalIdentityPromise;
                this.appendPromptLine(cmd, true);
                try {
                    const activeProjectId = localStorage.getItem("rf_active_project_id") || "";
                    const res = await workspacesApi.execute(cmd, null, null, activeProjectId, currentSessionId);
                    if (res.stdout) {
                        this.appendOutput(res.stdout, "text-slate-200", true);
                    }
                    if (res.stderr) {
                        this.appendOutput(res.stderr, "text-red-400", true);
                    }
                } catch (err) {
                    const errText = `Error: ${err.message}\n`;
                    this.appendOutput(errText, "text-red-400", true);
                }
            }
        });

        eventBus.on("session:selected", (sessionId) => {
            if (sessionId) this.setSession(sessionId);
        });
        eventBus.on("session.activated", (sessionId) => {
            if (sessionId) this.setSession(sessionId);
        });
        eventBus.on("terminal:write", ({ type, content }) => {
            this.appendOutput(content, type === "stderr" ? "text-red-400" : "text-slate-200", true);
        });
        
        eventBus.on("terminal.agent_output", (data) => {
            if (data && data.session_id === currentSessionId) {
                if (data.command) {
                    this.appendPromptLine(`[AGENT] ${data.command}`, false);
                }
                if (data.output) {
                    const styleClass = data.exit_code === 0 ? "text-emerald-300" : "text-red-400";
                    this.appendOutput(data.output, styleClass, false);
                }
            }
        });
    },

    async pollCommandApprovals() {
        if (approvalPollRunning || approvalDialogOpen) return;
        approvalPollRunning = true;
        try {
            const data = await approvalsApi.pending();
            for (const item of (data.pending || [])) {
                if (approvalDialogOpen || activeApprovalDialogs.has(item.pending_id)) break;
                activeApprovalDialogs.add(item.pending_id);
                approvalDialogOpen = true;
                (async () => {
                    try {
                        const [projectData, workspaceData] = await Promise.all([
                            projectsApi.list().catch(() => ({ projects: [] })),
                            workspacesApi.list(item.project_id || null).catch(() => ({ workspaces: [] })),
                        ]);
                        const projectList = Array.isArray(projectData) ? projectData : (projectData.projects || []);
                        const workspaceList = Array.isArray(workspaceData) ? workspaceData : (workspaceData.workspaces || []);
                        const projectName = projectList.find((project) => String(project.id) === String(item.project_id))?.name || (item.project_id ? "Project" : "");
                        const workspaceName = workspaceList.find((workspace) => String(workspace.id) === String(item.workspace_id))?.name || (item.workspace_id ? "Workspace" : "");
                        const context = [
                            `Target: ${item.target || "local"}`,
                            workspaceName ? `Workspace: ${workspaceName}` : "",
                            projectName ? `Project: ${projectName}` : "",
                            item.cwd ? `Working directory: ${item.cwd}` : "",
                            item.session_id ? "Session: active" : "",
                        ].filter(Boolean).join(" · ");
                        const choice = await showCommandApprovalModal(item.command, context, {
                            sessionAvailable: !!item.session_id,
                            workspaceAvailable: !!item.workspace_id,
                            projectAvailable: !!item.project_id,
                        });
                        await approvalsApi.decide(item.pending_id, choice || "deny");
                        if (choice === "deny") showToast("Команда отклонена и не была выполнена", "warning");
                    } catch (error) {
                        console.error("Command approval decision failed:", error);
                        showToast(`Не удалось отправить решение: ${error.message}`, "error");
                    } finally {
                        activeApprovalDialogs.delete(item.pending_id);
                        approvalDialogOpen = false;
                    }
                })();
                break;
            }
        } catch (error) {
            // Authentication may not be ready during initial page load.
        } finally {
            approvalPollRunning = false;
        }
    },

    async setSession(sessionId) {
        currentSessionId = sessionId;
        saveQueue = [];
        isSaving = false;
        await terminalIdentityPromise;
        await this.restoreHistory();
    },

    async restoreHistory() {
        const output = document.getElementById("terminal-output");
        if (!output || !currentSessionId) return;
        output.innerHTML = "";
        try {
            const data = await sessionsApi.terminal(currentSessionId);
            const entries = data.terminal || [];
            for (const entry of entries) {
                if (entry.entry_type === "input") {
                    this.appendPromptLine(entry.content.replace(/^\$ /, ""), false);
                } else if (entry.entry_type === "stdout") {
                    this.appendOutput(entry.content, "text-slate-200", false);
                } else if (entry.entry_type === "stderr") {
                    this.appendOutput(entry.content, "text-red-400", false);
                } else if (entry.entry_type === "system") {
                    this.appendOutput(entry.content, "text-cyan-400", false);
                }
            }
        } catch (e) {
            console.warn("Failed to restore terminal history:", e);
        }
    },

    appendPromptLine(cmd, persist = true) {
        const output = document.getElementById("terminal-output");
        if (!output) return;
        const line = document.createElement("div");
        line.className = "flex items-center gap-2 py-0.5 font-mono text-xs";
        const safeCmd = String(cmd || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        const safeUser = String(terminalIdentity.username || "user").replace(/[&<>"]/g, "");
        const safeHost = String(terminalIdentity.hostname || "localhost").replace(/[&<>"]/g, "");
        line.innerHTML =
            `<span class="text-[#07f77a] font-bold shrink-0">${safeUser}@${safeHost}:~$</span> ` +
            `<span class="text-white truncate font-bold">${safeCmd}</span>`;
        output.appendChild(line);
        output.scrollTop = output.scrollHeight;
        if (persist) queueSave("input", `$ ${cmd}`);
    },

    appendOutput(text, className = "text-slate-300", persist = true) {
        const output = document.getElementById("terminal-output");
        if (!output) return;
        const div = document.createElement("div");
        div.className = `font-mono text-xs leading-relaxed whitespace-pre-wrap ${className}`;
        div.textContent = text;
        output.appendChild(div);
        output.scrollTop = output.scrollHeight;
        if (persist) {
            const entryType = className.includes("red") ? "stderr" : "stdout";
            queueSave(entryType, text);
        }
    },

    clear() {
        const output = document.getElementById("terminal-output");
        if (output) output.innerHTML = "";
    },
};
