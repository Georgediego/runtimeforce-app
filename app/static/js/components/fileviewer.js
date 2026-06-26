import { state, setState } from "../state.js";
import { workspacesApi } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { showToast, showConfirm } from "./toast.js";

let editor = null;            
let currentPath = null;       
let currentContent = null;    
let isDirty = false;          
let monacoReady = false;      
let monacoLoadPromise = null; 

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
        const confirmed = await showConfirm(
            "Несохранённые изменения",
            "В текущем файле есть несохранённые изменения. Закрыть его без сохранения?",
            "Закрыть",
            "Отмена"
        );
        if (!confirmed) return;
    }

    currentPath = path;
    isDirty = false;
    updateHeader(name, false);
    
    // Переключаем интерфейс на вкладку Editor
    activateEditorTab();

    const container = document.getElementById("monaco-container");
    if (!container) return;

    container.innerHTML =
        '<div class="flex items-center justify-center h-full text-[var(--ide-text-muted)] text-sm">' +
        '<i data-lucide="loader" class="w-4 h-4 inline animate-spin mr-2"></i>' +
        'Загрузка ' + escapeHtml(name) + '...</div>';
    if (window.lucide) window.lucide.createIcons();

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

        bindHeaderButtons();
    } catch (e) {
        container.innerHTML =
            '<div class="flex items-center justify-center h-full text-ide-error text-sm">' +
            'Ошибка загрузки: ' + escapeHtml(e.message || String(e)) + '</div>';
    }
}

function activateEditorTab() {
    // 1. Обновляем визуальный статус кнопок-вкладок
    document.querySelectorAll('.right-tab-btn').forEach(btn => {
        btn.classList.remove('border-[var(--ide-accent)]', 'text-[var(--ide-text-primary)]');
        btn.classList.add('border-transparent', 'text-[var(--ide-text-muted)]');
        
        if (btn.dataset.panel === 'editor') {
            btn.classList.remove('border-transparent', 'text-[var(--ide-text-muted)]');
            btn.classList.add('border-[var(--ide-accent)]', 'text-[var(--ide-text-primary)]');
        }
    });
    
    // 2. Скрываем все панели
    document.querySelectorAll('.right-panel-content').forEach(panel => {
        panel.classList.add('hidden');
        panel.classList.remove('flex');
    });
    
    // 3. Показываем редактор
    const editorPanel = document.getElementById('right-panel-editor');
    if (editorPanel) {
        editorPanel.classList.remove('hidden');
        editorPanel.classList.add('flex');
    }
}

function renderMonaco(container, content, path) {
    if (editor && typeof editor.dispose === "function") { editor.dispose(); editor = null; }
    container.innerHTML = "";
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
    const saveBtn = document.getElementById("editor-save-btn");

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
    const titleEl = document.getElementById("editor-filename");
    if (titleEl) {
        titleEl.textContent = (dirty ? "● " : "") + (name || "Файл не выбран");
        // Подкрашиваем текст, если файл не сохранен
        if (dirty) {
            titleEl.classList.add("text-[var(--ide-warning)]");
            titleEl.classList.remove("text-[var(--ide-text-primary)]");
        } else {
            titleEl.classList.add("text-[var(--ide-text-primary)]");
            titleEl.classList.remove("text-[var(--ide-warning)]");
        }
    }
}

function bindHeaderButtons() {
    const saveBtn = document.getElementById("editor-save-btn");
    const closeBtn = document.getElementById("editor-close-btn");
    
    if (saveBtn && !saveBtn.dataset.bound) {
        saveBtn.addEventListener("click", saveFile);
        saveBtn.dataset.bound = "1";
    }
    if (closeBtn && !closeBtn.dataset.bound) {
        closeBtn.addEventListener("click", closeFile);
        closeBtn.dataset.bound = "1";
    }
}

window.addEventListener("close-file", closeFile);

export async function closeFile() {
    if (isDirty) {
        const confirmed = await showConfirm(
            "Несохранённые изменения",
            "В файле есть несохранённые изменения. Закрыть редактор без сохранения?",
            "Закрыть",
            "Отмена"
        );
        if (!confirmed) return;
    }
    
    const container = document.getElementById("monaco-container");
    if (container) {
        container.innerHTML = '<div class="flex items-center justify-center h-full text-[var(--ide-text-muted)] text-xs">Выберите файл для редактирования</div>';
    }
    
    updateHeader("", false);
    
    if (editor && typeof editor.dispose === "function") {
        editor.dispose();
    }
    editor = null;
    currentPath = null;
    currentContent = null;
    isDirty = false;
}