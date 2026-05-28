import { state } from "./state.js";
import { refreshIcons } from "./utils/icons.js";
import { initSearch, loadSessions } from "./components/sessions.js";
import { loadActiveWorkspace, startBackgroundWorkspaceSetup, loadWorkspaces } from "./components/workspace.js";
import { loadFileTree } from "./components/filetree.js";
import { loadGitStatus, initGitUI } from "./components/git.js";
import { initChat, renderContextStrip, initFileAttach, initContextPicker } from "./components/chat.js";
import { initSettings } from "./components/settings.js";
import { initTerminal } from "./components/terminal.js";
import { refreshModelsUI, renderProvidersUI, updateKeyStatusIndicators } from "./components/providers.js";

function applyTheme(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
    localStorage.setItem("ide:theme", theme);
    state.theme = theme;
    var hlLink = document.getElementById("hljs-theme");
    if (hlLink) {
        hlLink.href = theme === "dark"
            ? "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css"
            : "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-light.min.css";
    }
    var icon = theme === "dark" ? "moon" : "sun";
    var label = theme === "dark" ? "Dark" : "Light";
    ["theme-icon", "settings-theme-icon"].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.setAttribute("data-lucide", icon);
    });
    ["theme-label", "settings-theme-label"].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.textContent = label;
    });
    refreshIcons();
}

function toggleTheme() { applyTheme(state.theme === "dark" ? "light" : "dark"); }

function toggleSidebar(side) {
    var el = document.getElementById(side + "-sidebar");
    if (el) el.classList.toggle("collapsed");
}

function initUIComponents() {
    document.getElementById("theme-toggle-btn")?.addEventListener("click", toggleTheme);
    window.addEventListener("toggle-theme", toggleTheme);
    document.getElementById("toggle-left-sidebar-btn")?.addEventListener("click", function() { toggleSidebar("left"); });
    document.getElementById("toggle-right-sidebar-btn")?.addEventListener("click", function() { toggleSidebar("right"); });
    document.getElementById("refresh-sessions-btn")?.addEventListener("click", loadSessions);
    document.getElementById("refresh-tree-btn")?.addEventListener("click", function() { loadFileTree(); loadGitStatus(); });

    initSearch();
    initChat();
    initFileAttach();
    initContextPicker();
    initSettings();
    initTerminal();
    initGitUI();
    document.getElementById("close-file-viewer-btn")?.addEventListener("click", function() { window.dispatchEvent(new CustomEvent("close-file")); });

    renderProvidersUI();
    updateKeyStatusIndicators();
}

async function init() {
    applyTheme(state.theme);
    refreshIcons();
    initUIComponents();
    renderContextStrip();

    try {
        await loadWorkspaces();
    } catch (e) {
        console.error("Ошибка первичной прорисовки воркспейсов:", e);
    }

    Promise.allSettled([
        loadSessions().catch(function(e) { console.error("Sessions:", e); }),
        refreshModelsUI().catch(function(e) { console.error("Models:", e); }),
    ]);

    startBackgroundWorkspaceSetup();
    refreshIcons();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}