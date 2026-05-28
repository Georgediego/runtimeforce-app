import { state, setState } from "../state.js";
import { workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { refreshIcons, getFileIcon } from "../utils/icons.js";
import { openFile } from "./fileviewer.js";

export async function loadFileTree() {
    var container = document.getElementById("file-tree");
    if (!container) return;

    container.innerHTML = '<div class="text-center text-xs text-ide-muted py-4"><i data-lucide="loader" class="w-4 h-4 inline animate-spin"></i> Загрузка...</div>';
    refreshIcons(container);

    try {
        var data = await workspacesApi.tree();
        if (!data || !data.tree) {
            showEmptyState(container, "Нет активного workspace");
            return;
        }
        setState("cachedFileTree", data.tree);
        renderLazyTree(data.tree);
    } catch (e) {
        var msg = "Нет активного workspace";
        if (e && e.message) {
            if (e.message.includes("SSH") || e.message.includes("connect")) msg = "Нет подключения к workspace";
            else if (e.message.includes("404")) msg = "Workspace не найден";
            else if (e.message.includes("timeout")) msg = "Timeout";
            else msg = e.message;
        }
        showEmptyState(container, msg);
    }
}

function showEmptyState(container, message) {
    container.innerHTML = '<div class="text-center text-xs text-ide-muted py-4">' + escapeHtml(message) + '</div>';
}

export function renderLazyTree(tree) {
    var container = document.getElementById("file-tree");
    if (!container || !tree) return;
    if (tree.children && tree.children.length > 0) {
        container.innerHTML = tree.children.map(function(c) { return renderLazyNode(c, 0); }).join("");
    } else {
        container.innerHTML = '<div class="text-center text-xs text-ide-muted py-4">Пустой workspace</div>';
    }
    refreshIcons(container);
    bindTreeEvents(container);
}

function renderLazyNode(node, depth) {
    var isDir = node.is_dir !== undefined ? node.is_dir : !!node.children;
    var padStyle = "padding-left: " + (depth * 12 + 8) + "px";
    var gitClass = getGitClass(node.path);

    if (isDir) {
        return '<div class="tree-folder" data-path="' + escapeHtml(node.path) + '" data-loaded="false">' +
            '<div class="tree-folder-toggle" style="' + padStyle + '">' +
                '<i data-lucide="chevron-right" class="w-3 h-3 tree-chevron"></i>' +
                '<i data-lucide="folder" class="w-3.5 h-3.5 text-ide-warning shrink-0"></i>' +
                '<span class="truncate ' + gitClass + '">' + escapeHtml(node.name) + '</span>' +
            '</div>' +
            '<div class="tree-folder-children"></div>' +
        '</div>';
    }

    return '<div class="tree-file-item file-tree-item ' + gitClass + '" style="' + padStyle + '" data-path="' + escapeHtml(node.path) + '" data-name="' + escapeHtml(node.name) + '">' +
        '<i data-lucide="' + getFileIcon(node.name) + '" class="w-3.5 h-3.5 shrink-0"></i>' +
        '<span class="truncate">' + escapeHtml(node.name) + '</span>' +
    '</div>';
}

function getGitClass(path) {
    if (!state.gitStatus || !state.gitStatus.is_repo) return "";
    var entries = state.gitStatus.entries || [];
    var map = { modified: "git-modified", added: "git-added", deleted: "git-deleted", untracked: "git-untracked", renamed: "git-renamed" };
    for (var i = 0; i < entries.length; i++) {
        if (entries[i].path === path) return map[entries[i].status] || "";
    }
    return "";
}

function bindTreeEvents(container) {
    container.querySelectorAll(".tree-folder-toggle").forEach(function(toggle) {
        toggle.addEventListener("click", function(e) {
            e.stopPropagation();
            toggleLazyFolder(toggle);
        });
    });
    container.querySelectorAll(".tree-file-item").forEach(function(item) {
        item.addEventListener("click", function() {
            var path = item.dataset.path;
            var name = item.dataset.name;
            var entries = state.gitStatus ? (state.gitStatus.entries || []) : [];
            var entry = null;
            for (var i = 0; i < entries.length; i++) {
                if (entries[i].path === path) { entry = entries[i]; break; }
            }
            if (entry && entry.status === "modified") {
                window.dispatchEvent(new CustomEvent("open-diff", { detail: { path: path, name: name } }));
            } else {
                openFile(path, name);
            }
        });
    });
}

async function toggleLazyFolder(toggleEl) {
    var folder = toggleEl.parentElement;
    var childrenContainer = folder.querySelector(".tree-folder-children");
    var isExpanded = folder.classList.contains("expanded");
    var dirPath = folder.dataset.path;
    var isLoaded = folder.dataset.loaded === "true";

    if (isExpanded) {
        folder.classList.remove("expanded");
        var icon = toggleEl.querySelectorAll("i")[1];
        if (icon) { icon.setAttribute("data-lucide", "folder"); refreshIcons(toggleEl); }
        return;
    }

    folder.classList.add("expanded");
    var icon = toggleEl.querySelectorAll("i")[1];
    if (icon) { icon.setAttribute("data-lucide", "folder-open"); refreshIcons(toggleEl); }

    if (isLoaded) return;

    childrenContainer.innerHTML = '<div class="text-xs text-ide-muted py-1 pl-6"><i data-lucide="loader" class="w-3 h-3 inline animate-spin"></i></div>';
    refreshIcons(childrenContainer);

    try {
        var data = await workspacesApi.treeChildren(dirPath);
        if (data.children && data.children.length > 0) {
            var currentPad = parseInt(toggleEl.style.paddingLeft) || 8;
            var depth = Math.round((currentPad - 8) / 12);
            childrenContainer.innerHTML = data.children.map(function(c) { return renderLazyNode(c, depth + 1); }).join("");
        } else {
            childrenContainer.innerHTML = '<div class="text-xs text-ide-muted py-1 pl-6 italic">Пусто</div>';
        }
        folder.dataset.loaded = "true";
        refreshIcons(childrenContainer);
        bindTreeEvents(childrenContainer);
    } catch (e) {
        childrenContainer.innerHTML = '<div class="text-xs text-ide-error py-1 pl-6">Ошибка: ' + escapeHtml(e.message || String(e)) + '</div>';
    }
}

export function refreshGitClasses() {
    var container = document.getElementById("file-tree");
    if (!container) return;
    container.querySelectorAll("[data-path]").forEach(function(el) {
        var gitClass = getGitClass(el.dataset.path);
        el.classList.remove("git-modified", "git-added", "git-deleted", "git-untracked", "git-renamed");
        if (gitClass) el.classList.add(gitClass);
    });
}