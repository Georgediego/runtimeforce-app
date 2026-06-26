const BASE = "";

/**
 * Единый шлюз для всех запросов.
 * Гарантирует, что авторизация (JWT) всегда присутствует, если она есть в хранилище.
 */
async function request(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...options.headers };

    // Централизованный поиск токена — порядок приоритета зафиксирован
    const token = localStorage.getItem("rf_jwt_token")
               || localStorage.getItem("jwt_token")
               || localStorage.getItem("access_token");
    if (token) {
        const cleanToken = token.startsWith("Bearer ") ? token.slice(7) : token;
        headers["Authorization"] = "Bearer " + cleanToken;
    }

    const res = await fetch(BASE + path, { ...options, headers });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "HTTP " + res.status }));
        throw new Error(err.detail || ("HTTP " + res.status));
    }
    return res.json();
}

// Сессии
export const sessionsApi = {
    list: () => request("/api/v1/sessions"),
    create: (title, id = null) => request("/api/v1/sessions", {
        method: "POST", body: JSON.stringify({ title, id })
    }),
    delete: (id) => request("/api/v1/sessions/" + id, { method: "DELETE" }),
    messages: (id) => request("/api/v1/sessions/" + id + "/messages"),
};

// Workspaces
export const workspacesApi = {
    list: () => request("/api/v1/workspaces"),
    active: () => request("/api/v1/workspaces/active"),
    create: (payload) => request("/api/v1/workspaces", {
        method: "POST", body: JSON.stringify(payload)
    }),
    delete: (id) => request("/api/v1/workspaces/" + id, { method: "DELETE" }),
    activate: (id) => request("/api/v1/workspaces/" + id + "/activate", { method: "POST" }),
    test: (id) => request("/api/v1/workspaces/" + id + "/test", { method: "POST" }),
    tree: () => request("/api/v1/workspaces/tree"),
    treeChildren: (path) => request("/api/v1/workspaces/tree/children?path=" + encodeURIComponent(path)),
    file: (path) => request("/api/v1/workspaces/file?path=" + encodeURIComponent(path)),
    // ДОБАВЛЕНО: Функция сохранения файла
    saveFile: (path, content) => request("/api/v1/workspaces/file", {
        method: "POST", // или PUT в зависимости от вашего бэкенда
        body: JSON.stringify({ path: path, content: content })
    })
};

// Git
export const gitApi = {
    status: () => request("/api/v1/git/status"),
    init: () => request("/api/v1/git/init", { method: "POST" }), 
    diff: (path, staged = false) => request("/api/v1/git/diff?path=" + encodeURIComponent(path || "") + "&staged=" + staged),
    log: (n = 10) => request("/api/v1/git/log?n=" + n),
    branches: () => request("/api/v1/git/branches"),
    commit: (message, paths = null) => request("/api/v1/git/commit", {
        method: "POST", body: JSON.stringify({ message, paths })
    }),
    revert: (path) => request("/api/v1/git/revert", {
        method: "POST", body: JSON.stringify({ path })
    }),
};

// Модели
export const modelsApi = {
    list: () => request("/api/v1/models"),
};

// Ключи
export const keysApi = {
    update: (keys) => request("/api/v1/keys/update", {
        method: "POST", body: JSON.stringify({ keys })
    }),
    clear: () => request("/api/v1/keys/clear", { method: "POST" }),
};

// Стриминг чата — авторизация через тот же механизм
export async function* streamChat(payload) {
    const headers = { "Content-Type": "application/json" };

    const token = localStorage.getItem("rf_jwt_token")
               || localStorage.getItem("jwt_token")
               || localStorage.getItem("access_token");
    if (token) {
        const cleanToken = token.startsWith("Bearer ") ? token.slice(7) : token;
        headers["Authorization"] = "Bearer " + cleanToken;
    }

    const res = await fetch(BASE + "/api/v1/chat/stream", {
        method: "POST", headers, body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();
        for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6).trim();
            if (data === "[DONE]") continue;
            try {
                yield JSON.parse(data);
            } catch (e) {
                console.error("SSE parse error:", e, data);
            }
        }
    }
}