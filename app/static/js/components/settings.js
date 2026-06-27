import { refreshIcons } from "../utils/icons.js";
import { loadWorkspaces, addLocalWorkspace, addSshWorkspace, initSshAuthUI } from "./workspace.js";
import { renderProvidersUI, updateKeyStatusIndicators, saveAllKeys, clearAllKeys, initModelPickerUI } from "./providers.js";

// ═══════════════════════════════════════════════════════════
// Обновления: GitHub API (публичный репозиторий)
// ═══════════════════════════════════════════════════════════
const GITHUB_REPO = 'Georgediego/runtimeforce-app';
const GITHUB_API = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;  // ← ИЗМЕНЕНО
const CACHE_KEY = 'rf_last_release_tag';  // ← ИЗМЕНЕНО
const CACHE_TIME_KEY = 'rf_last_check_time';
const CACHE_DURATION = 24 * 60 * 60 * 1000;

export async function checkForUpdates(forceCheck = false) {
    const versionEl = document.getElementById('rf-settings-version');
    const checkBtn = document.getElementById('check-updates-btn');
    
    if (checkBtn) {
        checkBtn.disabled = true;
        checkBtn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin inline"></i> Checking...';
        if (window.lucide) window.lucide.createIcons({ root: checkBtn });
    }

    try {
        const now = Date.now();
        const cachedTag = localStorage.getItem(CACHE_KEY);  // ← ИЗМЕНЕНО
        const lastCheck = parseInt(localStorage.getItem(CACHE_TIME_KEY) || '0');
        
        let latestTag, releaseDate;  // ← ИЗМЕНЕНО

        if (forceCheck || !cachedTag || (now - lastCheck) >= CACHE_DURATION) {
            const response = await fetch(GITHUB_API, {
                headers: { 
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'RuntimeForce-App'
                }
            });

            if (response.status === 404) {
                if (checkBtn) {
                    checkBtn.disabled = false;
                    checkBtn.innerHTML = '<i data-lucide="package" class="w-3.5 h-3.5 inline"></i> No releases';
                    if (window.lucide) window.lucide.createIcons({ root: checkBtn });
                }
                if (versionEl) versionEl.textContent = 'No releases yet';
                return { hasUpdate: false, error: false, noReleases: true };
            }

            if (response.status === 403) {
                if (checkBtn) {
                    checkBtn.disabled = false;
                    checkBtn.innerHTML = '<i data-lucide="clock" class="w-3.5 h-3.5 inline"></i> Rate Limit';
                    if (window.lucide) window.lucide.createIcons({ root: checkBtn });
                }
                if (versionEl) versionEl.textContent = 'API rate limit exceeded';
                return { hasUpdate: false, error: false, rateLimited: true };
            }

            if (!response.ok) throw new Error(`GitHub API error: ${response.status}`);

            const data = await response.json();
            
            if (!data.tag_name) throw new Error('Invalid response from GitHub API');

            latestTag = data.tag_name;  // ← ИЗМЕНЕНО: "v1.1.0"
            releaseDate = new Date(data.published_at);  // ← ИЗМЕНЕНО

            localStorage.setItem(CACHE_KEY, latestTag);
            localStorage.setItem(CACHE_TIME_KEY, now.toString());
        } else {
            latestTag = cachedTag;
            releaseDate = new Date(lastCheck);
        }

        // Обновляем UI
        if (versionEl) {
            const dateStr = releaseDate.toLocaleDateString('en-US', { 
                year: 'numeric', month: 'short', day: 'numeric' 
            });
            versionEl.textContent = `${latestTag} • ${dateStr}`;  // ← ИЗМЕНЕНО
        }

        // Проверяем, есть ли новая версия
        const savedTag = localStorage.getItem('rf_current_release');  // ← ИЗМЕНЕНО
        const isNewVersion = savedTag && savedTag !== latestTag;

        if (isNewVersion && forceCheck) {
            showUpdateModal(latestTag, releaseDate);  // ← ИЗМЕНЕНО
        } else if (!savedTag) {
            localStorage.setItem('rf_current_release', latestTag);  // ← ИЗМЕНЕНО
        }

        if (checkBtn) {
            checkBtn.disabled = false;
            if (isNewVersion) {
                checkBtn.innerHTML = '<i data-lucide="download" class="w-3.5 h-3.5 inline"></i> Update Available';
            } else {
                checkBtn.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 inline"></i> Up to date';
            }
            if (window.lucide) window.lucide.createIcons({ root: checkBtn });
        }

        return { hasUpdate: isNewVersion, tag: latestTag, date: releaseDate };  // ← ИЗМЕНЕНО

    } catch (error) {
        console.error('[RF] Update check failed:', error);
        
        if (checkBtn) {
            checkBtn.disabled = false;
            checkBtn.innerHTML = '<i data-lucide="wifi-off" class="w-3.5 h-3.5 inline"></i> Offline';
            if (window.lucide) window.lucide.createIcons({ root: checkBtn });
        }

        if (versionEl) versionEl.textContent = 'Connection error';

        return { hasUpdate: false, error: true, message: error.message };
    }
}

function showUpdateModal(tag, date) {  // ← ИЗМЕНЕНО
    const modal = document.getElementById('update-available-modal');
    if (!modal) return;

    const dateStr = date.toLocaleDateString('en-US', { 
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });

    const tagEl = document.getElementById('update-new-sha');  // Можно переименовать в 'update-new-tag'
    const dateEl = document.getElementById('update-new-date');

    if (tagEl) tagEl.textContent = tag;  // ← ИЗМЕНЕНО
    if (dateEl) dateEl.textContent = dateStr;

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
}

function performUpdate() {
    const modal = document.getElementById('update-available-modal');
    const newTag = localStorage.getItem(CACHE_KEY);  // ← ИЗМЕНЕНО
    if (newTag) {
        localStorage.setItem('rf_current_release', newTag);  // ← ИЗМЕНЕНО
    }

    if (modal) modal.classList.add('hidden');
    window.location.reload(true);
}

export function initSettings() {
    var modal = document.getElementById("settings-modal");

    // Открыть настройки (провайдеры в сайдбаре)
    document.getElementById("open-providers-btn")?.addEventListener("click", function() {
        openSettings("providers");
    });

    // Открыть настройки (из профиля)
    document.getElementById("open-settings-btn")?.addEventListener("click", function(e) {
        if (e.target.closest('[data-lucide="settings"]') || e.target.id === "rf-settings-icon") {
            openSettings("general");
        }
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
        if (typeof window.clearChat === "function") window.clearChat();
        closeSettings();
    });

    // ═══════════════════════════════════════════════════════════
    // Проверка обновлений (принудительная при клике)
    // ═══════════════════════════════════════════════════════════
    var checkUpdatesBtn = document.getElementById("check-updates-btn");
    if (checkUpdatesBtn) {
        checkUpdatesBtn.addEventListener("click", function() {
            checkForUpdates(true); // Принудительная проверка
        });
    }

    // ═══════════════════════════════════════════════════════════
    // Модальное окно обновления
    // ═══════════════════════════════════════════════════════════
    var updateModal = document.getElementById('update-available-modal');
    if (updateModal) {
        var updateNowBtn = document.getElementById('update-now-btn');
        var updateLaterBtn = document.getElementById('update-later-btn');
        
        if (updateNowBtn) {
            updateNowBtn.addEventListener('click', performUpdate);
        }
        
        if (updateLaterBtn) {
            updateLaterBtn.addEventListener('click', function() {
                updateModal.classList.add('hidden');
            });
        }
        
        updateModal.addEventListener('click', function(e) {
            if (e.target === updateModal) {
                updateModal.classList.add('hidden');
            }
        });
    }

    // Workspace
    document.getElementById("refresh-workspaces-btn")?.addEventListener("click", loadWorkspaces);
    document.getElementById("add-local-ws-btn")?.addEventListener("click", addLocalWorkspace);
    document.getElementById("add-ssh-ws-btn")?.addEventListener("click", addSshWorkspace);

    // Провайдеры
    document.getElementById("save-keys-btn")?.addEventListener("click", saveAllKeys);
    document.getElementById("clear-keys-btn")?.addEventListener("click", clearAllKeys);

    initSshAuthUI();
    initModelPickerUI();

    // Escape закрывает
    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape") {
            if (modal && !modal.classList.contains("hidden")) {
                closeSettings();
            }
            if (updateModal && !updateModal.classList.contains("hidden")) {
                updateModal.classList.add("hidden");
            }
        }
    });
}

export function openSettings(tab) {
    var modal = document.getElementById("settings-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    switchSettingsTab(tab || "general");

    if (typeof lucide !== "undefined") {
        lucide.createIcons();
    }
    refreshIcons(document.getElementById("settings-panel"));

    if (tab === "general") {
        if (window.RFAuth && typeof window.RFAuth.updateProfileUI === 'function') {
            window.RFAuth.updateProfileUI();
        }
        // Проверяем обновления при открытии General (без модалки, с учётом кэша)
        checkForUpdates(false);
    }
    if (tab === "providers") {
        renderProvidersUI();
        updateKeyStatusIndicators();
    }
    if (tab === "workspace") {
        loadWorkspaces();
    }
}

export function closeSettings() {
    document.getElementById("settings-modal")?.classList.add("hidden");
}

function switchSettingsTab(tab) {
    // 1. Убираем active у всех вкладок
    document.querySelectorAll(".settings-tab").forEach(function(t) {
        t.classList.remove("active");
    });

    // 2. Убираем active у всех кнопок
    document.querySelectorAll(".settings-nav-btn").forEach(function(b) {
        b.classList.remove("active");
    });

    // 3. Показываем нужную вкладку
    var activeTab = document.getElementById("stab-" + tab);
    if (activeTab) {
        activeTab.classList.add("active");
    }

    // 4. Делаем кнопку активной
    var activeBtn = document.querySelector('.settings-nav-btn[data-tab="' + tab + '"]');
    if (activeBtn) {
        activeBtn.classList.add("active");
    }

    // 5. Триггеры
    if (tab === "providers") {
        renderProvidersUI();
        updateKeyStatusIndicators();
    }
    if (tab === "workspace") {
        loadWorkspaces();
    }
    if (tab === "general") {
        if (window.RFAuth && typeof window.RFAuth.updateProfileUI === 'function') {
            window.RFAuth.updateProfileUI();
        }
        checkForUpdates(false);
    }
}

// Глобальный доступ
window.RFOpenSettings = openSettings;
window.RFCloseSettings = closeSettings;
window.RFCheckForUpdates = checkForUpdates;