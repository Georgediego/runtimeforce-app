import { updateOrchestratorUI, addToolToExecutionList, updateToolInExecutionList } from "./components/orchestrator_ui.js";
import { initChat, initFileAttach, initContextPicker } from "./components/chat.js";
import { loadSessions, initSearch } from "./components/sessions.js";
import { loadGitStatus, initGit } from "./components/git.js";
import { renderProvidersUI, updateKeyStatusIndicators, saveAllKeys, clearAllKeys } from "./components/providers.js";

function safeInit(name, fn) {
    try {
        if (typeof fn === "function") fn();
    } catch (e) {
        console.error('[' + name + '] init failed:', e);
    }
}

document.addEventListener("DOMContentLoaded", function() {
    console.log("RuntimeForce IDE initializing...");
    safeInit("Chat", initChat);
    safeInit("FileAttach", initFileAttach);
    safeInit("ContextPicker", initContextPicker);
    safeInit("Search", initSearch);
    safeInit("Git", initGit);
    safeInit("Providers", renderProvidersUI);

    loadSessions();
    loadGitStatus();
    updateKeyStatusIndicators();

    if (window.lucide) {
        try {
            window.lucide.createIcons();
            document.body.dataset.iconsInitialized = "true";
        } catch (e) {}
    }

    // Bind settings buttons
    document.getElementById("save-providers-btn")?.addEventListener("click", saveAllKeys);
    document.getElementById("clear-providers-btn")?.addEventListener("click", clearAllKeys);

    console.log("RuntimeForce IDE ready");
});

if (document.readyState !== "loading") {
    document.dispatchEvent(new Event("DOMContentLoaded"));
}

// Обработчики кнопок toolbar
document.addEventListener('DOMContentLoaded', function() {
    const settingsBtn = document.getElementById('open-settings-btn');
    const gitBtn = document.getElementById('open-git-btn');
    
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            const modal = document.getElementById('settings-modal');
            if (modal) {
                modal.classList.remove('hidden');
                if (typeof initSettings === 'function') initSettings();
            }
        });
    }
    
    if (gitBtn) {
        gitBtn.addEventListener('click', () => {
            const modal = document.getElementById('git-modal');
            if (modal) {
                modal.classList.remove('hidden');
                if (typeof loadGitStatus === 'function') loadGitStatus();
            }
        });
    }
});

// Проверка инициализации всех компонентов
document.addEventListener('DOMContentLoaded', function() {
    console.log('🔍 Проверка инициализации компонентов:');
    
    const checks = [
        { name: 'Chat', id: 'chat-container' },
        { name: 'Settings Modal', id: 'settings-modal' },
        { name: 'Git Modal', id: 'git-modal' },
        { name: 'Terminal', id: 'terminal-container' },
        { name: 'Tools List', id: 'active-tools-list' },
        { name: 'Trace Log', id: 'debug-trace-log' }
    ];
    
    checks.forEach(check => {
        const el = document.getElementById(check.id);
        console.log(`${el ? '✅' : '❌'} ${check.name}: ${el ? 'найден' : 'ОТСУТСТВУЕТ'}`);
    });
    
    // Инициализируем Lucide иконки после всех компонентов
    if (window.lucide) {
        lucide.createIcons();
        console.log('✅ Lucide иконки инициализированы');
    }
});
