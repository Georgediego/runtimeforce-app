/**
 * Isolated Avatar UI Service.
 * Exclusively handles rendering user profile avatars across the application.
 */

function getStoredToken() {
    return localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
}

function getStoredEmail() {
    return localStorage.getItem("rf_email") || "";
}

function parseJwt(token) {
    if (!token || typeof token !== "string") return null;
    try {
        const cleanToken = token.startsWith("Bearer ") ? token.slice(7) : token;
        const parts = cleanToken.split(".");
        if (parts.length !== 3) return null;
        let base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        const pad = base64.length % 4;
        if (pad) {
            base64 += "=".repeat(4 - pad);
        }
        const jsonPayload = decodeURIComponent(
            atob(base64)
                .split("")
                .map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
                .join("")
        );
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

function getStoredAvatarUrl() {
    let avatar = localStorage.getItem("rf_avatar") || "";
    if (!avatar) {
        const token = getStoredToken();
        if (token) {
            const payload = parseJwt(token);
            if (payload) {
                avatar = payload.avatar || payload.picture || payload.avatar_url || "";
                if (avatar) {
                    localStorage.setItem("rf_avatar", avatar);
                }
            }
        }
    }
    return avatar;
}

function renderSingleAvatar(containerEl, initial, avatarUrl) {
    if (!containerEl) return;
    containerEl.classList.add("overflow-hidden");
    containerEl.style.padding = "0";
    containerEl.style.background = "linear-gradient(135deg, #07f77a, #05d66a)";
    containerEl.style.color = "#000000";
    containerEl.style.fontWeight = "bold";

    const cleanInitial = (initial || "U").toUpperCase();
    const fallbackHTML = `<div class="w-full h-full rounded-full flex items-center justify-center text-black font-bold text-xs select-none pointer-events-none">${cleanInitial}</div>`;

    if (avatarUrl && (avatarUrl.startsWith("http://") || avatarUrl.startsWith("https://"))) {
        const img = document.createElement("img");
        img.src = avatarUrl;
        img.alt = "Avatar";
        img.referrerPolicy = "no-referrer";
        img.className = "w-full h-full rounded-full object-cover block pointer-events-none";
        img.onerror = () => {
            containerEl.innerHTML = fallbackHTML;
        };
        containerEl.innerHTML = "";
        containerEl.appendChild(img);
    } else {
        containerEl.innerHTML = fallbackHTML;
    }
}

export function renderProfileAvatars() {
    const email = getStoredEmail();
    const avatarUrl = getStoredAvatarUrl();
    const initial = email ? email[0] : "U";

    const headerBtn = document.getElementById("open-profile-btn");
    if (headerBtn) {
        renderSingleAvatar(headerBtn, initial, avatarUrl);
    }

    const settingsAvatar = document.getElementById("rf-settings-avatar");
    if (settingsAvatar) {
        renderSingleAvatar(settingsAvatar, initial, avatarUrl);
    }

    if (!avatarUrl && getStoredToken()) {
        fetchUserAvatarFromSaaS(initial);
    }
}

async function fetchUserAvatarFromSaaS(initial) {
    try {
        const token = getStoredToken();
        if (!token) return;
        const res = await fetch("https://runtimeforce.dev/auth/me", {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            const data = await res.json();
            if (data.avatar) {
                localStorage.setItem("rf_avatar", data.avatar);
                const headerBtn = document.getElementById("open-profile-btn");
                const settingsAvatar = document.getElementById("rf-settings-avatar");
                if (headerBtn) renderSingleAvatar(headerBtn, initial, data.avatar);
                if (settingsAvatar) renderSingleAvatar(settingsAvatar, initial, data.avatar);
            }
        }
    } catch (e) {}
}
