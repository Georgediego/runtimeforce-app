import { gitApi, socialApi } from "../core/api_http_client.js";
import { showToast } from "./toast_ui_controller.js";

let activeDraftId = null;
let activeProjectId = null;

function setModal(open) {
    const modal = document.getElementById("social-draft-modal");
    if (!modal) return;
    modal.classList.toggle("hidden", !open);
    modal.style.display = open ? "flex" : "none";
}

function setStatus(message) {
    const el = document.getElementById("social-draft-status");
    if (el) el.textContent = message;
}

function setContent(value) {
    const input = document.getElementById("social-draft-content");
    if (input) input.value = value || "";
    updateCounter();
}

function updateCounter() {
    const input = document.getElementById("social-draft-content");
    const counter = document.getElementById("social-draft-counter");
    const publish = document.getElementById("social-draft-publish-btn");
    const length = input?.value.length || 0;
    if (counter) counter.textContent = `${length} / 280`;
    if (publish) publish.disabled = !activeDraftId || length < 1 || length > 280;
}

async function loadDraftList() {
    const list = document.getElementById("social-drafts-list");
    if (!list || !activeProjectId) return;
    try {
        const data = await socialApi.getDrafts(activeProjectId);
        const drafts = data.drafts || [];
        list.replaceChildren();
        if (!drafts.length) {
            list.textContent = "No drafts yet";
            list.className = "max-h-36 overflow-y-auto text-[10px] text-[var(--ide-text-muted)]";
            return;
        }
        list.className = "max-h-36 overflow-y-auto space-y-1";
        drafts.slice(0, 5).forEach((draft) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "block w-full truncate rounded px-2 py-1.5 text-left text-[10px] text-[var(--ide-text-secondary)] hover:bg-[var(--ide-elevated)] hover:text-[var(--ide-text-primary)]";
            button.textContent = draft.post_content || "Untitled draft";
            button.addEventListener("click", () => {
                activeDraftId = draft.id;
                setContent(draft.post_content);
                setStatus(draft.status === "published" ? "Already published" : "Review and edit before publishing");
                setModal(true);
            });
            list.appendChild(button);
        });
    } catch (error) {
        list.textContent = "Social Drafts require the Studio feature";
    }
}

export const socialDraftsUIController = {
    init() {
        document.getElementById("open-social-drafts-btn")?.addEventListener("click", () => this.generateFromLatestChanges());
        document.getElementById("social-draft-close-btn")?.addEventListener("click", () => setModal(false));
        document.getElementById("social-draft-cancel-btn")?.addEventListener("click", () => setModal(false));
        document.getElementById("social-draft-content")?.addEventListener("input", updateCounter);
        document.getElementById("social-draft-publish-btn")?.addEventListener("click", () => this.publish());
    },

    async generateFromLatestChanges() {
        activeProjectId = localStorage.getItem("rf_active_project_id") || "";
        if (!activeProjectId) {
            showToast("Select a project before creating a social draft.", "warning");
            return;
        }
        activeDraftId = null;
        setContent("");
        setStatus("Reading recent Git commits and local project memory…");
        setModal(true);
        try {
            const history = await gitApi.log(8);
            const commits = history.commits || [];
            const changelog = commits.map((commit) => commit.message).filter(Boolean).slice(0, 8).map((message) => `- ${message}`).join("\n");
            if (!changelog) throw new Error("No Git commits found. Commit your changes first.");
            setStatus("Generating a concise draft with the cheapest available configured text model…");
            const draft = await socialApi.generateDraft(activeProjectId, changelog);
            activeDraftId = draft.draft_id;
            setContent(draft.content);
            setStatus(`Draft generated with ${draft.model || "your configured model"}. Review before publishing.`);
            await loadDraftList();
        } catch (error) {
            setStatus(error.message || "Could not generate a draft.");
            showToast(`Social draft: ${error.message}`, "error");
        }
        updateCounter();
    },

    async publish() {
        const content = document.getElementById("social-draft-content")?.value.trim() || "";
        if (!activeDraftId || !activeProjectId || !content || content.length > 280) return;
        const button = document.getElementById("social-draft-publish-btn");
        if (button) button.disabled = true;
        setStatus("Publishing through your connected X.com account…");
        try {
            const result = await socialApi.publishDraft(activeDraftId, activeProjectId, content);
            setStatus("Published successfully.");
            showToast("Published to X.com", "success");
            if (result.url) window.open(result.url, "_blank", "noopener,noreferrer");
            await loadDraftList();
            setModal(false);
        } catch (error) {
            setStatus(error.message || "Publishing failed.");
            showToast(`X.com publish failed: ${error.message}`, "error");
        } finally {
            updateCounter();
        }
    },
};

document.addEventListener("DOMContentLoaded", () => socialDraftsUIController.init());
