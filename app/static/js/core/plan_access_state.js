import { billingApi } from "./api_http_client.js";

const FEATURE_ALIASES = {
    local_llms: ["local_llms", "local_models", "local llms"],
    atm: ["atm"],
    git: ["git", "github_git", "github_git_integration", "git_integration", "github / git integration"],
    software_updates: ["software_updates", "software updates"],
    free_cloud_byok: ["free_cloud_byok", "free cloud byok"],
    full_pro_byok: ["full_pro_byok", "full pro byok"],
    offline_grace: ["offline_grace", "offline grace"],
};

const LIMIT_ALIASES = {
    max_projects: ["max_projects", "workspaces_limit"],
    max_ssh_hosts: ["max_ssh_hosts"],
    git_repos: ["git_repos", "git_repos_limit", "max_git_repos"],
    offline_grace_hours: ["offline_grace_hours"],
};

export const planAccessState = {
    entitlements: {
        valid: false,
        plan: "unknown",
        features: {},
        limits: {},
    },

    async refresh() {
        try {
            const data = await billingApi.entitlements();
            this.entitlements = data?.valid === true
                ? {
                    ...data,
                    features: data.features || {},
                    limits: data.limits || {},
                }
                : { valid: false, plan: "unknown", features: {}, limits: {} };
        } catch {
            this.entitlements = { valid: false, plan: "unknown", features: {}, limits: {} };
        }
        return this.entitlements;
    },

    featureEnabled(featureKey) {
        if (this.entitlements.valid !== true) return false;
        const normalized = Object.fromEntries(
            Object.entries(this.entitlements.features || {}).map(([key, value]) => [key.trim().toLowerCase(), value])
        );
        const keys = FEATURE_ALIASES[featureKey] || [featureKey];
        for (const key of keys) {
            const normalizedKey = key.trim().toLowerCase();
            if (Object.prototype.hasOwnProperty.call(normalized, normalizedKey)) {
                return normalized[normalizedKey] === true;
            }
        }
        return false;
    },

    limit(limitKey) {
        const normalized = Object.fromEntries(
            Object.entries(this.entitlements.limits || {}).map(([key, value]) => [key.trim().toLowerCase(), value])
        );
        for (const key of (LIMIT_ALIASES[limitKey] || [limitKey])) {
            const value = normalized[key.toLowerCase()];
            if (value !== undefined && value !== null) {
                const number = Number(value);
                return Number.isFinite(number) ? Math.max(0, Math.floor(number)) : 0;
            }
        }
        return 0;
    },

    modelAllowed(model) {
        if (this.entitlements.valid !== true || !model) return false;
        const provider = String(model.provider || "").trim().toLowerCase().replace(/-/g, "_");
        const tier = String(model.tier || "standard").toLowerCase();
        if (["ollama", "lm_studio", "local", "local_llm"].includes(provider) || provider.startsWith("local_") || provider.endsWith("_local") || tier === "local") {
            return this.featureEnabled("local_llms");
        }
        if (["gemini", "openrouter", "groq", "sambanova", "cerebras"].includes(provider)) {
            return this.featureEnabled("free_cloud_byok");
        }
        if (["openai", "anthropic", "deepseek", "xai"].includes(provider) || ["pro", "standard", "paid"].includes(tier)) {
            return this.featureEnabled("full_pro_byok");
        }
        return this.featureEnabled("free_cloud_byok");
    },

    canAddProject(currentCount) {
        return this.limit("max_projects") > 0 && Number(currentCount) < this.limit("max_projects");
    },

    canAddSSHHost(host, knownHosts) {
        const maximum = this.limit("max_ssh_hosts");
        const normalizedHost = String(host || "").trim().toLowerCase();
        return maximum > 0 && (
            (normalizedHost && knownHosts?.has(normalizedHost)) ||
            (knownHosts?.size || 0) < maximum
        );
    },

    canAddGitRepo(existingCount, currentProjectHasRepo = false) {
        const maximum = this.limit("git_repos");
        return this.featureEnabled("git") && maximum > 0 && (
            currentProjectHasRepo || Number(existingCount) < maximum
        );
    },
};
