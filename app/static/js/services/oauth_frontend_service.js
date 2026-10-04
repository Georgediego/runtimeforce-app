/**
 * OAuth Frontend Service - Handles OAuth authentication flows for GitHub, X.com, and Reddit.
 */
import { eventBus } from "../core/event_bus.js";

const OAUTH_CONFIG = {
    github: {
        authorizeUrl: '/api/v1/oauth/github/authorize',
        callbackUrl: '/api/v1/oauth/github/callback',
        storageKey: 'rf_github_oauth_token'
    },
    x: {
        authorizeUrl: '/api/v1/oauth/x/authorize',
        callbackUrl: '/api/v1/oauth/x/callback',
        storageKey: 'rf_x_oauth_token'
    },
    reddit: {
        authorizeUrl: '/api/v1/oauth/reddit/authorize',
        callbackUrl: '/api/v1/oauth/reddit/callback',
        storageKey: 'rf_reddit_oauth_token'
    }
};

export const oauthService = {
    init() {
        this.setupOAuthButton('github-oauth-btn', 'github');
        this.setupOAuthButton('x-oauth-btn', 'x');
        this.setupOAuthButton('reddit-oauth-btn', 'reddit');
        this.checkOAuthStatus();
    },

    setupOAuthButton(buttonId, provider) {
        const button = document.getElementById(buttonId);
        if (!button) return;

        button.addEventListener('click', (e) => {
            e.preventDefault();
            this.initiateOAuth(provider);
        });
    },

    async initiateOAuth(provider) {
        const config = OAUTH_CONFIG[provider];
        if (!config) {
            console.error(`Unknown OAuth provider: ${provider}`);
            return;
        }

        try {
            // Request authorization URL from backend
            const response = await fetch(config.authorizeUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`Failed to get authorization URL: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.authorization_url) {
                // Open OAuth popup
                const width = 600;
                const height = 700;
                const left = window.screenX + (window.outerWidth - width) / 2;
                const top = window.screenY + (window.outerHeight - height) / 2;
                
                const popup = window.open(
                    data.authorization_url,
                    `${provider}_oauth`,
                    `width=${width},height=${height},left=${left},top=${top}`
                );

                if (!popup) {
                    throw new Error('Popup blocked. Please allow popups for this site.');
                }

                // Listen for OAuth completion
                this.waitForOAuthCompletion(popup, provider);
            } else {
                throw new Error('No authorization URL received');
            }
        } catch (error) {
            console.error(`OAuth initiation failed for ${provider}:`, error);
            this.updateOAuthStatus(provider, `Error: ${error.message}`, 'error');
        }
    },

    waitForOAuthCompletion(popup, provider) {
        const checkInterval = setInterval(() => {
            try {
                if (popup.closed) {
                    clearInterval(checkInterval);
                    // User closed popup without completing
                    this.updateOAuthStatus(provider, 'Authentication cancelled', 'warning');
                    return;
                }

                // Check if popup URL matches callback pattern
                const currentUrl = popup.location.href;
                if (currentUrl.includes('/oauth/') && currentUrl.includes('code=')) {
                    clearInterval(checkInterval);
                    popup.close();
                    this.handleOAuthCallback(provider, currentUrl);
                }
            } catch (e) {
                // Cross-origin restriction - popup is on different domain
                // This is expected during OAuth flow
            }
        }, 500);

        // Timeout after 5 minutes
        setTimeout(() => {
            clearInterval(checkInterval);
            if (!popup.closed) {
                popup.close();
                this.updateOAuthStatus(provider, 'Authentication timeout', 'error');
            }
        }, 300000);
    },

    async handleOAuthCallback(provider, url) {
        const config = OAUTH_CONFIG[provider];
        
        try {
            // Extract code from URL
            const urlParams = new URLSearchParams(url.split('?')[1]);
            const code = urlParams.get('code');
            const state = urlParams.get('state');

            if (!code) {
                throw new Error('No authorization code received');
            }

            // Exchange code for token
            const response = await fetch(`${config.callbackUrl}?code=${code}&state=${state}`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Token exchange failed');
            }

            const data = await response.json();
            
            // Store token securely
            if (data.access_token) {
                localStorage.setItem(config.storageKey, JSON.stringify({
                    token: data.access_token,
                    expires_at: data.expires_at,
                    scope: data.scope
                }));
                
                this.updateOAuthStatus(provider, 'Connected successfully!', 'success');
                eventBus.emit('oauth:connected', { provider, status: 'connected' });
                
                // Auto-fill project settings if in project context
                this.autoFillProjectSettings(provider, data);
            }
        } catch (error) {
            console.error(`OAuth callback failed for ${provider}:`, error);
            this.updateOAuthStatus(provider, `Callback error: ${error.message}`, 'error');
        }
    },

    autoFillProjectSettings(provider, data) {
        // Provider-specific auto-fill logic
        switch (provider) {
            case 'github':
                if (data.username) {
                    const urlInput = document.getElementById('ps-github-url');
                    if (urlInput && !urlInput.value) {
                        urlInput.placeholder = `https://github.com/${data.username}/repo.git`;
                    }
                }
                break;
            case 'x':
                // X.com doesn't need additional auto-fill
                break;
            case 'reddit':
                // Reddit doesn't need additional auto-fill
                break;
        }
    },

    checkOAuthStatus() {
        ['github', 'x', 'reddit'].forEach(provider => {
            const config = OAUTH_CONFIG[provider];
            const stored = localStorage.getItem(config.storageKey);
            
            if (stored) {
                try {
                    const tokenData = JSON.parse(stored);
                    const now = Date.now() / 1000;
                    
                    if (tokenData.expires_at && tokenData.expires_at < now) {
                        // Token expired
                        localStorage.removeItem(config.storageKey);
                        this.updateOAuthStatus(provider, 'Token expired', 'warning');
                    } else {
                        this.updateOAuthStatus(provider, 'Connected', 'success');
                    }
                } catch (e) {
                    localStorage.removeItem(config.storageKey);
                }
            }
        });
    },

    updateOAuthStatus(provider, message, type) {
        const statusEl = document.getElementById(`${provider}-oauth-status`);
        if (!statusEl) return;

        statusEl.textContent = message;
        statusEl.className = `mt-2 text-xs ${
            type === 'success' ? 'text-emerald-400' :
            type === 'error' ? 'text-red-400' :
            type === 'warning' ? 'text-amber-400' :
            'text-[var(--ide-text-muted)]'
        }`;

        // Update button state
        const button = document.getElementById(`${provider}-oauth-btn`);
        if (button) {
            if (type === 'success') {
                button.classList.add('opacity-75', 'cursor-not-allowed');
                button.setAttribute('disabled', 'true');
            } else {
                button.classList.remove('opacity-75', 'cursor-not-allowed');
                button.removeAttribute('disabled');
            }
        }
    },

    getToken(provider) {
        const config = OAUTH_CONFIG[provider];
        const stored = localStorage.getItem(config.storageKey);
        
        if (stored) {
            try {
                const tokenData = JSON.parse(stored);
                const now = Date.now() / 1000;
                
                if (tokenData.expires_at && tokenData.expires_at < now) {
                    localStorage.removeItem(config.storageKey);
                    return null;
                }
                
                return tokenData.token;
            } catch (e) {
                localStorage.removeItem(config.storageKey);
                return null;
            }
        }
        
        return null;
    },

    disconnect(provider) {
        const config = OAUTH_CONFIG[provider];
        localStorage.removeItem(config.storageKey);
        this.updateOAuthStatus(provider, 'Disconnected', 'warning');
        eventBus.emit('oauth:disconnected', { provider });
    }
};

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => oauthService.init());
} else {
    oauthService.init();
}
