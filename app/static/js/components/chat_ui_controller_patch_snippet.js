        } else if (event.status === "tool_start") {
            this.appendTrace("TOOL", `Running: ${event.tool_name}`);
            this.appendActiveTool(event.tool_id || `tool-${Date.now()}`, event.tool_name, "running");
            currentPhaseLabel = `Running tool: ${event.tool_name}...`;
            if (event.tool_name === "execute_command") {
                try {
                    const args = JSON.parse(event.arguments || "{}");
                    if (args.command) terminalUIController.appendPromptLine(args.command, false);
                } catch (e) {}
            }
            if (assistantDiv) this.renderAssistantBubble(assistantDiv, fullResponseText, fullReasoningText);
            this.setOrchestratorProgress(60);
        } else if (event.status === "tool_end") {
            this.appendTrace("DONE", `Completed: ${event.tool_name}`);
            this.updateActiveToolStatus(event.tool_id, event.tool_name, "success");
            if (event.tool_name === "execute_command") {
                try {
                    const result = JSON.parse(event.result || "{}");
                    if (result.stdout) terminalUIController.appendOutput(result.stdout, "text-slate-200", false);
                    if (result.stderr) terminalUIController.appendOutput(result.stderr, "text-red-400", false);
                } catch (e) {}
            }
            this.setOrchestratorProgress(85);
        } else if (event.status === "error" || event.status === "failed") {
