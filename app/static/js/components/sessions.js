import { state, setState } from "../state.js";
import { sessionsApi } from "../api.js";
import { escapeHtml, escapeRegex } from "../utils/escape.js";
import { formatSessionTime } from "../utils/format.js";
import { refreshIcons } from "../utils/icons.js";
import { showToast } from "./toast.js";

export async function loadSessions() {
    const container = document.getElementById("sessions-list");
    if (!container) return;
    try {
        const data = await sessionsApi.list();
        setState("allSessions", data.sessions || []);
        renderSessions(state.allSessions);
    } catch (e) {
        container.innerHTML = '<div class="text-center text-xs text-ide-error py-2">Ошибка</div>';
    }
}

function sessionItemHTML(s, q) {
    const isActive = s.id === state.currentSessionId;
    const rawTitle = s.title || "Без названия";
    const title = q ? highlightText(escapeHtml(rawTitle), q) : escapeHtml(rawTitle);
    const time = formatSessionTime(s.updated_at || s.created_at);
    const iconColor = isActive ? "var(--ide-accent)" : "var(--ide-muted)";

    return `
        <div class="session-item ${isActive ? 'active' : ''}" data-session-id="${s.id}">
            <i data-lucide="message-square" class="w-3.5 h-3.5 shrink-0" style="color: ${iconColor}"></i>
            <div class="session-content">
                <span class="session-title">${title}</span>
                <div class="session-meta">
                    <span class="session-time">${time}</span>
                    <div class="session-delete-btn" data-delete-id="${s.id}" title="Удалить">
                        <i data-lucide="trash-2" class="w-2.5 h-2.5"></i>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function bindSessionEvents(container) {
    container.onclick = (e) => {
        const deleteBtn = e.target.closest(".session-delete-btn");
        if (deleteBtn) {
            e.stopPropagation();
            deleteSession(deleteBtn.dataset.deleteId);
            return;
        }

        const toggleBtn = e.target.closest("#toggle-history-btn");
        if (toggleBtn) {
            e.stopPropagation();
            const historyDiv = document.getElementById("sessions-history");
            const chevron = document.getElementById("history-chevron");
            if (historyDiv) {
                const isHidden = historyDiv.style.display === "none";
                historyDiv.style.display = isHidden ? "block" : "none";
                if (chevron) {
                    chevron.style.transform = isHidden ? "rotate(180deg)" : "rotate(0deg)";
                }
            }
            return;
        }

        const sessionItem = e.target.closest(".session-item");
        if (sessionItem) {
            openSession(sessionItem.dataset.sessionId);
        }
    };
}

export function renderSessions(sessions, q) {
    const container = document.getElementById("sessions-list");
    if (!container) return;

    if (!sessions || !sessions.length) {
        container.innerHTML = `<div class="text-center text-xs text-ide-muted py-3">${q ? 'Ничего не найдено' : 'Нет сессий.'}</div>`;
        return;
    }

    if (q) {
        container.innerHTML = sessions.map(s => sessionItemHTML(s, q)).join("");
        bindSessionEvents(container);
        refreshIcons(container);
        return;
    }

    let topSession = null;
    const others = [];

    for (const s of sessions) {
        if (s.id === state.currentSessionId) {
            topSession = s;
        } else {
            others.push(s);
        }
    }

    if (!topSession && others.length > 0) {
        topSession = others.shift();
    }

    let html = "";

    if (topSession) {
        html += sessionItemHTML(topSession, "");
    }

    if (others.length > 0) {
        html += `
            <button id="toggle-history-btn" class="toggle-history-btn">
                <span>История (${others.length})</span>
                <i data-lucide="chevron-down" class="w-3 h-3 transition-transform" id="history-chevron"></i>
            </button>
            <div id="sessions-history" style="display: none;">
                ${others.map(s => sessionItemHTML(s, "")).join("")}
            </div>
        `;
    }

    container.innerHTML = html;
    bindSessionEvents(container);
    refreshIcons(container);
}

function highlightText(text, q) {
    if (!q) return text;
    return text.replace(new RegExp("(" + escapeRegex(q) + ")", "gi"), '<span class="session-match">$1</span>');
}

export async function openSession(id) {
    setState("currentSessionId", id);
    renderSessions(state.allSessions);
    try {
        const data = await sessionsApi.messages(id);
        setState("chatHistory", data.messages || []);
        const chatHistoryDOM = document.getElementById("chat-history");
        if (chatHistoryDOM) {
            chatHistoryDOM.innerHTML = "";
            state.chatHistory.forEach(m => {
                window.dispatchEvent(new CustomEvent("render-message", { detail: m }));
            });
        }
        window.dispatchEvent(new CustomEvent("agent-status", { detail: { status: "Idle" } }));
    } catch (e) {
        showToast("Ошибка загрузки истории", "error");
    }
}

async function deleteSession(id) {
    if (!confirm("Удалить сессию?")) return;
    try {
        await sessionsApi.delete(id);
        if (state.currentSessionId === id) {
            setState("currentSessionId", null);
            window.dispatchEvent(new CustomEvent("new-chat"));
        }
        showToast("Сессия удалена", "success");
        loadSessions();
    } catch (e) {
        showToast("Ошибка удаления", "error");
    }
}

export function initSearch() {
    const input = document.getElementById("search-input");
    const clearBtn = document.getElementById("search-clear");
    const countEl = document.getElementById("search-results-count");
    if (!input) return;

    input.addEventListener("input", () => {
        const q = input.value.trim();
        if (clearBtn) clearBtn.classList.toggle("hidden", !q);
        clearTimeout(state.searchDebounce);
        if (!q) {
            renderSessions(state.allSessions);
            if (countEl) countEl.classList.add("hidden");
            return;
        }
        state.searchDebounce = setTimeout(() => performSearch(q), 250);
    });

    if (clearBtn) {
        clearBtn.addEventListener("click", () => {
            input.value = "";
            clearBtn.classList.add("hidden");
            renderSessions(state.allSessions);
            if (countEl) countEl.classList.add("hidden");
        });
    }
}

async function performSearch(q) {
    const lower = q.toLowerCase();
    const matches = [];
    const countEl = document.getElementById("search-results-count");
    if (countEl) {
        countEl.classList.remove("hidden");
        countEl.textContent = "Поиск...";
    }

    for (const s of state.allSessions) {
        if (s.title && s.title.toLowerCase().includes(lower)) {
            matches.push(s);
            continue;
        }
        const msgs = await getMessagesCached(s.id);
        const found = msgs.some(m => m.content && m.content.toLowerCase().includes(lower));
        if (found) matches.push(s);
    }

    renderSessions(matches, q);
    if (countEl) {
        countEl.textContent = `Найдено: ${matches.length} из ${state.allSessions.length}`;
    }
}

async function getMessagesCached(id) {
    if (state.sessionsCache && state.sessionsCache.has(id)) {
        return state.sessionsCache.get(id);
    }
    try {
        const data = await sessionsApi.messages(id);
        const msgs = data.messages || [];
        if (state.sessionsCache) {
            state.sessionsCache.set(id, msgs);
        }
        return msgs;
    } catch (e) {
        return [];
    }
}