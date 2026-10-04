"""
Service for Detecting Infinite Loops, Empty Response Streaks, and Repeated Tool Calls.
"""
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("runtimeforce.service.agent.loop_detector")

class AgentLoopDetector:
    def __init__(
        self,
        max_empty_responses: int = 2,
        max_repeated_tools: int = 3,
        max_iterations: int = 25
    ):
        self.max_empty_responses = max_empty_responses
        self.max_repeated_tools = max_repeated_tools
        self.max_iterations = max_iterations
        self.empty_response_count = 0
        self.last_tool_signature = ""
        self.repeated_tool_count = 0

    def check_empty_response(self, text: str, tool_calls: List[Any]) -> Optional[str]:
        if len(text.strip()) == 0 and not tool_calls:
            self.empty_response_count += 1
            if self.empty_response_count >= self.max_empty_responses:
                return "EMPTY_RESPONSE_LOOP"
        else:
            self.empty_response_count = 0
        return None

    def check_tool_loop(self, tool_calls: List[Dict[str, Any]]) -> Optional[str]:
        if not tool_calls:
            self.last_tool_signature = ""
            self.repeated_tool_count = 0
            return None

        sig = json.dumps(
            [{"n": c.get("name"), "a": c.get("arguments")} for c in tool_calls],
            sort_keys=True
        )
        if sig == self.last_tool_signature:
            self.repeated_tool_count += 1
            if self.repeated_tool_count >= self.max_repeated_tools:
                return "REPEATED_TOOL_LOOP"
        else:
            self.last_tool_signature = sig
            self.repeated_tool_count = 1

        return None

    def check_max_iterations(self, iteration: int) -> Optional[str]:
        if iteration >= self.max_iterations:
            return "MAX_ITERATIONS_EXCEEDED"
        return None
