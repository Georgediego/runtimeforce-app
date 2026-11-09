/**
 * Toast Notifications, Prompts & Global Dangerous Command Approval Modal with Sudo Password (Section 15.5).
 */
export function showToast(message, type = "info", duration = 3000) {
    let container = document.getElementById("rf-toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "rf-toast-container";
        container.className = "fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    let bgClass = "rf-glass-surface border-[var(--ide-border-subtle)]";
    let icon = "info";
    let iconColor = "text-[var(--ide-accent)]";

    if (type === "success") { icon = "check-circle"; iconColor = "text-[var(--ide-success)]"; }
    else if (type === "error") { icon = "x-circle"; iconColor = "text-[var(--ide-error)]"; }
    else if (type === "warning") { icon = "alert-triangle"; iconColor = "text-[var(--ide-warning)]"; }

    toast.className = `flex items-start gap-3 px-4 py-3 rounded-xl border shadow-2xl transform transition-all duration-300 translate-y-4 opacity-0 pointer-events-auto ${bgClass} min-w-[280px] max-w-sm`;
    toast.innerHTML = `
        <div class="mt-0.5 shrink-0"><i data-lucide="${icon}" class="w-4 h-4 ${iconColor}"></i></div>
        <div class="flex-1 text-sm font-medium text-[var(--ide-text-primary)] leading-tight">${message}</div>
        <button class="shrink-0 text-[var(--ide-text-muted)] hover:text-[var(--ide-text-primary)] toast-close cursor-pointer"><i data-lucide="x" class="w-4 h-4"></i></button>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons({ root: toast });

    requestAnimationFrame(() => {
        toast.classList.remove("translate-y-4", "opacity-0");
    });

    const close = () => {
        toast.classList.add("translate-y-4", "opacity-0");
        setTimeout(() => toast.remove(), 300);
    };

    toast.querySelector(".toast-close")?.addEventListener("click", close);
    if (duration > 0) setTimeout(close, duration);
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
