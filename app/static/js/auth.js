/**
RuntimeForce Auth Module
Только OAuth авторизация через runtimeforce-server
*/
window.RFAuth = {
    TOKEN_KEY: 'rf_jwt_token',
    getToken: function() { return localStorage.getItem(this.TOKEN_KEY); },
    getPlan: function() { return localStorage.getItem('rf_plan') || 'free'; },
    getEmail: function() { return localStorage.getItem('rf_email') || ''; },
    isAuthenticated: function() { return !!this.getToken(); },
    
    showAuth: function() {
        var o = document.getElementById('rf-auth-overlay');
        if (o) o.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    },
    hideAuth: function() {
        var o = document.getElementById('rf-auth-overlay');
        if (o) o.style.display = 'none';
        document.body.style.overflow = '';
        setTimeout(function() {
            if (typeof window.RFAuth.updateProfileUI === 'function') {
                window.RFAuth.updateProfileUI();
            }
            window.dispatchEvent(new Event('rf-authenticated'));
        }, 100);
    },
    showError: function(msg) {
        var e = document.getElementById('rf-auth-error');
        var s = document.getElementById('rf-auth-success');
        if (s) s.classList.add('hidden');
        if (e) { e.textContent = msg; e.classList.remove('hidden'); }
    },
    oauth: function(provider) {
        var w = 600, h = 700;
        var left = (screen.width - w) / 2;
        var top = (screen.height - h) / 2;
        window.open('https://runtimeforce.dev/auth/' + provider, 'oauth_popup',
            'width=' + w + ',height=' + h + ',left=' + left + ',top=' + top);
    },
    toggleUserMenu: function(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        var m = document.getElementById('rf-user-menu');
        var chevron = document.getElementById('profile-chevron');
        if (!m) {
            console.warn('Profile menu not found');
            return;
        }
        if (m.classList.contains('hidden')) {
            m.classList.remove('hidden');
            requestAnimationFrame(function() {
                m.style.opacity = '1';
                m.style.transform = 'translateY(0)';
                if (chevron) chevron.style.transform = 'rotate(180deg)';
            });
        } else {
            this.closeUserMenu();
        }
    },
    closeUserMenu: function() {
        var m = document.getElementById('rf-user-menu');
        var chevron = document.getElementById('profile-chevron');
        if (!m) return;
        m.style.opacity = '0';
        m.style.transform = 'translateY(10px)';
        if (chevron) chevron.style.transform = 'rotate(0deg)';
        setTimeout(function() {
            if (m && (!m.style.opacity || m.style.opacity === '0')) {
                m.classList.add('hidden');
            }
        }, 200);
    },
    openSettings: function() {
        this.closeUserMenu();
        if (typeof window.RFOpenSettings === 'function') {
            window.RFOpenSettings('general');
        } else {
            var modal = document.getElementById('settings-modal');
            if (modal) modal.classList.remove('hidden');
        }
    },
    logout: function() {
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem('rf_plan');
        localStorage.removeItem('rf_email');
        localStorage.removeItem('rf_avatar');
        location.reload();
    },
    
    updateProfileUI: function() {
        var email = this.getEmail();
        if (!email) return;
        var plan = this.getPlan();
        var avatar = localStorage.getItem('rf_avatar') || email[0].toUpperCase();
        var displayName = email.split('@')[0];

        // ─── Хедер / Старые элементы ───
        var av = document.getElementById('rf-user-avatar');
        if (av) av.textContent = avatar;

        var nm = document.getElementById('rf-user-name');
        if (nm) nm.textContent = displayName;

        var pl = document.getElementById('rf-user-plan');
        if (pl) {
            var names = {free: 'Free', pro: 'PRO', studio: 'Studio'};
            pl.textContent = names[plan] || 'Free';
            pl.className = 'text-[10px]';
            if (plan === 'pro') pl.classList.add('text-[var(--ide-accent)]');
            else if (plan === 'studio') pl.classList.add('text-[var(--ide-warning)]');
            else pl.classList.add('text-[var(--ide-text-muted)]');
        }

        // ─── Settings Modal: General Tab ───
        var settingsAvatar = document.getElementById('rf-settings-avatar');
        if (settingsAvatar) settingsAvatar.textContent = avatar;

        var settingsName = document.getElementById('rf-settings-name');
        if (settingsName) settingsName.textContent = displayName;

        var settingsPlan = document.getElementById('rf-settings-plan');
        if (settingsPlan) {
            var names = {free: 'Free Plan', pro: 'PRO Plan', studio: 'Studio Plan'};
            settingsPlan.textContent = names[plan] || 'Free Plan';
            
            // Цветовая индикация плана (стандартные цвета)
            settingsPlan.classList.remove('text-[var(--ide-accent)]', 'text-[var(--ide-warning)]', 'text-[var(--ide-text-secondary)]');
            if (plan === 'pro') {
                settingsPlan.classList.add('text-[var(--ide-accent)]');
            } else if (plan === 'studio') {
                settingsPlan.classList.add('text-[var(--ide-warning)]');
            } else {
                settingsPlan.classList.add('text-[var(--ide-text-secondary)]');
            }
        }

        // Кнопка Upgrade: показываем для free и pro, скрываем только для studio
        var upgradeBtn = document.getElementById('rf-settings-upgrade-btn');
        if (upgradeBtn) {
            if (plan === 'studio') {
                upgradeBtn.classList.add('hidden');
            } else {
                upgradeBtn.classList.remove('hidden');
            }
        }

        // ─── Dropdown Menu ───
        var me = document.getElementById('rf-menu-email');
        if (me) me.textContent = email;

        var mp = document.getElementById('rf-menu-plan');
        if (mp) {
            var names = {free: 'Free Plan', pro: 'PRO Plan', studio: 'Studio Plan'};
            mp.textContent = names[plan] || 'Free Plan';
        }
    },

    init: function() {
        if (this.isAuthenticated()) {
            this.hideAuth();
        } else {
            this.showAuth();
        }

        // Слушаем OAuth callback из popup
        window.addEventListener('message', function(event) {
            if (event.origin !== 'https://runtimeforce.dev') return;
            if (event.data && (event.data.type === 'rf_github_auth' || event.data.type === 'rf_google_auth')) {
                localStorage.setItem(window.RFAuth.TOKEN_KEY, event.data.token);
                localStorage.setItem('rf_plan', event.data.plan || 'free');
                localStorage.setItem('rf_email', event.data.email);
                localStorage.setItem('rf_avatar', (event.data.email || 'U')[0].toUpperCase());
                window.RFAuth.hideAuth();
            }
        });

        // Закрытие dropdown при клике вне его
        document.addEventListener('click', function(e) {
            var m = document.getElementById('rf-user-menu');
            var p = document.getElementById('rf-user-profile');
            if (!m || !p) return;

            if (!m.contains(e.target) && !p.contains(e.target)) {
                if (!m.classList.contains('hidden')) {
                    window.RFAuth.closeUserMenu();
                }
            }
        });
    }
};

// ═══════════════════════════════════════════════════════════════
// Инициализация обработчиков событий
// ═══════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', function() {
    // Кнопка профиля
    var profileBtn = document.getElementById('open-profile-btn');
    if (profileBtn) {
        profileBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            window.RFAuth.toggleUserMenu(e);
        });
    }

    // Settings (из меню)
    var menuSettingsBtn = document.getElementById('rf-menu-settings-btn');
    if (menuSettingsBtn) {
        menuSettingsBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            window.RFAuth.openSettings();
        });
    }

    // Logout
    var logoutBtn = document.getElementById('rf-menu-logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            window.RFAuth.logout();
        });
    }

    // OAuth кнопки
    var githubBtn = document.getElementById('rf-auth-github-btn');
    if (githubBtn) {
        githubBtn.addEventListener('click', function() {
            window.RFAuth.oauth('github');
        });
    }

    var googleBtn = document.getElementById('rf-auth-google-btn');
    if (googleBtn) {
        googleBtn.addEventListener('click', function() {
            window.RFAuth.oauth('google');
        });
    }
});

// Автозапуск
document.addEventListener('DOMContentLoaded', function() { window.RFAuth.init(); });
if (document.readyState !== 'loading') window.RFAuth.init();