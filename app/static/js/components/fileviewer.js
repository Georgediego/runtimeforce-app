import { state, setState } from "../state.js";
import { workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { showToast, showConfirm } from "./toast.js";

let editor = null;            // Monaco editor instance
let currentPath = null;       // Путь открытого файла
let currentContent = null;    // Исходный контент (для проверки dirty state)
let isDirty = false;          // Были ли изменения
let monacoReady = false;      // Загрузился ли Monaco
let monacoLoadPromise = null; // Promise загрузки Monaco

function loadMonaco() {
    if (monacoReady) return Promise.resolve();
    if (monacoLoadPromise) return monacoLoadPromise;

    monacoLoadPromise = new Promise((resolve, reject) => {
        if (typeof require === "undefined") {
            reject(new Error("Monaco loader not found"));
            return;
        }
        require(["vs/editor/editor.main"], function() {
            monaco.editor.defineTheme("ide-dark", {
                base: "vs-dark",
                inherit: true,
                rules: [],
                colors: {
                    "editor.background": "#1e1e1e",
                    "editor.foreground": "#d4d4d4",
                    "editor.lineHighlightBackground": "#2a2a2a",
                    "editorLineNumber.foreground": "#6e7681",
                    "editorLineNumber.activeForeground": "#c9d1d9",
                }
            });
            monaco.editor.setTheme("ide-dark");
            monacoReady = true;
            resolve();
        });
    });

    setTimeout(() => {
        if (!monacoReady) {
            monacoLoadPromise = Promise.reject(new Error("Monaco load timeout"));
        }
    }, 15000);

    return monacoLoadPromise;
}

function detectLanguage(path) {
    const ext = (path.split(".").pop() || "").toLowerCase();
    const map = {
        js: "javascript", mjs: "javascript", cjs: "javascript",
        ts: "typescript", tsx: "typescript", jsx: "javascript",
        py: "python", pyw: "python", html: "html", htm: "html",
        css: "css", scss: "scss", sass: "scss", less: "less",
        json: "json", jsonc: "json", md: "markdown", markdown: "markdown",
        yml: "yaml", yaml: "yaml", xml: "xml", svg: "xml",
        sh: "shell", bash: "shell", zsh: "shell", sql: "sql",
        php: "php", rb: "ruby", go: "go", rs: "rust", java: "java",
        kt: "kotlin", c: "c", h: "c", cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp",
        cs: "csharp", swift: "swift", dockerfile: "dockerfile",
        toml: "ini", env: "ini", gitignore: "ini", txt: "plaintext",
    };
    return map[ext] || "plaintext";
}

export async function openFile(path, name) {
    if (isDirty && currentPath) {
        // Используем кастомный конфирм вместо confirm()
        const confirmed = await showConfirm(
            "Несохранённые изменения",
            "В текущем файле есть несохранённые изменения. Закрыть его без сохранения?",
            "Закрыть",
            "Отмена"
        );
        if (!confirmed) {
            return;
        }
    }

    currentPath = path;
    isDirty = false;
    updateHeader(name, false);

    // Открываем модальное окно
    const modal = document.getElementById("file-viewer-modal");
    if (modal) modal.classList.remove("hidden");

    const container = document.getElementById("file-viewer-content");
    if (!container) return;

    container.innerHTML =
        '<div class="flex items-center justify-center h-full text-ide-muted text-sm">' +
        '<i data-lucide="loader" class="w-4 h-4 inline animate-spin mr-2"></i>' +
        'Загрузка ' + escapeHtml(name) + '...</div>';

    try {
        const data = await workspacesApi.file(path);
        const content = data.content || "";
        currentContent = content;

        try {
            await loadMonaco();
            renderMonaco(container, content, path);
        } catch (monacoErr) {
            console.warn("Monaco failed, using fallback:", monacoErr);
            renderFallback(container, content, path);
        }

        showViewerChrome(name);
    } catch (e) {
        container.innerHTML =
            '<div class="flex items-center justify-center h-full text-ide-error text-sm">' +
            'Ошибка загрузки: ' + escapeHtml(e.message || String(e)) + '</div>';
    }
}

function renderMonaco(container, content, path) {
    if (editor && typeof editor.dispose === "function") { editor.dispose(); editor = null; }
    container.innerHTML = "";
    // Monaco конфликтует с Tailwind-классами на контейнере — сохраняем и очищаем
    container._savedClassName = container.className;
    container.className = "";
    container.style.height = "100%";
    container.style.width = "100%";

    editor = monaco.editor.create(container, {
        value: content,
        language: detectLanguage(path),
        theme: "ide-dark",
        automaticLayout: true,
        fontSize: 13,
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
        fontLigatures: true,
        minimap: { enabled: true, scale: 1 },
        lineNumbers: "on",
        renderLineHighlight: "all",
        scrollBeyondLastLine: false,
        wordWrap: "off",
        tabSize: 4,
        insertSpaces: true,
        folding: true,
        foldingStrategy: "indentation",
        showFoldingControls: "always",
        smoothScrolling: true,
        cursorSmoothCaretAnimation: "on",
        cursorBlinking: "smooth",
        renderWhitespace: "selection",
        bracketPairColorization: { enabled: true },
        guides: { bracketPairs: true, indentation: true },
        padding: { top: 8, bottom: 8 },
        readOnly: false,
    });

    editor.onDidChangeModelContent(() => {
        const newDirty = editor.getValue() !== currentContent;
        if (newDirty !== isDirty) {
            isDirty = newDirty;
            updateHeader(getFileName(currentPath), isDirty);
        }
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveFile);
    setTimeout(() => editor.focus(), 100);
}

function renderFallback(container, content, path) {
    container.innerHTML = "";
    container.style.height = "100%";

    const textarea = document.createElement("textarea");
    textarea.value = content;
    textarea.className = "w-full h-full bg-[#1e1e1e] text-[#d4d4d4] p-4 font-mono text-sm border-none outline-none resize-none";
    textarea.spellcheck = false;

    textarea.addEventListener("input", () => {
        const newDirty = textarea.value !== currentContent;
        if (newDirty !== isDirty) {
            isDirty = newDirty;
            updateHeader(getFileName(currentPath), isDirty);
        }
    });

    textarea.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            e.preventDefault();
            saveFile();
        }
    });

    container.appendChild(textarea);
    editor = { getValue: () => textarea.value, focus: () => textarea.focus() };
}

export async function saveFile() {
    if (!currentPath || !editor) return;
    if (!isDirty) {
        showToast("Нет изменений", "info", 1500);
        return;
    }

    const content = editor.getValue();
    const saveBtn = document.getElementById("file-save-btn");

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i>';
    }

    try {
        await workspacesApi.saveFile(currentPath, content);
        currentContent = content;
        isDirty = false;
        updateHeader(getFileName(currentPath), false);
        showToast("Сохранено: " + getFileName(currentPath), "success", 2000);
    } catch (e) {
        showToast("Ошибка сохранения: " + e.message, "error", 4000);
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i data-lucide="save" class="w-3.5 h-3.5"></i>';
            if (window.lucide) window.lucide.createIcons();
        }
    }
}

function getFileName(path) {
    return path ? path.split("/").pop() : "";
}

function updateHeader(name, dirty) {
    const titleEl = document.getElementById("file-viewer-title");
    if (titleEl) {
        titleEl.textContent = (dirty ? "● " : "") + (name || "Файл");
        titleEl.style.color = dirty ? "var(--ide-warning)" : "var(--ide-text)";
    }
}

function showViewerChrome(name) {
    const header = document.getElementById("file-viewer-header");
    const saveBtn = document.getElementById("file-save-btn");
    const closeBtn = document.getElementById("file-close-btn");
    if (header) header.classList.remove("hidden");
    if (saveBtn && !saveBtn.dataset.bound) {
        saveBtn.addEventListener("click", saveFile);
        saveBtn.dataset.bound = "1";
    }
    if (closeBtn && !closeBtn.dataset.bound) {
        closeBtn.addEventListener("click", closeFile);
        closeBtn.dataset.bound = "1";
    }
    updateHeader(name, false);
}

window.addEventListener("close-file", closeFile);

export async function closeFile() {
    if (isDirty) {
        // Используем кастомный конфирм вместо confirm()
        const confirmed = await showConfirm(
            "Несохранённые изменения",
            "В файле есть несохранённые изменения. Закрыть редактор без сохранения?",
            "Закрыть",
            "Отмена"
        );
        if (!confirmed) return;
    }
    const modal = document.getElementById("file-viewer-modal");
    if (modal) modal.classList.add("hidden");
    const header = document.getElementById("file-viewer-header");
    const container = document.getElementById("file-viewer-content");
    
    if (header) header.classList.add("hidden");
    if (container) {
        // Восстанавливаем классы контейнера которые очистили для Monaco
        if (container._savedClassName !== undefined) {
            container.className = container._savedClassName;
            container._savedClassName = undefined;
        }
        container.style.height = "";
        container.style.width = "";
        container.innerHTML = '<div class="flex items-center justify-center h-full text-ide-muted text-xs">Выберите файл для редактирования</div>';
    }
    
    if (editor && typeof editor.dispose === "function") {
        editor.dispose();
    }
    editor = null;
    currentPath = null;
    currentContent = null;
    isDirty = false;
}