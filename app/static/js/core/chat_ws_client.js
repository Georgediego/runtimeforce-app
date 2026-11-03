/**
 * RuntimeForce WebSocket Client with Abort Protocol & ATM 5-Role Payload (including Designer).
 */
export class ChatWSClient {
    constructor(sessionId, callbacks = {}) {
        this.sessionId = sessionId;
        this.ws = null;
        this.onEvent = callbacks.onEvent || (() => {});
        this.onError = callbacks.onError || (() => {});
        this.onClose = callbacks.onClose || (() => {});
    }

    connect() {
        return new Promise((resolve, reject) => {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            const proto = location.protocol === "https:" ? "wss:" : "ws:";
            const url = `${proto}//${location.host}/ws/chat/${encodeURIComponent(this.sessionId)}`;
            this.ws = new WebSocket(url);
            this.ws.onopen = () => {
                this.ws.send(JSON.stringify({ action: "authenticate", token: token.replace(/^Bearer\s+/i, "") }));
                resolve();
            };
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.onEvent(data);
                } catch (e) {
                    console.error("WS JSON parse error:", e);
                }
            };
            this.ws.onerror = (err) => {
                this.onError(err);
                reject(err);
            };
            this.ws.onclose = (event) => this.onClose(event);
        });
    }

    send(text, options = {}) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
        this.ws.send(
            JSON.stringify({
                action: "send",
                text: text,
                strategy: options.strategy || "auto",
                model_lock: options.model_lock || null,
                temperature: options.temperature || 0.2,
                enabled_models: options.enabled_models || null,
                atm_architect_model: options.atm_architect_model || null,
                atm_engineer_model: options.atm_engineer_model || null,
                atm_tester_model: options.atm_tester_model || null,
                atm_critic_model: options.atm_critic_model || null,
                atm_designer_model: options.atm_designer_model || null,
            })
        );
        return true;
    }

    abort() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
        this.ws.send(JSON.stringify({ action: "abort" }));
        return true;
    }

    close() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
