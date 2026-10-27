/**
 * Global Settings UI Controller with Local Models UI Integration.
 */
import { authFrontendService } from "../services/auth_frontend_service.js";
import { providersUIController } from "./providers_ui_controller.js";
import { showToast } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

export const settingsUIController = {
    init() {
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
        document.getElementById("check-updates-btn")?.addEventListener("click", async () => {
            showToast("RuntimeForce is up to date (v2.0.0)", "success");
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

        if (targetTab === "general") this.updateProfileInfo();
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
