/**
 * Orchestrator UI Controller with ATM 5-Role Dropdowns (including Designer).
 */
import { modelsApi, keysApi } from "../core/api_http_client.js";

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
        this.initCustomDropdowns();
        initCustomSelects();
        this.initModeCards();
        await this.loadModels();
        if (strategySelect) this.handleStrategyChange(strategySelect.value);
    },

    initModeCards() {
        const container = document.getElementById("orchestrator-mode-cards");
        if (!container) return;
        const plan = localStorage.getItem("rf_plan") || "free";
        const modes = [
            { id: "auto", name: "Auto", icon: "zap", color: "border-blue-500/40 text-blue-400 bg-blue-500/5", desc: "Smart local routing", premium: false },
            { id: "coding", name: "Autonomous Team (ATM)", icon: "users", color: "border-emerald-500/40 text-emerald-400 bg-emerald-500/5", desc: "Architect -> Engineer -> Implementer -> Designer", premium: plan === "free" },
            { id: "local", name: "Local", icon: "server", color: "border-purple-500/40 text-purple-400 bg-purple-500/5", desc: "Offline-first (Ollama/LM Studio)", premium: false },
            { id: "manual", name: "Manual", icon: "settings", color: "border-amber-500/40 text-amber-400 bg-amber-500/5", desc: "Lock to specific model", premium: false },
        ];
        const currentStrategy = document.getElementById("strategy-select")?.value || "auto";
        container.innerHTML = modes
            .map((m) => {
                const isActive = m.id === currentStrategy;
                return `
                <div class="mode-card cursor-pointer p-3 rounded-xl border transition-all duration-200 ${m.color} ${isActive ? "ring-2 ring-[var(--ide-accent)] shadow-lg" : "opacity-80 hover:opacity-100"}" data-mode="${m.id}">
                    <div class="flex items-center justify-between mb-1">
                        <div class="flex items-center gap-2">
                            <i data-lucide="${m.icon}" class="w-4 h-4"></i>
                            <span class="font-bold text-xs">${m.name}</span>
                        </div>
                        ${m.premium ? '<span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 uppercase">Premium</span>' : ""}
                    </div>
                    <p class="text-[11px] text-[var(--ide-text-secondary)] leading-tight">${m.desc}</p>
                </div>`;
            })
            .join("");
        if (window.lucide) window.lucide.createIcons({ root: container });
        container.querySelectorAll(".mode-card").forEach((card) => {
            card.addEventListener("click", () => {
                const modeId = card.dataset.mode;
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
        const filtered = await this._filterModelsByTier(this._cachedModels);
        const roles = ["architect", "engineer", "designer", "tester", "critic"];
        roles.forEach((roleKey) => {
            const container = document.getElementById(`atm-${roleKey}-options`);
            const hiddenInput = document.getElementById(`atm-${roleKey}-select`);
            const triggerSpan = document.getElementById(`atm-${roleKey}-trigger`)?.querySelector("span:first-child");
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
                    optionsHTML += `<div data-value="${m.id}" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded truncate" title="${m.name}">${m.name} (${m.provider})</div>`;
                });
            }
            container.innerHTML = optionsHTML;

            container.querySelectorAll(".option-item").forEach((opt) => {
                if (!opt.dataset.value && opt.dataset.value !== "") return;
                opt.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const val = opt.dataset.value;
                    if (hiddenInput) hiddenInput.value = val;
                    if (triggerSpan) triggerSpan.textContent = opt.textContent;
                    container.querySelectorAll(".option-item").forEach((o) => o.classList.remove("bg-[var(--ide-border-subtle)]", "font-bold"));
                    opt.classList.add("bg-[var(--ide-border-subtle)]", "font-bold");
                    container.classList.add("hidden");
                    const dropdown = container.closest('[id$="-dropdown"]') || container.closest('.custom-select-wrapper');
                    if (dropdown) dropdown.classList.add("hidden");
                });
            });
        });
    },

    async loadModels() {
        try {
            const data = await modelsApi.list();
            const modelsByProvider = data.models || {};
            const allModels = [];
            Object.entries(modelsByProvider).forEach(([provider, models]) => {
                models.forEach((m) => {
                    allModels.push({ ...m, provider });
                });
            });
            this._cachedModels = allModels;

            const filteredModels = await this._filterModelsByTier(allModels);

            const panels = [
                { hiddenInputId: "model-lock-select", triggerId: "model-lock-trigger", optionsContainerId: "model-lock-options" },
            ];
            panels.forEach((p) => {
                const container = document.getElementById(p.optionsContainerId);
                const hiddenInput = document.getElementById(p.hiddenInputId);
                const triggerSpan = document.getElementById(p.triggerId)?.querySelector("span:first-child");
                if (!container) return;
                let optionsHTML = `<div data-value="" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded bg-[var(--ide-elevated-2)] font-bold">Auto (recommended)</div>`;
                if (!filteredModels.length) {
                    optionsHTML += `<div class="option-item px-2 py-1 text-[var(--ide-text-muted)] cursor-not-allowed rounded" style="pointer-events: none;">No models selected. Open Providers to choose models.</div>`;
                } else {
                    filteredModels.forEach((m) => {
                        optionsHTML += `<div data-value="${m.id}" class="option-item px-2 py-1 hover:bg-[var(--ide-accent)] hover:text-black cursor-pointer rounded truncate" title="${m.name}">${m.name} (${m.provider})</div>`;
                    });
                }
                container.innerHTML = optionsHTML;
                container.querySelectorAll(".option-item").forEach((opt) => {
                    if (!opt.dataset.value && opt.dataset.value !== "") return;
                    opt.addEventListener("click", (e) => {
                        e.stopPropagation();
                        const val = opt.dataset.value;
                        if (hiddenInput) hiddenInput.value = val;
                        if (triggerSpan) triggerSpan.textContent = opt.textContent;
                        container.querySelectorAll(".option-item").forEach((o) => o.classList.remove("bg-[var(--ide-border-subtle)]", "font-bold"));
                        opt.classList.add("bg-[var(--ide-border-subtle)]", "font-bold");
                        container.classList.add("hidden");
                        const dropdown = container.closest('[id$="-dropdown"]') || container.closest('.custom-select-wrapper');
                        if (dropdown) dropdown.classList.add("hidden");
                    });
                });
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

  const closeAll = (except) => {
    document.querySelectorAll('.custom-select-wrapper [id$="-options"]').forEach((opts) => {
      if (opts !== except && !opts.closest('[id$="-dropdown"]')) opts.classList.add('hidden');
    });
  };

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const option = target.closest('.custom-select-wrapper .option-item');
    if (option) {
      const wrapper = option.closest('.custom-select-wrapper');
      const trigger = wrapper.querySelector('[id$="-trigger"]');
      const options = wrapper.querySelector('[id$="-options"]');
      const hidden = wrapper.querySelector('input[type="hidden"]');
      const value = option.dataset.value || '';
      if (hidden) {
        hidden.value = value;
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const label = trigger ? trigger.querySelector('span') : null;
      if (label) label.textContent = option.textContent.trim();
      wrapper.querySelectorAll('.option-item').forEach((el) => el.classList.remove('font-bold'));
      option.classList.add('font-bold');
      if (options) options.classList.add('hidden');
      return;
    }

    const trigger = target.closest('.custom-select-wrapper [id$="-trigger"]');
    if (trigger) {
      const wrapper = trigger.closest('.custom-select-wrapper');
      const options = wrapper.querySelector('[id$="-options"]');
      if (!options) return;
      const willOpen = options.classList.contains('hidden');
      closeAll(options);
      options.classList.toggle('hidden', !willOpen);
      return;
    }

    closeAll(null);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeAll(null);
  });
}
