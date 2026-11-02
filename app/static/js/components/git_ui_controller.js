/**
 * Git UI Controller.
 * "Initialize Repository" redirects to Project Settings -> Git tab.
 */
import { gitApi } from "../core/api_http_client.js";
import { showToast } from "./toast_ui_controller.js";
import { projectsUIController } from "./projects_ui_controller.js";
import { socialDraftsUIController } from "./social_drafts_ui_controller.js";

export const gitUIController = {
    init() {
        document.getElementById("git-init-btn")?.addEventListener("click", () => this.handleInitClick());
        document.getElementById("commit-btn")?.addEventListener("click", () => this.openCommitModal());
        document.getElementById("cancel-commit-btn")?.addEventListener("click", () => this.closeCommitModal());
        document.getElementById("close-commit-modal-btn")?.addEventListener("click", () => this.closeCommitModal());
        document.getElementById("confirm-commit-btn")?.addEventListener("click", () => this.executeCommit());
        document.getElementById("close-diff-viewer-btn")?.addEventListener("click", () => this.closeDiffModal());
        document.getElementById("git-push-btn")?.addEventListener("click", () => this.executePush());
        document.getElementById("git-pull-btn")?.addEventListener("click", () => this.executePull());
    },

    async handleInitClick() {
        const activeProjectId = localStorage.getItem("rf_active_project_id");
        if (activeProjectId) {
            await projectsUIController.openProjectSettingsModal(activeProjectId);
            projectsUIController.switchProjectSettingsTab("git");
        } else {
            await this.initRepository();
        }
    },

    async loadGitStatus() {
        const emptyState = document.getElementById("git-empty-state");
        const gitContent = document.getElementById("git-content");
        const filesList = document.getElementById("git-files-list");
        const badge = document.getElementById("git-badge");
        const branchName = document.getElementById("git-branch-name");
        const commitBtn = document.getElementById("commit-btn");
        try {
            const data = await gitApi.status();
            if (!data.is_repo) {
                if (emptyState) emptyState.classList.remove("hidden");
                if (gitContent) gitContent.classList.add("hidden");
                return;
            }
            if (emptyState) emptyState.classList.add("hidden");
            if (gitContent) gitContent.classList.remove("hidden");
            this.loadBranchName(branchName);
            const entries = data.entries || [];
            if (badge) {
                if (entries.length > 0) {
                    badge.textContent = entries.length;
                    badge.classList.remove("hidden");
                } else {
                    badge.classList.add("hidden");
                }
            }
            if (commitBtn) {
                if (entries.length > 0) {
                    commitBtn.classList.remove("hidden");
                    commitBtn.style.display = "inline-flex";
                } else {
                    commitBtn.classList.add("hidden");
                }
            }
            if (!entries.length) {
                if (filesList) filesList.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-6">No git changes</div>';
                return;
            }
            if (filesList) {
                filesList.innerHTML = entries
                    .map(
                        (e) => `
                    <div class="git-file-item flex items-center justify-between p-1.5 text-xs hover:bg-[var(--ide-elevated)] rounded cursor-pointer border-b border-[var(--ide-border-subtle)]" data-path="${e.path}">
                        <span class="truncate text-[var(--ide-text-primary)] font-mono text-[11px]" title="${e.path}">${e.path}</span>
                        <span class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${this.getStatusBadgeClass(e.status)}">${e.status}</span>
                    </div>`
                    )
                    .join("");
                filesList.querySelectorAll(".git-file-item").forEach((item) => {
                    item.addEventListener("click", () => this.showDiff(item.dataset.path));
                });
            }
        } catch (e) {
            if (emptyState) emptyState.classList.remove("hidden");
            if (gitContent) gitContent.classList.add("hidden");
        }
    },

    async loadBranchName(el) {
        if (!el) return;
        try {
            const res = await gitApi.branches();
            if (res.is_repo && res.branches && res.branches.length) {
                const current = res.branches.find((b) => b.current);
                el.textContent = current ? current.name : res.branches[0].name;
            } else {
                el.textContent = "main";
            }
        } catch (e) {
            el.textContent = "main";
        }
    },

    getStatusBadgeClass(status) {
        const s = (status || "").toLowerCase();
        if (s === "modified") return "bg-amber-500/15 text-amber-400";
        if (s === "added" || s === "untracked") return "bg-emerald-500/15 text-emerald-400";
        if (s === "deleted") return "bg-red-500/15 text-red-400";
        return "bg-blue-500/15 text-blue-400";
    },

    async initRepository() {
        try {
            showToast("Initializing Git repository...", "info");
            const res = await gitApi.init();
            if (res.success) {
                showToast("Git repository initialized", "success");
                await this.loadGitStatus();
            } else {
                showToast(`Git init failed: ${res.stderr || "Unknown error"}`, "error");
            }
        } catch (e) {
            showToast(`Failed to initialize Git: ${e.message}`, "error");
        }
    },

    async showDiff(path) {
        const modal = document.getElementById("diff-viewer-modal");
        const nameEl = document.getElementById("diff-viewer-name");
        const contentEl = document.getElementById("diff-viewer-content");
        if (nameEl) nameEl.textContent = path;
        if (contentEl) contentEl.textContent = "Loading diff...";
        if (modal) {
            modal.classList.remove("hidden");
            modal.style.display = "flex";
        }
        try {
            const res = await gitApi.diff(path);
            if (contentEl) contentEl.textContent = res.diff || "No diff available";
        } catch (e) {
            if (contentEl) contentEl.textContent = `Error: ${e.message}`;
        }
    },

    closeDiffModal() {
        const modal = document.getElementById("diff-viewer-modal");
        if (modal) {
            modal.classList.add("hidden");
            modal.style.display = "none";
        }
    },

    async openCommitModal() {
        const modal = document.getElementById("commit-modal");
        const previewEl = document.getElementById("commit-files-preview");
        const msgInput = document.getElementById("commit-message-input");
        if (msgInput) msgInput.value = "";
        try {
            const data = await gitApi.status();
            const entries = data.entries || [];
            if (previewEl) {
                previewEl.innerHTML = entries
                    .map(
                        (e) => `
                    <div class="flex items-center justify-between text-[11px] font-mono">
                        <span class="truncate">${e.path}</span>
                        <span class="uppercase font-bold text-[9px]">${e.status}</span>
                    </div>`
                    )
                    .join("");
            }
        } catch (e) {}
        if (modal) {
            modal.classList.remove("hidden");
            modal.style.display = "flex";
        }
    },

    closeCommitModal() {
        const modal = document.getElementById("commit-modal");
        if (modal) {
            modal.classList.add("hidden");
            modal.style.display = "none";
        }
    },

    async executeCommit() {
        const msgInput = document.getElementById("commit-message-input");
        const msg = msgInput ? msgInput.value.trim() : "";
        if (!msg) {
            showToast("Commit message is required", "warning");
            return;
        }
        try {
            showToast("Committing changes...", "info");
            const res = await gitApi.commit(msg);
            if (res.error) {
                showToast(`Commit failed: ${res.error}`, "error");
            } else {
                showToast("Changes committed successfully", "success");
                this.closeCommitModal();
                await this.loadGitStatus();
            }
        } catch (e) {
            showToast(`Commit failed: ${e.message}`, "error");
        }
    },

    async executePush() {
        try {
            showToast("Pushing to remote...", "info");
            const res = await gitApi.push();
            if (res.success) {
                showToast("Git push completed!", "success");
                await socialDraftsUIController.generateFromLatestChanges();
            } else showToast(`Push failed: ${res.stderr || "Unknown error"}`, "error");
        } catch (e) {
            showToast(`Git push failed: ${e.message}`, "error");
        }
    },

    async executePull() {
        try {
            showToast("Pulling latest...", "info");
            const res = await gitApi.pull();
            if (res.success) {
                showToast("Git pull completed!", "success");
                await this.loadGitStatus();
            } else {
                showToast(`Pull failed: ${res.stderr || "Unknown error"}`, "error");
            }
        } catch (e) {
            showToast(`Git pull failed: ${e.message}`, "error");
        }
    },
};
