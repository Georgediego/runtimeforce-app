/**
 * File Tree UI Controller with Chevron Rotation and Folder Toggle Fix.
 */
import { workspacesApi } from "../core/api_http_client.js";
import { eventBus } from "../core/event_bus.js";
import { projectsUIController } from "./projects_ui_controller.js";
import { planAccessState } from "../core/plan_access_state.js";

export const fileTreeUIController = {
    async loadTree() {
        const container = document.getElementById("file-tree");
        if (!container) return;
        await planAccessState.refresh();
        if (!planAccessState.featureEnabled("editor")) {
            container.innerHTML = '<div class="p-4 text-center text-xs text-[var(--ide-text-muted)]"><span class="inline-flex items-center gap-1.5 font-bold"><i data-lucide="lock" class="w-3.5 h-3.5"></i> Editor locked</span><p class="mt-2">Editor is not included in your current plan.</p></div>';
            if (window.lucide) window.lucide.createIcons({ root: container });
            return;
        }
        this.updateWorkspaceCard();
        container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-4"><i data-lucide="loader" class="w-4 h-4 inline animate-spin"></i> Loading...</div>';
        if (window.lucide) window.lucide.createIcons({ root: container });
        try {
            const activeProjectId = localStorage.getItem("rf_active_project_id") || "";
            const data = await workspacesApi.tree(activeProjectId);
            if (!data || !data.tree) {
                this.renderEmptyState(container);
                return;
            }
            this.renderTree(container, data.tree);
        } catch (e) {
            this.renderEmptyState(container);
        }
    },

    async updateWorkspaceCard() {
        const nameEl = document.getElementById("ws-card-name");
        const typeEl = document.getElementById("ws-card-type");
        const pathEl = document.getElementById("ws-card-path");
        try {
            const activeProjectId = localStorage.getItem("rf_active_project_id") || "";
            const data = await workspacesApi.active(activeProjectId);
            const active = data.active;
            if (active) {
                if (nameEl) nameEl.textContent = active.name || "Active Workspace";
                if (typeEl) typeEl.textContent = (active.type || "local").toUpperCase();
                if (pathEl) pathEl.textContent = active.path || active.host || "~";
            } else {
                if (nameEl) nameEl.textContent = "No Active Workspace";
                if (typeEl) typeEl.textContent = "NONE";
                if (pathEl) pathEl.textContent = "~";
            }
        } catch (e) {
            if (nameEl) nameEl.textContent = "No Workspace";
        }
    },

    renderEmptyState(container) {
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center py-8 px-4 text-center">
                <i data-lucide="folder-plus" class="w-8 h-8 text-[var(--ide-text-muted)] mb-3"></i>
                <p class="text-xs text-[var(--ide-text-muted)] mb-4">No active workspace configured</p>
                <button id="prompt-configure-ws-btn" class="px-3 py-1.5 bg-[var(--ide-accent)] text-black text-xs font-bold rounded-lg hover:brightness-110 cursor-pointer">
                    + Configure Workspace
                </button>
            </div>`;
        if (window.lucide) window.lucide.createIcons({ root: container });
        document.getElementById("prompt-configure-ws-btn")?.addEventListener("click", () => {
            const activeProjectId = localStorage.getItem("rf_active_project_id");
            if (activeProjectId) {
                projectsUIController.openProjectSettingsModal(activeProjectId).then(() => {
                    projectsUIController.switchProjectSettingsTab("workspace");
                });
            } else {
                eventBus.emit("settings:open", "workspace");
            }
        });
    },

    renderTree(container, tree) {
        if (!tree.children || tree.children.length === 0) {
            container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-4">Empty workspace directory</div>';
            return;
        }
        container.innerHTML = tree.children.map((child) => this.renderNodeHTML(child)).join("");
        if (window.lucide) window.lucide.createIcons({ root: container });
        this.bindTreeEvents(container);
    },

    renderNodeHTML(child) {
        const isDir = child.is_dir || child.type === "directory";
        if (isDir) {
            return `
                <div class="tree-folder" data-path="${child.path}" title="${child.path}">
                    <div class="tree-folder-toggle flex items-center gap-1.5 py-1 text-sm cursor-pointer hover:bg-[var(--ide-elevated)] px-2 rounded select-none">
                        <i data-lucide="chevron-right" class="w-3 h-3 text-[var(--ide-text-muted)] tree-chevron transition-transform duration-150"></i>
                        <i data-lucide="folder" class="w-3.5 h-3.5 text-[var(--ide-accent)]"></i>
                        <span class="tree-node-name truncate text-xs">${child.name}</span>
                    </div>
                    <div class="tree-folder-children hidden pl-4"></div>
                </div>`;
        }
        return `
            <div class="tree-file-item flex items-center gap-1.5 py-1 text-sm cursor-pointer hover:bg-[var(--ide-elevated)] px-2 rounded" data-path="${child.path}" data-name="${child.name}" title="${child.path}">
                <i data-lucide="file-code" class="w-3.5 h-3.5 text-[var(--ide-text-muted)]"></i>
                <span class="truncate text-xs">${child.name}</span>
            </div>`;
    },

    bindTreeEvents(container) {
        container.querySelectorAll(".tree-file-item, .tree-folder").forEach((item) => {
            item.addEventListener("contextmenu", async (event) => {
                event.preventDefault();
                event.stopPropagation();
                const path = item.dataset.path || "";
                if (!path) return;
                try {
                    await navigator.clipboard.writeText(path);
                    const previous = item.title;
                    item.title = "Copied: " + path;
                    setTimeout(() => { item.title = previous || path; }, 1200);
                } catch (error) {
                    console.warn("Could not copy workspace path:", error);
                }
            });
        });
        container.querySelectorAll(".tree-file-item").forEach((item) => {
            item.addEventListener("click", () => {
                eventBus.emit("file:open", { path: item.dataset.path, name: item.dataset.name });
                eventBus.emit("file.selected", { path: item.dataset.path, name: item.dataset.name });
            });
        });

        container.querySelectorAll(".tree-folder-toggle").forEach((toggle) => {
            toggle.addEventListener("click", async (e) => {
                e.stopPropagation();
                const folder = toggle.parentElement;
                const children = folder.querySelector(".tree-folder-children");
                const folderPath = folder.dataset.path;
                const chevron = toggle.querySelector(".tree-chevron");

                if (!children) return;

                if (children.classList.contains("hidden")) {
                    if (!children.dataset.loaded) {
                        try {
                            const activeProjectId = localStorage.getItem("rf_active_project_id") || "";
                            const res = await workspacesApi.treeChildren(folderPath, activeProjectId);
                            if (res && res.children) {
                                children.innerHTML = res.children.map((c) => this.renderNodeHTML(c)).join("");
                                if (window.lucide) window.lucide.createIcons({ root: children });
                                this.bindTreeEvents(children);
                                children.dataset.loaded = "true";
                            }
                        } catch (err) {
                            console.error("Failed to load folder children:", err);
                        }
                    }
                    children.classList.remove("hidden");
                    folder.classList.add("expanded");
                    if (chevron) chevron.classList.add("rotate-90");
                } else {
                    children.classList.add("hidden");
                    folder.classList.remove("expanded");
                    if (chevron) chevron.classList.remove("rotate-90");
                }
            });
        });
    },
};
