import { state, setState } from "../state.js";
import { modelsApi } from "../api.js";
import { refreshIcons } from "../utils/icons.js";
import { showToast } from "./toast.js";

const FREE_PROVIDERS = [
    { id: "gemini", name: "Gemini", icon: "sparkles", color: "blue", placeholder: "AIza..." },
    { id: "openrouter", name: "OpenRouter", icon: "layers", color: "orange", placeholder: "sk-or-..." },
    { id: "groq", name: "Groq", icon: "zap", color: "green", placeholder: "gsk_..." },
    { id: "sambanova", name: "SambaNova", icon: "activity", color: "yellow", placeholder: "..." },
    { id: "cerebras", name: "Cerebras", icon: "flame", color: "red", placeholder: "..." },
];

const PRO_PROVIDERS = [
    { id: "openai", name: "OpenAI", icon: "brain", color: "gray", placeholder: "sk-proj-..." },
    { id: "anthropic", name: "Anthropic", icon: "feather", color: "orange", placeholder: "sk-ant-..." },
    { id: "mistral", name: "Mistral", icon: "wind", color: "blue", placeholder: "..." },
    { id: "together", name: "Together", icon: "users", color: "blue", placeholder: "..." },
    { id: "fireworks", name: "Fireworks", icon: "sparkles", color: "orange", placeholder: "..." },
    { id: "cohere", name: "Cohere", icon: "hexagon", color: "purple", placeholder: "..." },
    { id: "perplexity", name: "Perplexity", icon: "search", color: "teal", placeholder: "pplx-..." },
    { id: "xai", name: "xAI", icon: "terminal", color: "gray", placeholder: "xai-..." },
    { id: "deepseek", name: "DeepSeek", icon: "code-2", color: "cyan", placeholder: "sk-..." },
    { id: "nvidia", name: "NVIDIA", icon: "cpu", color: "green", placeholder: "nvapi-..." },
];

const LOCAL_PROVIDERS = [
    { id: "local", name: "Local Models", icon: "monitor", color: "blue", placeholder: "http://localhost:11434/v1" }
];

// ═══════════════════════════════════════════════════════════
// Локальные модели (OpenAI-compatible: Ollama, LM Studio, vLLM)
// ═══════════════════════════════════════════════════════════
const LOCAL_MODELS_KEY = 'rf_local_models';

export function getLocalModels() {
    try {
        return JSON.parse(localStorage.getItem(LOCAL_MODELS_KEY) || '[]');
    } catch (e) {
        return [];
    }
}

function saveLocalModels(models) {
    localStorage.setItem(LOCAL_MODELS_KEY, JSON.stringify(models));
}

export function getLocalModelById(id) {
    return getLocalModels().find(m => m.id === id) || null;
}

export function addLocalModel(name, url, apiKey) {
    var models = getLocalModels();
    var id = 'local:' + name.replace(/[^a-zA-Z0-9._-]/g, '_');
    if (models.find(m => m.id === id)) {
        showToast('Model already added', 'warning');
        return false;
    }
    models.push({
        id: id,
        name: name,
        url: (url || 'http://localhost:11434/v1').replace(/\/$/, ''),
        model_name: name,
        api_key: apiKey || ''
    });
    saveLocalModels(models);
    injectLocalModelsIntoState();
    return true;
}

export function removeLocalModel(id) {
    var models = getLocalModels().filter(m => m.id !== id);
    saveLocalModels(models);
    injectLocalModelsIntoState();
}

export function injectLocalModelsIntoState() {
    var localModels = getLocalModels();
    var currentModels = state.models || {};
    currentModels['local'] = localModels.map(m => ({
        id: m.id,
        name: m.name,
        tier: 'free',
        capabilities: ['code', 'reasoning']
    }));
    setState('models', currentModels);
    if (typeof window.filterAllDropdowns === 'function') {
        window.filterAllDropdowns();
    }
}

export async function fetchModelsFromLocalServer(url) {
    var baseUrl = (url || 'http://localhost:11434/v1').replace(/\/$/, '');
    try {
        var response = await fetch(baseUrl + '/models', {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var data = await response.json();
        var models = (data.data || []).map(m => m.id || m.name).filter(Boolean);
        return { success: true, models: models };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

// ═══════════════════════════════════════════════════════════
// Управление выбранными моделями (облачные провайдеры)
// ═══════════════════════════════════════════════════════════
export function getSelectedModels(providerId) {
    const key = `rf_selected_models_${providerId}`;
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : [];
}

export function setSelectedModels(providerId, modelIds) {
    const key = `rf_selected_models_${providerId}`;
    localStorage.setItem(key, JSON.stringify(modelIds));
}

export function getAllSelectedModels() {
    const allModels = {};
    const allProviders = [...FREE_PROVIDERS, ...PRO_PROVIDERS];
    allProviders.forEach(provider => {
        const selected = getSelectedModels(provider.id);
        selected.forEach(modelId => {
            if (!allModels[provider.id]) allModels[provider.id] = [];
            allModels[provider.id].push(modelId);
        });
    });
    return allModels;
}

// ═══════════════════════════════════════════════════════════
// Рендеринг карточек провайдеров
// ═══════════════════════════════════════════════════════════
export function renderProvidersUI() {
    const freeList = document.getElementById("providers-list-free");
    const proList = document.getElementById("providers-list-pro");
    const localList = document.getElementById("providers-list-local");

    if (freeList) freeList.innerHTML = FREE_PROVIDERS.map(p => providerCardHTML(p, "free")).join("");
    if (proList) proList.innerHTML = PRO_PROVIDERS.map(p => providerCardHTML(p, "pro")).join("");
    if (localList) localList.innerHTML = LOCAL_PROVIDERS.map(p => localProviderCardHTML(p)).join("");

    refreshIcons(freeList);
    refreshIcons(proList);
    refreshIcons(localList);

    // Обработчики для облачных провайдеров
    document.querySelectorAll(".provider-card:not(.local-provider-card)").forEach(card => {
        card.addEventListener("click", (e) => {
            if (e.target.tagName === "INPUT" || e.target.closest(".manage-models-btn")) return;
            toggleProvider(card);
        });
    });

    document.querySelectorAll(".manage-models-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            openModelPicker(btn.dataset.provider);
        });
    });

    // Обработчики для локальных моделей
    document.querySelectorAll(".local-provider-card").forEach(card => {
        card.addEventListener("click", (e) => {
            if (e.target.tagName === "INPUT" || e.target.tagName === "BUTTON" || e.target.closest("button")) return;
            toggleProvider(card);
        });
    });

    updateProviderModelBadges();
    renderLocalModelsSection();
}

function providerCardHTML(p, tier) {
    return '<div class="provider-card" data-provider="' + p.id + '">' +
        '<div class="flex items-center justify-between">' +
            '<div class="flex items-center gap-2">' +
                '<div class="w-6 h-6 rounded bg-' + p.color + '-500/15 flex items-center justify-center">' +
                    '<i data-lucide="' + p.icon + '" class="w-3.5 h-3.5 text-' + p.color + '-400"></i>' +
                '</div>' +
                '<span class="text-sm font-medium text-ide-text">' + p.name + '</span>' +
                '<span class="provider-badge ' + tier + '">' + (tier === "free" ? "Free" : "Pro") + '</span>' +
                '<span class="key-status-dot empty" data-status="' + p.id + '"></span>' +
            '</div>' +
            '<i data-lucide="chevron-down" class="w-4 h-4 text-ide-muted provider-chevron"></i>' +
        '</div>' +
        '<div class="provider-key-row">' +
            '<label class="text-[11px] text-ide-muted block mb-1">API Key</label>' +
            '<input type="password" placeholder="' + p.placeholder + '" class="ide-input">' +
            '<div class="key-saved-display mt-1.5 hidden"></div>' +
            '<div class="provider-models-section mt-3 hidden">' +
                '<div class="flex items-center justify-between mb-2">' +
                    '<span class="text-[11px] text-ide-muted font-medium">Selected Models</span>' +
                    '<button class="manage-models-btn text-[10px] text-[var(--ide-accent)] hover:text-[var(--ide-accent-hover)] flex items-center gap-1" data-provider="' + p.id + '">' +
                        '<i data-lucide="settings" class="w-3 h-3"></i> Manage' +
                    '</button>' +
                '</div>' +
                '<div class="provider-model-badges flex flex-wrap gap-1"></div>' +
            '</div>' +
        '</div>' +
    '</div>';
}

function localProviderCardHTML(p) {
    return '<div class="provider-card local-provider-card" data-provider="' + p.id + '">' +
        '<div class="flex items-center justify-between">' +
            '<div class="flex items-center gap-2">' +
                '<div class="w-6 h-6 rounded bg-' + p.color + '-500/15 flex items-center justify-center">' +
                    '<i data-lucide="' + p.icon + '" class="w-3.5 h-3.5 text-' + p.color + '-400"></i>' +
                '</div>' +
                '<span class="text-sm font-medium text-ide-text">' + p.name + '</span>' +
                '<span class="provider-badge free">Local</span>' +
            '</div>' +
            '<i data-lucide="chevron-down" class="w-4 h-4 text-ide-muted provider-chevron"></i>' +
        '</div>' +
        '<div class="provider-key-row">' +
            '<div id="local-models-container"></div>' +
        '</div>' +
    '</div>';
}

function toggleProvider(card) {
    const was = card.classList.contains("expanded");
    document.querySelectorAll(".provider-card").forEach(c => c.classList.remove("expanded"));
    if (!was) card.classList.add("expanded");
    
    // Поворачиваем шеврон
    document.querySelectorAll(".provider-chevron").forEach(ch => ch.style.transform = '');
    if (!was) {
        const chevron = card.querySelector(".provider-chevron");
        if (chevron) chevron.style.transform = 'rotate(180deg)';
    }
}

// ═══════════════════════════════════════════════════════════
// Секция локальных моделей
// ═══════════════════════════════════════════════════════════
function renderLocalModelsSection() {
    var container = document.getElementById("local-models-container");
    if (!container) return;

    var localModels = getLocalModels();

    var html = '<div class="space-y-3">';

    // URL + Fetch
    html += '<div class="flex gap-2">';
    html += '<input type="text" id="local-model-url" value="http://localhost:11434/v1" placeholder="http://localhost:11434/v1" class="ide-input flex-1 text-xs">';
    html += '<button id="local-fetch-btn" class="px-3 py-1.5 text-xs bg-[var(--ide-accent)] text-white rounded-lg hover:bg-[var(--ide-accent-hover)] transition-colors shrink-0 flex items-center gap-1">';
    html += '<i data-lucide="search" class="w-3 h-3"></i> Fetch';
    html += '</button>';
    html += '</div>';

    // Ручное добавление
    html += '<div class="flex gap-2">';
    html += '<input type="text" id="local-model-name" placeholder="Model name (e.g. llama3, qwen2.5)" class="ide-input flex-1 text-xs">';
    html += '<button id="local-add-btn" class="px-3 py-1.5 text-xs bg-[var(--ide-elevated)] text-[var(--ide-text-primary)] rounded-lg hover:bg-[var(--ide-elevated-2)] transition-colors shrink-0 flex items-center gap-1">';
    html += '<i data-lucide="plus" class="w-3 h-3"></i> Add';
    html += '</button>';
    html += '</div>';

    // Список моделей
    if (localModels.length > 0) {
        html += '<div class="space-y-1.5 mt-2">';
        localModels.forEach(function(m) {
            html += '<div class="flex items-center justify-between px-3 py-2 bg-[var(--ide-elevated)] rounded-lg border border-[var(--ide-border-subtle)]">';
            html += '<div class="flex items-center gap-2 min-w-0">';
            html += '<i data-lucide="cpu" class="w-3.5 h-3.5 text-[var(--ide-accent)] shrink-0"></i>';
            html += '<div class="min-w-0">';
            html += '<div class="text-xs font-medium text-[var(--ide-text-primary)] truncate">' + m.name + '</div>';
            html += '<div class="text-[10px] text-[var(--ide-text-muted)] truncate">' + m.url + '</div>';
            html += '</div>';
            html += '</div>';
            html += '<button class="local-delete-btn text-[var(--ide-error)] hover:text-red-400 p-1 rounded hover:bg-[var(--ide-error)]/10 transition-colors" data-model-id="' + m.id + '">';
            html += '<i data-lucide="trash-2" class="w-3 h-3"></i>';
            html += '</button>';
            html += '</div>';
        });
        html += '</div>';
    } else {
        html += '<div class="text-center text-[11px] text-[var(--ide-text-muted)] py-3 italic">No local models added</div>';
    }

    html += '</div>';

    container.innerHTML = html;
    refreshIcons(container);

    // Обработчики
    var fetchBtn = document.getElementById('local-fetch-btn');
    if (fetchBtn) {
        fetchBtn.addEventListener('click', async function(e) {
            e.stopPropagation();
            var urlInput = document.getElementById('local-model-url');
            var url = urlInput ? urlInput.value.trim() : '';
            if (!url) { showToast('Enter server URL', 'warning'); return; }

            fetchBtn.disabled = true;
            fetchBtn.innerHTML = '<i data-lucide="loader-2" class="w-3 h-3 animate-spin"></i> Fetching...';
            refreshIcons(fetchBtn);

            var result = await fetchModelsFromLocalServer(url);

            fetchBtn.disabled = false;
            fetchBtn.innerHTML = '<i data-lucide="search" class="w-3 h-3"></i> Fetch';
            refreshIcons(fetchBtn);

            if (result.success && result.models.length > 0) {
                showToast('Found ' + result.models.length + ' models', 'success');
                showLocalModelsPicker(result.models, url);
            } else if (result.success) {
                showToast('No models found on server', 'warning');
            } else {
                showToast('Failed: ' + result.error, 'error');
            }
        });
    }

    var addBtn = document.getElementById('local-add-btn');
    if (addBtn) {
        addBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            var nameInput = document.getElementById('local-model-name');
            var urlInput = document.getElementById('local-model-url');
            var name = nameInput ? nameInput.value.trim() : '';
            var url = urlInput ? urlInput.value.trim() : '';
            if (!name) { showToast('Enter model name', 'warning'); return; }
            if (addLocalModel(name, url, '')) {
                showToast('Added: ' + name, 'success');
                nameInput.value = '';
                renderLocalModelsSection();
            }
        });
    }

    container.querySelectorAll('.local-delete-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var modelId = btn.dataset.modelId;
            removeLocalModel(modelId);
            showToast('Model removed', 'info');
            renderLocalModelsSection();
        });
    });
}

function showLocalModelsPicker(models, url) {
    var existing = getLocalModels();
    var existingNames = new Set(existing.map(m => m.model_name));

    var modal = document.getElementById('local-models-picker-modal');
    if (!modal) return;

    var listEl = document.getElementById('local-models-picker-list');
    if (!listEl) return;

    listEl.innerHTML = models.map(function(name) {
        var isAdded = existingNames.has(name);
        return '<div class="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-[var(--ide-elevated)] transition-colors ' + (isAdded ? 'opacity-50' : '') + '" data-model-name="' + name + '">' +
            '<div class="flex items-center gap-2">' +
                '<i data-lucide="cpu" class="w-3.5 h-3.5 text-[var(--ide-accent)]"></i>' +
                '<span class="text-xs text-[var(--ide-text-primary)]">' + name + '</span>' +
                (isAdded ? '<span class="text-[9px] text-[var(--ide-success)]">(added)</span>' : '') +
            '</div>' +
            (isAdded ? '' : '<button class="local-pick-add-btn px-2 py-1 text-[10px] bg-[var(--ide-accent)] text-white rounded hover:bg-[var(--ide-accent-hover)] transition-colors">Add</button>') +
        '</div>';
    }).join('');

    refreshIcons(listEl);

    listEl.querySelectorAll('.local-pick-add-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var row = btn.closest('[data-model-name]');
            var name = row.dataset.modelName;
            if (addLocalModel(name, url, '')) {
                showToast('Added: ' + name, 'success');
                btn.textContent = 'Added';
                btn.disabled = true;
                btn.classList.remove('bg-[var(--ide-accent)]');
                btn.classList.add('bg-[var(--ide-elevated)]', 'text-[var(--ide-text-muted)]');
                row.classList.add('opacity-50');
            }
        });
    });

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
}

// ═══════════════════════════════════════════════════════════
// Статус ключей
// ═══════════════════════════════════════════════════════════
export async function updateKeyStatusIndicators() {
    let connectedProviders = {};
    try {
        const response = await fetch('/api/v1/keys/status');
        if (response.ok) {
            const data = await response.json();
            connectedProviders = data.providers || {};
        }
    } catch (e) {
        console.error("Failed to fetch keys status:", e);
    }

    document.querySelectorAll("[data-status]").forEach(dot => {
        const p = dot.getAttribute("data-status");
        const has = connectedProviders[p];
        dot.classList.toggle("saved", !!has);
        dot.classList.toggle("empty", !has);
    });

    document.querySelectorAll(".provider-card:not(.local-provider-card)").forEach(card => {
        const p = card.getAttribute("data-provider");
        const display = card.querySelector(".key-saved-display");
        const input = card.querySelector('input[type="password"]');
        const modelsSection = card.querySelector(".provider-models-section");

        if (!display || !input) return;

        if (connectedProviders[p]) {
            display.innerHTML = '<div class="key-display"><i data-lucide="check-circle" class="w-3 h-3"></i><span>•••••••• (connected)</span></div>';
            display.classList.remove("hidden");
            refreshIcons(display);
            if (!input.value) input.placeholder = "(saved - enter new to replace)";
            if (modelsSection) modelsSection.classList.remove("hidden");
        } else {
            display.innerHTML = "";
            display.classList.add("hidden");
            if (modelsSection) modelsSection.classList.add("hidden");
        }
    });
}

// ═══════════════════════════════════════════════════════════
// Бейджи выбранных моделей
// ═══════════════════════════════════════════════════════════
function updateProviderModelBadges() {
    document.querySelectorAll(".provider-card:not(.local-provider-card)").forEach(card => {
        const providerId = card.getAttribute("data-provider");
        const badgesContainer = card.querySelector(".provider-model-badges");
        if (!badgesContainer) return;

        const selectedModels = getSelectedModels(providerId);

        if (selectedModels.length === 0) {
            badgesContainer.innerHTML = '<span class="text-[10px] text-[var(--ide-text-muted)] italic">No models selected</span>';
        } else {
            const allModels = state.models || {};
            const providerModels = allModels[providerId] || [];

            badgesContainer.innerHTML = selectedModels.slice(0, 3).map(modelId => {
                const model = providerModels.find(m => m.id === modelId);
                return '<span class="text-[9px] px-1.5 py-0.5 rounded bg-[var(--ide-elevated-2)] text-[var(--ide-text-secondary)]">' + (model ? model.name : modelId) + '</span>';
            }).join("");

            if (selectedModels.length > 3) {
                badgesContainer.innerHTML += '<span class="text-[9px] px-1.5 py-0.5 rounded bg-[var(--ide-elevated-2)] text-[var(--ide-text-muted)]">+' + (selectedModels.length - 3) + '</span>';
            }
        }
    });
}

// ═══════════════════════════════════════════════════════════
// Сохранение ключей
// ═══════════════════════════════════════════════════════════
export async function saveAllKeys() {
    const keysToSave = {};
    document.querySelectorAll(".provider-card:not(.local-provider-card)").forEach(card => {
        const p = card.getAttribute("data-provider");
        const input = card.querySelector('input[type="password"]');
        if (!p || !input) return;
        const v = input.value.trim();
        if (v) {
            keysToSave[p] = v;
            input.value = "";
        }
    });

    if (Object.keys(keysToSave).length === 0) {
        showToast("No new keys to save", "info");
        return;
    }

    try {
        const response = await fetch('/api/v1/keys/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys: keysToSave })
        });

        if (!response.ok) throw new Error('HTTP ' + response.status);

        await response.json();
        showToast('Saved ' + Object.keys(keysToSave).length + ' keys', "success");
        await updateKeyStatusIndicators();
        await refreshModelsUI();

        const savedProviders = Object.keys(keysToSave);
        if (savedProviders.length === 1) {
            setTimeout(() => openModelPicker(savedProviders[0]), 500);
        }
    } catch (e) {
        console.error("Failed to save keys:", e);
        showToast("Failed to save keys", "error");
    }
}

// ═══════════════════════════════════════════════════════════
// Удаление всех ключей
// ═══════════════════════════════════════════════════════════
export async function clearAllKeys() {
    if (!confirm("Delete all keys and local models?")) return;
    try {
        const response = await fetch('/api/v1/keys/status');
        if (response.ok) {
            const data = await response.json();
            const providers = Object.keys(data.providers || {});
            for (const provider of providers) {
                await fetch('/api/v1/keys/' + provider, { method: 'DELETE' });
            }
        }
        document.querySelectorAll('.provider-card:not(.local-provider-card) input[type="password"]').forEach(i => i.value = "");

        const allProviders = [...FREE_PROVIDERS, ...PRO_PROVIDERS];
        allProviders.forEach(provider => {
            localStorage.removeItem('rf_selected_models_' + provider.id);
        });

        localStorage.removeItem(LOCAL_MODELS_KEY);
        injectLocalModelsIntoState();

        await updateKeyStatusIndicators();
        await refreshModelsUI();
        renderLocalModelsSection();
        showToast("All keys and local models deleted", "success");
    } catch (e) {
        console.error("Failed to clear keys:", e);
        showToast("Failed to clear keys", "error");
    }
}

// ═══════════════════════════════════════════════════════════
// Обновление списка моделей
// ═══════════════════════════════════════════════════════════
export async function refreshModelsUI() {
    try {
        const data = await modelsApi.list();
        setState("models", data.models || {});
        setState("providersWithKeys", data.providers_with_keys || []);
        injectLocalModelsIntoState();
        updateProviderModelBadges();
    } catch (e) {
        console.error("Failed to refresh models:", e);
        injectLocalModelsIntoState();
    }
}

// ═══════════════════════════════════════════════════════════
// Model Picker Modal (облачные провайдеры)
// ═══════════════════════════════════════════════════════════
let currentPickerProvider = null;
let pickerSelection = new Set();

export function openModelPicker(providerId) {
    currentPickerProvider = providerId;
    const modal = document.getElementById("model-picker-modal");
    if (!modal) return;

    const allModels = state.models || {};
    const providerModels = allModels[providerId] || [];

    if (providerModels.length === 0) {
        showToast("No models available for this provider", "warning");
        return;
    }

    const providerName = [...FREE_PROVIDERS, ...PRO_PROVIDERS].find(p => p.id === providerId)?.name || providerId;
    const providerNameEl = document.getElementById("model-picker-provider-name");
    if (providerNameEl) providerNameEl.textContent = '— ' + providerName;

    pickerSelection = new Set(getSelectedModels(providerId));
    renderModelPickerList(providerModels);

    var searchInput = document.getElementById("model-picker-search");
    if (searchInput) searchInput.value = "";

    modal.classList.remove("hidden");
    if (window.lucide) window.lucide.createIcons();
}

function renderModelPickerList(models) {
    const container = document.getElementById("model-picker-list");
    if (!container) return;

    if (models.length === 0) {
        container.innerHTML = '<div class="text-center text-[var(--ide-text-muted)] text-xs py-8">No models found</div>';
        return;
    }

    container.innerHTML = models.map(model => {
        const isSelected = pickerSelection.has(model.id);
        const tierClass = model.tier === "free" ? "text-emerald-400" : "text-purple-400";
        const caps = model.capabilities || [];

        return '<div class="model-picker-item flex items-center gap-3 p-3 rounded-lg hover:bg-[var(--ide-elevated)] cursor-pointer transition-colors ' + (isSelected ? 'bg-[var(--ide-elevated)]' : '') + '" data-model-id="' + model.id + '">' +
            '<input type="checkbox" class="rounded accent-[var(--ide-accent)] w-4 h-4 shrink-0" ' + (isSelected ? 'checked' : '') + '>' +
            '<div class="flex-1 min-w-0">' +
                '<div class="text-sm font-medium text-[var(--ide-text-primary)] truncate">' + model.name + '</div>' +
                '<div class="flex items-center gap-2 mt-1">' +
                    '<span class="text-[10px] ' + tierClass + '">' + model.tier + '</span>' +
                    caps.map(cap => '<span class="text-[9px] px-1.5 py-0.5 rounded bg-[var(--ide-elevated-2)] text-[var(--ide-text-muted)]">' + cap + '</span>').join('') +
                '</div>' +
            '</div>' +
        '</div>';
    }).join("");

    container.querySelectorAll(".model-picker-item").forEach(item => {
        item.addEventListener("click", () => {
            const modelId = item.dataset.modelId;
            const checkbox = item.querySelector('input[type="checkbox"]');

            if (pickerSelection.has(modelId)) {
                pickerSelection.delete(modelId);
                checkbox.checked = false;
                item.classList.remove("bg-[var(--ide-elevated)]");
            } else {
                pickerSelection.add(modelId);
                checkbox.checked = true;
                item.classList.add("bg-[var(--ide-elevated)]");
            }
            updateModelPickerCount();
        });
    });

    updateModelPickerCount();
}

function updateModelPickerCount() {
    const countEl = document.getElementById("model-picker-count");
    if (countEl) countEl.textContent = 'Selected: ' + pickerSelection.size;
}

function filterModelPicker(query) {
    const allModels = state.models || {};
    const providerModels = allModels[currentPickerProvider] || [];

    if (!query) { renderModelPickerList(providerModels); return; }

    const q = query.toLowerCase();
    const filtered = providerModels.filter(model => {
        return model.name.toLowerCase().includes(q) ||
               model.id.toLowerCase().includes(q) ||
               model.tier.toLowerCase().includes(q) ||
               (model.capabilities || []).some(cap => cap.toLowerCase().includes(q));
    });

    renderModelPickerList(filtered);
}

function confirmModelPicker() {
    if (!currentPickerProvider) return;
    setSelectedModels(currentPickerProvider, Array.from(pickerSelection));
    updateProviderModelBadges();

    var modal = document.getElementById("model-picker-modal");
    if (modal) modal.classList.add("hidden");

    showToast('Saved ' + pickerSelection.size + ' models', "success");
    if (typeof window.filterAllDropdowns === "function") {
        window.filterAllDropdowns();
    }
}

function cancelModelPicker() {
    var modal = document.getElementById("model-picker-modal");
    if (modal) modal.classList.add("hidden");
}

export function initModelPickerUI() {
    var modal = document.getElementById("model-picker-modal");
    if (modal) {
        var searchInput = document.getElementById("model-picker-search");
        if (searchInput) {
            searchInput.addEventListener("input", (e) => filterModelPicker(e.target.value));
        }
        var confirmBtn = document.getElementById("model-picker-confirm");
        if (confirmBtn) confirmBtn.addEventListener("click", confirmModelPicker);
        var cancelBtn = document.getElementById("model-picker-cancel");
        if (cancelBtn) cancelBtn.addEventListener("click", cancelModelPicker);
        var closeBtn = document.getElementById("close-model-picker-btn");
        if (closeBtn) closeBtn.addEventListener("click", cancelModelPicker);
        modal.addEventListener("click", (e) => { if (e.target === modal) cancelModelPicker(); });
    }

    // Local models picker modal
    var localModal = document.getElementById("local-models-picker-modal");
    if (localModal) {
        var localCloseBtn = document.getElementById("close-local-models-picker-btn");
        if (localCloseBtn) {
            localCloseBtn.addEventListener("click", function() {
                localModal.classList.add("hidden");
            });
        }
        localModal.addEventListener("click", (e) => {
            if (e.target === localModal) localModal.classList.add("hidden");
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            if (modal && !modal.classList.contains("hidden")) cancelModelPicker();
            if (localModal && !localModal.classList.contains("hidden")) localModal.classList.add("hidden");
        }
    });
}

// ═══════════════════════════════════════════════════════════
// Глобальные экспорты
// ═══════════════════════════════════════════════════════════
window.getAllSelectedModels = getAllSelectedModels;
window.getLocalModelById = getLocalModelById;
window.getLocalModels = getLocalModels;