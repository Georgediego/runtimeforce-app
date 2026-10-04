/**
 * Dedicated Agent Trace & Active Tools UI Controller.
 */
import { eventBus } from "../core/event_bus.js";

export const traceUIController = {
    init() {
        eventBus.on("agent:trace_event", (event) => {
            this.appendTrace(event.badge || "INFO", event.text || "");
        });
    },

    appendTrace(badge, text) {
        const log = document.getElementById("debug-trace-log");
        if (!log) return;
        const time = new Date().toLocaleTimeString();
        const entry = document.createElement("div");
        entry.className = "flex items-center gap-2 text-[10px] py-1 border-b border-[var(--ide-border-subtle)]";
        entry.innerHTML = `
            <span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-bold uppercase shrink-0">${badge}</span>
            <span class="truncate flex-1 text-[var(--ide-text-primary)] font-medium">${text}</span>
            <span class="text-[var(--ide-text-muted)] text-[9px] shrink-0">${time}</span>
        `;
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight;
    }
};
