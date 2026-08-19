/**
 * Social Build-in-Public UI Controller with Draft Approval and Feedback Tasks.
 */
import { socialApi } from "../core/api_http_client.js";
import { showToast } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

export const socialUIController = {
    init() {
        eventBus.on("project:version_bumped", async (data) => {
            if (data && data.project_id && data.changelog) {
                await this.generateDraftForChangelog(data.project_id, data.changelog);
            }
        });

        document.getElementById("refresh-social-drafts-btn")?.addEventListener("click", () => this.loadSocialDrafts());
    },

    async generateDraftForChangelog(projectId, changelog) {
        try {
            showToast("Generating social draft in background...", "info");
            const res = await socialApi.generateDraft(projectId, changelog, "x.com");
            showToast(`Draft generated for X.com: "${res.draft_id}"`, "success");
            this.loadSocialDrafts(projectId);
        } catch (e) {
            console.warn("Failed to auto-generate social post:", e);
        }
    },

    async loadSocialDrafts(projectId = "active") {
        const container = document.getElementById("social-drafts-list");
        if (!container) return;

        try {
            const data = await socialApi.getFeedback(projectId);
            const feedback = data.feedback || [];
            if (!feedback.length) {
                container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-4">No social drafts or feedback items</div>';
                return;
            }

            container.innerHTML = feedback.map(item => `
                <div class="p-2.5 mb-2 rounded-lg bg-[var(--ide-elevated)] border border-[var(--ide-border-subtle)] flex flex-col gap-1.5 text-xs">
                    <div class="flex items-center justify-between">
                        <span class="font-bold text-[var(--ide-accent)] font-mono">${item.source_platform || 'X.com'}</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold uppercase">${item.status}</span>
                    </div>
                    <div class="text-[11px] text-[var(--ide-text-primary)] leading-relaxed">${item.structured_task || item.raw_text}</div>
                </div>
            `).join("");
        } catch (e) {
            container.innerHTML = '<div class="text-center text-xs text-[var(--ide-text-muted)] py-2">No drafts found</div>';
        }
    }
};
