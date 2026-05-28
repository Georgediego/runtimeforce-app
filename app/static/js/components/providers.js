
import { state, setState } from "../state.js";
import { modelsApi, keysApi } from "../api.js";
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
    freeList.innerHTML = FREE_PROVIDERS.map(p => providerCardHTML(p, "free")).join("");
    proList.innerHTML = PRO_PROVIDERS.map(p => providerCardHTML(p, "pro")).join("");
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
    return "<div class=\"provider-card\" data-provider=\"" + p.id + "\">" +
        "<div class=\"flex items-center justify-between\">" +
        "<div class=\"flex items-center gap-2\">" +
        "<div class=\"w-6 h-6 rounded bg-" + p.color + "-500/15 flex items-center justify-center\">" +
        "<i data-lucide=\"" + p.icon + "\" class=\"w-3.5 h-3.5 text-" + p.color + "-400\"></i>" +
        "</div>" +
        "<span class=\"text-sm font-medium text-ide-text\">" + p.name + "</span>" +
        "<span class=\"provider-badge " + tier + "\">" + (tier === "free" ? "Free" : "Pro") + "</span>" +
        "<span class=\"key-status-dot empty\" data-status=\"" + p.id + "\"></span>" +
        "</div>" +
        "<i data-lucide=\"chevron-down\" class=\"w-4 h-4 text-ide-muted\"></i>" +
        "</div>" +
        "<div class=\"provider-key-row\">" +
        "<label class=\"text-[11px] text-ide-muted block mb-1\">API Key</label>" +
        "<input type=\"password\" placeholder=\"" + p.placeholder + "\" class=\"ide-input\">" +
        "<div class=\"key-saved-display mt-1.5 hidden\"></div>" +
        "</div>" +
        "</div>";
}

function toggleProvider(card) {
    const was = card.classList.contains("expanded");
    document.querySelectorAll(".provider-card").forEach(c => c.classList.remove("expanded"));
    if (!was) card.classList.add("expanded");
}

export function updateKeyStatusIndicators() {
    const saved = getSavedKeys();
    document.querySelectorAll("[data-status]").forEach(dot => {
        const p = dot.getAttribute("data-status");
        const has = saved[p]?.trim();
        dot.classList.toggle("saved", !!has);
        dot.classList.toggle("empty", !has);
    });
    document.querySelectorAll(".provider-card").forEach(card => {
        const p = card.getAttribute("data-provider");
        const display = card.querySelector(".key-saved-display");
        const input = card.querySelector("input[type=\"password\"]");
        if (!display || !input) return;
        const key = saved[p];
        if (key && key.trim()) {
            display.innerHTML = "<div class=\"key-display\"><i data-lucide=\"check-circle\" class=\"w-3 h-3\"></i><span>" + maskKey(key) + "</span></div>";
            display.classList.remove("hidden");
            refreshIcons(display);
            if (!input.value) input.placeholder = "(сохранен — введите новый)";
        } else {
            display.innerHTML = "";
            display.classList.add("hidden");
        }
    });
}

function getSavedKeys() {
    try { return JSON.parse(localStorage.getItem("ide:provider_keys") || "{}"); } catch { return {}; }
}
function setSavedKeys(k) { try { localStorage.setItem("ide:provider_keys", JSON.stringify(k)); return true; } catch { return false; } }
function maskKey(k) { return !k ? "" : k.length <= 8 ? "••••••••" : k.slice(0, 4) + "••••••••" + k.slice(-4); }

export async function saveAllKeys() {
    const saved = getSavedKeys();
    document.querySelectorAll("#stab-providers .provider-card").forEach(card => {
        const p = card.getAttribute("data-provider");
        const input = card.querySelector("input[type=\"password\"]");
        if (!p || !input) return;
        const v = input.value.trim();
        if (v) { saved[p] = v; input.value = ""; }
    });
    if (!setSavedKeys(saved)) { showToast("Ошибка сохранения", "error"); return; }
    const toSend = { ...saved };
    Object.keys(toSend).forEach(k => !toSend[k] && delete toSend[k]);
    try {
        await keysApi.update(toSend);
        showToast("Ключи сохранены", "success");
        await refreshModelsUI();
    } catch (e) {
        showToast("Ключи сохранены локально (backend недоступен)", "info");
    }
    updateKeyStatusIndicators();
}

export async function clearAllKeys() {
    if (!confirm("Удалить все ключи?")) return;
    localStorage.removeItem("ide:provider_keys");
    document.querySelectorAll("#stab-providers input[type=\"password\"]").forEach(i => i.value = "");
    updateKeyStatusIndicators();
    showToast("Ключи удалены", "success");
    try { await keysApi.update({}); } catch {}
    await refreshModelsUI();
}

export async function refreshModelsUI() {
    try {
        const data = await modelsApi.list();
        setState("models", data.models || {});
        setState("providersWithKeys", data.providers_with_keys || []);
        populateModelLockSelect();
    } catch (e) {
        console.error("Failed to refresh models:", e);
    }
}

function populateModelLockSelect() {
    const select = document.getElementById("model-lock-select");
    if (!select) return;
    select.innerHTML = "<option value=\"\">— Использовать стратегию —</option>";
    const order = ["groq", "gemini", "sambanova", "cerebras", "openrouter", "openai", "anthropic", "deepseek"];
    for (const provider of order) {
        const models = state.models[provider];
        if (!models || !models.length) continue;
        const hasKey = state.providersWithKeys.includes(provider);
        const group = document.createElement("optgroup");
        group.label = provider.toUpperCase() + " " + (hasKey ? "✓" : "(нет ключа)");
        for (const m of models) {
            const opt = document.createElement("option");
            opt.value = m.id;
            let label = m.name;
            const badges = [];
            if (m.tier === "free") badges.push("🆓");
            if (m.capabilities.includes("code")) badges.push("💻");
            if (m.capabilities.includes("reasoning")) badges.push("🧠");
            if (badges.length) label += " " + badges.join(" ");
            opt.textContent = label;
            group.appendChild(opt);
        }
        select.appendChild(group);
    }
}
