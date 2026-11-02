/**
 * Orchestrator UI Controller with ATM 5-Role Dropdowns (including Designer).
 */
import { modelsApi, keysApi, billingApi } from "../core/api_http_client.js";
import { showToast } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

const ALL_PROVIDERS = ["gemini", "openrouter", "groq", "sambanova", "cerebras", "ollama", "lm_studio", "openai", "anthropic", "perplexity", "deepseek", "xai"];

const ROLE_CAPABILITIES = {
    architect: {
        keywords: ["reason", "think", "r1", "o1", "o3", "opus", "pro", "deep", "heavy", "analysis", "ultra"],
        boostKeywords: ["opus", "r1", "o3", "pro", "ultra"],
        label: "Architect",
    },
    engineer: {
        keywords: ["code", "coder", "dev", "python", "typescript", "sonnet", "gpt-4"],
        boostKeywords: ["sonnet", "gpt-4o", "coder", "qwen"],
        label: "Engineer",
    },
    designer: {
        keywords: ["ui", "ux", "design", "css", "tailwind", "layout", "style", "frontend", "html"],
        boostKeywords: ["html", "css", "tailwind", "ui", "ux", "design"],
        label: "Designer",
    },
    tester: {
        keywords: ["code", "flash", "mini", "haiku", "turbo", "groq", "cerebras", "fast"],
        boostKeywords: ["flash", "groq", "cerebras", "haiku", "mini"],
        label: "Tester",
    },
    critic: {
        keywords: ["reason", "think", "r1", "o1", "o3", "opus", "pro"],
        boostKeywords: ["opus", "r1", "o3"],
        label: "Critic",
    },
};

export const orchestratorUIController = {
    _cachedModels: [],
    _features: {},

    async init() {
        const strategySelect = document.getElementById("strategy-select");
        const filterFree = document.getElementById("filter-tier-free");
        const filterPro = document.getElementById("filter-tier-pro");

        if (filterFree) {
            filterFree.checked = localStorage.getItem("rf_filter_tier_free") !== "false";
            filterFree.addEventListener("change", (e) => {
                localStorage.setItem("rf_filter_tier_free", e.target.checked ? "true" : "false");
                this.loadModels();
            });
        }

        if (filterPro) {
            filterPro.checked = localStorage.getItem("rf_filter_tier_pro") !== "false";
            filterPro.addEventListener("change", (e) => {
                localStorage.setItem("rf_filter_tier_pro", e.target.checked ? "true" : "false");
                this.loadModels();
            });
        }

        strategySelect?.addEventListener("change", (e) => this.handleStrategyChange(e.target.value));
        eventBus.on("auth:success", async () => { await this.loadEntitlements(); this.initModeCards(); await this.loadModels(); });
        this.initCustomDropdowns();
        initCustomSelects();
        await this.loadEntitlements();
        this.initModeCards();
        await this.loadModels();
        if (strategySelect) this.handleStrategyChange(strategySelect.value);
    },

    async loadEntitlements() {
        try {
            const data = await billingApi.entitlements();
            this._features = data?.valid ? (data.features || {}) : {};
        } catch (error) {
            this._features = {};
            console.warn("Unable to load verified plan features:", error);
        }
    },

    initModeCards() {
        const container = document.getElementById("orchestrator-mode-cards");
        if (!container) return;
        const modes = [
            { id: "auto", feature: "auto", name: "Auto", icon: "zap", color: "border-blue-500/40 text-blue-400 bg-blue-500/5", desc: "Smart local routing" },
            { id: "coding", feature: "atm", name: "Autonomous Team (ATM)", icon: "users", color: "border-emerald-500/40 text-emerald-400 bg-emerald-500/5", desc: "Architect -> Engineer -> Implementer -> Designer" },
            { id: "local", feature: "local_models", name: "Local", icon: "server", color: "border-purple-500/40 text-purple-400 bg-purple-500/5", desc: "Offline-first (Ollama/LM Studio)" },
            { id: "manual", feature: "manual", name: "Manual", icon: "settings", color: "border-amber-500/40 text-amber-400 bg-amber-500/5", desc: "Lock to specific model" },
        ];
        const currentStrategy = document.getElementById("strategy-select")?.value || "auto";
        container.innerHTML = modes
            .map((m) => {
                const isActive = m.id === currentStrategy;
                const enabled = this._features[m.feature] === true;
                return `
                <div class="mode-card cursor-pointer p-3 rounded-xl border transition-all duration-200 ${m.color} ${!enabled ? "opacity-40 cursor-not-allowed" : isActive ? "ring-2 ring-[var(--ide-accent)] shadow-lg" : "opacity-80 hover:opacity-100"}" data-mode="${m.id}">
                    <div class="flex items-center justify-between mb-1">
                        <div class="flex items-center gap-2">
                            <i data-lucide="${m.icon}" class="w-4 h-4"></i>
                            <span class="font-bold text-xs">${m.name}</span>
                        </div>
                        ${!enabled ? '<span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-[var(--ide-elevated)] text-[var(--ide-text-muted)] uppercase">Not included</span>' : ""}
                    </div>
                    <p class="text-[11px] text-[var(--ide-text-secondary)] leading-tight">${m.desc}</p>
                </div>`;
            })
            .join("");
        if (window.lucide) window.lucide.createIcons({ root: container });
        container.querySelectorAll(".mode-card").forEach((card) => {
            card.addEventListener("click", () => {
                const modeId = card.dataset.mode;
                const featureKey = ({ auto: "auto", coding: "atm", local: "local_models", manual: "manual" })[modeId];
                if (this._features[featureKey] !== true) {
                    showToast("This feature is not enabled for your current plan.", "warning");
                    return;
                }
                const strategySelect = document.getElementById("strategy-select");
                if (strategySelect) {
                    strategySelect.value = modeId;
                    strategySelect.dispatchEvent(new Event("change"));
                }
                this.initModeCards();
            });
        });
    },

    initCustomDropdowns() {
        document.querySelectorAll(".custom-select-wrapper").forEach((wrapper) => {
            const trigger = wrapper.querySelector('[id$="-trigger"]');
            const dropdown = wrapper.querySelector('[id$="-dropdown"]');
            if (!trigger || !dropdown) return;
            trigger.addEventListener("click", (e) => {
                e.stopPropagation();
                document.querySelectorAll('[id$="-dropdown"]').forEach((d) => {
                    if (d !== dropdown) d.classList.add("hidden");
                });
                dropdown.classList.toggle("hidden");
                if (!dropdown.classList.contains("hidden")) {
                    const searchInput = dropdown.querySelector(".custom-model-search");
                    if (searchInput) {
                        searchInput.focus();
                        searchInput.value = "";
                        dropdown.querySelectorAll(".option-item").forEach((opt) => opt.classList.remove("hidden"));
                    }
                }
            });
        });
        document.addEventListener("click", () => {
            document.querySelectorAll('[id$="-dropdown"]').forEach((d) => d.classList.add("hidden"));
        });
        document.querySelectorAll(".custom-model-search").forEach((input) => {
            input.addEventListener("click", (e) => e.stopPropagation());
            input.addEventListener("input", (e) => {
                const filterText = e.target.value.toLowerCase().trim();
                const dropdown = e.target.closest('[id$="-dropdown"]');
                if (!dropdown) return;
                dropdown.querySelectorAll(".option-item").forEach((opt) => {
                    const text = opt.textContent.toLowerCase();
                    const val = (opt.dataset.value || "").toLowerCase();
                    if (!filterText || text.includes(filterText) || val.includes(filterText) || opt.dataset.value === "auto") {
                        opt.classList.remove("hidden");
                    } else {
                        opt.classList.add("hidden");
                    }
                });
            });
        });
    },

    async getEnabledModelsSet() {
        const enabled = new Set();
        try {
            const data = await keysApi.getSelectedModels();
            const selectedMap = data.selected_models || {};
            Object.values(selectedMap).forEach((ids) => {
                if (Array.isArray(ids)) ids.forEach((id) => enabled.add(id));
            });
        } catch (e) {
            console.warn("Failed to get selected models:", e);
        }
        return enabled;
    },

    handleStrategyChange(strategy) {
        const settingsPanel = document.getElementById("orchestrator-settings");
        const manualPanel = document.getElementById("settings-manual-panel");
        const atmPanel = document.getElementById("settings-atm-panel");
        const filtersContainer = document.getElementById("model-filters-container");

        if (settingsPanel) settingsPanel.classList.remove("hidden");
        if (filtersContainer) filtersContainer.classList.remove("hidden");

        manualPanel?.classList.add("hidden");
        atmPanel?.classList.add("hidden");

        if (strategy === "manual") {
            manualPanel?.classList.remove("hidden");
        } else if (strategy === "coding") {
            atmPanel?.classList.remove("hidden");
            this.populateATMDropdowns();
        }
        this.initModeCards();
    },

    _scoreModelForRole(model, roleKey) {
        const roleCfg = ROLE_CAPABILITIES[roleKey];
        if (!roleCfg) return 0;
        const modelText = `${model.id || ""} ${model.name || ""} ${(model.capabilities || []).join(" ")}`.toLowerCase();
        let score = 0;
        roleCfg.keywords.forEach((kw) => {
            if (modelText.includes(kw)) score += 5;
        });
        roleCfg.boostKeywords.forEach((kw) => {
            if (modelText.includes(kw)) score += 10;
        });
        const ctx = model.context_window || 8000;
        if (ctx >= 128000) score += 5;
        else if (ctx >= 32000) score += 3;
        const tier = (model.tier || "").toLowerCase();
        if (tier === "free") score += 2;
        return score;
    },

    _escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    },

    async _filterModelsByTier(models) {
        const allowFree = localStorage.getItem("rf_filter_tier_free") !== "false";
        const allowPro = localStorage.getItem("rf_filter_tier_pro") !== "false";
        const enabledSet = await this.getEnabledModelsSet();
        const FREE_PROVIDERS_SET = new Set(["gemini", "groq", "sambanova", "cerebras", "ollama", "lm_studio"]);

        return models.filter((m) => {
            if (enabledSet.size > 0 && !enabledSet.has(m.id)) return false;
            const isFree = m.tier === "free" || FREE_PROVIDERS_SET.has(m.provider);
            if (isFree && !allowFree) return false;
            if (!isFree && !allowPro) return false;
            return true;
        });
    },

    async populateATMDropdowns() {
        // ATM role overrides are not currently wired through the coordinator's per-role execution path.
        // Keep this legacy selector local-only until each role has a real server route.
        const filtered = await this._filterModelsByTier(this._cachedModels);
        const roles = ["architect", "engineer", "designer", "tester", "critic"];
        roles.forEach((roleKey) => {
            const container = document.getElementById(`atm-${roleKey}-options`);
            if (!container) return;

            let optionsHTML = `<div data-value="" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded bg-[var(--ide-elevated-2)] font-bold">Auto (recommended)</div>`;
            if (!filtered.length) {
                optionsHTML += `<div class="option-item px-2 py-1 text-[var(--ide-text-muted)] cursor-not-allowed rounded" style="pointer-events: none;">No models selected. Open Providers to choose models.</div>`;
            } else {
                const scored = filtered.map((m) => ({ model: m, score: this._scoreModelForRole(m, roleKey) }));
                scored.sort((a, b) => b.score - a.score);
                const top = scored.filter((s) => s.score > 0).slice(0, 20);
                const list = top.length > 0 ? top.map((s) => s.model) : filtered.slice(0, 20);

                list.forEach((m) => {
                    const modelId = this._escapeHtml(m.id);
                    const modelName = this._escapeHtml(m.name);
                    const provider = this._escapeHtml(m.provider);
                    optionsHTML += `<div data-value="${modelId}" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded truncate" title="${modelName}">${modelName} (${provider})</div>`;
                });
            }
            container.innerHTML = optionsHTML;
        });
    },

    async loadModels() {
        try {
            const allModels = [];
            const localResult = await modelsApi.list().catch((error) => {
                console.warn("Local model catalog is unavailable:", error);
                return { models: {} };
            });
            const modelsByProvider = localResult.models || {};
            Object.entries(modelsByProvider).forEach(([provider, models]) => {
                (models || []).forEach((model) => {
                    allModels.push({ ...model, provider });
                });
            });
            this._cachedModels = allModels;

            const filteredModels = await this._filterModelsByTier(allModels);

            const panels = [{ optionsContainerId: "model-lock-options" }];
            panels.forEach((p) => {
                const container = document.getElementById(p.optionsContainerId);
                if (!container) return;
                let optionsHTML = `<div data-value="" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded bg-[var(--ide-elevated-2)] font-bold">Auto (recommended)</div>`;
                if (!filteredModels.length) {
                    optionsHTML += `<div class="option-item px-2 py-1 text-[var(--ide-text-muted)] cursor-not-allowed rounded" style="pointer-events: none;">No models selected. Open Providers to choose models.</div>`;
                } else {
                    filteredModels.forEach((m) => {
                        const modelId = this._escapeHtml(m.id);
                        const modelName = this._escapeHtml(m.name);
                        const provider = this._escapeHtml(m.provider);
                        optionsHTML += `<div data-value="${modelId}" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded truncate" title="${modelName}">${modelName} (${provider})</div>`;
                    });
                }
                container.innerHTML = optionsHTML;
            });

            const strategy = document.getElementById("strategy-select")?.value;
            if (strategy === "coding") await this.populateATMDropdowns();
        } catch (e) {
            console.warn("Failed to load models:", e);
        }
    },
};

// Click handling for custom dropdowns (trigger / options / hidden input pattern).
// Wrappers that contain a "-dropdown" container are handled by initCustomDropdowns().
export function initCustomSelects() {
  if (window.__rfCustomSelectsInit) return;
  window.__rfCustomSelectsInit = true;

  let wrapperIndex = 0;
  document.querySelectorAll('.custom-select-wrapper').forEach((wrapper) => {
    if (!wrapper.id) wrapper.id = `rf-custom-select-${wrapperIndex++}`;
    const options = wrapper.querySelector('[id$="-options"]');
    const trigger = wrapper.querySelector('[id$="-trigger"]');
    const hidden = wrapper.querySelector('input[type="hidden"]');
    if (options) {
      options.dataset.ownerId = wrapper.id;
      options.dataset.triggerId = trigger?.id || '';
      options.dataset.hiddenId = hidden?.id || '';
      if (trigger) trigger.dataset.optionsId = options.id;
    }
  });

  let activePortalOptions = null;
  let activePortalTrigger = null;

  const closeAll = (except) => {
    document.querySelectorAll('.custom-select-wrapper [id$="-options"], .custom-select-portal').forEach((opts) => {
      if (opts !== except && !opts.closest('[id$="-dropdown"]')) opts.classList.add('hidden');
    });
    if (activePortalOptions !== except) {
      activePortalOptions = null;
      activePortalTrigger = null;
    }
  };

  const positionPortal = (options, trigger) => {
    const rect = trigger.getBoundingClientRect();
    const padding = 8;
    const roomBelow = Math.max(0, window.innerHeight - rect.bottom - padding);
    const roomAbove = Math.max(0, rect.top - padding);
    const openUp = roomBelow < 180 && roomAbove > roomBelow;
    const available = openUp ? roomAbove : roomBelow;
    const maxHeight = Math.max(80, Math.min(240, available || 240, window.innerHeight - padding * 2));
    const width = Math.min(rect.width, window.innerWidth - padding * 2);
    const left = Math.min(Math.max(padding, rect.left), Math.max(padding, window.innerWidth - width - padding));
    const proposedTop = openUp ? rect.top - maxHeight - 4 : rect.bottom + 4;
    const top = Math.min(Math.max(padding, proposedTop), Math.max(padding, window.innerHeight - maxHeight - padding));

    if (options.parentElement !== document.body) document.body.appendChild(options);
    options.classList.add('custom-select-portal');
    Object.assign(options.style, {
      position: 'fixed',
      top: `${top}px`,
      bottom: 'auto',
      left: `${left}px`,
      right: 'auto',
      width: `${width}px`,
      maxHeight: `${maxHeight}px`,
      zIndex: '10000',
    });
  };

  const openPortal = (options, trigger) => {
    activePortalOptions = options;
    activePortalTrigger = trigger;
    positionPortal(options, trigger);
  };

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const option = target.closest('.custom-select-wrapper .option-item, .custom-select-portal .option-item');
    if (option) {
      const options = option.closest('[id$="-options"]');
      const wrapper = document.getElementById(options?.dataset.ownerId || '') || option.closest('.custom-select-wrapper');
      const trigger = document.getElementById(options?.dataset.triggerId || '') || wrapper?.querySelector('[id$="-trigger"]');
      const hidden = document.getElementById(options?.dataset.hiddenId || '') || wrapper?.querySelector('input[type="hidden"]');
      const value = option.dataset.value || '';
      if (hidden) {
        hidden.value = value;
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const label = trigger ? trigger.querySelector('span') : null;
      if (label) label.textContent = option.textContent.trim();
      options?.querySelectorAll('.option-item').forEach((el) => el.classList.remove('font-bold'));
      option.classList.add('font-bold');
      if (options) options.classList.add('hidden');
      if (activePortalOptions === options) {
        activePortalOptions = null;
        activePortalTrigger = null;
      }
      return;
    }

    const trigger = target.closest('.custom-select-wrapper [id$="-trigger"]');
    if (trigger) {
      const wrapper = trigger.closest('.custom-select-wrapper');
      const options = document.getElementById(trigger.dataset.optionsId || '') || wrapper.querySelector('[id$="-options"]');
      if (!options) return;
      const willOpen = options.classList.contains('hidden');
      closeAll(options);
      if (willOpen) {
        openPortal(options, trigger);
        options.classList.remove('hidden');
      } else {
        options.classList.add('hidden');
        if (activePortalOptions === options) {
          activePortalOptions = null;
          activePortalTrigger = null;
        }
      }
      return;
    }

    closeAll(null);
  });

  const repositionOpenPortal = () => {
    if (activePortalOptions && activePortalTrigger && !activePortalOptions.classList.contains('hidden')) {
      positionPortal(activePortalOptions, activePortalTrigger);
    }
  };
  document.addEventListener('scroll', repositionOpenPortal, true);
  window.addEventListener('resize', repositionOpenPortal);
}
