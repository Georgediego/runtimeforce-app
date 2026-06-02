import { escapeHtml } from "../utils/escape.js";
import { showToast } from "./toast.js";
import { refreshIcons } from "../utils/icons.js";

var terminalOutput = document.getElementById("terminal-output");
var terminalHeader = document.getElementById("terminal-header");
var terminalChevron = document.getElementById("terminal-chevron");
var terminalInputRow = document.getElementById("terminal-input-row");
var terminalCmdInput = document.getElementById("terminal-cmd-input");

var isExpanded = false;

function toggleTerminal() {
    isExpanded = !isExpanded;
    
    if (isExpanded) {
        terminalOutput.classList.remove("hidden");
        terminalInputRow.classList.remove("hidden");
        terminalChevron.style.transform = "rotate(180deg)";
    } else {
        terminalOutput.classList.add("hidden");
        terminalInputRow.classList.add("hidden");
        terminalChevron.style.transform = "rotate(0deg)";
    }
}

export function initTerminal() {
    // Клик по header раскрывает/сворачивает
    terminalHeader?.addEventListener("click", toggleTerminal);
    
    // Enter в input отправляет команду
    terminalCmdInput?.addEventListener("keydown", async function(e) {
        if (e.key === "Enter" && this.value.trim()) {
            var cmd = this.value.trim();
            this.value = "";
            await executeCommand(cmd);
        }
    });
    
    // Инициализация - свёрнут
    terminalChevron.style.transform = "rotate(0deg)";
}

async function executeCommand(cmd) {
    // Показываем команду в терминале
    appendToTerminal("<span class='text-ide-accent'>$ </span>" + escapeHtml(cmd));
    
    try {
        var response = await fetch("/api/v1/workspaces/execute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: cmd })
        });
        
        if (!response.ok) throw new Error("HTTP " + response.status);
        
        var data = await response.json();
        
        if (data.stdout) {
            appendToTerminal("<span class='text-ide-text'>" + escapeHtml(data.stdout) + "</span>");
        }
        if (data.stderr) {
            appendToTerminal("<span class='text-ide-error'>" + escapeHtml(data.stderr) + "</span>");
        }
        if (data.exit_code !== 0) {
            appendToTerminal("<span class='text-ide-muted'>[Exit code: " + data.exit_code + "]</span>");
        }
    } catch (err) {
        appendToTerminal("<span class='text-ide-error'>Error: " + escapeHtml(err.message) + "</span>");
    }
}

function appendToTerminal(html) {
    var line = document.createElement("div");
    line.innerHTML = html;
    line.style.whiteSpace = "pre-wrap";
    line.style.wordBreak = "break-all";
    terminalOutput.appendChild(line);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// ✅ Глобальная функция для записи команд агента в терминал
window.appendAgentTerminalOutput = function(cmd, result) {
    if (!isExpanded) {
        // Если терминал свёрнут, просто показываем иконку с количеством
        var badge = document.getElementById("terminal-badge");
        if (!badge) {
            badge = document.createElement("span");
            badge.id = "terminal-badge";
            badge.className = "text-[9px] bg-ide-accent/20 text-ide-accent px-1.5 py-0.5 rounded ml-1";
            terminalHeader.insertBefore(badge, terminalChevron);
        }
        var count = parseInt(badge.textContent || "0") + 1;
        badge.textContent = count;
    }
    
    appendToTerminal("<span class='text-yellow-400'>[Agent] $ </span>" + escapeHtml(cmd));
    if (result.stdout) {
        appendToTerminal("<span class='text-ide-muted text-[10px]'>" + escapeHtml(result.stdout.substring(0, 200)) + (result.stdout.length > 200 ? "..." : "") + "</span>");
    }
    if (result.stderr) {
        appendToTerminal("<span class='text-ide-error text-[10px]'>" + escapeHtml(result.stderr.substring(0, 200)) + "</span>");
    }
};