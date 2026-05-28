
const BASE = "";

async function request(path, options = {}) {
    const res = await fetch(BASE + path, {
        headers: { "Content-Type": "application/json", ...options.headers },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "HTTP " + res.status }));
        throw new Error(err.detail || ("HTTP " + res.status));
    }
    return res.json();
}

export const sessionsApi = {
    list: () => request("/api/v1/sessions"),
    create: (title, id = null) => request("/api/v1/sessions", {
        method: "POST", body: JSON.stringify({ title, id })
    }),
    delete: (id) => request("/api/v1/sessions/" + id, { method: "DELETE" }),
    messages: (id) => request("/api/v1/sessions/" + id + "/messages"),
};

export const workspacesApi = {
    list: () => request("/api/v1/workspaces"),
    create: (payload) => request("/api/v1/workspaces", {
        method: "POST", body: JSON.stringify(payload)
    }),
    delete: (id) => request("/api/v1/workspaces/" + id, { method: "DELETE" }),
    activate: (id) => request("/api/v1/workspaces/" + id + "/activate", { method: "POST" }),
    test: (id) => request("/api/v1/workspaces/" + id + "/test", { method: "POST" }),
    tree: () => request("/api/v1/workspaces/tree"),
    treeChildren: (path) => request("/api/v1/workspaces/tree/children?path=" + encodeURIComponent(path)),
    file: (path) => request("/api/v1/workspaces/file?path=" + encodeURIComponent(path)),
    saveFile: (path, content) => request("/api/v1/workspaces/file", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, content }) }),
};

export const gitApi = {
    status: () => request("/api/v1/git/status"),
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

export const modelsApi = {
    list: () => request("/api/v1/models"),
};

export const keysApi = {
    update: (keys) => request("/api/v1/keys/update", {
        method: "POST", body: JSON.stringify({ keys })
    }),
    clear: () => request("/api/v1/keys/clear", { method: "POST" }),
};

export async function* streamChat(payload) {
    const res = await fetch(BASE + "/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
