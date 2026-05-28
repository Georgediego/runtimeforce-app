
export const state = {
    theme: localStorage.getItem("ide:theme") || "dark",
    allSessions: [],
    currentSessionId: null,
    sessionsCache: new Map(),
    chatHistory: [],
    isGenerating: false,
    attachedContext: [],
    activeWorkspace: null,
    workspaces: [],
    cachedFileTree: null,
    gitStatus: { is_repo: false, entries: [] },
    searchDebounce: null,
    models: {},
    providersWithKeys: [],
};

const subscribers = new Map();

export function subscribe(key, callback) {
    if (!subscribers.has(key)) subscribers.set(key, new Set());
    subscribers.get(key).add(callback);
    return () => subscribers.get(key).delete(callback);
}

export function setState(key, value) {
    state[key] = value;
    const subs = subscribers.get(key);
    if (subs) {
        for (const cb of subs) {
            try { cb(value); } catch (e) { console.error("Subscriber error:", e); }
        }
    }
}
