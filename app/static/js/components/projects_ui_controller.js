/**
 * Projects UI Controller with Immediate Boot Synchronization.
 */
import { projectsApi } from "../core/api_http_client.js";
import { showToast, showPrompt, showConfirm } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";
import { workspaceUIController } from "./workspace_ui_controller.js";
import { fileTreeUIController } from "./file_tree_ui_controller.js";
import { chatUIController } from "./chat_ui_controller.js";

let activeSettingsProjectId = null;
let projectAttachedContextFiles = [];

function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val || "";
}

function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : "";
}

export const projectsUIController = {
    init() {
        document.getElementById("refresh-projects-btn")?.addEventListener("click", () => this.loadProjectsList());
        document.getElementById("add-project-btn")?.addEventListener("click", () => this.openCreateProjectModal());
        document.getElementById("close-project-settings-btn")?.addEventListener("click", () => this.closeProjectSettingsModal());
        document.getElementById("save-project-settings-btn")?.addEventListener("click", () => this.saveProjectSettings());
        const attachBtn = document.getElementById("ps-attach-files-btn");
        const fileInput = document.getElementById("ps-context-files-input");
        attachBtn?.addEventListener("click", () => fileInput?.click());
        fileInput?.addEventListener("change", (e) => this.handleProjectContextFiles(e));
        document.querySelectorAll(".proj-settings-tab-btn").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                this.switchProjectSettingsTab(e.currentTarget.dataset.tab);
            });
        });
    },

    async initActiveProject() {
        try {
            const data = await projectsApi.list();
            const projects = Array.isArray(data) ? data : data.projects || [];
            if (projects.length > 0) {
                const savedId = localStorage.getItem("rf_active_project_id");
                let activeProj = projects.find((p) => p.id === savedId) || projects.find((p) => p.is_active) || projects[0];
                
                localStorage.setItem("rf_active_project_id", activeProj.id);
                this.updateActiveHeader(activeProj);

                await Promise.all([
                    fileTreeUIController.loadTree(),
                    workspaceUIController.loadActiveWorkspace(),
                    chatUIController.loadSessionsList()
                ]);
            }
        } catch (e) {
            console.warn("Failed to initialize active project on boot:", e);
        }
    },

    handleProjectContextFiles(e) {
        const files = Array.from(e.target.files || []);
        files.forEach((file) => {
            const reader = new FileReader();
            reader.onload = (event) => {
                projectAttachedContextFiles.push({ name: file.name, content: event.target.result });
                this.renderProjectAttachedFiles();
            };
            reader.readAsText(file);
        });
        e.target.value = "";
    },

    renderProjectAttachedFiles() {
        const listEl = document.getElementById("ps-attached-files-list");
        if (!listEl) return;
        if (!projectAttachedContextFiles.length) {
            listEl.innerHTML = '<span class="text-[10px] text-[var(--ide-text-muted)] italic">No attached context files</span>';
            return;
        }
        listEl.innerHTML = projectAttachedContextFiles
            .map(
                (f, idx) => `
            <div class="flex items-center gap-1.5 px-2 py-1 rounded bg-[var(--ide-elevated)] border border-[var(--ide-border-subtle)] text-[10px] font-mono text-[var(--ide-accent)]">
                <i data-lucide="file-text" class="w-3 h-3"></i>
                <span class="truncate max-w-[120px]">${f.name}</span>
                <button type="button" class="remove-proj-file-btn text-red-400 hover:text-red-300 ml-1 cursor-pointer" data-index="${idx}">&times;</button>
            </div>`
            )
            .join("");
        listEl.querySelectorAll(".remove-proj-file-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                projectAttachedContextFiles.splice(parseInt(btn.dataset.index, 10), 1);
                this.renderProjectAttachedFiles();
            });
        });
    },

    async loadProjectsList() {
        const container = document.getElementById("projects-list");
        if (!container) return;
        try {
            const data = await projectsApi.list();
            const projects = Array.isArray(data) ? data : data.projects || [];
            if (!projects.length) {
                container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-6">No Studio projects configured</div>';
                this.updateActiveHeader(null);
                return;
            }
            const savedId = localStorage.getItem("rf_active_project_id");
            const activeProj = projects.find((p) => p.id === savedId) || projects.find((p) => p.is_active) || projects[0];
            localStorage.setItem("rf_active_project_id", activeProj.id);
            this.updateActiveHeader(activeProj);

            container.innerHTML = projects
                .map(
                    (p) => `
                <div class="p-3 mb-2.5 rounded-xl bg-[var(--ide-elevated)] border ${p.id === activeProj.id ? "border-[var(--ide-accent)] bg-[var(--ide-accent)]/5" : "border-[var(--ide-border-subtle)]"} flex flex-col gap-2 glass-cover" data-id="${p.id}">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2 min-w-0">
                            <span class="w-2 h-2 rounded-full ${p.id === activeProj.id ? "bg-[var(--ide-success)] animate-pulse" : "bg-gray-500"}"></span>
                            <span class="text-xs font-bold text-[var(--ide-text-primary)] truncate">${p.name}</span>
                        </div>
                        <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-[var(--ide-accent)]/10 text-[var(--ide-accent)] font-bold">${p.current_version || "v1.0.0"}</span>
                    </div>
                    <div class="flex items-center justify-between pt-2 border-t border-[var(--ide-border-subtle)] gap-1">
                        ${p.id !== activeProj.id ? `<button class="activate-proj-btn text-[10px] px-2 py-1 rounded bg-[var(--ide-accent)]/10 text-[var(--ide-accent)] hover:bg-[var(--ide-accent)]/20 cursor-pointer font-bold" data-id="${p.id}">Activate</button>` : '<span class="text-[10px] text-[var(--ide-success)] font-bold">Active</span>'}
                        <div class="flex items-center gap-1">
                            <button class="bump-ver-btn text-[10px] px-2 py-1 rounded bg-[var(--ide-surface)] hover:text-[var(--ide-accent)] cursor-pointer transition-colors" data-id="${p.id}" title="Bump Version">+ Bump</button>
                            <button class="edit-proj-btn text-[10px] text-[var(--ide-text-secondary)] hover:text-[var(--ide-text-primary)] p-1 cursor-pointer" data-id="${p.id}" title="Project Settings">
                                <i data-lucide="settings" class="w-3.5 h-3.5"></i>
                            </button>
                            <button class="delete-proj-btn text-[10px] text-[var(--ide-error)] hover:text-red-400 p-1 cursor-pointer" data-id="${p.id}" title="Delete Project">
                                <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                            </button>
                        </div>
                    </div>
                </div>`
                )
                .join("");

            if (window.lucide) window.lucide.createIcons({ root: container });

            container.querySelectorAll(".activate-proj-btn").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    await projectsApi.activate(btn.dataset.id);
                    localStorage.setItem("rf_active_project_id", btn.dataset.id);
                    showToast("Project activated", "success");
                    eventBus.emit("project.activated", btn.dataset.id);
                    eventBus.emit("workspace:changed");
                    this.loadProjectsList();
                });
            });
            container.querySelectorAll(".bump-ver-btn").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    const changelog = await showPrompt("Release Version Bump", "Enter changelog summary:", "", "Bump Version", "Cancel");
                    if (changelog && changelog.trim()) {
                        try {
                            const res = await projectsApi.bumpVersion(btn.dataset.id, changelog.trim(), "patch");
                            showToast(`Project bumped to ${res.new_version}`, "success");
                            this.loadProjectsList();
                        } catch (e) {
                            showToast(`Failed to bump version: ${e.message}`, "error");
                        }
                    }
                });
            });
            container.querySelectorAll(".edit-proj-btn").forEach((btn) => {
                btn.addEventListener("click", () => {
                    this.openProjectSettingsModal(btn.dataset.id);
                });
            });
            container.querySelectorAll(".delete-proj-btn").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    const confirmed = await showConfirm("Delete Project", "Are you sure?", "Delete", "Cancel");
                    if (confirmed) {
                        try {
                            await projectsApi.delete(btn.dataset.id);
                            showToast("Project deleted", "info");
                            this.loadProjectsList();
                        } catch (e) {
                            showToast(`Delete failed: ${e.message}`, "error");
                        }
                    }
                });
            });
        } catch (e) {
            container.innerHTML = `<div class="text-center text-xs text-[var(--ide-error)] py-4">Failed to load projects: ${e.message}</div>`;
        }
    },

    updateActiveHeader(proj) {
        const nameEl = document.getElementById("active-project-name-display");
        const verEl = document.getElementById("active-project-ver-display");
        if (nameEl) nameEl.textContent = proj ? proj.name : "No Active Project";
        if (verEl) verEl.textContent = proj ? proj.current_version || "v1.0.0" : "v1.0.0";
    },

    async openCreateProjectModal() {
        const name = await showPrompt("New Studio Project", "Enter project name:", "", "Create", "Cancel");
        if (!name || !name.trim()) return;
        try {
            const res = await projectsApi.create({
                name: name.trim(),
                project_context: "Project architecture, stack definition, and guidelines.",
                rules_of_engagement: "Workflow: Code -> Test -> Changelog -> SemVer Bump -> Git Push",
                git_mode: "manual",
                git_branch_main: "main",
                git_branch_dev: "dev",
                version_scheme: "semver",
                prerelease_tag: "",
                current_version: "v1.0.0",
                activate: true,
            });
            if (res && res.id) {
                localStorage.setItem("rf_active_project_id", res.id);
                eventBus.emit("project.activated", res.id);
                eventBus.emit("workspace:changed");
            }
            showToast(`Project "${name}" created`, "success");
            this.loadProjectsList();
        } catch (e) {
            showToast(`Failed to create project: ${e.message}`, "error");
        }
    },

    async openProjectSettingsModal(projectId) {
        activeSettingsProjectId = projectId;
        projectAttachedContextFiles = [];
        this.renderProjectAttachedFiles();
        const modal = document.getElementById("project-settings-modal");
        try {
            const proj = await projectsApi.get(projectId);
            if (!proj) return;

            const headerTitle = document.getElementById("project-settings-header-title");
            if (headerTitle) headerTitle.textContent = proj.name || "Project Settings";

            setVal("ps-name-input", proj.name);
            setVal("ps-context-input", proj.project_context);
            setVal("ps-rules-input", proj.rules_of_engagement);

            setVal("ps-path-input", proj.workspace_path);
            setVal("ps-ssh-host", proj.ssh_host);
            setVal("ps-ssh-port", proj.ssh_port || 22);
            setVal("ps-ssh-user", proj.ssh_username);

            setVal("ps-github-url", proj.github_remote_url);
            setVal("ps-github-pat", proj.github_pat_enc);
            setVal("ps-git-mode", proj.git_mode || "manual");
            setVal("ps-branch-main", proj.git_branch_main || "main");
            setVal("ps-branch-dev", proj.git_branch_dev || "dev");
            setVal("ps-version-scheme", proj.version_scheme || "semver");
            setVal("ps-prerelease-tag", proj.prerelease_tag);
            setVal("ps-current-version", proj.current_version || "v1.0.0");

            setVal("ps-x-bearer", proj.x_api_key_enc);
            setVal("ps-reddit-client", proj.reddit_client_id_enc);

            this.switchProjectSettingsTab("general");

            workspaceUIController.setActiveEditingProject(projectId);
            await workspaceUIController.loadWorkspacesList(projectId);

            if (modal) {
                modal.classList.remove("hidden");
                modal.style.display = "flex";
            }
        } catch (e) {
            showToast(`Failed to fetch project details: ${e.message}`, "error");
        }
    },

    switchProjectSettingsTab(targetTab) {
        document.querySelectorAll(".proj-settings-content-tab").forEach((t) => t.classList.add("hidden"));
        document.getElementById(`pst-tab-${targetTab}`)?.classList.remove("hidden");
        document.querySelectorAll(".proj-settings-tab-btn").forEach((b) => {
            const isActive = b.dataset.tab === targetTab;
            b.className = `proj-settings-tab-btn px-3 py-1.5 text-xs rounded-lg cursor-pointer ${isActive ? "bg-[var(--ide-accent)] text-black font-bold" : "bg-[var(--ide-elevated)] text-[var(--ide-text-secondary)] hover:text-white"}`;
        });
        if (targetTab === "workspace" && activeSettingsProjectId) {
            workspaceUIController.loadWorkspacesList(activeSettingsProjectId);
        }
    },

    closeProjectSettingsModal() {
        const modal = document.getElementById("project-settings-modal");
        if (modal) {
            modal.classList.add("hidden");
            modal.style.display = "none";
        }
        workspaceUIController.setActiveEditingProject(null);
        activeSettingsProjectId = null;
    },

    async saveProjectSettings() {
        if (!activeSettingsProjectId) return;
        let combinedContext = getVal("ps-context-input");
        if (projectAttachedContextFiles.length > 0) {
            const fileBlocks = projectAttachedContextFiles
                .map((f) => `\n### Attached File: ${f.name}\n\`\`\`\n${f.content}\n\`\`\``)
                .join("");
            combinedContext += fileBlocks;
        }
        const payload = {
            name: getVal("ps-name-input"),
            project_context: combinedContext,
            rules_of_engagement: getVal("ps-rules-input"),
            workspace_path: getVal("ps-path-input"),
            ssh_host: getVal("ps-ssh-host"),
            ssh_port: parseInt(getVal("ps-ssh-port")) || 22,
            ssh_username: getVal("ps-ssh-user"),
            github_remote_url: getVal("ps-github-url"),
            github_pat_enc: getVal("ps-github-pat"),
            git_mode: getVal("ps-git-mode") || "manual",
            git_branch_main: getVal("ps-branch-main") || "main",
            git_branch_dev: getVal("ps-branch-dev") || "dev",
            version_scheme: getVal("ps-version-scheme") || "semver",
            prerelease_tag: getVal("ps-prerelease-tag"),
            current_version: getVal("ps-current-version") || "v1.0.0",
            x_api_key_enc: getVal("ps-x-bearer"),
            reddit_client_id_enc: getVal("ps-reddit-client"),
        };
        try {
            await projectsApi.update(activeSettingsProjectId, payload);
            showToast("Project settings saved successfully", "success");
            this.closeProjectSettingsModal();
            this.loadProjectsList();
            eventBus.emit("workspace:changed");
        } catch (e) {
            showToast(`Save failed: ${e.message}`, "error");
        }
    },
};
