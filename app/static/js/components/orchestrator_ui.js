/**
 * RuntimeForce IDE — Orchestrator UI Controller
 * Отображение статуса агента, текущей модели и активных инструментов
 */
import { refreshIcons } from "../utils/icons.js";

/**
 * Обновляет статус агента и текущую модель в шапке чата
 */
export function updateOrchestratorUI(data) {
    var statusEl = document.getElementById("agent-status-text");
    var modelEl = document.getElementById("current-model-display");
    
    if (statusEl && data.status) {
        statusEl.textContent = data.status;
        
        // Цветовая индикация статуса
        if (data.status === "Running") {
            statusEl.style.color = "var(--ide-warning)";
        } else if (data.status === "Stopped" || data.status === "Error") {
            statusEl.style.color = "var(--ide-error)";
        } else {
            statusEl.style.color = "var(--ide-text)";
        }
    }
    
    if (modelEl && data.model) {
        modelEl.textContent = data.model.split("/").pop();
    }
}

/**
 * Добавляет новый инструмент в панель активного выполнения
 */
export function addToolToExecutionList(tool) {
    var container = document.getElementById("active-tools-list");
    if (!container) return;
    
    // Удаляем placeholder "Нет активных инструментов"
    var placeholder = container.querySelector(".text-center");
    if (placeholder) placeholder.remove();
    
    // Защита от дубликатов
    var existing = container.querySelector("[data-tool-id='" + tool.tool_id + "']");
    if (existing) existing.remove();
    
    var toolEl = document.createElement("div");
    toolEl.className = "tool-execution-item running";
    toolEl.dataset.toolId = tool.tool_id;
    
    var argsStr = tool.arguments ? String(tool.arguments).substring(0, 40) : "";
    
    toolEl.innerHTML = 
        '<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin text-yellow-500 shrink-0"></i>' +
        '<span class="tool-name text-xs font-medium text-ide-text truncate flex-1">' + 
            (tool.name || "unknown") + 
        '</span>' +
        '<span class="tool-time text-[9px] text-ide-muted truncate max-w-[80px]" title="' + 
            (tool.arguments || "") + '">' + 
            argsStr + 
        '</span>';
    
    container.appendChild(toolEl);
    container.scrollTop = container.scrollHeight;
    
    // Обновляем счётчик в шапке
    var counter = document.getElementById("tools-count");
    if (counter) {
        var count = container.querySelectorAll(".tool-execution-item").length;
        counter.textContent = "(" + count + ")";
    }
    
    refreshIcons(toolEl);
}

/**
 * Обновляет статус выполнения инструмента (успех/ошибка)
 */
export function updateToolInExecutionList(toolId, result) {
    var items = document.querySelectorAll(".tool-execution-item");
    items.forEach(function(item) {
        if (item.dataset.toolId !== toolId) return;
        
        var icon = item.querySelector("i");
        if (!icon) return;
        
        var isSuccess = result && (result.success || !result.error);
        
        if (isSuccess) {
            item.classList.remove("running");
            item.classList.add("success");
            icon.className = "w-3.5 h-3.5 text-green-500 shrink-0";
            icon.setAttribute("data-lucide", "check-circle");
        } else {
            item.classList.remove("running");
            item.classList.add("error");
            icon.className = "w-3.5 h-3.5 text-red-500 shrink-0";
            icon.setAttribute("data-lucide", "x-circle");
        }
        
        refreshIcons(item);
        
        // Удаляем инструмент через 2.5 секунды после завершения
        setTimeout(function() {
            if (item && item.parentNode) {
                item.remove();
                
                var container = document.getElementById("active-tools-list");
                if (container && container.children.length === 0) {
                    container.innerHTML = '<div class="text-center text-[11px] text-ide-muted py-3">Нет активных инструментов</div>';
                }
                
                // Обновляем счётчик
                var counter = document.getElementById("tools-count");
                if (counter && container) {
                    var count = container.querySelectorAll(".tool-execution-item").length;
                    counter.textContent = "(" + count + ")";
                }
            }
        }, 2500);
    });
}