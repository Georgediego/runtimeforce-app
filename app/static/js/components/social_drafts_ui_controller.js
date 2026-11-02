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
                activeDraftId = draft.status === "published" ? null : draft.id;
                setContent(draft.post_content);
                setStatus(draft.status === "published" ? "Already published" : "Review and edit before publishing");
                updateCounter();
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
        const mediaInput = document.getElementById("social-draft-media");
        if (mediaInput) mediaInput.value = "";
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
        const files = Array.from(document.getElementById("social-draft-media")?.files || []);
        if (!activeDraftId || !activeProjectId || !content || content.length > 280) return;
        const videos = files.filter((file) => file.type === "video/mp4");
        const images = files.filter((file) => file.type.startsWith("image/"));
        if (videos.length > 1 || (videos.length && images.length) || images.length > 4 || files.length !== videos.length + images.length) {
            showToast("Attach up to 4 images or one MP4 video.", "warning");
            return;
        }
        const button = document.getElementById("social-draft-publish-btn");
        if (button) button.disabled = true;
        try {
            const mediaIds = [];
            for (let index = 0; index < files.length; index++) {
                setStatus(`Uploading media ${index + 1} of ${files.length} to X.com…`);
                const uploaded = await socialApi.uploadMedia(files[index]);
                mediaIds.push(uploaded.media_id);
            }
            setStatus("Publishing through your connected X.com account…");
            await socialApi.publishDraft(activeDraftId, activeProjectId, content, mediaIds);
            setStatus("Published successfully.");
            showToast("Published to X.com", "success");
            await loadDraftList();
            setModal(false);
        } catch (error) {
            setStatus(error.message || "Publishing failed.");
            showToast(`X.com publish failed: ${error.message}`, "error");
        } finally {
            updateCounter();
        }
    }
};

document.addEventListener("DOMContentLoaded", () => socialDraftsUIController.init());
