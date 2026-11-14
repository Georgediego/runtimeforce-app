const UPDATE_CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000;
const UPDATE_SNOOZE_MS = 4 * 60 * 60 * 1000;
const UPDATE_LAST_CHECK_KEY = "rf_update_last_check_v2";
const UPDATE_SNOOZE_KEY = "rf_update_snooze_v2";

let checkTimer = null;
let checking = false;
let pendingUpdate = null;
let applyingUpdate = false;

function authHeaders(extra = {}) {
    const rawToken = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
    const token = rawToken.startsWith("Bearer ") ? rawToken.slice(7) : rawToken;
    return { ...extra, ...(token ? { "Authorization": "Bearer " + token } : {}) };
}

function readStoredJson(key) {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch { return null; }
}

function isSnoozed(version) {
    const saved = readStoredJson(UPDATE_SNOOZE_KEY);
    return Boolean(saved && saved.version === version && Number(saved.until) > Date.now());
}

function snooze(version) {
    localStorage.setItem(UPDATE_SNOOZE_KEY, JSON.stringify({
        version,
        until: Date.now() + UPDATE_SNOOZE_MS,
    }));
}

function hasBlockingActivity() {
    const stopGenerationButton = document.getElementById("stop-gen-btn");
    if (stopGenerationButton && !stopGenerationButton.classList.contains("hidden")) return true;

    const authOverlay = document.getElementById("rf-auth-overlay");
    if (authOverlay && window.getComputedStyle(authOverlay).display !== "none"
        && !authOverlay.classList.contains("hidden")) return true;

    return [...document.querySelectorAll('[id$="-modal"]')].some((element) => {
        if (element.id === "rf-update-modal" || element.classList.contains("hidden")) return false;
        return window.getComputedStyle(element).display !== "none";
    });
}

function updateCommands() {
    const platform = navigator.userAgentData?.platform || navigator.platform || "";
    if (/win/i.test(platform)) {
        return [
            'Set-Location "$HOME\\.runtimeforce"',
            "git fetch origin main",
            "git pull --ff-only origin main",
            ".\\venv\\Scripts\\python.exe -m pip install -r requirements.txt",
            "",
            "# Then restart RuntimeForce IDE.",
        ].join("\n");
    }
    return [
        'cd "$HOME/Runtimeforce/runtimeforce-app"',
        "git fetch origin main",
        "git pull --ff-only origin main",
        "./venv/bin/python -m pip install -r requirements.txt",
        "",
        "# Then restart RuntimeForce IDE.",
    ].join("\n");
}

function setApplyStatus(message, isError = false) {
    const status = document.getElementById("rf-update-apply-status");
    if (status) {
        status.textContent = message;
        status.classList.toggle("text-red-400", isError);
        status.classList.toggle("text-[var(--ide-text-muted)]", !isError);
    }
    const settingsStatus = document.getElementById("rf-update-settings-status");
    if (settingsStatus && message) settingsStatus.textContent = message;
}

function ensureApplyButton() {
    const copyButton = document.getElementById("rf-update-copy-btn");
    if (!copyButton || document.getElementById("rf-update-apply-btn")) return;
    const button = document.createElement("button");
    button.id = "rf-update-apply-btn";
    button.type = "button";
    button.className = "px-4 py-2.5 rounded-lg bg-[var(--ide-accent)] text-black text-xs font-extrabold hover:brightness-110 transition-all";
    button.textContent = "Update Now";
    button.addEventListener("click", applyUpdate);
    copyButton.parentElement.insertBefore(button, copyButton);

    const status = document.createElement("p");
    status.id = "rf-update-apply-status";
    status.className = "text-[10px] text-[var(--ide-text-muted)] text-center";
    status.setAttribute("aria-live", "polite");
    copyButton.closest("#rf-update-modal")?.querySelector(".border-t")?.after(status);
}

function showUpdateModal(currentVersion, latestVersion) {
    const modal = document.getElementById("rf-update-modal");
    if (!modal) return;
    document.getElementById("rf-update-current-version").textContent = currentVersion;
    document.getElementById("rf-update-latest-version").textContent = latestVersion;
    document.getElementById("rf-update-commands").textContent = updateCommands();
    modal.dataset.latestVersion = latestVersion;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    ensureApplyButton();
    pendingUpdate = null;
}

function hideUpdateModal() {
    const modal = document.getElementById("rf-update-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
}

async function copyUpdateCommands() {
    const text = document.getElementById("rf-update-commands")?.textContent || "";
    const button = document.getElementById("rf-update-copy-btn");
    if (!text) return;
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        const field = document.createElement("textarea");
        field.value = text;
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.appendChild(field);
        field.select();
        document.execCommand("copy");
        field.remove();
    }
    if (button) {
        const previous = button.textContent;
        button.textContent = "Commands copied";
        window.setTimeout(() => { button.textContent = previous; }, 2500);
    }
}

async function applyUpdate() {
    if (applyingUpdate) return;
    const modal = document.getElementById("rf-update-modal");
    const modalIsVisible = modal && !modal.classList.contains("hidden");
    const latestVersion = (modalIsVisible ? modal.dataset.latestVersion : null)
        || pendingUpdate?.latest_version;
    const button = modalIsVisible
        ? document.getElementById("rf-update-apply-btn")
        : document.getElementById("rf-update-settings-apply-btn")
            || document.getElementById("rf-update-apply-btn");
    if (!latestVersion || !button) return;

    applyingUpdate = true;
    button.disabled = true;
    button.textContent = "Updating...";
    setApplyStatus("Preparing the update. Keep RuntimeForce open.");

    try {
        const response = await fetch("/api/v1/updates/apply", {
            method: "POST",
            cache: "no-store",
            headers: authHeaders({ "Accept": "application/json" }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.accepted) {
            throw new Error(result.detail || "Unable to start the update.");
        }

        setApplyStatus("Downloading the release and installing dependencies...");
        const deadline = Date.now() + 10 * 60 * 1000;
        while (Date.now() < deadline) {
            await new Promise((resolve) => window.setTimeout(resolve, 2000));
            try {
                const stateResponse = await fetch("/api/v1/updates/status", { cache: "no-store", headers: authHeaders() });
                if (stateResponse.ok) {
                    const state = await stateResponse.json();
                    if (state.status === "error") throw new Error(state.message || "The update failed.");
                    if (state.status === "installing") setApplyStatus("Installing application dependencies...");
                    if (state.status === "restarting") setApplyStatus("Restarting RuntimeForce IDE...");
                    if (state.status === "idle") {
                        const versionResponse = await fetch("/api/v1/version", { cache: "no-store" });
                        if (versionResponse.ok) {
                            const installed = await versionResponse.json();
                            if (installed.version === latestVersion) {
                                setApplyStatus("Update complete. Reloading RuntimeForce IDE...");
                                window.location.reload();
                                return;
                            }
                        }
                    }
                }
            } catch (error) {
                if (error instanceof Error && !/fetch|network/i.test(error.message)) throw error;
                setApplyStatus("Restarting RuntimeForce IDE...");
            }
        }
        throw new Error("The update is taking longer than expected. Check the IDE service before trying again.");
    } catch (error) {
        setApplyStatus(error.message || "The update failed.", true);
        button.disabled = false;
        button.textContent = "Retry Update";
        applyingUpdate = false;
    }
}

function presentPendingUpdate() {
    if (!pendingUpdate || document.hidden || hasBlockingActivity()) return;
    if (isSnoozed(pendingUpdate.latest_version)) return;
    showUpdateModal(pendingUpdate.current_version, pendingUpdate.latest_version);
}

async function checkForUpdates({ force = false } = {}) {
    if (checking || document.hidden) return;
    const lastCheck = Number(localStorage.getItem(UPDATE_LAST_CHECK_KEY) || 0);
    if (!force && lastCheck && Date.now() - lastCheck < UPDATE_CHECK_INTERVAL_MS) {
        presentPendingUpdate();
        return;
    }

    checking = true;
    try {
        const response = await fetch("/api/v1/updates/check", {
            method: "GET",
            cache: "no-store",
            headers: authHeaders({ "Accept": "application/json" }),
        });
        const status = document.getElementById("rf-update-settings-status");
        const current = document.getElementById("rf-update-settings-current");
        const latest = document.getElementById("rf-update-settings-latest");

        if (!response.ok) {
            if (status) status.textContent = "Unable to check for updates. Please try again.";
            return;
        }
        const result = await response.json();

        // Always show the locally installed version, even if all remote sources fail.
        if (current) current.textContent = result.current_version || "—";
        if (!result.checked) {
            if (latest) latest.textContent = "—";
            if (status) status.textContent = "GitHub is temporarily unavailable";
            pendingUpdate = null;
            return;
        }

        localStorage.setItem(UPDATE_LAST_CHECK_KEY, String(Date.now()));
        if (latest) latest.textContent = result.latest_version || "—";
        if (status) status.textContent = result.update_available
            ? "A new update is available"
            : result.installed_newer
                ? "Installed version is newer than the latest stable release"
                : "You're up to date";

        const settingsApplyButton = document.getElementById("rf-update-settings-apply-btn");
        if (!result.update_available) {
            if (settingsApplyButton) settingsApplyButton.classList.add("hidden");
            pendingUpdate = null;
            return;
        }
        if (settingsApplyButton) settingsApplyButton.classList.remove("hidden");
        pendingUpdate = {
            current_version: result.current_version,
            latest_version: result.latest_version,
        };
        presentPendingUpdate();
    } catch (error) {
        const status = document.getElementById("rf-update-settings-status");
        if (status) status.textContent = "Unable to check for updates. Please try again.";
        console.debug("[Updates] Version check unavailable:", error);
    } finally {
        checking = false;
    }
}

export const updateNotificationService = {
    init() {
        if (checkTimer) return;
        ensureApplyButton();
        document.getElementById("rf-update-later-btn")?.addEventListener("click", () => {
            const version = document.getElementById("rf-update-modal")?.dataset.latestVersion;
            if (version) snooze(version);
            hideUpdateModal();
        });
        document.getElementById("rf-update-copy-btn")?.addEventListener("click", copyUpdateCommands);
        checkForUpdates();
        // A lightweight minute tick only displays a pending notice when the IDE is idle.
        // Network checks remain limited to once every 12 hours.
        checkTimer = window.setInterval(() => checkForUpdates(), 60 * 1000);
    },
    checkNow() {
        return checkForUpdates({ force: true });
    },
    applyNow() {
        return applyUpdate();
    },
};
