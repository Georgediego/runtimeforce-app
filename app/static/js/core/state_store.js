/**
 * Central Reactive State Manager.
 */
import { eventBus } from "./event_bus.js";

class StateStoreManager {
    constructor() {
        this.state = {
            theme: localStorage.getItem("ide:theme") || "dark",
            allSessions: [],
            currentSessionId: null,
            chatHistory: [],
            isGenerating: false,
            attachedContext: [],
            activeWorkspace: null,
            workspaces: [],
            gitStatus: { is_repo: false, entries: [] },
            models: {},
            providersWithKeys: [],
        };
    }

    get(key) {
        return this.state[key];
    }

    set(key, value) {
        this.state[key] = value;
        eventBus.emit(`state:${key}`, value);
    }
}

export const stateStore = new StateStoreManager();
