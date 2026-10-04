/**
 * Pub/Sub EventBus ES Module.
 * Eliminates direct component calls and window.* pollution.
 */
class EventBusService {
    constructor() {
        this.listeners = new Map();
    }

    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(callback);
        return () => this.off(event, callback);
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).delete(callback);
        }
    }

    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(cb => {
                try {
                    cb(data);
                } catch (e) {
                    console.error(`[EventBus] Error in handler for "${event}":`, e);
                }
            });
        }
    }
}

export const eventBus = new EventBusService();
