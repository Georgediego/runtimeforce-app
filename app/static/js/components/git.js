import { state, setState } from "../state.js";
import { gitApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons } from "../utils/icons.js";
import { showToast } from "./toast.js";
import { refreshGitClasses } from "./filetree.js";

// ─── Главная функция загрузки статуса ───────────────────────
export async function loadGitStatus() {
    const emptyState = document.getElementById("git-empty-state");
    const content    = document.getElementById("git-content");
    if (!emptyState || !content) return;

    // Показываем индикатор загрузки пока ждём ответа
    setLoadingState(true);

    try {
        const data = await gitApi.status();
        setState("gitStatus", data);

        if (data && data.is_repo) {
            emptyState.classList.add("hidden");
            content.classList.remove("hidden");
            renderGitFilesList(data.entries || []);
            renderBranchName(data.branch || data.current_branch);
            updateCommitBtn(data.entries || []);
        } else {
            emptyState.classList.remove("hidden");
            content.classList.add("hidden");
        }

        refreshGitClasses();
    } catch (e) {
        console.error("Git status load failed:", e);
        // Ошибка — в toast, не в DOM
        showToast("Git: " + (e.message || "Failed to load status"), "error");
        emptyState.classList.remove("hidden");
        content.classList.add("hidden");
    } finally {
        setLoadingState(false);
    }
}

// ─── Индикатор загрузки на кнопке рефреша ───────────────────
function setLoadingState(loading) {
    var refreshBtn = document.getElementById("refresh-tree-btn");
    if (!refreshBtn) return;
    if (loading) {
        refreshBtn.dataset.gitLoading = "1";
        refreshBtn.style.opacity = "0.5";
        refreshBtn.style.pointerEvents = "none";
    } else {
        delete refreshBtn.dataset.gitLoading;
        refreshBtn.style.opacity = "";
        refreshBtn.style.pointerEvents = "";
    }
}

// ─── Рендер списка изменённых файлов ────────────────────────
function renderGitFilesList(entries) {
    const list = document.getElementById("git-files-list");
    if (!list) return;

    if (!entries.length) {
        list.innerHTML = '<div class="text-center text-xs text-ide-muted py-6">No changes</div>';
        return;
    }

    const statusIcon = {
        modified:  { icon: "pencil",      color: "text-yellow-400" },
        added:     { icon: "plus",         color: "text-green-400"  },
        deleted:   { icon: "trash-2",      color: "text-red-400"    },
        untracked: { icon: "file-plus",    color: "text-ide-muted"  },
        renamed:   { icon: "arrow-right",  color: "text-blue-400"   },
    };

    list.innerHTML = entries.map(function(e) {
        var s = statusIcon[e.status] || { icon: "file", color: "text-ide-muted" };
        var shortPath = e.path.split("/").pop();
        var dirPath   = e.path.includes("/") ? e.path.substring(0, e.path.lastIndexOf("/")) : "";
        return (
            '<div class="git-file-item flex items-center gap-2 px-2 py-1.5 rounded hover:bg-ide-hover cursor-pointer group" data-path="' + escapeHtml(e.path) + '" data-status="' + escapeHtml(e.status) + '">' +
                '<i data-lucide="' + s.icon + '" class="w-3 h-3 shrink-0 ' + s.color + '"></i>' +
                '<div class="flex-1 min-w-0">' +
                    '<div class="text-[11px] text-ide-text truncate">' + escapeHtml(shortPath) + '</div>' +
                    (dirPath ? '<div class="text-[10px] text-ide-muted truncate">' + escapeHtml(dirPath) + '</div>' : '') +
                '</div>' +
                '<span class="text-[9px] uppercase font-semibold ' + s.color + ' opacity-70">' + escapeHtml(e.status[0]) + '</span>' +
            '</div>'
        );
    }).join("");

    refreshIcons(list);

    // Клик по файлу — открываем diff
    list.querySelectorAll(".git-file-item").forEach(function(item) {
        item.addEventListener("click", function() {
            var path   = item.dataset.path;
            var status = item.dataset.status;
            if (status !== "deleted") {
                openDiffViewer(path, path.split("/").pop());
            }
        });
    });
}

// ─── Кнопка Commit: показываем с числом изменений ───────────
function updateCommitBtn(entries) {
    var btn   = document.getElementById("commit-btn");
    var badge = document.getElementById("git-badge");
    if (!btn) return;

    if (entries.length > 0) {
        btn.classList.remove("hidden");
        if (badge) {
            badge.textContent = String(entries.length);
            badge.classList.remove("hidden");
        }
    } else {
        btn.classList.add("hidden");
        if (badge) badge.classList.add("hidden");
    }
    refreshIcons(btn);
}

// ─── Имя текущей ветки ──────────────────────────────────────
function renderBranchName(branch) {
    var el = document.getElementById("git-branch-name");
    if (el) el.textContent = branch || "main";
}

// ─── Инициализация обработчиков ─────────────────────────────
export function initGitUI() {
    var initBtn = document.getElementById("git-init-btn");
    if (initBtn) {
        initBtn.addEventListener("click", handleGitInit);
    }

    document.getElementById("commit-btn")?.addEventListener("click", openCommitModal);
    document.getElementById("close-commit-modal-btn")?.addEventListener("click", closeCommitModal);
    document.getElementById("cancel-commit-btn")?.addEventListener("click", closeCommitModal);
    document.getElementById("confirm-commit-btn")?.addEventListener("click", doCommit);
    document.getElementById("close-diff-viewer-btn")?.addEventListener("click", closeDiffViewer);

    // Слушаем открытие diff из дерева файлов
    window.addEventListener("open-diff", function(e) {
        if (e.detail) openDiffViewer(e.detail.path, e.detail.name);
    });

    loadGitStatus();
}

// ─── Инициализация репозитория ──────────────────────────────
async function handleGitInit() {
    var initBtn = document.getElementById("git-init-btn");
    if (!initBtn) return;

    initBtn.disabled = true;
    initBtn.innerHTML = '<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i> Initializing...';
    if (window.lucide) window.lucide.createIcons({ root: initBtn });

    try {
        // gitApi.init может отсутствовать — выполняем через execute_command напрямую
        if (typeof gitApi.init === "function") {
            await gitApi.init();
        } else {
            // Фоллбэк: вызываем через API workspaces/execute
            await fetch("/api/v1/workspaces/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: "git init" }),
            });
        }
        showToast("Repository initialized", "success");
        await loadGitStatus();
    } catch (err) {
        showToast("Init failed: " + err.message, "error");
        initBtn.disabled = false;
        initBtn.innerHTML = '<i data-lucide="plus" class="w-3.5 h-3.5"></i> Initialize Repository';
        if (window.lucide) window.lucide.createIcons({ root: initBtn });
    }
}

// ─── Модалка коммита ────────────────────────────────────────
function openCommitModal() {
    var modal   = document.getElementById("commit-modal");
    var preview = document.getElementById("commit-files-preview");
    var input   = document.getElementById("commit-message-input");
    if (!modal) return;

    var entries = (state.gitStatus && state.gitStatus.entries) || [];
    if (preview) {
        preview.innerHTML = entries.length
            ? entries.map(function(e) {
                return (
                    '<div class="flex items-center gap-2 py-0.5">' +
                        '<span class="git-' + e.status + ' text-[10px] uppercase w-16 shrink-0">' + escapeHtml(e.status) + '</span>' +
                        '<span class="truncate text-[11px]">' + escapeHtml(e.path) + '</span>' +
                    '</div>'
                );
            }).join("")
            : '<div class="text-ide-muted text-xs">No changes</div>';
    }

    if (input) input.value = "";
    modal.classList.remove("hidden");
    if (input) input.focus();
}

function closeCommitModal() {
    document.getElementById("commit-modal")?.classList.add("hidden");
}

async function doCommit() {
    var input   = document.getElementById("commit-message-input");
    var message = input ? input.value.trim() : "";
    if (!message) { showToast("Enter commit message", "error"); return; }

    try {
        var result = await gitApi.commit(message);
        if (result.error) {
            showToast(result.error, "error");
        } else {
            showToast("Commit " + (result.hash ? result.hash.substring(0, 7) : "OK") + ": " + message, "success");
            closeCommitModal();
            await loadGitStatus();
        }
    } catch (e) {
        showToast("Commit failed: " + e.message, "error");
    }
}

// ─── Просмотр diff ───────────────────────────────────────────
async function openDiffViewer(path, name) {
    var modal     = document.getElementById("diff-viewer-modal");
    var nameEl    = document.getElementById("diff-viewer-name");
    var contentEl = document.getElementById("diff-viewer-content");
    if (!modal || !contentEl) return;

    if (nameEl) nameEl.textContent = name || path;
    contentEl.textContent = "Loading...";
    modal.classList.remove("hidden");

    try {
        var data = await gitApi.diff(path);
        contentEl.innerHTML = renderDiff(data.diff || "");
    } catch (e) {
        // Закрываем модалку и показываем ошибку в toast — не пишем в DOM
        modal.classList.add("hidden");
        showToast("Diff failed: " + (e.message || "Unknown error"), "error");
    }
}

function closeDiffViewer() {
    document.getElementById("diff-viewer-modal")?.classList.add("hidden");
}

function renderDiff(diffText) {
    if (!diffText) return '<span class="text-ide-muted">No changes</span>';
    return diffText.split("\n").map(function(line) {
        var cls = "";
        if (line.startsWith("+") && !line.startsWith("+++"))      cls = "diff-line-added";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-line-removed";
        else if (line.startsWith("@@"))                            cls = "diff-line-hunk";
        return '<div class="' + cls + '">' + (escapeHtml(line) || "&nbsp;") + '</div>';
    }).join("");
}