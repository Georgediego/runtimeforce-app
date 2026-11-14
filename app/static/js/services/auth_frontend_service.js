/**
 * Auth Frontend Service with SQLite-backed Cross-Origin Handshake.
 * Seamlessly authenticates via central SaaS (https://runtimeforce.dev)
 * and automatically inherits existing server sessions.
 */
import { eventBus } from "../core/event_bus.js";
import { renderProfileAvatars } from "./avatar_ui_service.js";

const SAAS_URL = "https://runtimeforce.dev";

function generateTicket() {
    const array = new Uint8Array(24);
    if (typeof crypto !== "undefined" && crypto.getRandomValues) {
        crypto.getRandomValues(array);
    } else {
        for (let i = 0; i < array.length; i++) {
            array[i] = Math.floor(Math.random() * 256);
        }
    }
    return Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
}

export const authFrontendService = {
    _pollInterval: null,

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

    async init() {
        this.bindAuthSyncButton();

        // Прием токена через редирект из кабинета.
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get("rf_token");
        if (token) {
            this.setSession(
                token,
                urlParams.get("rf_plan") || "free",
                urlParams.get("rf_email") || "",
                urlParams.get("rf_avatar") || ""
            );
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        // Всегда пробуем обновить короткоживущий access token через HttpOnly
        // refresh cookie. Наличие строки токена в localStorage не доказывает,
        // что токен еще действителен.
        const hadLocalToken = this.isAuthenticated();
        const synced = await this.syncSessionFromServer();
        if (synced) return;

        if (hadLocalToken) {
            // Не стираем токен при временной сетевой ошибке. Первый API 401
            // запустит контролируемое восстановление сессии.
            this.hideAuth();
            eventBus.emit("auth:success", { email: this.getEmail(), plan: this.getPlan() });
            return;
        }

        this.showAuth();
        eventBus.emit("auth:required");
    },

    bindAuthSyncButton() {
        if (this._authSyncBound) return;
        const button = document.getElementById("rf-auth-sync-btn");
        if (!button) return;
        button.addEventListener("click", () => this.syncViaPopup());
        this._authSyncBound = true;
    },

    async syncSessionFromServer() {
        try {
            const res = await fetch(`${SAAS_URL}/api/v1/auth/session-sync`, {
                credentials: "include",
                cache: "no-store"
            });
            if (!res.ok) return false;
            const data = await res.json();
            if (data.authenticated && data.token) {
                this.setSession(data.token, data.plan, data.email, data.avatar);
                return true;
            }
        } catch (e) {
            console.debug("Silent session sync skipped:", e);
        }
        return false;
    },

    async recoverSession() {
        try {
            const res = await fetch(`${SAAS_URL}/api/v1/auth/session-sync`, {
                credentials: "include",
                cache: "no-store"
            });
            if (!res.ok) {
                // 5xx/429 are transient: keep the current token and local data.
                if (res.status < 500 && res.status !== 429) this.invalidateSession();
                return false;
            }
            const data = await res.json();
            if (data.authenticated && data.token) {
                this.setSession(data.token, data.plan, data.email, data.avatar);
                return true;
            }
            this.invalidateSession();
            return false;
        } catch (e) {
            console.warn("Session recovery unavailable:", e);
            return false;
        }
    },

    invalidateSession() {
        // Remove credentials only. Provider keys, projects, workspaces,
        // conversations and all other SQLite data must remain untouched.
        localStorage.removeItem("rf_jwt_token");
        localStorage.removeItem("access_token");
        this.showAuth();
        eventBus.emit("auth:required");
    },

    syncViaPopup() {
        const ticket = generateTicket();

        const origin = encodeURIComponent(window.location.origin);
        const syncUrl = `${SAAS_URL}/auth/connect-client?ticket=${encodeURIComponent(ticket)}&origin=${origin}`;

        const onMessage = (e) => {
            if (e.data && (e.data.type === "rf_auth_success" || e.data.type === "rf_auth_sync")) {
                if (e.data.token) {
                    cleanup();
                    this.setSession(e.data.token, e.data.plan, e.data.email, e.data.avatar);
                    window.location.reload();
                }
            }
        };
        window.addEventListener("message", onMessage);

        if (this._pollInterval) clearInterval(this._pollInterval);
        this._pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`${SAAS_URL}/api/v1/auth/poll-ticket?ticket=${encodeURIComponent(ticket)}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.ready && data.token) {
                        cleanup();
                        this.setSession(data.token, data.plan, data.email, data.avatar);
                        window.location.reload();
                    }
                }
            } catch (pollErr) {}
        }, 800);

        const cleanup = () => {
            if (this._pollInterval) {
                clearInterval(this._pollInterval);
                this._pollInterval = null;
            }
            window.removeEventListener("message", onMessage);
        };

        setTimeout(cleanup, 180000);
        window.open(syncUrl, "rf_sync_popup", "width=500,height=600");
    },

    setSession(token, plan, email, avatar) {
        localStorage.setItem("rf_jwt_token", token);
        localStorage.setItem("rf_plan", plan || "free");
        localStorage.setItem("rf_email", email || "");
        if (avatar) {
            localStorage.setItem("rf_avatar", avatar);
        }
        this.hideAuth();
        this.updateProfileUI();
        eventBus.emit("auth:success", { email, plan });
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
        const ticket = generateTicket();

        const origin = encodeURIComponent(window.location.origin);
        const authUrl = `${SAAS_URL}/auth/${provider}?ticket=${encodeURIComponent(ticket)}&origin=${origin}`;

        const onMessage = (e) => {
            if (e.data && (e.data.type === "rf_auth_success" || e.data.type === "rf_auth_sync")) {
                if (e.data.token) {
                    cleanup();
                    this.setSession(e.data.token, e.data.plan, e.data.email, e.data.avatar);
                    window.location.reload();
                }
            }
        };
        window.addEventListener("message", onMessage);

        if (this._pollInterval) clearInterval(this._pollInterval);
        this._pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`${SAAS_URL}/api/v1/auth/poll-ticket?ticket=${encodeURIComponent(ticket)}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.ready && data.token) {
                        cleanup();
                        this.setSession(data.token, data.plan, data.email, data.avatar);
                        window.location.reload();
                    }
                }
            } catch (pollErr) {}
        }, 1000);

        const cleanup = () => {
            if (this._pollInterval) {
                clearInterval(this._pollInterval);
                this._pollInterval = null;
            }
            window.removeEventListener("message", onMessage);
        };

        setTimeout(cleanup, 300000);
        window.open(authUrl, "_blank");
    }
};
