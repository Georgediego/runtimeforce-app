/**
 * Auth Frontend Service with SQLite-backed Cross-Origin Handshake.
 * Seamlessly authenticates via central SaaS (https://runtimeforce.dev)
 * and automatically inherits existing server sessions.
 */
import { eventBus } from "../core/event_bus.js";
import { renderProfileAvatars } from "./avatar_ui_service.js";

const SAAS_URL = "https://runtimeforce.dev";

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
        // 1. Прием токена через редирект с сервера (например, кнопка "Authorize Local IDE" из кабинета)
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
            return;
        }

        // 2. Если уже авторизован локально
        if (this.isAuthenticated()) {
            this.hideAuth();
            this.refreshEntitlements(this.getToken()).catch(() => {});
            eventBus.emit("auth:success", { email: this.getEmail(), plan: this.getPlan() });
            return;
        }

        // 3. Тихая фоновая проверка активной сессии с сервера
        await this.syncSessionFromServer();

        // 4. Привязка кнопки 1-кликовой синхронизации на оверлее
        document.getElementById("rf-auth-sync-btn")?.addEventListener("click", () => {
            this.syncViaPopup();
        });
    },

    async syncSessionFromServer() {
        try {
            const res = await fetch(`${SAAS_URL}/api/v1/auth/session-sync`, {
                credentials: "include"
            });
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated && data.token) {
                    this.setSession(data.token, data.plan, data.email, data.avatar);
                    return;
                }
            }
        } catch (e) {
            console.debug("Silent session sync skipped:", e);
        }
        
        if (!this.isAuthenticated()) {
            this.showAuth();
            eventBus.emit("auth:required");
        }
    },

    async _createPkceRequest() {
        if (!window.crypto?.subtle || !window.crypto?.getRandomValues) {
            throw new Error("Secure browser cryptography is unavailable");
        }
        const encode = (bytes) => btoa(String.fromCharCode(...bytes))
            .replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/g, "");
        const random = () => window.crypto.getRandomValues(new Uint8Array(32));
        const ticket = encode(random());
        const verifier = encode(random());
        const state = encode(random());
        const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
        return { ticket, verifier, state, challenge: encode(new Uint8Array(digest)) };
    },

    async _startPkceLogin(provider = null) {
        const popup = window.open("about:blank", "rf_sync_popup", "width=520,height=680");
        if (!popup) {
            console.warn("Allow popups to sign in to RuntimeForce.");
            return;
        }
        if (this._pollInterval) clearInterval(this._pollInterval);
        let completed = false;
        let exchanging = false;
        const cleanup = () => {
            if (this._pollInterval) { clearInterval(this._pollInterval); this._pollInterval = null; }
            if (popup && !popup.closed) { try { popup.close(); } catch (e) {} }
        };
        try {
            const pkce = await this._createPkceRequest();
            const params = new URLSearchParams({
                ticket: pkce.ticket,
                code_challenge: pkce.challenge,
                state: pkce.state,
                origin: window.location.origin
            });
            if (provider) params.set("provider", provider);
            popup.location.href = `${SAAS_URL}/auth/connect-client?${params.toString()}`;

            this._pollInterval = setInterval(async () => {
                if (completed || exchanging) return;
                try {
                    const pollUrl = `${SAAS_URL}/api/v1/auth/poll-ticket?ticket=${encodeURIComponent(pkce.ticket)}&state=${encodeURIComponent(pkce.state)}`;
                    const response = await fetch(pollUrl, { credentials: "omit", cache: "no-store" });
                    if (!response.ok) return;
                    const result = await response.json();
                    if (!result.ready || !result.code) return;
                    exchanging = true;
                    const exchange = await fetch(`${SAAS_URL}/api/v1/auth/exchange-code`, {
                        method: "POST",
                        credentials: "omit",
                        headers: { "Content-Type": "application/json", "Accept": "application/json" },
                        body: JSON.stringify({ code: result.code, code_verifier: pkce.verifier, state: pkce.state })
                    });
                    const auth = await exchange.json();
                    if (!exchange.ok || !auth.access_token) {
                        throw new Error(auth.detail || "Desktop authorization failed");
                    }
                    completed = true;
                    cleanup();
                    this.setSession(auth.access_token, auth.plan, auth.email, auth.avatar);
                    window.location.reload();
                } catch (error) {
                    exchanging = false;
                    console.debug("PKCE authorization polling:", error);
                }
            }, 800);
            setTimeout(() => { if (!completed) cleanup(); }, 180000);
        } catch (error) {
            cleanup();
            console.error("Could not start secure RuntimeForce login:", error);
        }
    },

    syncViaPopup() {
        return this._startPkceLogin();
    },

    async refreshEntitlements(accessToken) {
        if (!accessToken) return false;
        try {
            const response = await fetch(`${SAAS_URL}/api/v1/auth/entitlements`, {
                method: "GET",
                headers: { "Authorization": `Bearer ${accessToken}`, "Accept": "application/json" },
                credentials: "omit"
            });
            if (!response.ok) return false;

            const data = await response.json();
            if (!data.entitlement_token) return false;

            const localResponse = await fetch(`${window.location.origin}/api/v1/billing/entitlements`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${accessToken}`,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ entitlement_token: data.entitlement_token })
            });
            return localResponse.ok;
        } catch (error) {
            console.debug("Entitlement refresh unavailable; using verified local cache:", error);
            return false;
        }
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
        this.refreshEntitlements(token).catch(() => {});
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
        const token = this.getToken();
        if (token) {
            fetch(`${window.location.origin}/api/v1/billing/entitlements`, {
                method: "DELETE",
                headers: { "Authorization": `Bearer ${token}` }
            }).catch(() => {});
        }
        localStorage.removeItem("rf_jwt_token");
        localStorage.removeItem("access_token");
        localStorage.removeItem("rf_plan");
        localStorage.removeItem("rf_email");
        localStorage.removeItem("rf_avatar");
        this.showAuth();
        eventBus.emit("auth:required");
    },

    oauth(provider) {
        return this._startPkceLogin(provider);
    }
};
