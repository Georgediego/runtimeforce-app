/**
 * Global Settings UI Controller with Local Models UI Integration.
 */
import { authFrontendService } from "../services/auth_frontend_service.js";
import { providersUIController } from "./providers_ui_controller.js";
import { showToast } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";
import { updateNotificationService } from "../services/update_notification_service.js";
import { billingApi } from "../core/api_http_client.js";

export const settingsUIController = {
    _features: {},

    async loadPlanFeatures() {
        try {
            const data = await billingApi.entitlements();
            this._features = data?.valid ? (data.features || {}) : {};
        } catch {
            this._features = {};
        }
        const updatesAllowed = this._features.software_updates === true || this._features["software updates"] === true;
        const updatesButton = document.querySelector('.settings-nav-btn[data-tab="updates"]');
        if (updatesButton) {
            updatesButton.disabled = !updatesAllowed;
            updatesButton.title = updatesAllowed ? "" : "Software Updates are not included in your current plan";
            updatesButton.classList.toggle("opacity-40", !updatesAllowed);
            updatesButton.classList.toggle("cursor-not-allowed", !updatesAllowed);
        }
        ["rf-update-settings-check-btn", "rf-update-settings-apply-btn"].forEach((id) => {
            const button = document.getElementById(id);
            if (button) button.disabled = !updatesAllowed;
        });

        const featureStates = [
            { selector: '.right-tab-btn[data-panel="editor"]', feature: "editor" },
            { selector: '.right-tab-btn[data-panel="terminal"]', feature: "terminal" },
        ];
        for (const item of featureStates) {
            const allowed = this._features[item.feature] === true;
            document.querySelectorAll(item.selector).forEach((button) => {
                button.disabled = !allowed;
                button.title = allowed ? "" : item.feature + " is not included in your current plan";
                button.classList.toggle("opacity-40", !allowed);
                button.classList.toggle("cursor-not-allowed", !allowed);
            });
        }
        const editorSave = document.getElementById("editor-save-btn");
        if (editorSave) editorSave.disabled = this._features.editor !== true;
        const terminalInput = document.getElementById("terminal-cmd-input");
        if (terminalInput) terminalInput.disabled = this._features.terminal !== true;
    },

    init() {
        this.loadPlanFeatures();
        document.getElementById("close-settings-btn")?.addEventListener("click", () => this.close());
        const modal = document.getElementById("settings-modal");
        modal?.addEventListener("click", (e) => {
            if (e.target === modal) this.close();
        });
        document.querySelectorAll(".settings-nav-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                this.switchTab(btn.dataset.tab);
            });
        });
        document.getElementById("rf-update-settings-apply-btn")?.addEventListener("click", () => {
            updateNotificationService.applyNow();
        });
        document.getElementById("rf-update-settings-check-btn")?.addEventListener("click", async () => {
            const status = document.getElementById("rf-update-settings-status");
            if (status) status.textContent = "Checking GitHub for updates...";
            await updateNotificationService.checkNow();
            if (status && status.textContent === "Checking GitHub for updates...") {
                status.textContent = "GitHub is temporarily unavailable";
            }
        });
        document.getElementById("clear-chat-btn")?.addEventListener("click", () => {
            const history = document.getElementById("chat-history");
            if (history) history.innerHTML = "";
            showToast("Chat history cleared from UI", "info");
        });

        eventBus.on("settings.modal.opened", (tab) => {
            this.open(tab || "general");
        });
    },

    open(tab = "general") {
        const modal = document.getElementById("settings-modal");
        if (modal) {
            modal.classList.remove("hidden");
            modal.style.display = "flex";
        }
        this.switchTab(tab);
    },

    close() {
        const modal = document.getElementById("settings-modal");
        if (modal) {
            modal.classList.add("hidden");
            modal.style.display = "none";
        }
    },

    async switchTab(targetTab) {
        if (targetTab === "updates" && !(this._features.software_updates === true || this._features["software updates"] === true)) {
            showToast("Software Updates are not included in your current plan.", "warning");
            return;
        }
        document.querySelectorAll(".settings-tab").forEach((t) => {
            t.classList.add("hidden");
            t.style.display = "none";
        });
        const activePanel = document.getElementById(`stab-${targetTab}`);
        if (activePanel) {
            activePanel.classList.remove("hidden");
            activePanel.style.display = "block";
        }
        document.querySelectorAll(".settings-nav-btn").forEach((b) => {
            const isActive = b.dataset.tab === targetTab;
            b.classList.toggle("active", isActive);
        });

        if (targetTab === "general") {
            this.updateProfileInfo();
            updateNotificationService.checkNow();
        }
        if (targetTab === "providers") providersUIController.loadProvidersList();
        if (targetTab === "local-models") providersUIController.renderLocalModelsSection();
    },

    updateProfileInfo() {
        const email = authFrontendService.getEmail() || "User";
        const nameEl = document.getElementById("rf-settings-name");
        if (nameEl) nameEl.textContent = email ? email.split("@")[0] : "User";
        authFrontendService.updateProfileUI();
    }
};
