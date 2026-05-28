
import { state, setState } from "../state.js";
import { gitApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons } from "../utils/icons.js";
import { showToast } from "./toast.js";
import { refreshGitClasses } from "./filetree.js";

export async function loadGitStatus() {
    setGitUIVisible(false);
    try {
        var data = await gitApi.status();
        setState("gitStatus", data);
        if (data && data.is_repo) setGitUIVisible(true);
        refreshGitClasses();
    } catch (e) {
        console.error("Git status load failed:", e);
        setGitUIVisible(false);
    }
}

function setGitUIVisible(visible) {
    var badge = document.getElementById("git-badge");
    var commitBtn = document.getElementById("commit-btn");
    if (badge) badge.classList.toggle("hidden", !visible);
    if (commitBtn) {
        commitBtn.classList.toggle("hidden", !visible);
        if (visible) refreshIcons(commitBtn);
    }
}

export function initGitUI() {
    document.getElementById("commit-btn")?.addEventListener("click", openCommitModal);
    document.getElementById("close-commit-modal-btn")?.addEventListener("click", closeCommitModal);
    document.getElementById("cancel-commit-btn")?.addEventListener("click", closeCommitModal);
    document.getElementById("confirm-commit-btn")?.addEventListener("click", doCommit);
    document.getElementById("close-diff-viewer-btn")?.addEventListener("click", closeDiffViewer);
    document.getElementById("diff-viewer-modal")?.addEventListener("click", function(e) {
        if (e.target === e.currentTarget) closeDiffViewer();
    });
    window.addEventListener("open-diff", function(e) { openDiffViewer(e.detail.path, e.detail.name); });
}

function openCommitModal() {
    var modal = document.getElementById("commit-modal");
    var preview = document.getElementById("commit-files-preview");
    var input = document.getElementById("commit-message-input");
    if (!modal || !preview || !input) return;
    var entries = (state.gitStatus && state.gitStatus.entries) || [];
    preview.innerHTML = entries.length
        ? entries.map(function(e) {
            return '<div class="flex items-center gap-2 py-0.5"><span class="git-' + e.status + ' text-[10px] uppercase w-16">' + escapeHtml(e.status) + '</span><span class="truncate">' + escapeHtml(e.path) + '</span></div>';
        }).join("")
        : '<div class="text-ide-muted">Нет изменений</div>';
    input.value = "";
    modal.classList.remove("hidden");
    input.focus();
}

function closeCommitModal() { document.getElementById("commit-modal")?.classList.add("hidden"); }

async function doCommit() {
    var input = document.getElementById("commit-message-input");
    var message = input ? input.value.trim() : "";
    if (!message) { showToast("Введите сообщение", "error"); return; }
    try {
        var result = await gitApi.commit(message);
        if (result.error) showToast(result.error, "error");
        else { showToast("Commit " + (result.hash || "OK") + ": " + message, "success"); closeCommitModal(); loadGitStatus(); }
    } catch (e) { showToast("Commit failed: " + e.message, "error"); }
}

async function openDiffViewer(path, name) {
    var modal = document.getElementById("diff-viewer-modal");
    var nameEl = document.getElementById("diff-viewer-name");
    var contentEl = document.getElementById("diff-viewer-content");
    if (!modal || !contentEl) return;
    if (nameEl) nameEl.textContent = name || path;
    contentEl.textContent = "Загрузка...";
    modal.classList.remove("hidden");
    try {
        var data = await gitApi.diff(path);
        contentEl.innerHTML = renderDiff(data.diff || "");
    } catch (e) { contentEl.textContent = "Ошибка: " + e.message; }
}

function closeDiffViewer() { document.getElementById("diff-viewer-modal")?.classList.add("hidden"); }

function renderDiff(diffText) {
    if (!diffText) return '<span class="text-ide-muted">Нет изменений</span>';
    return diffText.split("\n").map(function(line) {
        var cls = "";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-line-added";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-line-removed";
        else if (line.startsWith("@@")) cls = "diff-line-hunk";
        return '<div class="' + cls + '">' + (escapeHtml(line) || "&nbsp;") + '</div>';
    }).join("");
}
