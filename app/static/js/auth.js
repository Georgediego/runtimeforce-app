/**
 * RuntimeForce Auth Module
 * Только OAuth авторизация через runtimeforce-server
 */
window.RFAuth = {
    TOKEN_KEY: 'rf_jwt_token',

    getToken: function() { return localStorage.getItem(this.TOKEN_KEY); },
    getPlan: function() { return localStorage.getItem('rf_plan') || 'free'; },
    getEmail: function() { return localStorage.getItem('rf_email') || ''; },
    isAuthenticated: function() { return !!this.getToken(); },

    showAuth: function() {
        const o = document.getElementById('rf-auth-overlay');
        if (o) o.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    },

    hideAuth: function() {
        const o = document.getElementById('rf-auth-overlay');
        if (o) o.style.display = 'none';
        document.body.style.overflow = '';
        setTimeout(() => {
            if (typeof this.updateProfileUI === 'function') this.updateProfileUI();
            // Уведомляем app.js что пользователь авторизован — можно загружать данные
            window.dispatchEvent(new Event('rf-authenticated'));
        }, 100);
    },

    showError: function(msg) {
        const e = document.getElementById('rf-auth-error');
        const s = document.getElementById('rf-auth-success');
        if (s) s.classList.add('hidden');
        if (e) { e.textContent = msg; e.classList.remove('hidden'); }
    },

    oauth: function(provider) {
        const w = 600, h = 700;
        const left = (screen.width - w) / 2;
        const top = (screen.height - h) / 2;
        window.open('https://runtimeforce.dev/auth/' + provider, 'oauth_popup',
            'width=' + w + ',height=' + h + ',left=' + left + ',top=' + top);
    },

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

    logout: function() {
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

    init: function() {
        if (this.isAuthenticated()) {
            this.hideAuth();
        } else {
            this.showAuth();
        }

        // Слушаем OAuth callback из popup
        window.addEventListener('message', (event) => {
            if (event.origin !== 'https://runtimeforce.dev') return;
            if (event.data && (event.data.type === 'rf_github_auth' || event.data.type === 'rf_google_auth')) {
                localStorage.setItem(this.TOKEN_KEY, event.data.token);
                localStorage.setItem('rf_plan', event.data.plan || 'free');
                localStorage.setItem('rf_email', event.data.email);
                localStorage.setItem('rf_avatar', (event.data.email || 'U')[0].toUpperCase());
                this.hideAuth();
            }
        });

        // Закрытие dropdown при клике вне его
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
            if (typeof window.RFOpenSettings === 'function') {
                window.RFOpenSettings('general');
            }
        } else {
            window.RFAuth.toggleUserMenu(e);
        }
    });

    document.getElementById('rf-menu-settings-btn')?.addEventListener('click', function() {
        if (typeof window.RFOpenSettings === 'function') {
            window.RFOpenSettings('general');
        }
    });

    document.getElementById('rf-menu-logout-btn')?.addEventListener('click', function() {
        window.RFAuth.logout();
    });

    // OAuth кнопки
    document.getElementById('rf-auth-github-btn')?.addEventListener('click', function() {
        window.RFAuth.oauth('github');
    });

    document.getElementById('rf-auth-google-btn')?.addEventListener('click', function() {
        window.RFAuth.oauth('google');
    });
});

// Автозапуск
document.addEventListener('DOMContentLoaded', () => window.RFAuth.init());
if (document.readyState !== 'loading') window.RFAuth.init();