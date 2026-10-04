/**
 * HTTP API Client with Strict project_id Isolation & AUTOSELECT ALL Endpoints.
 */
async function request(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...options.headers };
    const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token");
    if (token) {
        const cleanToken = token.startsWith("Bearer ") ? token.slice(7) : token;
        headers["Authorization"] = `Bearer ${cleanToken}`;
    }
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) throw new Error("Authentication required");
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

function resolveProjectId(explicitProjectId) {
    if (explicitProjectId) return explicitProjectId;
    return localStorage.getItem("rf_active_project_id") || "";
}

export const sessionsApi = {
    list: (projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request(`/api/v1/sessions${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`);
    },
    create: (title, id = null, projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request("/api/v1/sessions", {
            method: "POST",
            body: JSON.stringify({ title, id, project_id: pid }),
        });
    },
    delete: (id) => request(`/api/v1/sessions/${id}`, { method: "DELETE" }),
    messages: (id) => request(`/api/v1/sessions/${id}/messages`),
    traces: (id) => request(`/api/v1/sessions/${id}/traces`),
    tools: (id) => request(`/api/v1/sessions/${id}/tools`),
    terminal: (id) => request(`/api/v1/sessions/${id}/terminal`),
    saveTerminalEntry: (id, entry_type, content) =>
        request(`/api/v1/sessions/${id}/terminal`, {
            method: "POST",
            body: JSON.stringify({ entry_type, content }),
        }),
};

export const workspacesApi = {
    list: (projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request(`/api/v1/workspaces${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`);
    },
    active: (projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request(`/api/v1/workspaces/active${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`);
    },
    create: (payload) =>
        request("/api/v1/workspaces", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
    delete: (id) => request(`/api/v1/workspaces/${id}`, { method: "DELETE" }),
    activate: (id) => request(`/api/v1/workspaces/${id}/activate`, { method: "POST" }),
    test: (id) => request(`/api/v1/workspaces/${id}/test`, { method: "POST" }),
    tree: (projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request(`/api/v1/workspaces/tree${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`);
    },
    treeChildren: (path, projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request(`/api/v1/workspaces/tree/children?path=${encodeURIComponent(path)}${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`);
    },
    file: (path, projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request(`/api/v1/workspaces/file?path=${encodeURIComponent(path)}${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`);
    },
    saveFile: (path, content, projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request("/api/v1/workspaces/file", {
            method: "POST",
            body: JSON.stringify({ path, content, project_id: pid }),
        });
    },
    execute: (command, cwd = null, password = null, projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request("/api/v1/workspaces/execute", {
            method: "POST",
            body: JSON.stringify({ command, cwd, password, project_id: pid }),
        });
    },
};

export const gitApi = {
    status: () => request("/api/v1/git/status"),
    init: () => request("/api/v1/git/init", { method: "POST" }),
    diff: (path, staged = false) =>
        request(`/api/v1/git/diff?path=${encodeURIComponent(path || "")}&staged=${staged}`),
    log: (n = 10) => request(`/api/v1/git/log?n=${n}`),
    branches: () => request("/api/v1/git/branches"),
    commit: (message, paths = null) =>
        request("/api/v1/git/commit", {
            method: "POST",
            body: JSON.stringify({ message, paths }),
        }),
    push: (projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request("/api/v1/git/push", {
            method: "POST",
            body: JSON.stringify({ project_id: pid }),
        });
    },
    pull: (projectId = null) => {
        const pid = resolveProjectId(projectId);
        return request("/api/v1/git/pull", {
            method: "POST",
            body: JSON.stringify({ project_id: pid }),
        });
    },
};

export const projectsApi = {
    list: () => request("/api/v1/projects"),
    get: (id) => request(`/api/v1/projects/${id}`),
    create: (payload) => request("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) }),
    update: (id, payload) => request(`/api/v1/projects/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
    activate: (id) => request(`/api/v1/projects/${id}/activate`, { method: "POST" }),
    delete: (id) => request(`/api/v1/projects/${id}`, { method: "DELETE" }),
    bumpVersion: (id, changelog, bumpType = "patch") =>
        request(`/api/v1/projects/${id}/bump-version`, {
            method: "POST",
            body: JSON.stringify({ changelog, bump_type: bumpType }),
        }),
};

export const modelsApi = {
    list: () => request("/api/v1/models"),
};

export const keysApi = {
    update: (keys) => request("/api/v1/keys/update", { method: "POST", body: JSON.stringify({ keys }) }),
    delete: (provider) => request(`/api/v1/keys/${provider}`, { method: "DELETE" }),
    status: () => request("/api/v1/keys/status"),
    getSelectedModels: () => request("/api/v1/keys/selected-models"),
    saveSelectedModels: (provider_id, model_ids) =>
        request("/api/v1/keys/selected-models", {
            method: "POST",
            body: JSON.stringify({ provider_id, model_ids }),
        }),
    autoselect: (provider_id) =>
        request("/api/v1/keys/autoselect", {
            method: "POST",
            body: JSON.stringify({ provider_id }),
        }),
    autoselectAll: () =>
        request("/api/v1/keys/autoselect-all", {
            method: "POST",
        }),
};

export const billingApi = {
    status: () => request("/api/v1/billing/status"),
    credits: () => request("/api/v1/billing/credits"),
};

export const usageApi = {
    summary: (hours = 24) => request(`/api/v1/usage/summary?hours=${hours}`),
};

export const auditApi = {
    logs: (limit = 50, eventType = null) =>
        request(`/api/v1/audit/logs?limit=${limit}${eventType ? `&event_type=${eventType}` : ""}`),
};

export const supportApi = {
    createTicket: (subject, description, diagnostics = null) =>
        request("/api/v1/support/tickets", {
            method: "POST",
            body: JSON.stringify({ subject, description, diagnostics }),
        }),
    listTickets: () => request("/api/v1/support/tickets"),
};

export const socialApi = {
    generateDraft: (projectId, changelogEntry, platform = "x.com") =>
        request("/api/v1/social/draft", {
            method: "POST",
            body: JSON.stringify({ project_id: projectId, changelog_entry: changelogEntry, platform }),
        }),
    approveDraft: (draftId) => request(`/api/v1/social/drafts/${draftId}/approve`, { method: "POST" }),
    getFeedback: (projectId) => request(`/api/v1/social/feedback/${projectId}`),
};
