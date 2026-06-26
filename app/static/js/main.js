import { state, setState } from "./state.js";
import { refreshIcons } from "./utils/icons.js";
import { initSearch, loadSessions } from "./components/sessions.js";
import { loadActiveWorkspace, startBackgroundWorkspaceSetup, loadWorkspaces } from "./components/workspace.js";
import { loadFileTree } from "./components/filetree.js";
import { loadGitStatus, initGitUI } from "./components/git.js";
import { initChat, clearChat } from "./components/chat.js";
import { initSettings, checkForUpdates } from "./components/settings.js";
import { initTerminal } from "./components/terminal.js";
import { refreshModelsUI, updateKeyStatusIndicators, initModelPickerUI } from "./components/providers.js";

// Глобальный экспорт clearChat
window.clearChat = clearChat;

// ─── Переключение тем оформления ───
function applyTheme(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
    localStorage.setItem("ide:theme", theme);
    state.theme = theme;

    var icon = theme === "dark" ? "moon" : "sun";
    var label = theme === "dark" ? "Dark Appearance" : "Light Appearance";
    var iconEl = document.getElementById("theme-icon");
    var labelEl = document.getElementById("theme-label");
    if (iconEl) iconEl.setAttribute("data-lucide", icon);
    if (labelEl) labelEl.textContent = label;

    var settingsIcon = document.getElementById("settings-theme-icon");
    var settingsLabel = document.getElementById("settings-theme-label");
    if (settingsIcon) settingsIcon.setAttribute("data-lucide", icon);
    if (settingsLabel) settingsLabel.textContent = theme === "dark" ? "Dark" : "Light";

    refreshIcons();
}

function toggleTheme() {
    applyTheme(state.theme === "dark" ? "light" : "dark");
}

// ─── Загрузка данных пользователя после авторизации ───
async function loadUserData() {
    var isAuth = window.RFAuth && window.RFAuth.isAuthenticated();
    if (!isAuth) {
        console.info("[RF] User not authenticated — data loading skipped");
        return;
    }
    console.info("[RF] User authenticated — loading user data");

    // Проверка обновлений при запуске
    if (typeof checkForUpdates === 'function') {
        checkForUpdates(true).then(result => {
            if (result.hasUpdate) {
                console.info('[RF] New version available:', result.sha?.substring(0, 7));
            }
        }).catch(e => {
            console.error('[RF] Update check failed:', e);
        });
    }

    try {
        await loadWorkspaces();
    } catch (e) {
        console.error("Workspaces load error:", e);
    }

    try {
        await startBackgroundWorkspaceSetup();
    } catch (e) {
        console.error("Workspace setup error:", e);
    }

    Promise.allSettled([
        loadSessions().catch(function(e) { console.error("Sessions:", e); }),
        refreshModelsUI().catch(function(e) { console.error("Models:", e); }),
    ]);

    updateKeyStatusIndicators();
    refreshIcons();
}

// ─── Главная инициализация приложения ───
async function init() {
    applyTheme(state.theme);
    refreshIcons();
    initSearch();
    initChat();
    initSettings();
    initTerminal();
    initGitUI();
    initModelPickerUI();

    // ─── Context Picker ───
    var pickerContainer = document.getElementById("context-picker-modal");
    if (pickerContainer) {
        // initContextPicker вызывается внутри initChat
    }

    // ─── Переключение табов в правой панели (Chat/Editor/Terminal) ───
    document.querySelectorAll('.right-tab-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.right-tab-btn').forEach(function(b) {
                b.classList.remove('border-[var(--ide-accent)]', 'text-[var(--ide-text-primary)]');
                b.classList.add('border-transparent', 'text-[var(--ide-text-muted)]');
            });

            btn.classList.remove('border-transparent', 'text-[var(--ide-text-muted)]');
            btn.classList.add('border-[var(--ide-accent)]', 'text-[var(--ide-text-primary)]');

            document.querySelectorAll('.right-panel-content').forEach(function(panel) {
                panel.classList.add('hidden');
                panel.classList.remove('flex');
            });

            var activePanel = document.getElementById('right-panel-' + btn.dataset.panel);
            if (activePanel) {
                activePanel.classList.remove('hidden');
                activePanel.classList.add('flex');
            }
        });
    });

    // ─── Переключение табов в левой панели (Explorer/Sessions/Git) ───
    document.querySelectorAll('.left-tab-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.left-tab-btn').forEach(function(b) {
                b.classList.remove('active');
            });

            document.querySelectorAll('.left-panel-content').forEach(function(p) {
                p.classList.add('hidden');
                p.classList.remove('flex');
            });

            btn.classList.add('active');
            var panel = document.getElementById('left-panel-' + btn.dataset.panel);
            if (panel) {
                panel.classList.remove('hidden');
                panel.classList.add('flex');
            }
        });
    });

    // ═══════════════════════════════════════════════════════════
    // ВНИМАНИЕ: Обработчик вкладок настроек УДАЛЁН отсюда!
    // Он теперь ТОЛЬКО в settings.js (initSettings).
    // ═══════════════════════════════════════════════════════════

    // ─── Переключение полей авторизации SSH ───
    var sshAuthType = document.getElementById('ssh-auth-type');
    if (sshAuthType) {
        sshAuthType.addEventListener('change', function() {
            var t = sshAuthType.value;
            var passRow = document.getElementById('ssh-password');
            var keyRow = document.getElementById('ssh-key');
            if (passRow) passRow.classList.toggle('hidden', t !== 'password');
            if (keyRow) keyRow.classList.toggle('hidden', t !== 'key');
        });
    }

    // ─── Закрытие модальных окон при клике на overlay ───
    document.querySelectorAll('#settings-modal, #commit-modal, #diff-viewer-modal, #file-viewer-modal, #model-picker-modal').forEach(function(modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) modal.classList.add('hidden');
        });
    });

    // ─── Закрытие всех окон по Escape ───
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('#settings-modal, #commit-modal, #diff-viewer-modal, #file-viewer-modal, #context-picker-modal, #model-picker-modal')
                .forEach(function(m) { m.classList.add('hidden'); });
        }
    });

    // ─── Сворачивание боковых панелей ───
    document.getElementById('toggle-left-sidebar-btn')?.addEventListener('click', function() {
        document.getElementById('left-sidebar')?.classList.toggle('collapsed');
    });
    document.getElementById('toggle-right-sidebar-btn')?.addEventListener('click', function() {
        document.getElementById('right-sidebar')?.classList.toggle('collapsed');
    });

    // ─── Переключение темы ───
    document.getElementById("theme-toggle-btn")?.addEventListener("click", toggleTheme);
    window.addEventListener("toggle-theme", toggleTheme);

    // ─── Автоматическое изменение высоты поля ввода в чате ───
    var promptInput = document.getElementById('prompt-input');
    if (promptInput) {
        promptInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
        });
    }

    // ═══════════════════════════════════════════════════════════
    // ВЫПАДАЮЩЕЕ МЕНЮ ПРОФИЛЯ
    // ═══════════════════════════════════════════════════════════
    document.getElementById('open-profile-btn')?.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (window.RFAuth) window.RFAuth.toggleUserMenu(e);
    });

    document.addEventListener('click', function(e) {
        var menu = document.getElementById('rf-user-menu');
        var profileContainer = document.getElementById('rf-user-profile');
        if (!menu || !profileContainer) return;
        if (menu.classList.contains('hidden')) return;

        var clickedInsideMenu = menu.contains(e.target);
        var clickedInsideProfile = profileContainer.contains(e.target);

        if (!clickedInsideMenu && !clickedInsideProfile) {
            if (window.RFAuth && typeof window.RFAuth.closeUserMenu === 'function') {
                window.RFAuth.closeUserMenu();
            } else {
                menu.style.opacity = '0';
                menu.style.transform = 'translateY(10px)';
                setTimeout(function() { menu.classList.add('hidden'); }, 200);
            }
        }
    });

    // ─── Refresh Tree ───
    var refreshTreeBtn = document.getElementById('refresh-tree-btn');
    if (refreshTreeBtn) {
        refreshTreeBtn.addEventListener('click', async function(e) {
            e.stopPropagation();
            try {
                await loadFileTree();
            } catch (err) {
                console.error('Tree refresh failed:', err);
            }
        });
    }

    // ─── Загрузка данных ───
    setTimeout(loadUserData, 300);
    window.addEventListener("rf-authenticated", loadUserData);

    refreshIcons();
    console.log('✅ RuntimeForce IDE ready');
}

// Запуск инициализации
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}