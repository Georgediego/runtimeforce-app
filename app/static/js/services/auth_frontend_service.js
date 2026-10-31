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
        if (!this._storageHandlerBound) {
            this._storageHandlerBound = true;
            window.addEventListener("storage", (event) => {
                if (event.key === "rf_jwt_token" && event.newValue && !this.isAuthenticated()) {
                    this.setSession(event.newValue, localStorage.getItem("rf_plan"), localStorage.getItem("rf_email"), localStorage.getItem("rf_avatar"));
                    window.location.reload();
                }
                if (event.key === "rf_provider_oauth_result" && event.newValue) {
                    try {
                        const result = JSON.parse(event.newValue);
                        localStorage.removeItem("rf_provider_oauth_result");
                        eventBus.emit("auth:provider_oauth_success", result);
                    } catch (error) { console.error("Invalid provider OAuth result", error); }
                }
                if (event.key === "rf_pkce_error" && event.newValue) {
                    console.error(event.newValue);
                    localStorage.removeItem("rf_pkce_error");
                }
            });
        }
        const params = new URLSearchParams(window.location.search);
        const callbackCode = params.get("rf_auth_code");
        const callbackState = params.get("rf_auth_state");
        if (callbackCode || callbackState) {
            await this._completePkceCallback(callbackCode, callbackState);
            return;
        }

        if (this.isAuthenticated()) {
            this.hideAuth();
            this.refreshEntitlements(this.getToken()).catch(() => {});
            eventBus.emit("auth:success", { email: this.getEmail(), plan: this.getPlan() });
            return;
        }

        await this.syncSessionFromServer();
        document.getElementById("rf-auth-sync-btn")?.addEventListener("click", () => {
            this.syncViaPopup();
        });
    },

    async _completePkceCallback(code, state) {
        const fail = (message) => {
            localStorage.removeItem("rf_pkce_pending");
            localStorage.setItem("rf_pkce_error", String(message || "RuntimeForce login failed"));
            console.error("RuntimeForce login failed:", message);
            window.close();
        };
        try {
            const pending = JSON.parse(localStorage.getItem("rf_pkce_pending") || "null");
            if (!code || !state || !pending?.verifier || pending.state !== state || Date.now() - pending.createdAt > 180000) {
                fail("The login request expired or the browser state did not match. Start sign-in again.");
                return;
            }
            const response = await fetch(`${SAAS_URL}/api/v1/auth/exchange-code`, {
                method: "POST",
                credentials: "omit",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify({ code, code_verifier: pending.verifier, state })
            });
            const auth = await response.json();
            if (!response.ok || !auth.access_token) {
                fail(auth.detail || "Desktop authorization failed");
                return;
            }
            localStorage.removeItem("rf_pkce_pending");
            window.history.replaceState({}, document.title, window.location.pathname);
            if (auth.purpose === "provider_link") {
                if (!auth.provider_token || !auth.provider) {
                    fail("Provider authorization did not return a usable token.");
                    return;
                }
                localStorage.setItem("rf_provider_oauth_result", JSON.stringify({
                    provider: auth.provider,
                    provider_token: auth.provider_token,
                    username: auth.username,
                    email: auth.email,
                    project_id: pending.context?.project_id || "default"
                }));
                window.close();
                return;
            }
            this.setSession(auth.access_token, auth.plan, auth.email, auth.avatar);
            window.close();
        } catch (error) {
            fail(error.message || "Desktop authorization failed");
        }
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
            .replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
        const random = () => window.crypto.getRandomValues(new Uint8Array(32));
        const ticket = encode(random());
        const verifier = encode(random());
        const state = encode(random());
        const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
        return { ticket, verifier, state, challenge: encode(new Uint8Array(digest)) };
    },

    async _startPkceLogin(provider = null, purpose = "login", context = {}) {
        if (this._authPopup && !this._authPopup.closed) this._authPopup.close();
        const popup = window.open("about:blank", "rf_sync_popup", "width=520,height=680");
        if (!popup) {
            console.warn("Allow popups to sign in to RuntimeForce.");
            return;
        }
        this._authPopup = popup;
        try {
            const pkce = await this._createPkceRequest();
            localStorage.setItem("rf_pkce_pending", JSON.stringify({
                verifier: pkce.verifier, state: pkce.state, purpose, context, createdAt: Date.now()
            }));
            const params = new URLSearchParams({
                ticket: pkce.ticket,
                code_challenge: pkce.challenge,
                state: pkce.state,
                origin: window.location.origin,
                purpose
            });
            if (provider) params.set("provider", provider);
            popup.location.href = `${SAAS_URL}/auth/connect-client?${params.toString()}`;
            this._authTimeout = setTimeout(() => {
                const pending = JSON.parse(localStorage.getItem("rf_pkce_pending") || "null");
                if (pending?.state === pkce.state) localStorage.removeItem("rf_pkce_pending");
                this._authPopup = null;
                if (!popup.closed) popup.close();
            }, 180000);
        } catch (error) {
            localStorage.removeItem("rf_pkce_pending");
            this._authPopup = null;
            if (!popup.closed) popup.close();
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

    connectProviderOAuth(provider, projectId) {
        return this._startPkceLogin(provider, "provider_link", { project_id: projectId });
    },

    oauth(provider) {
        return this._startPkceLogin(provider, "login");
    }
};
