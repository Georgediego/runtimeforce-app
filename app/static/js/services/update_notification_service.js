const UPDATE_CHECK_INTERVAL_MS = 8 * 60 * 60 * 1000;
const UPDATE_SNOOZE_MS = 8 * 60 * 60 * 1000;
const UPDATE_SNOOZE_KEY = "rf_update_snooze_v1";

let checkTimer = null;
let checking = false;

function isSnoozed(version) {
    try {
        const saved = JSON.parse(localStorage.getItem(UPDATE_SNOOZE_KEY) || "null");
        return Boolean(saved && saved.version === version && Number(saved.until) > Date.now());
    } catch {
        return false;
    }
}

function snooze(version) {
    localStorage.setItem(UPDATE_SNOOZE_KEY, JSON.stringify({
        version,
        until: Date.now() + UPDATE_SNOOZE_MS,
    }));
}

function hasBlockingModal() {
    const stopGenerationButton = document.getElementById("stop-gen-btn");
    if (stopGenerationButton && !stopGenerationButton.classList.contains("hidden")) {
        return true;
    }

    const authOverlay = document.getElementById("rf-auth-overlay");
    if (authOverlay && window.getComputedStyle(authOverlay).display !== "none"
        && !authOverlay.classList.contains("hidden")) {
        return true;
    }
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
        'cd "$HOME/.runtimeforce"',
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

async function checkForUpdates() {
    if (checking || document.hidden) return;
    checking = true;
    try {
        const response = await fetch("/api/v1/updates/check", {
            method: "GET",
            cache: "no-store",
            headers: { "Accept": "application/json" },
        });
        if (!response.ok) return;
        const result = await response.json();
        if (!result.checked || !result.update_available) return;
        if (isSnoozed(result.latest_version) || hasBlockingModal()) return;
        showUpdateModal(result.current_version, result.latest_version);
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

        // One check at startup, then no more than once every eight hours.
        checkForUpdates();
        checkTimer = window.setInterval(checkForUpdates, UPDATE_CHECK_INTERVAL_MS);
    },
};
