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

export function renderProvidersUI() {
    const freeList = document.getElementById("providers-list-free");
    const proList = document.getElementById("providers-list-pro");
    if (freeList) freeList.innerHTML = FREE_PROVIDERS.map(p => providerCardHTML(p, "free")).join("");
    if (proList) proList.innerHTML = PRO_PROVIDERS.map(p => providerCardHTML(p, "pro")).join("");
    refreshIcons(freeList);
    refreshIcons(proList);

    document.querySelectorAll(".provider-card").forEach(card => {
        card.addEventListener("click", (e) => {
            if (e.target.tagName === "INPUT") return;
            toggleProvider(card);
        });
    });
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
        '<i data-lucide="chevron-down" class="w-4 h-4 text-ide-muted"></i>' +
        '</div>' +
        '<div class="provider-key-row">' +
        '<label class="text-[11px] text-ide-muted block mb-1">API Key</label>' +
        '<input type="password" placeholder="' + p.placeholder + '" class="ide-input">' +
        '<div class="key-saved-display mt-1.5 hidden"></div>' +
        '</div>' +
        '</div>';
}

function toggleProvider(card) {
    const was = card.classList.contains("expanded");
    document.querySelectorAll(".provider-card").forEach(c => c.classList.remove("expanded"));
    if (!was) card.classList.add("expanded");
}

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

    document.querySelectorAll(".provider-card").forEach(card => {
        const p = card.getAttribute("data-provider");
        const display = card.querySelector(".key-saved-display");
        const input = card.querySelector("input[type=\"password\"]");
        if (!display || !input) return;

        const isConnected = connectedProviders[p];
        if (isConnected) {
            display.innerHTML = '<div class="key-display"><i data-lucide="check-circle" class="w-3 h-3"></i><span>•••••••• (connected)</span></div>';
            display.classList.remove("hidden");
            refreshIcons(display);
            if (!input.value) input.placeholder = "(saved - enter new to replace)";
        } else {
            display.innerHTML = "";
            display.classList.add("hidden");
        }
    });
}

export async function saveAllKeys() {
    const keysToSave = {};
    document.querySelectorAll(".provider-card").forEach(card => {
        const p = card.getAttribute("data-provider");
        const input = card.querySelector("input[type=\"password\"]");
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

        const data = await response.json();
        showToast('Saved ' + Object.keys(keysToSave).length + ' keys', "success");
        await updateKeyStatusIndicators();
        await refreshModelsUI();
    } catch (e) {
        console.error("Failed to save keys:", e);
        showToast("Failed to save keys", "error");
    }
}

export async function clearAllKeys() {
    if (!confirm("Delete all keys?")) return;
    try {
        const response = await fetch('/api/v1/keys/status');
        if (response.ok) {
            const data = await response.json();
            const providers = Object.keys(data.providers || {});
            for (const provider of providers) {
                await fetch('/api/v1/keys/' + provider, { method: 'DELETE' });
            }
        }
        document.querySelectorAll(".provider-card input[type=\"password\"]").forEach(i => i.value = "");
        await updateKeyStatusIndicators();
        await refreshModelsUI();
        showToast("All keys deleted", "success");
    } catch (e) {
        console.error("Failed to clear keys:", e);
        showToast("Failed to clear keys", "error");
    }
}

export async function refreshModelsUI() {
    try {
        const data = await modelsApi.list();
        setState("models", data.models || {});
        setState("providersWithKeys", data.providers_with_keys || []);
    } catch (e) {
        console.error("Failed to refresh models:", e);
    }
}
