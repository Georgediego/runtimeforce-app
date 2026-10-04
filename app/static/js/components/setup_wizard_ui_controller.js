/**
 * Setup Assistant Controller.
 * Checks system configuration on startup and guides the user directly
 * into EXISTING settings modals (Providers & Project Settings) without duplicating fields.
 */
import { keysApi, projectsApi, workspacesApi } from "../core/api_http_client.js";
import { settingsUIController } from "./settings_ui_controller.js";
import { projectsUIController } from "./projects_ui_controller.js";
import { chatUIController } from "./chat_ui_controller.js";
import { showToast } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

let isWizardOpen = false;

export const setupWizardUIController = {
    init() {
        document.getElementById("wiz-btn-providers")?.addEventListener("click", () => this.openExistingProvidersModal());
        document.getElementById("wiz-btn-project")?.addEventListener("click", () => this.openExistingProjectModal());
        document.getElementById("wiz-btn-start")?.addEventListener("click", () => this.startCoding());
        document.getElementById("close-wizard-btn")?.addEventListener("click", () => this.close());
        document.getElementById("wiz-skip-btn")?.addEventListener("click", () => this.close());

        // Re-check configuration when settings or projects change
        eventBus.on("providers.updated", () => this.refreshStatus());
        eventBus.on("workspace:changed", () => this.refreshStatus());
        eventBus.on("project.activated", () => this.refreshStatus());
    },

    async checkAndPrompt() {
        const status = await this.evaluateStatus();
        if (status.needsSetup) {
            this.open();
        }
    },

    async evaluateStatus() {
        let hasKeys = false;
        let hasProject = false;
        let activeProjectName = "";
        let connectedProvidersList = [];

        // Check 1: Provider API keys & selected models
        try {
            const statusRes = await keysApi.status();
            const providers = statusRes.providers || {};
            connectedProvidersList = Object.keys(providers);
            
            const modelsRes = await keysApi.getSelectedModels();
            const selectedModels = modelsRes.selected_models || {};
            const totalSelected = Object.values(selectedModels).reduce((acc, list) => acc + (list?.length || 0), 0);

            if (connectedProvidersList.length > 0 || totalSelected > 0) {
                hasKeys = true;
            }
        } catch (e) {
            console.debug("Keys evaluation:", e);
        }

        // Check 2: Configured project & workspace
        try {
            const data = await projectsApi.list();
            const projects = Array.isArray(data) ? data : data.projects || [];
            if (projects.length > 0) {
                const savedId = localStorage.getItem("rf_active_project_id");
                const activeProj = projects.find(p => p.id === savedId) || projects.find(p => p.is_active) || projects[0];
                if (activeProj) {
                    activeProjectName = activeProj.name || "Project";
                    const wsRes = await workspacesApi.active(activeProj.id);
                    if (wsRes.active || activeProj.workspace_path || activeProj.ssh_host) {
                        hasProject = true;
                    }
                }
            }
        } catch (e) {
            console.debug("Project evaluation:", e);
        }

        return {
            hasKeys,
            hasProject,
            connectedProvidersList,
            activeProjectName,
            needsSetup: !hasKeys || !hasProject
        };
    },

    async refreshStatus() {
        if (!isWizardOpen) return;
        const status = await this.evaluateStatus();
        this.renderStatus(status);
    },

    open() {
        const modal = document.getElementById("setup-wizard-modal");
        if (modal) {
            modal.classList.remove("hidden");
            modal.style.display = "flex";
            isWizardOpen = true;
            this.evaluateStatus().then(status => this.renderStatus(status));
        }
    },

    close() {
        const modal = document.getElementById("setup-wizard-modal");
        if (modal) {
            modal.classList.add("hidden");
            modal.style.display = "none";
            isWizardOpen = false;
        }
    },

    renderStatus(status) {
        // Step 1: Providers & Keys UI
        const step1Badge = document.getElementById("wiz-step1-badge");
        const step1Desc = document.getElementById("wiz-step1-desc");
        const step1Btn = document.getElementById("wiz-btn-providers");

        if (status.hasKeys) {
            if (step1Badge) {
                step1Badge.className = "w-6 h-6 rounded-full bg-emerald-500 text-black font-bold flex items-center justify-center text-xs shrink-0";
                step1Badge.innerHTML = "✓";
            }
            if (step1Desc) {
                step1Desc.textContent = `Configured (${status.connectedProvidersList.join(', ') || 'Models connected'})`;
                step1Desc.className = "text-[11px] text-emerald-400 font-semibold";
            }
            if (step1Btn) {
                step1Btn.textContent = "Edit Providers";
                step1Btn.className = "px-3 py-1.5 rounded-lg bg-[var(--ide-surface)] border border-[var(--ide-border-subtle)] text-[var(--ide-text-secondary)] hover:text-white text-xs font-semibold cursor-pointer";
            }
        } else {
            if (step1Badge) {
                step1Badge.className = "w-6 h-6 rounded-full bg-amber-500 text-black font-bold flex items-center justify-center text-xs shrink-0";
                step1Badge.innerHTML = "1";
            }
            if (step1Desc) {
                step1Desc.textContent = "No API keys or models configured yet";
                step1Desc.className = "text-[11px] text-amber-400 font-semibold";
            }
            if (step1Btn) {
                step1Btn.textContent = "Configure Providers →";
                step1Btn.className = "px-3.5 py-1.5 rounded-lg bg-[var(--ide-accent)] text-black text-xs font-bold hover:brightness-110 cursor-pointer shadow-md";
            }
        }

        // Step 2: Project & Workspace UI
        const step2Badge = document.getElementById("wiz-step2-badge");
        const step2Desc = document.getElementById("wiz-step2-desc");
        const step2Btn = document.getElementById("wiz-btn-project");

        if (status.hasProject) {
            if (step2Badge) {
                step2Badge.className = "w-6 h-6 rounded-full bg-emerald-500 text-black font-bold flex items-center justify-center text-xs shrink-0";
                step2Badge.innerHTML = "✓";
            }
            if (step2Desc) {
                step2Desc.textContent = `Configured (${status.activeProjectName})`;
                step2Desc.className = "text-[11px] text-emerald-400 font-semibold";
            }
            if (step2Btn) {
                step2Btn.textContent = "Edit Project";
                step2Btn.className = "px-3 py-1.5 rounded-lg bg-[var(--ide-surface)] border border-[var(--ide-border-subtle)] text-[var(--ide-text-secondary)] hover:text-white text-xs font-semibold cursor-pointer";
            }
        } else {
            if (step2Badge) {
                step2Badge.className = "w-6 h-6 rounded-full bg-amber-500 text-black font-bold flex items-center justify-center text-xs shrink-0";
                step2Badge.innerHTML = "2";
            }
            if (step2Desc) {
                step2Desc.textContent = "Project workspace directory or SSH host missing";
                step2Desc.className = "text-[11px] text-amber-400 font-semibold";
            }
            if (step2Btn) {
                step2Btn.textContent = "Configure Project →";
                step2Btn.className = "px-3.5 py-1.5 rounded-lg bg-[var(--ide-accent)] text-black text-xs font-bold hover:brightness-110 cursor-pointer shadow-md";
            }
        }

        // Step 3: Readiness indicator
        const step3Badge = document.getElementById("wiz-step3-badge");
        const step3Btn = document.getElementById("wiz-btn-start");
        const isReady = status.hasKeys && status.hasProject;

        if (step3Badge) {
            step3Badge.className = `w-6 h-6 rounded-full ${isReady ? 'bg-emerald-500 text-black' : 'bg-[var(--ide-elevated)] border border-[var(--ide-border-subtle)] text-[var(--ide-text-muted)]'} font-bold flex items-center justify-center text-xs shrink-0`;
            step3Badge.innerHTML = isReady ? "✓" : "3";
        }

        if (step3Btn) {
            if (isReady) {
                step3Btn.className = "w-full py-2.5 rounded-xl bg-[var(--ide-accent)] text-black font-extrabold text-xs hover:brightness-110 cursor-pointer shadow-lg";
            } else {
                step3Btn.className = "w-full py-2.5 rounded-xl bg-[var(--ide-elevated)] border border-[var(--ide-border-subtle)] text-[var(--ide-text-muted)] text-xs font-semibold cursor-pointer";
            }
        }
    },

    openExistingProvidersModal() {
        this.close();
        settingsUIController.open("providers");

        const closeBtn = document.getElementById("close-settings-btn");
        const onModalClosed = () => {
            closeBtn?.removeEventListener("click", onModalClosed);
            this.evaluateStatus().then(status => {
                if (status.needsSetup) this.open();
            });
        };
        closeBtn?.addEventListener("click", onModalClosed);
    },

    async openExistingProjectModal() {
        this.close();
        let targetId = localStorage.getItem("rf_active_project_id");
        if (!targetId) {
            try {
                const res = await projectsApi.create({
                    name: "My Project",
                    project_context: "Main project architecture guidelines",
                    rules_of_engagement: "Workflow: Code -> Test -> Release",
                    activate: true
                });
                targetId = res.id;
                localStorage.setItem("rf_active_project_id", targetId);
                await projectsUIController.loadProjectsList();
            } catch (e) {}
        }

        if (targetId) {
            await projectsUIController.openProjectSettingsModal(targetId);
        }

        const closeBtn = document.getElementById("close-project-settings-btn");
        const onModalClosed = () => {
            closeBtn?.removeEventListener("click", onModalClosed);
            this.evaluateStatus().then(status => {
                if (status.needsSetup) this.open();
            });
        };
        closeBtn?.addEventListener("click", onModalClosed);
    },

    startCoding() {
        const strategy = document.getElementById("wiz-select-strategy")?.value || "auto";
        const mainSelect = document.getElementById("strategy-select");
        if (mainSelect) {
            mainSelect.value = strategy;
            mainSelect.dispatchEvent(new Event("change"));
        }

        this.close();
        chatUIController.newChat(true);

        const promptInput = document.getElementById("prompt-input");
        promptInput?.focus();
        showToast("Ready! Ask RuntimeForce anything to begin.", "success");
    }
};
