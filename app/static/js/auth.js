/**
 * RuntimeForce Auth Module
 * Отвечает за: авторизацию, регистрацию, OAuth, изоляцию данных пользователей
 */
window.RFAuth = {
    API_LOGIN: 'https://runtimeforce.dev/api/auth/login',
    API_REGISTER: 'https://runtimeforce.dev/api/auth/register',
    TOKEN_KEY: 'rf_jwt_token',
    
    // --- ИЗОЛЯЦИЯ ДАННЫХ ПО ПОЛЬЗОВАТЕЛЮ ---
    getUserPrefix: function() {
        const email = localStorage.getItem('rf_email');
        if (!email) return 'rf_guest_';
        return 'rf_' + email.replace(/[@.]/g, '_') + '_';
    },
    
    userSet: function(key, value) {
        localStorage.setItem(this.getUserPrefix() + key, typeof value === 'object' ? JSON.stringify(value) : value);
    },
    
    userGet: function(key, parse = false) {
        const val = localStorage.getItem(this.getUserPrefix() + key);
        if (val === null) return null;
        return parse ? JSON.parse(val) : val;
    },
    
    userRemove: function(key) {
        localStorage.removeItem(this.getUserPrefix() + key);
    },
    
    userClear: function() {
        const prefix = this.getUserPrefix();
        // Безопасный сбор ключей перед удалением
        const keys = Object.keys(localStorage).filter(k => k.startsWith(prefix));
        keys.forEach(k => localStorage.removeItem(k));
    },
    
    getToken: function() { return localStorage.getItem(this.TOKEN_KEY); },
    getPlan: function() { return localStorage.getItem('rf_plan') || 'free'; },
    getEmail: function() { return localStorage.getItem('rf_email') || ''; },
    isAuthenticated: function() { return !!this.getToken(); },
    
    // --- UI КОНТРОЛЬ ---
    showAuth: function() {
        const o = document.getElementById('rf-auth-overlay');
        if (o) o.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    },
    
    hideAuth: function() {
        const o = document.getElementById('rf-auth-overlay');
        if (o) o.style.display = 'none';
        document.body.style.overflow = '';
        setTimeout(() => { if (typeof this.updateProfileUI === 'function') this.updateProfileUI(); }, 100);
    },
    
    showError: function(msg) {
        const e = document.getElementById('rf-auth-error');
        const s = document.getElementById('rf-auth-success');
        if (s) s.classList.add('hidden');
        if (e) { e.textContent = msg; e.classList.remove('hidden'); }
    },
    
    showSuccess: function(msg) {
        const s = document.getElementById('rf-auth-success');
        const e = document.getElementById('rf-auth-error');
        if (e) e.classList.add('hidden');
        if (s) { s.textContent = msg; s.classList.remove('hidden'); }
    },
    
    // --- ЛОГИН / РЕГИСТРАЦИЯ ---
    login: async function() {
        const userEl = document.getElementById('rf-auth-user');
        const passEl = document.getElementById('rf-auth-pass');
        const user = userEl ? userEl.value.trim() : '';
        const pass = passEl ? passEl.value : '';
        if (!user || !pass) return this.showError('Введите email и пароль');
        
        try {
            const res = await fetch(this.API_LOGIN, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: user, password: pass})
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Ошибка входа');
            this.saveSession(data.access_token, data.plan, user);
            this.hideAuth();
        } catch (e) {
            this.showError(e.message);
        }
    },
    
    register: async function() {
        const userEl = document.getElementById('rf-auth-user');
        const passEl = document.getElementById('rf-auth-pass');
        const user = userEl ? userEl.value.trim() : '';
        const pass = passEl ? passEl.value : '';
        if (!user || !pass) return this.showError('Введите email и пароль');
        if (pass.length < 6) return this.showError('Пароль минимум 6 символов');
        
        try {
            const res = await fetch(this.API_REGISTER, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: user, password: pass})
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Ошибка регистрации');
            this.showSuccess('Аккаунт создан! Выполняем вход...');
            setTimeout(() => this.login(), 500);
        } catch (e) {
            this.showError(e.message);
        }
    },
    
    saveSession: function(token, plan, email) {
        localStorage.setItem(this.TOKEN_KEY, token);
        localStorage.setItem('rf_plan', plan || 'free');
        localStorage.setItem('rf_email', email);
        localStorage.setItem('rf_avatar', (email || 'U')[0].toUpperCase());
    },
    
    // --- OAUTH ---
    oauth: function(provider) {
        const w = 600, h = 700;
        const left = (screen.width - w) / 2;
        const top = (screen.height - h) / 2;
        window.open('https://runtimeforce.dev/auth/' + provider, 'oauth_popup',
            'width=' + w + ',height=' + h + ',left=' + left + ',top=' + top);
    },
    
    // --- ПРОФИЛЬ В САЙДБАРЕ ---
    toggleUserMenu: function(e) {
        if (e) e.stopPropagation();
        const m = document.getElementById('rf-user-menu');
        if (!m) return;
        if (m.classList.contains('hidden')) {
            m.classList.remove('hidden');
            requestAnimationFrame(() => {
                m.style.opacity = '1';
                m.style.transform = 'translateY(0)';
            });
        } else {
            m.style.opacity = '0';
            m.style.transform = 'translateY(10px)';
            setTimeout(() => m.classList.add('hidden'), 200);
        }
    },
    
    onProfileClick: function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (e.target.closest('[data-lucide="settings"]')) return;
        this.toggleUserMenu(e);
    },
    
    openSettings: function() {
        var menu = document.getElementById('rf-user-menu');
        if (menu) menu.classList.add('hidden');
        if (typeof window.RFOpenSettings === 'function') {
            window.RFOpenSettings('general');
        } else {
            const modal = document.getElementById('settings-modal');
            if (modal) modal.classList.remove('hidden');
        }
    },
    
    upgradePlan: function() {
        const plan = this.getPlan();
        const email = this.getEmail();
        window.open('https://runtimeforce.dev/account#plan=' + plan + '&email=' + encodeURIComponent(email), '_blank');
    },
    
    checkUpdates: function() {
        const btn = document.getElementById('check-updates-btn');
        const icon = document.getElementById('refresh-icon');
        const text = document.getElementById('check-updates-text');
        const status = document.getElementById('update-status');
        
        if (btn) btn.disabled = true;
        if (icon) icon.classList.add('animate-spin');
        if (text) text.textContent = 'Проверка...';
        if (status) status.classList.add('hidden');
        
        const currentVersion = 'v2.0.0';
        
        fetch('https://api.github.com/repos/runtimeforce/ide/releases/latest')
            .then(r => r.json())
            .then(data => {
                const latest = data.tag_name || currentVersion;
                if (status) {
                    status.classList.remove('hidden');
                    if (latest !== currentVersion) {
                        status.innerHTML = '<span class="text-yellow-400">Доступна новая версия: <b>' + latest + '</b> (у вас ' + currentVersion + ')</span>';
                    } else {
                        status.innerHTML = '<span class="text-green-400">✓ У вас последняя версия: ' + currentVersion + '</span>';
                    }
                }
            })
            .catch(() => {
                if (status) {
                    status.classList.remove('hidden');
                    status.innerHTML = '<span class="text-red-400">Ошибка проверки обновлений</span>';
                }
            })
            .finally(() => {
                if (btn) btn.disabled = false;
                if (icon) icon.classList.remove('animate-spin');
                if (text) text.textContent = 'Проверить обновления';
            });
    },

    logout: function() {
        this.userClear();
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem('rf_plan');
        localStorage.removeItem('rf_email');
        localStorage.removeItem('rf_avatar');
        location.reload();
    },
    
    updateProfileUI: function() {
        const email = this.getEmail();
        if (!email) return;
        const plan = this.getPlan();
        const avatar = localStorage.getItem('rf_avatar') || email[0].toUpperCase();
        
        const av = document.getElementById('rf-user-avatar');
        if (av) av.textContent = avatar;
        
        const nm = document.getElementById('rf-user-name');
        if (nm) nm.textContent = email.split('@')[0];
        
        const pl = document.getElementById('rf-user-plan');
        if (pl) {
            const names = {free: 'Free', pro: 'PRO', studio: 'Studio'};
            pl.textContent = names[plan] || 'Free';
            pl.className = 'text-xs';
            if (plan === 'pro') pl.classList.add('text-blue-400');
            else if (plan === 'studio') pl.classList.add('text-purple-400');
            else pl.classList.add('text-gray-400');
        }
        
        const settingsPlan = document.getElementById('rf-settings-plan');
        if (settingsPlan) {
            const names = {free: 'Бесплатный тариф', pro: 'PRO (€29/мес)', studio: 'Studio (€99/мес)'};
            settingsPlan.textContent = names[plan] || 'Бесплатный тариф';
        }
        
        const me = document.getElementById('rf-menu-email');
        if (me) me.textContent = email;
        const mp = document.getElementById('rf-menu-plan');
        if (mp) {
            const names = {free: 'Free Plan', pro: 'PRO Plan', studio: 'Studio Plan'};
            mp.textContent = names[plan] || 'Free Plan';
        }
    },
    
    // --- МИГРАЦИЯ СТАРЫХ ГЛОБАЛЬНЫХ КЛЮЧЕЙ ---
    migrateToUserNamespace: function() {
        const email = this.getEmail();
        if (!email) return;
        const prefix = this.getUserPrefix();
        const keys = ['workspaces', 'ssh_connections', 'settings', 'chat_history', 'api_keys', 'dock_items', 'sessions'];
        keys.forEach(k => {
            const val = localStorage.getItem(k);
            if (val !== null && localStorage.getItem(prefix + k) === null) {
                localStorage.setItem(prefix + k, val);
                localStorage.removeItem(k);
            }
        });
    },
    
    // --- ИНИЦИАЛИЗАЦИЯ ---
    init: function() {
        if (this.isAuthenticated()) {
            this.migrateToUserNamespace();
            this.hideAuth();
        } else {
            this.showAuth();
        }
        
        // Слушаем OAuth из popup
        window.addEventListener('message', (event) => {
            if (event.origin !== 'https://runtimeforce.dev') return;
            if (event.data && (event.data.type === 'rf_github_auth' || event.data.type === 'rf_google_auth')) {
                this.saveSession(event.data.token, event.data.plan, event.data.email);
                this.hideAuth();
            }
        });
        
        // Закрываем dropdown при клике вне его
        document.addEventListener('click', (e) => {
            const m = document.getElementById('rf-user-menu');
            const p = document.getElementById('rf-user-profile');
            if (m && p && !m.contains(e.target) && !p.contains(e.target)) {
                m.classList.add('hidden');
            }
        });
    }
};


// Инициализация обработчиков событий
document.addEventListener('DOMContentLoaded', function() {
    // Кнопка профиля
    document.getElementById('open-settings-btn')?.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (e.target.closest('[data-lucide="settings"]')) {
            // Клик по шестерёнке → открываем настройки
            if (typeof window.RFOpenSettings === 'function') {
                window.RFOpenSettings('general');
            }
        } else {
            // Клик по остальному профилю → dropdown
            window.RFAuth.toggleUserMenu(e);
        }
    });

    // Кнопки в dropdown меню
    document.getElementById('rf-menu-settings-btn')?.addEventListener('click', function() {
        if (typeof window.RFOpenSettings === 'function') {
            window.RFOpenSettings('general');
        }
    });
    
    document.getElementById('rf-menu-logout-btn')?.addEventListener('click', function() {
        window.RFAuth.logout();
    });

    // Кнопки в модалке авторизации
    document.getElementById('rf-auth-login-btn')?.addEventListener('click', function() {
        window.RFAuth.login();
    });
    
    document.getElementById('rf-auth-register-btn')?.addEventListener('click', function() {
        window.RFAuth.register();
    });
    
    document.getElementById('rf-auth-github-btn')?.addEventListener('click', function() {
        window.RFAuth.oauth('github');
    });
    
    document.getElementById('rf-auth-google-btn')?.addEventListener('click', function() {
        window.RFAuth.oauth('google');
    });
});

// Закрытие dropdown при клике вне его
document.addEventListener('click', (e) => {
    const m = document.getElementById('rf-user-menu');
    const p = document.getElementById('rf-user-profile');
    if (m && p && !m.contains(e.target) && !p.contains(e.target)) {
        m.classList.add('hidden');
    }
});

// --- ПЕРЕХВАТЧИК FETCH: ПРИШИВАЕМ JWT К ЗАПРОСАМ НА СЕРВЕР ---
(function() {
    const origFetch = window.fetch;
    window.fetch = function(url, options) {
        options = options || {};
        if (typeof url === 'string' && url.startsWith('https://runtimeforce.dev/')) {
            const token = window.RFAuth.getToken();
            if (token) {
                if (!options.headers) options.headers = {};
                if (!(options.headers instanceof Headers)) {
                    options.headers['Authorization'] = 'Bearer ' + token;
                }
            }
        }
        return origFetch.call(this, url, options);
    };
})();

// Автозапуск
document.addEventListener('DOMContentLoaded', () => window.RFAuth.init());
if (document.readyState !== 'loading') window.RFAuth.init();
