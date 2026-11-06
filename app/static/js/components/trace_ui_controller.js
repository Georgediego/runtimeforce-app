/**
 * Live Agent Graph and trace UI.
 * The graph is driven only by real chat-stream lifecycle events.
 */
import { eventBus } from "../core/event_bus.js";

const STAGES = ["context", "plan", "execute", "verify", "deliver"];

export const traceUIController = {
    _tools: new Map(),
    _stage: -1,

    init() {
        eventBus.on("agent:trace_event", (event) => this.appendTrace(event.badge || "INFO", event.text || ""));
        eventBus.on("agent:graph_event", (event) => this.handleGraphEvent(event || {}));
        eventBus.on("session:selected", () => this.resetGraph());
        this.resetGraph();
    },

    resetGraph() {
        this._tools.clear(); this._stage = -1; this._renderStages();
        const state = document.getElementById("rf-graph-state");
        const role = document.getElementById("rf-graph-role");
        const model = document.getElementById("rf-graph-model");
        const tools = document.getElementById("rf-graph-tools");
        if (state) { state.textContent = "IDLE"; state.classList.remove("is-running"); }
        if (role) role.textContent = "Waiting for task";
        if (model) model.textContent = "—";
        if (tools) tools.innerHTML = '<span class="rf-graph-empty">Execution events will appear here</span>';
    },

    handleGraphEvent(event) {
        const status = event.status || "";
        const label = String(event.label || "");
        const role = String(event.role || "");
        const tool = String(event.tool_name || "");
        const modelName = String(event.model || "");
        const state = document.getElementById("rf-graph-state");
        const roleEl = document.getElementById("rf-graph-role");
        const modelEl = document.getElementById("rf-graph-model");
        if (status === "phase") {
            const phase = label.toLowerCase();
            if (/context|memory|retriev/.test(phase)) this._setStage("context");
            else if (/rout|plan|architect|analyz|decompos/.test(phase)) this._setStage("plan");
            else if (/test|lint|audit|verif|check/.test(phase)) this._setStage("verify");
            else this._setStage("execute");
        } else if (["model_try", "reasoning", "streaming"].includes(status)) {
            this._setStage("execute");
        } else if (status === "tool_start") {
            const verifyTool = /test|pytest|lint|type|audit|security|check/i.test(tool);
            this._setStage(verifyTool ? "verify" : "execute");
            const id = String(event.tool_id || tool || ("tool-" + this._tools.size));
            this._tools.set(id, { name: tool || "Tool", status: "running" }); this._renderTools();
        } else if (status === "tool_end") {
            const id = String(event.tool_id || tool || "");
            const existing = this._tools.get(id) || { name: tool || "Tool" };
            this._tools.set(id, { ...existing, status: "done" }); this._renderTools();
        } else if (status === "done") {
            this._setStage("deliver");
            if (state) { state.textContent = "COMPLETE"; state.classList.remove("is-running"); }
        } else if (["error", "failed", "aborted"].includes(status)) {
            if (state) { state.textContent = status === "aborted" ? "STOPPED" : "ATTENTION"; state.classList.remove("is-running"); }
        }
        if (roleEl && (role || label)) roleEl.textContent = role || label;
        if (modelEl && modelName) modelEl.textContent = modelName.split("/").pop();
        if (state && !["done", "error", "failed", "aborted"].includes(status)) { state.textContent = "LIVE"; state.classList.add("is-running"); }
    },

    _setStage(stage) {
        const index = STAGES.indexOf(stage); if (index < 0) return;
        this._stage = Math.max(this._stage, index); this._renderStages();
    },

    _renderStages() {
        const root = document.getElementById("rf-graph-stages"); if (!root) return;
        root.querySelectorAll(".rf-graph-stage").forEach((node) => {
            const index = STAGES.indexOf(node.dataset.stage);
            node.classList.toggle("is-done", index < this._stage);
            node.classList.toggle("is-active", index === this._stage);
        });
    },

    _renderTools() {
        const root = document.getElementById("rf-graph-tools"); if (!root) return;
        const entries = Array.from(this._tools.values()).slice(-4); root.replaceChildren();
        if (!entries.length) { const empty = document.createElement("span"); empty.className = "rf-graph-empty"; empty.textContent = "Waiting for tool activity"; root.appendChild(empty); return; }
        entries.forEach((item) => {
            const chip = document.createElement("span");
            chip.className = "rf-graph-tool " + (item.status === "running" ? "is-running" : "is-done");
            chip.textContent = (item.status === "running" ? "● " : "✓ ") + item.name;
            chip.title = item.name; root.appendChild(chip);
        });
    },

    appendTrace(badge, text) {
        const log = document.getElementById("debug-trace-log"); if (!log) return;
        const entry = document.createElement("div"); entry.className = "flex items-center gap-2 text-[10px] py-1 border-b border-[var(--ide-border-subtle)]";
        const badgeEl = document.createElement("span"); badgeEl.className = "px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 font-bold uppercase shrink-0"; badgeEl.textContent = String(badge);
        const textEl = document.createElement("span"); textEl.className = "truncate flex-1 text-[var(--ide-text-primary)] font-medium"; textEl.textContent = String(text);
        const timeEl = document.createElement("span"); timeEl.className = "text-[var(--ide-text-muted)] text-[9px] shrink-0"; timeEl.textContent = new Date().toLocaleTimeString();
        entry.append(badgeEl, textEl, timeEl); log.appendChild(entry); log.scrollTop = log.scrollHeight;
    }
};
