/**
 * Providers UI Controller with English-only UI, Hardware Diagnostics & Seamless Local Models.
 */
import { keysApi, modelsApi, billingApi } from "../core/api_http_client.js";
import { showToast, showConfirm } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

const FREE_PROVIDERS = [
    { id: "gemini", name: "Gemini", placeholder: "AIza...", refUrl: "https://aistudio.google.com/app/apikey" },
    { id: "openrouter", name: "OpenRouter", placeholder: "sk-or-...", refUrl: "https://openrouter.ai/keys" },
    { id: "groq", name: "Groq", placeholder: "gsk_...", refUrl: "https://console.groq.com/keys" },
    { id: "sambanova", name: "SambaNova", placeholder: "Key...", refUrl: "https://cloud.sambanova.ai/analytics/api-keys" },
    { id: "cerebras", name: "Cerebras", placeholder: "Key...", refUrl: "https://cloud.cerebras.ai/platform" }
];

const PRO_PROVIDERS = [
    { id: "openai", name: "OpenAI", placeholder: "sk-proj-..." },
    { id: "anthropic", name: "Anthropic", placeholder: "sk-ant-..." },
    { id: "deepseek", name: "DeepSeek", placeholder: "sk-..." },
    { id: "xai", name: "xAI (Grok)", placeholder: "xai-..." }
];

let activePickerProvider = null;
let providerModelsMap = {};
let activeFilterTag = "all";
let cachedHardwareInfo = null;

export const providersUIController = {
    _features: {},

    _featureEnabled(featureKey) {
        const aliases = {
            local_llms: ["local_llms", "local_models", "local llms"],
            free_cloud_byok: ["free_cloud_byok", "free cloud byok"],
            full_pro_byok: ["full_pro_byok", "full pro byok"],
        };
        for (const key of (aliases[featureKey] || [featureKey])) {
            if (Object.prototype.hasOwnProperty.call(this._features, key)) return this._features[key] === true;
        }
        return false;
    },

    applyPlanLocks() {
        const groups = [
            [FREE_PROVIDERS, "free_cloud_byok"],
            [PRO_PROVIDERS, "full_pro_byok"],
        ];
        for (const [providers, feature] of groups) {
            const allowed = this._featureEnabled(feature);
            for (const provider of providers) {
                const input = document.getElementById("key-input-" + provider.id);
                const card = input?.closest(".p-3");
                if (input) input.disabled = !allowed;
                card?.querySelectorAll(".provider-toggle-btn, .configure-models-btn").forEach((button) => {
                    button.disabled = !allowed;
                });
                if (card && !allowed) {
                    card.classList.add("opacity-50");
                    const heading = card.querySelector(".key-status-" + provider.id);
                    if (heading) {
                        heading.textContent = "Locked by plan";
                        heading.title = feature + " is not enabled for this plan";
                    }
                }
            }
        }
        const localButton = document.getElementById("add-local-provider-btn");
        if (localButton) {
            localButton.disabled = !this._featureEnabled("local_llms");
            if (localButton.disabled) {
                localButton.title = "Local LLMs are not included in this plan";
                localButton.classList.add("opacity-50", "cursor-not-allowed");
            }
        }
    },

    async loadProvidersList() {
        try {
            const entitlements = await billingApi.entitlements();
            this._features = entitlements?.valid ? (entitlements.features || {}) : {};
        } catch {
            this._features = {};
        }
        const freeContainer = document.getElementById("providers-list-free");
        const proContainer = document.getElementById("providers-list-pro");

        if (freeContainer) freeContainer.innerHTML = FREE_PROVIDERS.map(p => this.providerCardHTML(p)).join("");
        if (proContainer) proContainer.innerHTML = PRO_PROVIDERS.map(p => this.providerCardHTML(p)).join("");
        this.applyPlanLocks();

        await this.fetchHardwareDiagnostics();
        this.renderLocalModelsSection();
        this.bindCardEvents();
        await this.syncSelectedModelsFromSQLite();
        await this.updateStatus();
    },

    async fetchHardwareDiagnostics() {
        try {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            const res = await fetch("/api/v1/models/hardware", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                cachedHardwareInfo = await res.json();
            }
        } catch (e) {
            console.debug("Hardware check skipped:", e);
        }
    },

    _selectedModelsMap: {},

    async syncSelectedModelsFromSQLite() {
        try {
            const data = await keysApi.getSelectedModels();
            this._selectedModelsMap = data.selected_models || {};
        } catch (e) {
            console.warn("Failed to sync selected models from SQLite:", e);
        }
    },

    async autoSelectAllProviders() {
        try {
            showToast("Auto-selecting models for all connected providers...", "info");
            const res = await keysApi.autoselectAll();
            if (res && res.results) {
                await this.syncSelectedModelsFromSQLite();
                await this.updateStatus();
                showToast(`Auto-selected ${res.total_selected} models across ${Object.keys(res.results).length} providers`, "success");
                eventBus.emit("providers.updated");
            }
        } catch (e) {
            showToast(`Autoselect All failed: ${e.message}`, "error");
        }
    },

    renderLocalModelsSection() {
        const container = document.getElementById("providers-list-local") || document.getElementById("local-models-container");
        if (!container) return;

        let hwBadge = "";
        if (cachedHardwareInfo) {
            const isLow = cachedHardwareInfo.is_low_spec;
            const gpuText = cachedHardwareInfo.has_gpu ? "GPU Ready" : "CPU Only";
            hwBadge = `
                <div class="p-2.5 rounded-lg ${isLow ? 'bg-amber-500/10 border-amber-500/30 text-amber-300' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'} border text-[11px] font-mono flex items-center justify-between mb-3">
                    <div>
                        <span class="font-bold">Hardware:</span> ${cachedHardwareInfo.total_ram_gb} GB RAM • ${cachedHardwareInfo.cpu_cores} Cores • ${gpuText}
                    </div>
                    ${isLow ? '<span class="text-[10px] uppercase font-bold text-amber-400">Performance notice</span>' : '<span class="text-[10px] uppercase font-bold text-emerald-400">Optimal</span>'}
                </div>
            `;
        }

        container.innerHTML = `
            <div class="space-y-3">
                ${hwBadge}
                <div class="flex items-center justify-between">
                    <span class="text-xs text-[var(--ide-text-muted)]">Connected local engines:</span>
                    <button id="add-local-provider-btn" type="button" class="px-2.5 py-1 bg-[var(--ide-accent)] text-black text-[11px] font-bold rounded hover:brightness-110 cursor-pointer">
                        + Add Local Engine
                    </button>
                </div>
                <div id="local-providers-list" class="space-y-2"></div>
                <div class="text-[11px] text-[var(--ide-text-muted)] italic leading-relaxed pt-1">
                    💡 <b>Tip:</b> Free cloud providers (Groq, Gemini, SambaNova, Cerebras) deliver sub-second (500-1000 tok/s) performance with zero hardware load.
                </div>
            </div>
        `;

        if (window.lucide) window.lucide.createIcons({ root: container });

        document.getElementById("add-local-provider-btn")?.addEventListener("click", () => this.addLocalProviderModal());
        this.renderExistingLocalProviders();
    },

    addLocalProviderModal() {
        let modal = document.getElementById("add-local-provider-modal");
        if (modal) modal.remove();

        modal = document.createElement("div");
        modal.id = "add-local-provider-modal";
        modal.className = "fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[500]";

        modal.innerHTML = `
            <div class="bg-[var(--ide-surface)] border border-[var(--ide-border-subtle)] rounded-xl p-5 max-w-md w-full mx-4 space-y-4 text-xs shadow-2xl">
                <div class="flex items-center justify-between border-b border-[var(--ide-border-subtle)] pb-2">
                    <h3 class="text-sm font-bold text-[var(--ide-text-primary)]">Add Local LLM Provider</h3>
                    <button id="close-add-local-modal-x" class="text-[var(--ide-text-muted)] hover:text-white p-1 cursor-pointer"><i data-lucide="x" class="w-4 h-4"></i></button>
                </div>

                <div>
                    <label class="block text-[11px] font-bold text-[var(--ide-text-muted)] mb-1">Provider Name</label>
                    <input type="text" id="local-provider-name-input" placeholder="e.g. ollama, lm_studio" class="w-full p-2 bg-[var(--ide-bg)] border border-[var(--ide-border-subtle)] rounded text-white font-mono outline-none focus:border-[var(--ide-accent)]">
                </div>

                <div>
                    <label class="block text-[11px] font-bold text-[var(--ide-text-muted)] mb-1">Base URL</label>
                    <input type="text" id="local-provider-url-input" placeholder="http://localhost:11434" class="w-full p-2 bg-[var(--ide-bg)] border border-[var(--ide-border-subtle)] rounded text-white font-mono outline-none focus:border-[var(--ide-accent)]">
                    <div class="text-[10px] text-[var(--ide-text-muted)] mt-1 font-mono leading-relaxed">
                        Ollama: http://localhost:11434<br>
                        LM Studio: http://localhost:1234
                    </div>
                </div>

                <div id="add-local-status-box"></div>

                <div class="flex justify-end gap-2 pt-2 border-t border-[var(--ide-border-subtle)]">
                    <button id="close-add-local-modal-btn" class="px-3 py-1.5 border border-[var(--ide-border-subtle)] rounded text-[var(--ide-text-secondary)] hover:bg-[var(--ide-elevated)] cursor-pointer">Cancel</button>
                    <button id="confirm-discover-local-btn" class="px-4 py-1.5 bg-[var(--ide-accent)] text-black font-bold rounded hover:brightness-110 cursor-pointer">Discover & Add</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        if (window.lucide) window.lucide.createIcons({ root: modal });

        document.getElementById("close-add-local-modal-x")?.addEventListener("click", () => this.closeAddLocalProviderModal());
        document.getElementById("close-add-local-modal-btn")?.addEventListener("click", () => this.closeAddLocalProviderModal());
        document.getElementById("confirm-discover-local-btn")?.addEventListener("click", () => this.discoverAndAddLocalProvider());
    },

    closeAddLocalProviderModal() {
        const modal = document.getElementById("add-local-provider-modal");
        if (modal) modal.remove();
    },

    async discoverAndAddLocalProvider() {
        const nameInput = document.getElementById("local-provider-name-input");
        const urlInput = document.getElementById("local-provider-url-input");
        const statusBox = document.getElementById("add-local-status-box");

        const name = nameInput?.value.trim() || "";
        const url = urlInput?.value.trim() || "";

        if (!name || !url) {
            showToast("Please enter provider name and Base URL", "warning");
            return;
        }

        if (statusBox) statusBox.innerHTML = '<span class="text-amber-400 font-mono">Discovering local endpoints...</span>';

        try {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            const res = await fetch("/api/v1/models/discover-local", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ provider_name: name, base_url: url })
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
                throw new Error(err.detail || `Status ${res.status}`);
            }

            const data = await res.json();
            showToast(`Connected ${name}: ${data.models.length} models discovered`, "success");
            this.closeAddLocalProviderModal();
            await this.renderExistingLocalProviders();
            eventBus.emit("providers.updated");

        } catch (err) {
            if (statusBox) {
                statusBox.innerHTML = `
                    <div class="p-2 rounded bg-red-500/10 border border-red-500/30 text-red-400">
                        ✗ Discovery failed: ${err.message}
                    </div>
                `;
            }
            showToast(`Local discovery failed: ${err.message}`, "error");
        }
    },

    async renderExistingLocalProviders() {
        const container = document.getElementById("local-providers-list");
        if (!container) return;

        try {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            const res = await fetch("/api/v1/models", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            const data = await res.json();
            const allModels = data.models || {};

            const localProviders = Object.entries(allModels).filter(([pName, models]) => {
                return models.length > 0 && (models[0].tier === "local" || pName === "local" || pName === "ollama" || pName === "lm_studio");
            });

            if (localProviders.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-4 text-[var(--ide-text-muted)] border border-dashed border-[var(--ide-border-subtle)] rounded-lg space-y-1">
                        <div class="font-bold text-xs text-[var(--ide-text-primary)]">No local engines detected</div>
                        <div class="text-[10px]">Make sure Ollama is running on http://localhost:11434</div>
                    </div>
                `;
                return;
            }

            container.innerHTML = localProviders.map(([pName, models]) => {
                const selectedCount = this.getSelectedModelsCount(pName);
                const totalCount = models.length;

                return `
                    <div class="border border-[var(--ide-border-subtle)] bg-[var(--ide-elevated)] rounded-lg p-3 space-y-2">
                        <div class="flex items-center justify-between">
                            <div>
                                <div class="font-bold text-xs text-[var(--ide-text-primary)] uppercase">${pName}</div>
                                <div class="text-[10px] ${selectedCount ? "text-[var(--ide-success)]" : "text-[var(--ide-text-muted)]"} font-mono font-bold">
                                    ${selectedCount ? "Enabled" : "Disconnected"} • ${selectedCount}/${totalCount} models selected
                                </div>
                            </div>
                            <div class="flex items-center gap-2">
                                <button class="toggle-local-provider-btn text-xs text-[var(--ide-accent)] hover:underline font-bold cursor-pointer" data-provider="${pName}">${selectedCount ? "Disconnect" : "Connect"}</button>
                                <button class="remove-local-provider-btn text-xs text-red-400 hover:text-red-300 font-bold cursor-pointer" data-provider="${pName}">Remove</button>
                            </div>
                        </div>

                        <div class="space-y-1 max-h-40 overflow-y-auto custom-scrollbar pt-1 border-t border-[var(--ide-border-subtle)]">
                            ${models.map(m => `
                                <label class="flex items-center justify-between p-1.5 rounded hover:bg-[var(--ide-surface)] cursor-pointer text-xs">
                                    <div class="flex flex-col min-w-0 pr-2">
                                        <span class="font-semibold text-[var(--ide-text-primary)] truncate">${m.name || m.id}</span>
                                        <span class="text-[10px] text-[var(--ide-text-muted)] font-mono">${(m.capabilities || []).join(", ")}</span>
                                    </div>
                                    <input type="checkbox" value="${m.id}" data-provider="${pName}" ${this.isModelSelected(pName, m.id) ? 'checked' : ''} class="local-model-cb w-4 h-4 rounded accent-[var(--ide-accent)] cursor-pointer">
                                </label>
                            `).join('')}
                        </div>
                    </div>
                `;
            }).join('');

            container.querySelectorAll(".toggle-local-provider-btn").forEach(btn => {
                btn.addEventListener("click", () => this.toggleProviderConnection(btn.dataset.provider));
            });

            container.querySelectorAll(".remove-local-provider-btn").forEach(btn => {
                btn.addEventListener("click", () => this.removeLocalProvider(btn.dataset.provider));
            });

            container.querySelectorAll(".local-model-cb").forEach(cb => {
                cb.addEventListener("change", (e) => {
                    this.toggleLocalModelSelection(e.target.dataset.provider, e.target.value, e.target.checked);
                });
            });

        } catch (err) {
            container.innerHTML = `<div class="text-xs text-red-400 p-2">Failed to load local engines: ${err.message}</div>`;
        }
    },

    getSelectedModelsCount(providerName) {
        const list = this._selectedModelsMap[(providerName || "").toLowerCase()] || [];
        return list.length;
    },

    isModelSelected(providerName, modelId) {
        const list = this._selectedModelsMap[(providerName || "").toLowerCase()] || [];
        return list.includes(modelId);
    },

    async toggleLocalModelSelection(providerName, modelId, checked) {
        if (checked && cachedHardwareInfo && cachedHardwareInfo.is_low_spec) {
            showToast(`ℹ️ Performance note: '${modelId}' may take 10-20s per response. This is informational; local model selection remains enabled.`, "info", 5000);
        }

        const pKey = (providerName || "").toLowerCase();
        let selected = [...(this._selectedModelsMap[pKey] || [])];

        if (checked) {
            if (!selected.includes(modelId)) selected.push(modelId);
        } else {
            selected = selected.filter(id => id !== modelId);
        }

        this._selectedModelsMap[pKey] = selected;
        keysApi.saveSelectedModels(providerName, selected).catch(() => {});
        this.renderExistingLocalProviders();
        eventBus.emit("providers.updated");
    },

    async removeLocalProvider(providerName) {
        const confirmed = await showConfirm("Remove Provider", `Remove ${providerName}? Selected models will be cleared.`, "Remove", "Cancel");
        if (!confirmed) return;

        try {
            const token = localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "";
            const res = await fetch(`/api/v1/models/providers/${encodeURIComponent(providerName)}`, {
                method: "DELETE",
                headers: { "Authorization": `Bearer ${token}` }
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            delete this._selectedModelsMap[(providerName || "").toLowerCase()];
            keysApi.saveSelectedModels(providerName, []).catch(() => {});
            showToast(`Removed ${providerName}`, "success");
            await this.renderExistingLocalProviders();
            eventBus.emit("providers.updated");
        } catch (err) {
            showToast(`Failed to remove provider: ${err.message}`, "error");
        }
    },

    providerCardHTML(p) {
        const savedSelections = this._selectedModelsMap[(p.id || "").toLowerCase()] || null;
        const countBadgeText = Array.isArray(savedSelections) ? `${savedSelections.length} models selected` : "";
        const refLinkHTML = p.refUrl ? `<a href="${p.refUrl}" target="_blank" rel="noopener noreferrer" class="text-[10px] text-[var(--ide-accent)] hover:underline flex items-center gap-0.5">Get Free Key ↗</a>` : "";

        return `
            <div class="p-3 bg-[var(--ide-elevated)] rounded-lg border border-[var(--ide-border-subtle)] space-y-2.5">
                <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 min-w-0 text-xs font-semibold">
                        <span>${p.name}</span>
                        ${refLinkHTML}
                    </div>
                    <span class="text-[10px] key-status-${p.id} text-[var(--ide-text-muted)] shrink-0">No API key</span>
                </div>
                <input type="password" id="key-input-${p.id}" placeholder="${p.placeholder}" class="w-full p-2 text-xs bg-[var(--ide-bg)] border border-[var(--ide-border-subtle)] rounded text-white font-mono outline-none focus:border-[var(--ide-accent)]">
                <div class="flex items-center justify-between gap-2">
                    <span class="text-[10px] text-[var(--ide-accent)] font-mono selected-count-${p.id}">${countBadgeText}</span>
                    <div class="flex items-center gap-1.5 shrink-0">
                        <button type="button" class="provider-toggle-btn text-[10px] px-3 py-1 rounded bg-[var(--ide-accent)]/10 text-[var(--ide-accent)] border border-[var(--ide-accent)]/30 hover:bg-[var(--ide-accent)]/20 cursor-pointer" data-provider="${p.id}">Connect</button>
                        <button type="button" class="provider-delete-key-btn text-[10px] px-3 py-1 rounded text-red-400 border border-red-500/30 hover:bg-red-500/10 cursor-pointer" data-provider="${p.id}" disabled>Delete key</button>
                        <button type="button" class="configure-models-btn hidden text-[10px] px-2 py-1 rounded bg-[var(--ide-accent)]/10 text-[var(--ide-accent)] hover:bg-[var(--ide-accent)]/20 cursor-pointer" data-provider="${p.id}">Select Models</button>
                    </div>
                </div>
            </div>
        `;
    },

    bindCardEvents() {
        document.querySelectorAll(".provider-toggle-btn").forEach(btn => {
            btn.addEventListener("click", e => this.toggleProviderConnection(e.currentTarget.dataset.provider));
        });
        document.querySelectorAll(".provider-delete-key-btn").forEach(btn => {
            btn.addEventListener("click", e => this.deleteProviderKey(e.currentTarget.dataset.provider));
        });
        document.querySelectorAll(".configure-models-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const provider = e.currentTarget.dataset.provider;
                this.openModelPicker(provider);
            });
        });
    },

    async toggleProviderConnection(providerId) {
        const provider = String(providerId || "").toLowerCase();
        const selected = [...(this._selectedModelsMap[provider] || [])];
        try {
            if (selected.length) {
                await keysApi.saveSelectedModels(provider, []);
                this._selectedModelsMap[provider] = [];
                showToast(`${provider} disconnected. API key retained.`, "info");
            } else {
                const status = await keysApi.status();
                if (!(status.providers || {})[provider]) {
                    showToast("Add and save this provider's API key first.", "warning");
                    return;
                }
                await this.autoSelectModels(provider);
            }
            await this.syncSelectedModelsFromSQLite();
            await this.updateStatus();
            await this.renderExistingLocalProviders();
            eventBus.emit("providers.updated");
        } catch (error) {
            showToast(`Provider update failed: ${error.message}`, "error");
        }
    },

    async deleteProviderKey(providerId) {
        const provider = String(providerId || "").toLowerCase();
        const confirmed = await showConfirm(
            "Delete API Key",
            `Permanently delete the saved API key for ${provider}?`,
            "Delete Key",
            "Cancel"
        );
        if (!confirmed) return;
        try {
            await keysApi.delete(provider);
            this._selectedModelsMap[provider] = [];
            await this.syncSelectedModelsFromSQLite();
            await this.updateStatus();
            await this.renderExistingLocalProviders();
            showToast(`${provider} API key deleted`, "success");
            eventBus.emit("providers.updated");
        } catch (error) {
            showToast(`Failed to delete key: ${error.message}`, "error");
        }
    },

    async updateStatus() {
        try {
            const data = await keysApi.status();
            const connected = data.providers || {};
            const modelsRes = await modelsApi.list().catch(() => ({ models: {} }));
            const availableModelsMap = modelsRes.models || {};

            [...FREE_PROVIDERS, ...PRO_PROVIDERS].forEach(p => {
                const statusEl = document.querySelector(`.key-status-${p.id}`);
                const configBtn = document.querySelector(`.configure-models-btn[data-provider="${p.id}"]`);
                const savedSelections = this._selectedModelsMap[p.id.toLowerCase()] || null;
                const availableModels = availableModelsMap[p.id] || [];
                const totalAvailable = availableModels.length;

                const hasKey = Boolean(connected[p.id]);
                const selectedCount = Array.isArray(savedSelections) ? savedSelections.length : 0;
                const enabled = hasKey && selectedCount > 0;
                const toggleBtn = document.querySelector(`.provider-toggle-btn[data-provider="${p.id}"]`);
                const deleteBtn = document.querySelector(`.provider-delete-key-btn[data-provider="${p.id}"]`);
                if (statusEl) {
                    statusEl.textContent = !hasKey
                        ? "No API key"
                        : `${enabled ? "Enabled" : "Disconnected"} • ${selectedCount}/${totalAvailable || selectedCount} models`;
                    statusEl.className = `text-[10px] key-status-${p.id} ${enabled ? "text-[var(--ide-success)]" : "text-[var(--ide-text-muted)]"} font-bold`;
                }
                if (toggleBtn) {
                    toggleBtn.textContent = enabled ? "Disconnect" : "Connect";
                    toggleBtn.disabled = !hasKey;
                    toggleBtn.classList.toggle("opacity-40", !hasKey);
                    toggleBtn.classList.toggle("cursor-not-allowed", !hasKey);
                }
                if (deleteBtn) {
                    deleteBtn.disabled = !hasKey;
                    deleteBtn.classList.toggle("opacity-40", !hasKey);
                    deleteBtn.classList.toggle("cursor-not-allowed", !hasKey);
                }
                if (configBtn) configBtn.classList.toggle("hidden", !hasKey && totalAvailable === 0);
            });
        } catch (e) {
            console.warn("Failed to check keys status:", e);
        }
    },

    async openModelPicker(providerId) {
        activePickerProvider = providerId;
        activeFilterTag = "all";

        const modal = document.getElementById("model-picker-modal");
        const titleEl = document.getElementById("model-picker-provider-name");
        const listEl = document.getElementById("model-picker-list");
        const searchInput = document.getElementById("model-picker-search");

        if (titleEl) titleEl.textContent = `(${providerId})`;
        if (listEl) listEl.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-6">Loading models...</div>';
        if (searchInput) searchInput.value = "";

        this.resetTagButtonsUI();

        if (modal) {
            modal.classList.remove("hidden");
            modal.style.display = "flex";
        }

        try {
            const data = await modelsApi.list();
            const allModels = data.models || {};
            const models = allModels[providerId] || [];
            providerModelsMap[providerId] = models;
            this.renderModelPickerList(models);
        } catch (e) {
            if (listEl) listEl.innerHTML = `<div class="text-center text-xs text-[var(--ide-error)] py-6">Failed to load models: ${e.message}</div>`;
        }
    },

    renderModelPickerList(models) {
        const listEl = document.getElementById("model-picker-list");
        if (!listEl) return;

        if (!models.length) {
            listEl.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-6">No models available for this provider.</div>';
            this.updatePickerCount();
            return;
        }

        const savedSelections = this._selectedModelsMap[(activePickerProvider || "").toLowerCase()] || null;
        const selectedSet = new Set(Array.isArray(savedSelections) ? savedSelections : []);

        listEl.innerHTML = models.map(m => {
            const isChecked = selectedSet.has(m.id);
            return `
                <label class="model-picker-item flex items-center justify-between p-2.5 mb-1.5 rounded-lg bg-[var(--ide-elevated)] hover:bg-[var(--ide-elevated-2)] cursor-pointer border border-[var(--ide-border-subtle)]"
                       data-model-id="${m.id.toLowerCase()}" data-name="${(m.name || '').toLowerCase()}" data-tier="${(m.tier || '').toLowerCase()}">
                    <div class="flex flex-col min-w-0 pr-2">
                        <div class="flex items-center gap-1.5">
                            <span class="text-xs font-semibold text-[var(--ide-text-primary)] truncate">${m.name || m.id}</span>
                            <span class="text-[9px] px-1 py-0.2 rounded bg-[var(--ide-accent)]/10 text-[var(--ide-accent)] uppercase font-bold">${m.tier || 'std'}</span>
                        </div>
                        <span class="text-[10px] text-[var(--ide-text-muted)] font-mono truncate">${m.id}</span>
                    </div>
                    <input type="checkbox" value="${m.id}" data-model-id="${m.id}" ${isChecked ? 'checked' : ''} class="model-picker-cb w-4 h-4 rounded accent-[var(--ide-accent)]">
                </label>
            `;
        }).join("");

        this.updatePickerCount();
        listEl.querySelectorAll(".model-picker-cb").forEach(cb => {
            cb.addEventListener("change", () => this.updatePickerCount());
        });

        this.applyFilters();
    },

    applyFilters() {
        const query = (document.getElementById("model-picker-search")?.value || "").toLowerCase().trim();
        const items = document.querySelectorAll("#model-picker-list .model-picker-item");

        items.forEach(item => {
            const mid = item.dataset.modelId || "";
            const name = item.dataset.name || "";
            const tier = item.dataset.tier || "";
            const text = `${mid} ${name}`.toLowerCase();

            const matchesSearch = !query || text.includes(query);
            let matchesTag = true;

            if (activeFilterTag === "code") {
                matchesTag = text.includes("code") || text.includes("coder") || text.includes("python");
            } else if (activeFilterTag === "thinking") {
                matchesTag = text.includes("think") || text.includes("reason") || text.includes("r1") || text.includes("o1") || text.includes("o3") || text.includes("claude-3-5");
            } else if (activeFilterTag === "flash") {
                matchesTag = text.includes("flash") || text.includes("haiku") || text.includes("mini") || text.includes("turbo") || text.includes("instant");
            } else if (activeFilterTag === "pro") {
                matchesTag = tier === "pro" || tier === "standard" || text.includes("gpt-4") || text.includes("claude-3-5");
            }

            if (matchesSearch && matchesTag) {
                item.style.display = "flex";
            } else {
                item.style.display = "none";
            }
        });

        this.updatePickerCount();
    },

    toggleAllVisible() {
        const visibleItems = Array.from(document.querySelectorAll("#model-picker-list .model-picker-item"))
            .filter(item => item.style.display !== "none");

        if (!visibleItems.length) return;

        const visibleCheckboxes = visibleItems.map(item => item.querySelector(".model-picker-cb")).filter(Boolean);
        const allChecked = visibleCheckboxes.every(cb => cb.checked);

        visibleCheckboxes.forEach(cb => {
            cb.checked = !allChecked;
        });

        this.updatePickerCount();
    },

    resetTagButtonsUI() {
        document.querySelectorAll(".model-tag-filter-btn").forEach(btn => {
            btn.className = "model-tag-filter-btn text-[10px] px-2 py-0.5 rounded bg-[var(--ide-elevated-2)] text-[var(--ide-text-secondary)] hover:text-white cursor-pointer shrink-0";
        });
    },

    updatePickerCount() {
        const countEl = document.getElementById("model-picker-count");
        const checked = document.querySelectorAll("#model-picker-list .model-picker-cb:checked").length;
        const total = (providerModelsMap[activePickerProvider] || []).length;
        if (countEl) countEl.textContent = `Selected: ${checked}/${total}`;
    },

    async autoSelectModels(providerId) {
        if (!providerId) return;
        try {
            showToast(`Auto-selecting optimal models for ${providerId}...`, "info");
            const res = await keysApi.autoselect(providerId);
            const autoselected = res.autoselected_models || [];
            
            this._selectedModelsMap[(providerId || "").toLowerCase()] = autoselected;
            
            if (activePickerProvider === providerId) {
                this.renderModelPickerList(providerModelsMap[providerId] || []);
            }
            
            await this.updateStatus();
            showToast(`Auto-selected ${autoselected.length} models for ${providerId}`, "success");
            eventBus.emit("provider.models_autoselected", { providerId, count: autoselected.length });
            eventBus.emit("providers.updated");
        } catch (e) {
            showToast(`Autoselect failed: ${e.message}`, "error");
        }
    },

    savePickerSelections() {
        if (!activePickerProvider) return;
        const checked = Array.from(document.querySelectorAll("#model-picker-list .model-picker-cb:checked")).map(cb => cb.value);
        this._selectedModelsMap[(activePickerProvider || "").toLowerCase()] = checked;
        keysApi.saveSelectedModels(activePickerProvider, checked).catch(() => {});
        this.updateStatus();
    },

    closeModelPicker() {
        const modal = document.getElementById("model-picker-modal");
        if (modal) {
            modal.classList.add("hidden");
            modal.style.display = "none";
        }
    },

    init() {
        this.syncSelectedModelsFromSQLite().then(() => this.updateStatus());
        eventBus.on("providers.updated", () => this.updateStatus());

        document.getElementById("autoselect-btn")?.addEventListener("click", () => {
            if (activePickerProvider) {
                this.autoSelectModels(activePickerProvider);
            }
        });

        document.getElementById("autoselect-all-btn")?.addEventListener("click", async () => {
            await this.autoSelectAllProviders();
        });

        document.getElementById("save-keys-btn")?.addEventListener("click", async () => {
            const keys = {};
            [...FREE_PROVIDERS, ...PRO_PROVIDERS].forEach(p => {
                const val = document.getElementById(`key-input-${p.id}`)?.value.trim();
                if (val) keys[p.id] = val;
            });

            if (Object.keys(keys).length === 0) {
                showToast("Please enter at least one API key", "warning");
                return;
            }

            try {
                await keysApi.update(keys);
                showToast("API keys saved successfully", "success");
                [...FREE_PROVIDERS, ...PRO_PROVIDERS].forEach(p => {
                    const input = document.getElementById(`key-input-${p.id}`);
                    if (input) input.value = "";
                });
                await this.updateStatus();
                const firstSaved = Object.keys(keys)[0];
                if (firstSaved) {
                    this.openModelPicker(firstSaved);
                }
            } catch (e) {
                showToast(`Failed to save keys: ${e.message}`, "error");
            }
        });

        document.getElementById("clear-keys-btn")?.addEventListener("click", async () => {
            for (const p of [...FREE_PROVIDERS, ...PRO_PROVIDERS]) {
                try { await keysApi.delete(p.id); } catch(e) {}
            }
            showToast("All keys cleared", "info");
            this.updateStatus();
        });

        document.getElementById("close-model-picker-btn")?.addEventListener("click", () => this.closeModelPicker());
        document.getElementById("model-picker-cancel")?.addEventListener("click", () => this.closeModelPicker());
        document.getElementById("model-picker-confirm")?.addEventListener("click", () => {
            this.savePickerSelections();
            showToast("Model preferences saved", "success");
            this.closeModelPicker();
        });

        document.getElementById("model-picker-search")?.addEventListener("input", () => {
            this.applyFilters();
        });

        document.getElementById("model-picker-all-btn")?.addEventListener("click", () => {
            this.toggleAllVisible();
        });

        document.querySelectorAll(".model-tag-filter-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const clickedTag = e.currentTarget.dataset.tag;
                if (activeFilterTag === clickedTag) {
                    activeFilterTag = "all";
                    this.resetTagButtonsUI();
                } else {
                    activeFilterTag = clickedTag;
                    this.resetTagButtonsUI();
                    e.currentTarget.className = "model-tag-filter-btn text-[10px] px-2 py-0.5 rounded bg-[var(--ide-accent)] text-black font-bold cursor-pointer shrink-0";
                }
                this.applyFilters();
            });
        });
    }
};
