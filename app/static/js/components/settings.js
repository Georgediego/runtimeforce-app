import { refreshIcons } from "../utils/icons.js";
import { loadWorkspaces, addLocalWorkspace, addSshWorkspace, initSshAuthUI } from "./workspace.js";
import { renderProvidersUI, updateKeyStatusIndicators, saveAllKeys, clearAllKeys } from "./providers.js";
import { clearChat } from "./chat.js";

export function initSettings() {
    var modal = document.getElementById("settings-modal");

    // Кнопка провайдеров в правом сайдбаре
    document.getElementById("open-providers-btn")?.addEventListener("click", function() {
        openSettings("providers");
    });

    // Закрыть настройки
    document.getElementById("close-settings-btn")?.addEventListener("click", closeSettings);
    modal?.addEventListener("click", function(e) {
        if (e.target === modal) closeSettings();
    });

    // Вкладки
    document.querySelectorAll(".settings-nav-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            switchSettingsTab(btn.dataset.tab);
        });
    });

    // Тема
    document.getElementById("settings-theme-btn")?.addEventListener("click", function() {
        window.dispatchEvent(new CustomEvent("toggle-theme"));
    });

    // Очистить чат
    document.getElementById("clear-chat-btn")?.addEventListener("click", function() {
        clearChat();
        closeSettings();
    });

    // Workspace
    document.getElementById("refresh-workspaces-btn")?.addEventListener("click", loadWorkspaces);
    document.getElementById("add-local-ws-btn")?.addEventListener("click", addLocalWorkspace);
    document.getElementById("add-ssh-ws-btn")?.addEventListener("click", addSshWorkspace);

    // Провайдеры
    document.getElementById("save-keys-btn")?.addEventListener("click", saveAllKeys);
    document.getElementById("clear-keys-btn")?.addEventListener("click", clearAllKeys);

    initSshAuthUI();

    // Escape закрывает
    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape" && modal && !modal.classList.contains("hidden")) {
            closeSettings();
        }
    });
}

export function openSettings(tab) {
    var modal = document.getElementById("settings-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    switchSettingsTab(tab || "general");
    refreshIcons(document.getElementById("settings-panel"));
    if (tab === "providers") {
        renderProvidersUI();
        updateKeyStatusIndicators();
    }
    if (tab === "workspace") {
        loadWorkspaces();
    }
}

export function closeSettings() {
    document.getElementById("settings-modal").classList.add("hidden");
}

function switchSettingsTab(tab) {
    document.querySelectorAll(".settings-tab").forEach(function(t) {
        t.classList.remove("active");
    });
    document.querySelectorAll(".settings-nav-btn").forEach(function(b) {
        b.classList.remove("active");
    });
    document.getElementById("stab-" + tab)?.classList.add("active");
    document.querySelector('.settings-nav-btn[data-tab="' + tab + '"]')?.classList.add("active");
}

// Экспорт в window для вызова из auth.js
window.RFOpenSettings = openSettings;
window.RFCloseSettings = closeSettings;
