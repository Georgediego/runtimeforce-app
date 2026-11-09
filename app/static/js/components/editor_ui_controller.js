/**
 * Editor UI Controller with Event-Driven Monaco Model Loading and Syncing.
 */
import { workspacesApi } from "../core/api_http_client.js";
import { showToast, showConfirm } from "./toast_ui_controller.js";
import { eventBus } from "../core/event_bus.js";

let editor = null;
let currentPath = null;
let isDirty = false;

export const editorUIController = {
    init() {
        document.getElementById("editor-save-btn")?.addEventListener("click", () => this.save());
        document.getElementById("editor-close-btn")?.addEventListener("click", () => this.closeWithConfirmation());

        document.querySelector('.right-tab-btn[data-panel="editor"]')?.addEventListener("click", () => {
            setTimeout(() => { if (editor && typeof editor.layout === "function") editor.layout(); }, 50);
        });

        eventBus.on("file:open", ({ path, name }) => {
            this.openFile(path, name);
        });
        eventBus.on("file.selected", ({ path, name }) => {
            this.openFile(path, name);
        });
    },

    async openFile(path, name) {
        if (isDirty) {
            const confirmed = await showConfirm("Unsaved Changes", `File "${currentPath}" has unsaved changes. Discard?`, "Discard", "Cancel");
            if (!confirmed) return;
        }

        document.querySelector('.right-tab-btn[data-panel="editor"]')?.click();

        currentPath = path;
        isDirty = false;
        this.updateHeader(name || path.split("/").pop(), false);

        const container = document.getElementById("monaco-container");
        if (!container) return;

        try {
            const activeProjectId = localStorage.getItem("rf_active_project_id");
            const data = await workspacesApi.file(path, activeProjectId);
            container.innerHTML = "";
            if (window.monaco) {
                if (editor) editor.dispose();
                editor = monaco.editor.create(container, {
                    value: data.content || "",
                    language: this.detectLanguage(path),
                    theme: document.documentElement.classList.contains("light") ? "vs" : "vs-dark",
                    automaticLayout: true,
                    fontSize: 13,
                });

                editor.onDidChangeModelContent(() => {
                    if (!isDirty) {
                        isDirty = true;
                        this.updateHeader(name || path.split("/").pop(), true);
                    }
                });

                setTimeout(() => { if (editor) editor.layout(); }, 100);
            } else {
                const textarea = document.createElement("textarea");
                textarea.value = data.content || "";
                textarea.className = "w-full h-full bg-[var(--ide-bg)] text-[var(--ide-text-primary)] p-4 font-mono text-sm outline-none resize-none";
                textarea.addEventListener("input", () => {
                    if (!isDirty) {
                        isDirty = true;
                        this.updateHeader(name || path.split("/").pop(), true);
                    }
                });
                container.appendChild(textarea);
                editor = { getValue: () => textarea.value };
            }
        } catch (e) {
            showToast(`Failed to open file: ${e.message}`, "error");
        }
    },

    updateHeader(name, dirty) {
        const filenameEl = document.getElementById("editor-filename");
        if (filenameEl) {
            filenameEl.textContent = `${name}${dirty ? " •" : ""}`;
            filenameEl.className = dirty ? "text-xs font-mono text-[var(--ide-accent)] font-bold truncate" : "text-xs font-mono text-[var(--ide-text-primary)] truncate";
        }
    },

    async save() {
        if (!currentPath || !editor) return;
        try {
            const activeProjectId = localStorage.getItem("rf_active_project_id");
            await workspacesApi.saveFile(currentPath, editor.getValue(), activeProjectId);
            isDirty = false;
            this.updateHeader(currentPath.split("/").pop(), false);
            showToast("File saved", "success");
        } catch (e) {
            showToast(`Save failed: ${e.message}`, "error");
        }
    },

    async closeWithConfirmation() {
        if (isDirty) {
            const confirmed = await showConfirm("Unsaved Changes", "You have unsaved changes in this file. Are you sure you want to close without saving?", "Discard & Close", "Cancel");
            if (!confirmed) return;
        }
        this.close();
    },

    close() {
        if (editor && typeof editor.dispose === "function") editor.dispose();
        editor = null;
        currentPath = null;
        isDirty = false;
        const container = document.getElementById("monaco-container");
        if (container) container.innerHTML = '<div class="flex items-center justify-center h-full text-[var(--ide-text-muted)] text-xs">Select a file to edit</div>';
        const filenameEl = document.getElementById("editor-filename");
        if (filenameEl) filenameEl.textContent = "No file selected";

        document.querySelector('.right-tab-btn[data-panel="chat"]')?.click();
    },

    detectLanguage(path) {
        const ext = (path.split(".").pop() || "").toLowerCase();
        const map = {
            py: "python", pyw: "python", js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
            ts: "typescript", tsx: "typescript", json: "json", jsonc: "json", html: "html", htm: "html",
            css: "css", scss: "scss", less: "less", md: "markdown", mdx: "markdown",
            yml: "yaml", yaml: "yaml", xml: "xml", svg: "xml", sh: "shell", bash: "shell",
            zsh: "shell", sql: "sql", go: "go", rs: "rust", java: "java", kt: "kotlin",
            c: "c", h: "c", cpp: "cpp", hpp: "cpp", cs: "csharp", php: "php",
            rb: "ruby", swift: "swift", toml: "ini", ini: "ini", dockerfile: "dockerfile"
        };
        return map[ext] || "plaintext";
    }
};
