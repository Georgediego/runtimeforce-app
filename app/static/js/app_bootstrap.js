/**
 * Main Application Bootstrap Script.
 */
import { eventBus } from "./core/event_bus.js";
import { keysApi } from "./core/api_http_client.js";
import { authFrontendService } from "./services/auth_frontend_service.js";
import { fileTreeUIController } from "./components/file_tree_ui_controller.js";
import { editorUIController } from "./components/editor_ui_controller.js";
import { workspaceUIController } from "./components/workspace_ui_controller.js";
import { providersUIController } from "./components/providers_ui_controller.js";
import { settingsUIController } from "./components/settings_ui_controller.js";
import { chatUIController } from "./components/chat_ui_controller.js";
import { gitUIController } from "./components/git_ui_controller.js";
import { orchestratorUIController } from "./components/orchestrator_ui.js";
import { terminalUIController } from "./components/terminal.js";
import { projectsUIController } from "./components/projects_ui_controller.js";
import { socialUIController } from "./components/social_ui_controller.js";
import { traceUIController } from "./components/trace_ui_controller.js";
import { setupWizardUIController } from "./components/setup_wizard_ui_controller.js";

document.addEventListener("DOMContentLoaded", async () => {
    console.log("🚀 Initializing RuntimeForce IDE...");

    // One-time migration from localStorage rf_selected_models_*
    try {
        const data = await keysApi.getSelectedModels();
        const serverSelected = data.selected_models || {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith("rf_selected_models_")) {
                const providerId = key.replace("rf_selected_models_", "").toLowerCase();
                const rawVal = localStorage.getItem(key);
                if (rawVal) {
                    const modelIds = JSON.parse(rawVal);
                    if (Array.isArray(modelIds) && modelIds.length > 0) {
                        if (!serverSelected[providerId] || serverSelected[providerId].length === 0) {
                            await keysApi.saveSelectedModels(providerId, modelIds);
                            console.log(`[Migration] Migrated selected models for provider '${providerId}' from localStorage to server.`);
                        }
                    }
                }
                localStorage.removeItem(key);
            }
        }
    } catch (e) {
        console.warn("[Migration] Failed to migrate localStorage selected models:", e);
    }

    const controllers = [
        { name: "editorUIController", instance: editorUIController },
        { name: "workspaceUIController", instance: workspaceUIController },
        { name: "providersUIController", instance: providersUIController },
        { name: "settingsUIController", instance: settingsUIController },
        { name: "chatUIController", instance: chatUIController },
        { name: "orchestratorUIController", instance: orchestratorUIController },
        { name: "terminalUIController", instance: terminalUIController },
        { name: "gitUIController", instance: gitUIController },
        { name: "projectsUIController", instance: projectsUIController },
        { name: "socialUIController", instance: socialUIController },
        { name: "traceUIController", instance: traceUIController },
        { name: "setupWizardUIController", instance: setupWizardUIController },
    ];

    controllers.forEach(({ name, instance }) => {
        try {
            if (instance && typeof instance.init === "function") {
                instance.init();
            }
        } catch (err) {
            console.error(`[Bootstrap] Failed to initialize ${name}:`, err);
        }
    });

    const explorerCol = document.getElementById("file-explorer-col");
    const rightSidebar = document.getElementById("right-sidebar-col");

    document.getElementById("toggle-left-sidebar-btn")?.addEventListener("click", () => {
        if (explorerCol) explorerCol.classList.toggle("hidden");
    });
    document.getElementById("toggle-right-sidebar-btn")?.addEventListener("click", () => {
        if (rightSidebar) rightSidebar.classList.toggle("hidden");
    });

    const themeBtn = document.getElementById("theme-toggle-btn");
    themeBtn?.addEventListener("click", () => {
        const html = document.documentElement;
        const currentTheme = html.classList.contains("dark") ? "dark" : "light";
        const newTheme = currentTheme === "dark" ? "light" : "dark";
        html.classList.remove("dark", "light");
        html.classList.add(newTheme);
        localStorage.setItem("ide:theme", newTheme);
        const themeIcon = document.getElementById("theme-icon");
        if (themeIcon) {
            themeIcon.setAttribute("data-lucide", newTheme === "dark" ? "moon" : "sun");
            if (window.lucide) window.lucide.createIcons({ root: themeBtn });
        }
    });

    document.querySelectorAll(".left-tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const panel = btn.dataset.panel;
            if (explorerCol && explorerCol.classList.contains("hidden")) explorerCol.classList.remove("hidden");
            document.querySelectorAll(".left-panel-content").forEach((p) => p.classList.add("hidden"));
            document.getElementById(`left-panel-${panel}`)?.classList.remove("hidden");
            document.querySelectorAll(".left-tab-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            if (panel === "git") gitUIController.loadGitStatus();
            if (panel === "sessions") chatUIController.loadSessionsList();
            if (panel === "explorer") fileTreeUIController.loadTree();
            if (panel === "projects") projectsUIController.loadProjectsList();
        });
    });

    document.getElementById("refresh-tree-btn")?.addEventListener("click", () => fileTreeUIController.loadTree(true));

    document.querySelectorAll(".right-tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const panel = btn.dataset.panel;
            document.querySelectorAll(".right-panel-content").forEach((p) => p.classList.add("hidden"));
            document.getElementById(`right-panel-${panel}`)?.classList.remove("hidden");
            document.querySelectorAll(".right-tab-btn").forEach((b) => {
                b.classList.remove("border-[var(--ide-accent)]", "text-[var(--ide-text-primary)]");
                b.classList.add("border-transparent", "text-[var(--ide-text-muted)]");
            });
            btn.classList.remove("border-transparent", "text-[var(--ide-text-muted)]");
            btn.classList.add("border-[var(--ide-accent)]", "text-[var(--ide-text-primary)]");
        });
    });

    const openProfileBtn = document.getElementById("open-profile-btn");
    const userMenu = document.getElementById("rf-user-menu");
    openProfileBtn?.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!userMenu) return;
        const isHidden = userMenu.classList.contains("hidden") || userMenu.style.opacity === "0";
        if (isHidden) {
            userMenu.classList.remove("hidden");
            userMenu.style.opacity = "1";
            userMenu.style.transform = "translateY(0)";
            userMenu.style.pointerEvents = "auto";
        } else {
            userMenu.classList.add("hidden");
            userMenu.style.opacity = "0";
            userMenu.style.transform = "translateY(10px)";
            userMenu.style.pointerEvents = "none";
        }
    });
    document.addEventListener("click", (e) => {
        if (userMenu && !userMenu.contains(e.target) && !openProfileBtn?.contains(e.target)) {
            userMenu.classList.add("hidden");
            userMenu.style.opacity = "0";
            userMenu.style.transform = "translateY(10px)";
            userMenu.style.pointerEvents = "none";
        }
    });

    document.getElementById("open-settings-btn")?.addEventListener("click", () => settingsUIController.open("general"));
    document.getElementById("rf-menu-settings-btn")?.addEventListener("click", () => settingsUIController.open("general"));
    document.getElementById("rf-menu-logout-btn")?.addEventListener("click", () => authFrontendService.logout());

    eventBus.on("file:open", ({ path, name }) => {
        editorUIController.openFile(path, name);
        document.querySelector('.right-tab-btn[data-panel="editor"]')?.click();
    });
    eventBus.on("settings:open", (tab) => settingsUIController.open(tab || "general"));
    
    eventBus.on("auth:success", async () => {
        await projectsUIController.initActiveProject();
        settingsUIController.updateProfileInfo();
        authFrontendService.updateProfileUI();
        setupWizardUIController.checkAndPrompt();
    });

    eventBus.on("auth:required", () => authFrontendService.showAuth());
    eventBus.on("workspace:changed", () => {
        fileTreeUIController.loadTree(true);
        workspaceUIController.loadActiveWorkspace();
        gitUIController.loadGitStatus();
    });

    document.getElementById("rf-auth-google-btn")?.addEventListener("click", () => authFrontendService.oauth("google"));
    document.getElementById("rf-auth-github-btn")?.addEventListener("click", () => authFrontendService.oauth("github"));
    document.getElementById("rf-auth-x-btn")?.addEventListener("click", () => authFrontendService.oauth("x"));
    document.getElementById("rf-auth-reddit-btn")?.addEventListener("click", () => authFrontendService.oauth("reddit"));

    authFrontendService.init();
    await projectsUIController.initActiveProject();

    if (window.lucide) window.lucide.createIcons();
});
