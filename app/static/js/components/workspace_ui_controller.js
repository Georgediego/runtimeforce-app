/**
 * Workspace Management UI Controller with Strict Active Project Scope.
 * PATCHED: workspace list is now scoped to the project being EDITED in the
 * Project Settings modal (via setActiveEditingProject), not just the globally
 * active project from localStorage — prevents "all workspaces shown" leaks
 * when editing a project that is not currently active.
 */
import { workspacesApi } from "../core/api_http_client.js";
import { planAccessState } from "../core/plan_access_state.js";
import { showToast, showConfirm } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

let editingProjectId = null;

function resolveScopedProjectId(explicitId) {
    return explicitId || editingProjectId || localStorage.getItem("rf_active_project_id") || "";
}

export const workspaceUIController = {
    _sshHostLimit: 0,
    _knownSSHHosts: new Set(),
    _allowedSSHHosts: new Set(),

    async refreshSSHPlanState() {
        try {
            const [, usage] = await Promise.all([
                planAccessState.refresh(),
                workspacesApi.sshUsage(),
            ]);
            this._sshHostLimit = Number(usage.maximum ?? planAccessState.limit("max_ssh_hosts"));
            this._knownSSHHosts = new Set((usage.known_hosts || []).map((host) => String(host).trim().toLowerCase()));
            this._allowedSSHHosts = new Set((usage.allowed_hosts || []).map((host) => String(host).trim().toLowerCase()));
        } catch {
            this._sshHostLimit = 0;
            this._knownSSHHosts = new Set();
            this._allowedSSHHosts = new Set();
        }
        this.updateSSHHostControl();
    },

    updateSSHHostControl() {
        const button = document.getElementById("add-ssh-ws-btn");
        if (!button) return;
        const requestedHost = String(document.getElementById("ssh-host")?.value || "").trim().toLowerCase();
        const allowed = planAccessState.canAddSSHHost(requestedHost, this._knownSSHHosts, this._allowedSSHHosts);
        button.disabled = !allowed;
        button.title = allowed ? "" : "SSH host limit reached or SSH access is not included in your plan";
        button.classList.toggle("opacity-40", !allowed);
        button.classList.toggle("cursor-not-allowed", !allowed);
    },

    setActiveEditingProject(projectId) {
        editingProjectId = projectId || null;
    },

    async loadActiveWorkspace() {
        try {
            const data = await workspacesApi.active();
            const active = data.active;
            const nameEl = document.getElementById("workspace-name");
            const pathEl = document.getElementById("workspace-path");

            if (active) {
                if (nameEl) nameEl.textContent = active.name;
                if (pathEl) pathEl.textContent = active.path || active.host || "~";
            } else {
                if (nameEl) nameEl.textContent = "No Active Workspace";
                if (pathEl) pathEl.textContent = "Click to configure in Settings";
            }
        } catch (e) {
            console.warn("Failed to load active workspace:", e);
        }
    },

    async loadWorkspacesList(projectIdOverride = null) {
        const container = document.getElementById("ws-list");
        if (!container) return;
        const scopedProjectId = resolveScopedProjectId(projectIdOverride);
        await this.refreshSSHPlanState();

        if (!scopedProjectId) {
            container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-4">No project selected</div>';
            return;
        }

        try {
            const data = await workspacesApi.list(scopedProjectId);
            const list = data.workspaces || [];
            if (!list.length) {
                container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-4">No workspaces configured for this project</div>';
                return;
            }

            container.innerHTML = list.map(w => `
                <div class="ws-card flex items-center justify-between p-2.5 bg-[var(--ide-elevated)] rounded-lg border border-[var(--ide-border-subtle)] mb-2" data-id="${w.id}">
                    <div class="flex items-center gap-2 min-w-0 flex-1">
                        <span class="w-2 h-2 rounded-full ${w.is_active ? 'bg-[var(--ide-success)] animate-pulse' : 'bg-gray-500'}"></span>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center gap-2">
                                <span class="text-xs font-bold text-[var(--ide-text-primary)] truncate">${w.name}</span>
                                <span class="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-[var(--ide-accent)]/10 text-[var(--ide-accent)] uppercase">${(w.type || 'local').toUpperCase()}</span>
                            </div>
                            <div class="text-[10px] text-[var(--ide-text-muted)] font-mono truncate">${w.path || w.host || "~"}</div>
                        </div>
                    </div>
                    <div class="flex items-center gap-1.5 shrink-0">
                        <button class="test-ws-btn text-[10px] px-2 py-1 rounded bg-[var(--ide-elevated-2)] hover:bg-[var(--ide-accent)] hover:text-black text-[var(--ide-text-primary)] font-bold transition-colors cursor-pointer" data-id="${w.id}">Test</button>
                        ${!w.is_active ? `<button class="activate-ws-btn text-[10px] px-2.5 py-1 rounded bg-[var(--ide-accent)] text-black font-bold hover:brightness-110 cursor-pointer transition-all" data-id="${w.id}">Activate</button>` : '<span class="text-[10px] text-[var(--ide-success)] font-bold px-1.5 py-0.5 rounded bg-[var(--ide-success)]/10">Active</span>'}
                        <button class="delete-ws-btn text-[var(--ide-error)] hover:text-red-400 p-1 cursor-pointer" data-id="${w.id}" title="Delete Workspace"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>
                    </div>
                </div>
            `).join("");

            if (window.lucide) window.lucide.createIcons({ root: container });

            container.querySelectorAll(".test-ws-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    showToast("Testing workspace connection...", "info");
                    try {
                        const res = await workspacesApi.test(btn.dataset.id);
                        if (res.status === "success") {
                            showToast("Workspace connection verified successfully!", "success");
                        } else {
                            showToast(`Connection failed: ${res.message || "Error"}`, "error");
                        }
                    } catch (e) {
                        showToast(`Test failed: ${e.message}`, "error");
                    }
                });
            });

            container.querySelectorAll(".activate-ws-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    try {
                        await workspacesApi.activate(btn.dataset.id);
                        showToast("Workspace activated", "success");
                        await this.loadActiveWorkspace();
                        await this.loadWorkspacesList(scopedProjectId);
                        eventBus.emit("workspace:changed");
                    } catch (e) {
                        showToast(`Activation failed: ${e.message}`, "error");
                    }
                });
            });

            container.querySelectorAll(".delete-ws-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const confirmed = await showConfirm("Delete Workspace", "Are you sure you want to delete this workspace configuration?", "Delete", "Cancel");
                    if (confirmed) {
                        try {
                            await workspacesApi.delete(btn.dataset.id);
                            showToast("Workspace deleted", "info");
                            await this.loadActiveWorkspace();
                            await this.loadWorkspacesList(scopedProjectId);
                            eventBus.emit("workspace:changed");
                        } catch (e) {
                            showToast(`Delete failed: ${e.message}`, "error");
                        }
                    }
                });
            });

        } catch (e) {
            container.innerHTML = `<div class="text-center text-xs text-[var(--ide-error)] py-4">Failed to load workspaces: ${e.message}</div>`;
        }
    },

    init() {
        document.getElementById("workspace-info-badge")?.addEventListener("click", () => {
            eventBus.emit("settings:open", "workspace");
        });

        document.getElementById("refresh-workspaces-btn")?.addEventListener("click", () => {
            this.loadWorkspacesList();
        });

        document.getElementById("add-local-ws-btn")?.addEventListener("click", async () => {
            const name = document.getElementById("ws-local-name")?.value.trim() || "Local Project";
            const path = document.getElementById("ws-path-input")?.value.trim();
            const scopedProjectId = resolveScopedProjectId();
            if (!path) { showToast("Path is required", "warning"); return; }
            if (!scopedProjectId) { showToast("No project selected to bind this workspace to", "warning"); return; }

            try {
                await workspacesApi.create({ name, type: "local", path, project_id: scopedProjectId, activate: true });
                showToast(`Workspace "${name}" added`, "success");
                if (document.getElementById("ws-local-name")) document.getElementById("ws-local-name").value = "";
                if (document.getElementById("ws-path-input")) document.getElementById("ws-path-input").value = "";
                await this.loadActiveWorkspace();
                await this.loadWorkspacesList(scopedProjectId);
                eventBus.emit("workspace:changed");
            } catch (e) {
                showToast(`Error: ${e.message}`, "error");
            }
        });

        document.getElementById("add-ssh-ws-btn")?.addEventListener("click", async () => {
            const scopedProjectId = resolveScopedProjectId();
            if (!scopedProjectId) { showToast("No project selected to bind this workspace to", "warning"); return; }

            const payload = {
                name: document.getElementById("ssh-name")?.value.trim() || "SSH Server",
                type: "ssh",
                host: document.getElementById("ssh-host")?.value.trim(),
                port: parseInt(document.getElementById("ssh-port")?.value) || 22,
                username: document.getElementById("ssh-user")?.value.trim(),
                auth_type: document.getElementById("ssh-auth-type")?.value || "password",
                password: document.getElementById("ssh-password")?.value || "",
                private_key: document.getElementById("ssh-key")?.value.trim() || "",
                passphrase: document.getElementById("ssh-passphrase")?.value || "",
                path: document.getElementById("ssh-path")?.value.trim() || "~",
                project_id: scopedProjectId,
                activate: true
            };

            if (!payload.host || !payload.username) {
                showToast("Host and Username are required for SSH", "warning");
                return;
            }

            try {
                showToast("Testing and creating SSH connection...", "info");
                await workspacesApi.create(payload);
                showToast(`SSH Workspace "${payload.name}" added`, "success");
                
                if (document.getElementById("ssh-name")) document.getElementById("ssh-name").value = "";
                if (document.getElementById("ssh-host")) document.getElementById("ssh-host").value = "";
                if (document.getElementById("ssh-user")) document.getElementById("ssh-user").value = "";
                if (document.getElementById("ssh-password")) document.getElementById("ssh-password").value = "";
                if (document.getElementById("ssh-key")) document.getElementById("ssh-key").value = "";

                await this.loadActiveWorkspace();
                await this.loadWorkspacesList(scopedProjectId);
                eventBus.emit("workspace:changed");
            } catch (e) {
                showToast(`SSH Error: ${e.message}`, "error");
            }
        });

        document.getElementById("ssh-host")?.addEventListener("input", () => this.updateSSHHostControl());
        this.refreshSSHPlanState();

        document.getElementById("ssh-auth-type")?.addEventListener("change", (e) => {
            const val = e.target.value;
            document.getElementById("ssh-password-row")?.classList.toggle("hidden", val !== "password");
            document.getElementById("ssh-key-row")?.classList.toggle("hidden", val !== "key");
        });
    }
};
