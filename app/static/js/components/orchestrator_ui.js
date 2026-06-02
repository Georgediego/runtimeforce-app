OK: orchestrator_ui.js создан
�ация работы оркестратора и инструментов

export function updateOrchestratorUI(data) {
    var statusEl = document.getElementById("agent-status-text");
    var modelEl = document.getElementById("current-model-display");
    if (statusEl && data.status) statusEl.textContent = data.status;
    if (modelEl && data.model) modelEl.textContent = data.model.split("/").pop();
}

export function addToolToExecutionList(tool) {
    var container = document.getElementById("active-tools-list");
    if (!container) return;
    
    var placeholder = container.querySelector(".text-center");
    if (placeholder) placeholder.remove();
    
    var existing = container.querySelector("[data-tool-id='" + tool.tool_id + "']");
    if (existing) existing.remove();
    
    var toolEl = document.createElement("div");
    toolEl.className = "tool-execution-item flex items-center gap-2 p-2 bg-ide-bg border border-ide-border rounded text-xs";
    toolEl.dataset.toolId = tool.tool_id;
    var argsStr = tool.arguments ? String(tool.arguments).substring(0, 40) : "";
    toolEl.innerHTML = 
        '<i data-lucide="loader" class="w-3 h-3 animate-spin text-yellow-500 shrink-0"></i>' +
        '<span class="font-medium truncate flex-1">' + tool.name + '</span>' +
        '<span class="text-[9px] text-ide-muted truncate max-w-[80px]" title="' + (tool.arguments || "") + '">' + argsStr + '</span>';
    
    container.appendChild(toolEl);
    container.scrollTop = container.scrollHeight;
    
    if (window.lucide) window.lucide.createIcons();
}

export function updateToolInExecutionList(toolId, result) {
    var items = document.querySelectorAll(".tool-execution-item");
    items.forEach(function(item) {
        if (item.dataset.toolId === toolId) {
            var icon = item.querySelector("i");
            if (!icon) return;
            if (result && result.success) {
                icon.className = "w-3 h-3 text-green-500 shrink-0";
                icon.setAttribute("data-lucide", "check-circle");
            } else {
                icon.className = "w-3 h-3 text-red-500 shrink-0";
                icon.setAttribute("data-lucide", "x-circle");
            }
            if (window.lucide) window.lucide.createIcons();
            
            setTimeout(function() {
                if (item && item.parentNode) {
                    item.remove();
                    var container = document.getElementById("active-tools-list");
                    if (container && container.children.length === 0) {
                        container.innerHTML = '<div class="text-[11px] text-ide-muted text-center py-3">Нет активных инструментов</div>';
                    }
                }
            }, 2000);
        }
    });
}
