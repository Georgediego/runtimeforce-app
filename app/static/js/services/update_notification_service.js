const UPDATE_CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000;
const UPDATE_SNOOZE_MS = 4 * 60 * 60 * 1000;
const UPDATE_LAST_CHECK_KEY = "rf_update_last_check_v2";
const UPDATE_SNOOZE_KEY = "rf_update_snooze_v2";

let checkTimer = null;
let checking = false;
let pendingUpdate = null;

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
            "# Затем перезапустите RuntimeForce IDE.",
        ].join("\n");
    }
    return [
        'cd "$HOME/Runtimeforce/runtimeforce-app"',
        "git fetch origin main",
        "git pull --ff-only origin main",
        "./venv/bin/python -m pip install -r requirements.txt",
        "",
        "# Затем перезапустите RuntimeForce IDE.",
    ].join("\n");
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
        button.textContent = "Команды скопированы";
        window.setTimeout(() => { button.textContent = previous; }, 2500);
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
            headers: { "Accept": "application/json" },
        });
        if (response.status === 403) {
            const status = document.getElementById("rf-update-settings-status");
            const latest = document.getElementById("rf-update-settings-latest");
            if (latest) latest.textContent = "—";
            if (status) status.textContent = "Software Updates недоступна на вашем тарифе";
            pendingUpdate = null;
            return;
        }
        if (!response.ok) return;
        const result = await response.json();
        const status = document.getElementById("rf-update-settings-status");
        const current = document.getElementById("rf-update-settings-current");
        const latest = document.getElementById("rf-update-settings-latest");

        // Always show the locally installed version, even if all remote sources fail.
        if (current) current.textContent = result.current_version || "—";
        if (!result.checked) {
            if (latest) latest.textContent = "—";
            if (status) status.textContent = "GitHub временно недоступен";
            pendingUpdate = null;
            return;
        }

        localStorage.setItem(UPDATE_LAST_CHECK_KEY, String(Date.now()));
        if (latest) latest.textContent = result.latest_version || "—";
        if (status) status.textContent = result.update_available
            ? "Доступно обновление"
            : result.installed_newer
                ? "Установлена версия новее стабильной"
                : "Установлена последняя версия";

        if (!result.update_available) {
            pendingUpdate = null;
            return;
        }
        pendingUpdate = {
            current_version: result.current_version,
            latest_version: result.latest_version,
        };
        presentPendingUpdate();
    } catch (error) {
        console.debug("[Updates] Version check unavailable:", error);
    } finally {
        checking = false;
    }
}

export const updateNotificationService = {
    init() {
        if (checkTimer) return;
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
};
