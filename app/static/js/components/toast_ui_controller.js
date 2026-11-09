/**
 * Toast Notifications, Prompts & Global Dangerous Command Approval Modal with Sudo Password (Section 15.5).
 */
function errorText(value) {
    if (value instanceof Error) return value.message || value.name || "Unknown error";
    if (typeof value === "string") return value.trim() || "Unknown error";
    if (value && typeof value === "object") {
        for (const key of ["message", "detail", "error", "reason", "description"]) {
            const candidate = value[key];
            if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
            if (candidate && typeof candidate === "object") return errorText(candidate);
        }
        try { return JSON.stringify(value, null, 2); } catch (_) { return "Unknown application error"; }
    }
    return String(value ?? "Unknown error");
}

export function showToast(message, type = "info", duration = 3000) {
    let container = document.getElementById("rf-toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "rf-toast-container";
        container.className = "fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    const isError = type === "error";
    const icon = type === "success" ? "check-circle" : isError ? "x-circle" : type === "warning" ? "alert-triangle" : "info";
    const iconColor = type === "success" ? "text-[var(--ide-success)]" : isError ? "text-[var(--ide-error)]" : type === "warning" ? "text-[var(--ide-warning)]" : "text-[var(--ide-accent)]";
    const detail = errorText(message);
    const heading = isError ? "Application error" : type === "success" ? "Success" : type === "warning" ? "Warning" : "Notification";
    toast.className = `rf-toast-notification flex items-start gap-3 px-4 py-3 rounded-xl border shadow-2xl transform transition-all duration-300 translate-y-4 opacity-0 pointer-events-auto border-[var(--ide-border-subtle)] min-w-[280px] max-w-md`;
    toast.innerHTML = `
        <div class="mt-0.5 shrink-0"><i data-lucide="${icon}" class="w-4 h-4 ${iconColor}"></i></div>
        <div class="flex-1 min-w-0">
            <div class="text-sm font-semibold text-[var(--ide-text-primary)] leading-tight rf-toast-heading"></div>
            <div class="text-xs text-[var(--ide-text-secondary)] leading-relaxed mt-1 rf-toast-message whitespace-pre-wrap break-words"></div>
            ${isError ? '<div class="flex gap-2 mt-3"><button class="rf-toast-report px-3 py-1.5 rounded-lg text-[11px] font-bold bg-[var(--ide-accent)] text-black hover:brightness-110">Send to developer</button><span class="rf-toast-report-status text-[10px] text-[var(--ide-text-muted)] self-center"></span></div>' : ''}
        </div>
        <button class="shrink-0 text-[var(--ide-text-muted)] hover:text-[var(--ide-text-primary)] toast-close cursor-pointer" aria-label="Close"><i data-lucide="x" class="w-4 h-4"></i></button>
    `;
    toast.querySelector(".rf-toast-heading").textContent = heading;
    toast.querySelector(".rf-toast-message").textContent = detail;
    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons({ root: toast });
    requestAnimationFrame(() => toast.classList.remove("translate-y-4", "opacity-0"));
    const close = () => {
        toast.classList.add("translate-y-4", "opacity-0");
        setTimeout(() => toast.remove(), 300);
    };
    toast.querySelector(".toast-close")?.addEventListener("click", close);
    if (isError) {
        const reportButton = toast.querySelector(".rf-toast-report");
        const reportStatus = toast.querySelector(".rf-toast-report-status");
        reportButton?.addEventListener("click", async () => {
            reportButton.disabled = true;
            reportButton.textContent = "Sending…";
            try {
                const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
                const clientInstanceId = localStorage.getItem("rf_client_instance_id") || (crypto.randomUUID ? crypto.randomUUID() : "rf-" + Date.now() + "-" + Math.random().toString(36).slice(2));
                localStorage.setItem("rf_client_instance_id", clientInstanceId);
                const response = await fetch("https://runtimeforce.dev/api/v1/bug-reports", {
                    method: "POST",
                    credentials: "include",
                    headers: {
                        "Content-Type": "application/json",
                        ...(token ? { "Authorization": `Bearer ${token.replace(/^Bearer\s+/i, "")}` } : {})
                    },
                    body: JSON.stringify({
                        title: "RuntimeForce IDE error",
                        message: detail.slice(0, 8000),
                        component: "IDE Notification",
                        diagnostics: {
                            app_version: document.documentElement.dataset.appVersion || "unknown",
                            url: location.pathname,
                            user_agent: navigator.userAgent,
                            occurred_at: new Date().toISOString(),
                            client_instance_id: clientInstanceId
                        }
                    })
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
                reportButton.textContent = "Sent";
                reportStatus.textContent = "Report received by the developer";
            } catch (error) {
                reportButton.disabled = false;
                reportButton.textContent = "Retry";
                reportStatus.textContent = errorText(error).slice(0, 100);
            }
        });
    } else if (duration > 0) {
        setTimeout(close, duration);
    }
}

export function showConfirm(title, message, confirmText = "Confirm", cancelText = "Cancel") {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.className = "fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-md rf-modal-backdrop animate-fadeIn";
        overlay.innerHTML = `
            <div class="rf-glass-surface border border-[var(--ide-border-subtle)] rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4 flex flex-col gap-3">
                <div class="text-base font-bold text-[var(--ide-text-primary)]">${title}</div>
                <div class="text-xs text-[var(--ide-text-secondary)] leading-relaxed">${message}</div>
                <div class="flex items-center justify-end gap-2 pt-2">
                    <button class="px-3.5 py-1.5 rounded-lg text-xs font-medium text-[var(--ide-text-secondary)] hover:bg-[var(--ide-elevated)] confirm-cancel cursor-pointer transition-colors">${cancelText}</button>
                    <button class="px-4 py-1.5 rounded-lg text-xs font-bold bg-red-500 text-white confirm-ok cursor-pointer hover:bg-red-600 transition-all">${confirmText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const close = (result) => {
            overlay.remove();
            resolve(result);
        };

        overlay.querySelector(".confirm-cancel")?.addEventListener("click", () => close(false));
        overlay.querySelector(".confirm-ok")?.addEventListener("click", () => close(true));
    });
}

export function showPrompt(title, message = "", defaultValue = "", confirmText = "Save", cancelText = "Cancel") {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.className = "fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-md rf-modal-backdrop animate-fadeIn";
        const escapedValue = (defaultValue || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        overlay.innerHTML = `
            <div class="rf-glass-surface border border-[var(--ide-border-subtle)] rounded-xl shadow-2xl p-5 max-w-md w-full mx-4 flex flex-col gap-3">
                <div class="text-sm font-bold text-[var(--ide-text-primary)]">${title}</div>
                ${message ? `<div class="text-xs text-[var(--ide-text-muted)]">${message}</div>` : ''}
                <input type="text" id="rf-prompt-input" value="${escapedValue}" class="w-full bg-[var(--ide-bg)] border border-[var(--ide-border-subtle)] rounded-lg px-3 py-2 text-xs text-[var(--ide-text-primary)] outline-none focus:border-[var(--ide-accent)] font-sans">
                <div class="flex items-center justify-end gap-2 pt-2">
                    <button class="px-3.5 py-1.5 rounded-lg text-xs font-medium text-[var(--ide-text-secondary)] hover:bg-[var(--ide-elevated)] confirm-cancel cursor-pointer transition-colors">${cancelText}</button>
                    <button class="px-4 py-1.5 rounded-lg text-xs font-bold bg-[var(--ide-accent)] text-black confirm-ok cursor-pointer hover:brightness-110 transition-all">${confirmText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        const input = overlay.querySelector("#rf-prompt-input");
        input?.focus();

        const close = (result) => {
            overlay.remove();
            resolve(result);
        };

        input?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") close(input.value.trim());
            if (e.key === "Escape") close(null);
        });

        overlay.querySelector(".confirm-cancel")?.addEventListener("click", () => close(null));
        overlay.querySelector(".confirm-ok")?.addEventListener("click", () => close(input ? input.value.trim() : null));
    });
}

export function showMultiLinePrompt(title, message = "", defaultValue = "", confirmText = "Resend", cancelText = "Cancel") {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.className = "fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-md rf-modal-backdrop animate-fadeIn";
        const escapedValue = (defaultValue || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        overlay.innerHTML = `
            <div class="rf-glass-surface border border-[var(--ide-border-subtle)] rounded-2xl shadow-2xl p-6 max-w-2xl w-full mx-4 flex flex-col gap-4">
                <div class="text-base font-bold text-[var(--ide-text-primary)]">${title}</div>
                ${message ? `<div class="text-xs text-[var(--ide-text-muted)]">${message}</div>` : ''}
                <textarea id="rf-multiline-prompt-input" rows="8" class="w-full bg-[var(--ide-bg)] border border-[var(--ide-border-subtle)] rounded-xl p-3 text-xs text-[var(--ide-text-primary)] outline-none focus:border-[var(--ide-accent)] font-sans resize-y leading-relaxed max-h-[300px] min-h-[120px]">${escapedValue}</textarea>
                <div class="flex items-center justify-end gap-2 pt-2 border-t border-[var(--ide-border-subtle)]">
                    <button class="px-4 py-2 rounded-lg text-xs font-medium text-[var(--ide-text-secondary)] hover:bg-[var(--ide-elevated)] confirm-cancel cursor-pointer transition-colors">${cancelText}</button>
                    <button class="px-5 py-2 rounded-lg text-xs font-bold bg-[var(--ide-accent)] text-black confirm-ok cursor-pointer hover:brightness-110 transition-all">${confirmText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        const textarea = overlay.querySelector("#rf-multiline-prompt-input");
        textarea?.focus();

        const close = (result) => {
            overlay.remove();
            resolve(result);
        };

        textarea?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) close(textarea.value.trim());
            if (e.key === "Escape") close(null);
        });

        overlay.querySelector(".confirm-cancel")?.addEventListener("click", () => close(null));
        overlay.querySelector(".confirm-ok")?.addEventListener("click", () => close(textarea ? textarea.value.trim() : null));
    });
}

export function showCommandApprovalModal(command, reason = "", options = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById("command-approval-modal");
        const cmdBox = document.getElementById("approval-cmd-box");
        const contextBox = document.getElementById("approval-context-box");
        const decisionSelect = document.getElementById("approval-decision-select");
        const allowBtn = document.getElementById("approval-allow-btn");
        const denyBtn = document.getElementById("approval-deny-btn");

        if (cmdBox) cmdBox.textContent = command || "";
        if (contextBox) {
            contextBox.replaceChildren();
            const contextText = reason || "This command is awaiting your approval. It will not run until you decide.";
            contextText.split(" · ").forEach((part, index) => {
                if (index) contextBox.appendChild(document.createTextNode(" · "));
                const separator = part.indexOf(":");
                if (separator < 0) {
                    contextBox.appendChild(document.createTextNode(part));
                    return;
                }
                const label = document.createElement("span");
                label.className = "rf-approval-context-label";
                label.textContent = part.slice(0, separator + 1) + " ";
                const value = document.createElement("strong");
                value.className = "rf-approval-context-value";
                value.textContent = part.slice(separator + 1).trim();
                contextBox.append(label, value);
            });
        }
        if (decisionSelect) {
            decisionSelect.value = "once";
            const sessionOption = decisionSelect.querySelector('option[value="session"]');
            const workspaceOption = decisionSelect.querySelector('option[value="workspace"]');
            const projectOption = decisionSelect.querySelector('option[value="project"]');
            if (sessionOption) sessionOption.disabled = !options.sessionAvailable;
            if (workspaceOption) workspaceOption.disabled = !options.workspaceAvailable;
            if (projectOption) projectOption.disabled = !options.projectAvailable;
        }
        if (modal) {
            modal.classList.remove("hidden");
            modal.style.display = "flex";
        }

        let settled = false;
        const close = (choice) => {
            if (settled) return;
            settled = true;
            window.removeEventListener("rf:cancel-command-approval", cancelApproval);
            if (modal) {
                modal.classList.add("hidden");
                modal.style.display = "none";
            }
            resolve(choice);
        };
        const cancelApproval = () => close("cancelled");
        window.addEventListener("rf:cancel-command-approval", cancelApproval, { once: true });
        if (allowBtn) allowBtn.onclick = () => close(decisionSelect?.value || "once");
        if (denyBtn) denyBtn.onclick = () => close("deny");
    });
}

function initRuntimeForceTooltips() {
    if (typeof document === "undefined") return;
    const enhance = (element) => {
        const title = element.getAttribute("title");
        if (!title || !title.trim()) return;
        element.setAttribute("data-rf-tooltip", title);
        element.removeAttribute("title");
        if (!element.hasAttribute("aria-label")) element.setAttribute("aria-label", title);
    };
    document.querySelectorAll("[title]").forEach(enhance);
    if (typeof MutationObserver !== "undefined") {
        new MutationObserver((records) => records.forEach((record) => {
            if (record.type === "attributes" && record.attributeName === "title") enhance(record.target);
            record.addedNodes?.forEach((node) => {
                if (node.nodeType !== 1) return;
                if (node.hasAttribute("title")) enhance(node);
                node.querySelectorAll?.("[title]").forEach(enhance);
            });
        })).observe(document.documentElement, {
            subtree: true, childList: true, attributes: true, attributeFilter: ["title"],
        });
    }
}

initRuntimeForceTooltips();


// Surface otherwise-unhandled frontend failures in the persistent error center.
if (typeof window !== "undefined" && !window.__rfGlobalErrorToastsBound) {
    window.__rfGlobalErrorToastsBound = true;
    window.addEventListener("unhandledrejection", (event) => {
        const reason = event.reason;
        showToast(reason ?? "Unknown async error", "error", 0);
    });
    window.addEventListener("error", (event) => {
        if (!event.message) return;
        showToast(`Application error: ${event.message}`, "error", 0);
    });
}


// Persistent developer inbox in the user profile area.
if (typeof window !== "undefined" && !window.__rfInboxStarted) {
    window.__rfInboxStarted = true;
    const API = "https://runtimeforce.dev/api/v1/bug-reports";
    const authHeaders = () => {
        const token = (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer\s+/i, "");
        return token ? { Authorization: "Bearer " + token } : {};
    };
    const escInbox = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    let inboxItems = [];

    function ensureInboxUI() {
        const profile = document.getElementById("rf-user-profile");
        if (!profile || document.getElementById("rf-inbox-button")) return;
        const button = document.createElement("button");
        button.id = "rf-inbox-button";
        button.type = "button";
        button.className = "relative w-8 h-8 rounded-full hover:bg-[var(--ide-elevated)] flex items-center justify-center text-[var(--ide-text-secondary)] cursor-pointer";
        button.setAttribute("aria-label", "Developer inbox");
        button.innerHTML = '<i data-lucide="mail" class="w-4 h-4"></i><span id="rf-inbox-badge" class="hidden absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-red-500 text-white text-[9px] leading-4 font-bold text-center"></span>';
        const panel = document.createElement("section");
        panel.id = "rf-inbox-panel";
        panel.className = "hidden absolute top-10 right-0 z-[250] w-[min(390px,calc(100vw-24px))] max-h-[min(70vh,620px)] overflow-hidden rounded-xl border border-[var(--ide-border-subtle)] bg-[var(--ide-surface)] shadow-2xl";
        panel.innerHTML = '<div class="flex items-center justify-between px-3 py-3 border-b border-[var(--ide-border-subtle)]"><div class="text-xs font-bold text-[var(--ide-text-primary)]">Developer messages</div><button type="button" id="rf-inbox-refresh" class="text-[10px] text-[var(--ide-text-muted)] hover:text-[var(--ide-text-primary)]">Refresh</button></div><div id="rf-inbox-list" class="overflow-y-auto max-h-[calc(min(70vh,620px)-48px)] p-2 space-y-2"><div class="p-4 text-xs text-[var(--ide-text-muted)]">Loading messages…</div></div>';
        profile.insertBefore(button, profile.firstChild);
        profile.appendChild(panel);
        button.addEventListener("click", event => {
            event.stopPropagation();
            panel.classList.toggle("hidden");
            if (!panel.classList.contains("hidden")) loadInbox(true);
        });
        panel.addEventListener("click", event => event.stopPropagation());
        panel.querySelector("#rf-inbox-refresh")?.addEventListener("click", () => loadInbox(true));
        document.addEventListener("click", event => {
            if (!panel.contains(event.target) && !button.contains(event.target)) panel.classList.add("hidden");
        });
        if (window.lucide) window.lucide.createIcons({ root: button });
    }

    function updateBadge(count) {
        const badge = document.getElementById("rf-inbox-badge");
        if (!badge) return;
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.classList.toggle("hidden", !count);
    }

    function renderInbox() {
        const list = document.getElementById("rf-inbox-list");
        if (!list) return;
        if (!inboxItems.length) {
            list.innerHTML = '<div class="p-5 text-center text-xs text-[var(--ide-text-muted)]">No messages yet.</div>';
            return;
        }
        list.innerHTML = inboxItems.map(item => {
            const messages = (item.messages || []).map(message => {
                const own = message.sender === "user";
                return '<div class="rounded-lg p-2.5 ' + (own ? 'bg-[var(--ide-elevated)]' : 'bg-[var(--ide-accent)]/10') + '">' +
                    '<div class="flex justify-between gap-2 text-[9px] text-[var(--ide-text-muted)]"><b>' + (own ? 'You' : 'RuntimeForce Support') + '</b><time>' + escInbox(message.created_at ? new Date(message.created_at).toLocaleString() : '') + '</time></div>' +
                    '<div class="mt-1 text-xs text-[var(--ide-text-primary)] whitespace-pre-wrap break-words">' + escInbox(message.message) + '</div></div>';
            }).join("");
            return '<article class="rounded-lg border border-[var(--ide-border-subtle)] p-2.5 space-y-2" data-inbox-report="' + Number(item.report_id) + '">' +
                '<div class="text-[11px] font-bold text-[var(--ide-text-primary)]">' + escInbox(item.title || 'Support message') + '</div>' +
                '<div class="space-y-2">' + messages + '</div>' +
                '<form class="rf-inbox-reply flex gap-2" data-reply-report="' + Number(item.report_id) + '">' +
                '<textarea rows="2" maxlength="8000" required placeholder="Write a reply…" class="min-w-0 flex-1 resize-y rounded-lg border border-[var(--ide-border-subtle)] bg-[var(--ide-bg)] p-2 text-xs text-[var(--ide-text-primary)] outline-none focus:border-[var(--ide-accent)]"></textarea>' +
                '<button type="submit" class="shrink-0 self-end rounded-lg bg-[var(--ide-accent)] px-3 py-2 text-[10px] font-bold text-black">Send</button></form></article>';
        }).join("");
        list.querySelectorAll(".rf-inbox-reply").forEach(form => form.addEventListener("submit", async event => {
            event.preventDefault();
            const field = form.querySelector("textarea");
            const button = form.querySelector("button");
            const message = field?.value.trim();
            if (!message) return;
            button.disabled = true;
            button.textContent = "Sending…";
            try {
                const response = await fetch(API + "/" + form.dataset.replyReport + "/reply", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", ...authHeaders() },
                    credentials: "include",
                    body: JSON.stringify({ message })
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(payload.detail || "HTTP " + response.status);
                field.value = "";
                await loadInbox(false);
                showToast("Your reply was sent to RuntimeForce Support.", "success", 5000);
            } catch (error) {
                showToast("Could not send reply: " + errorText(error), "error", 0);
            } finally {
                button.disabled = false;
                button.textContent = "Send";
            }
        }));
    }

    async function loadInbox(markRead) {
        ensureInboxUI();
        try {
            const response = await fetch(API + "/inbox", { headers: authHeaders(), credentials: "include", cache: "no-store" });
            if (!response.ok) return;
            const payload = await response.json();
            inboxItems = Array.isArray(payload.items) ? payload.items : [];
            updateBadge(Number(payload.unread_count || 0));
            renderInbox();
            if (markRead) {
                const unreadReports = inboxItems.filter(item => (item.messages || []).some(message => message.unread)).map(item => item.report_id);
                await Promise.all(unreadReports.map(id => fetch(API + "/" + id + "/read", {
                    method: "POST", headers: authHeaders(), credentials: "include"
                }).catch(() => null)));
                if (unreadReports.length) {
                    const refreshed = await fetch(API + "/inbox", { headers: authHeaders(), credentials: "include", cache: "no-store" });
                    if (refreshed.ok) {
                        const data = await refreshed.json();
                        inboxItems = Array.isArray(data.items) ? data.items : [];
                        updateBadge(Number(data.unread_count || 0));
                        renderInbox();
                    }
                }
            }
        } catch (_) {
            const list = document.getElementById("rf-inbox-list");
            if (list) list.innerHTML = '<div class="p-4 text-xs text-red-400">Inbox is temporarily unavailable.</div>';
        }
    }

    function startInbox() {
        ensureInboxUI();
        loadInbox(false);
        window.setInterval(() => loadInbox(false), 30000);
        window.addEventListener("focus", () => loadInbox(false));
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startInbox, { once: true });
    else startInbox();
}
