/**
 * Auth Frontend Service for managing OAuth login and JWT tokens.
 */
import { eventBus } from "../core/event_bus.js";
import { renderProfileAvatars } from "./avatar_ui_service.js";

export const authFrontendService = {
    getToken() {
        return localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
    },
    getPlan() {
        return localStorage.getItem("rf_plan") || "free";
    },
    getEmail() {
        return localStorage.getItem("rf_email") || "";
    },
    isAuthenticated() {
        return !!this.getToken();
    },
    init() {
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get("rf_token");
        if (token) {
            localStorage.setItem("rf_jwt_token", token);
            localStorage.setItem("rf_plan", urlParams.get("rf_plan") || "free");
            localStorage.setItem("rf_email", urlParams.get("rf_email") || "");
            if (urlParams.get("rf_avatar")) {
                localStorage.setItem("rf_avatar", urlParams.get("rf_avatar"));
            }
            window.history.replaceState({}, document.title, window.location.pathname);
            this.hideAuth();
            eventBus.emit("auth:success", { email: this.getEmail(), plan: this.getPlan() });
            return;
        }
        if (this.isAuthenticated()) {
            this.hideAuth();
            eventBus.emit("auth:success", { email: this.getEmail(), plan: this.getPlan() });
        } else {
            this.showAuth();
            eventBus.emit("auth:required");
        }
    },
    showAuth() {
        const overlay = document.getElementById("rf-auth-overlay");
        if (overlay) {
            overlay.classList.remove("hidden");
            overlay.style.display = "flex";
        }
    },
    hideAuth() {
        const overlay = document.getElementById("rf-auth-overlay");
        if (overlay) {
            overlay.classList.add("hidden");
            overlay.style.display = "none";
        }
        this.updateProfileUI();
    },
    updateProfileUI() {
        const email = this.getEmail();
        const plan = this.getPlan();

        renderProfileAvatars();

        const nameEl = document.getElementById("rf-settings-name");
        if (nameEl) nameEl.textContent = email ? email.split("@")[0] : "User";

        const menuEmail = document.getElementById("rf-menu-email");
        if (menuEmail) menuEmail.textContent = email || "user@example.com";

        document.querySelectorAll("#rf-menu-plan, #rf-settings-plan").forEach(el => {
            el.innerHTML = `${plan.toUpperCase()} Plan <span class="text-[var(--ide-text-secondary)]">→ Upgrade</span>`;
        });
    },
    logout() {
        localStorage.removeItem("rf_jwt_token");
        localStorage.removeItem("access_token");
        localStorage.removeItem("rf_plan");
        localStorage.removeItem("rf_email");
        localStorage.removeItem("rf_avatar");
        this.showAuth();
        eventBus.emit("auth:required");
    },
    oauth(provider) {
        const redirectUri = encodeURIComponent(window.location.origin);
        window.location.href = `https://runtimeforce.dev/auth/${provider}?redirect_uri=${redirectUri}`;
    }
};
