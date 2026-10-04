"""
Service for Task-Relevant Terminal Execution Memory & Error Node Recording.
"""
import logging
from app.services.memory.graph_memory_service import GraphMemoryService

logger = logging.getLogger("runtimeforce.service.memory.terminal_intelligence")

class TerminalIntelligenceService:
    def __init__(self, graph_memory: GraphMemoryService):
        self.graph_memory = graph_memory

    def record_command(
        self,
        tool_call_id: str,
        command: str,
        exit_code: int,
        project_id: str,
        user_id: str
    ):
        node_id = f"term-{tool_call_id[:12]}"
        node_type = "Error" if exit_code != 0 else "TerminalCmd"

        self.graph_memory.record_entity(
            node_id=node_id,
            user_id=user_id,
            project_id=project_id,
            node_type=node_type,
            label=f"$ {command[:60]} (exit={exit_code})",
            attributes={"command": command, "exit_code": exit_code, "tool_call_id": tool_call_id},
            text_for_search=command
        )
