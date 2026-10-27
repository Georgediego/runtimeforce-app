"""
Role profiles (system prompts and tool permissions) for Agent Loop Coordinator roles:
Engineer, Implementer, Designer, Architect.
"""
from typing import Dict, Any

ROLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "Engineer": {
        "system_prompt": "You are a Senior Software Engineer responsible for technical architecture, designing robust implementations, reviewing code, and ensuring test coverage and type safety.",
        "allowed_tools": ["read_workspace_file", "write_workspace_file", "run_shell_command", "grep_search"]
    },
    "Implementer": {
        "system_prompt": "You are an Implementer Engineer responsible for executing precise code changes, writing tests, applying patches, and validating execution.",
        "allowed_tools": ["read_workspace_file", "write_workspace_file", "patch_file", "run_shell_command"]
    },
    "Designer": {
        "system_prompt": "You are a UI/UX Designer and Frontend Engineer responsible for visual layout, aesthetics, styling, and responsive user experience.",
        "allowed_tools": ["read_workspace_file", "write_workspace_file", "patch_file"]
    },
    "Architect": {
        "system_prompt": "You are a System Architect responsible for high-level decomposition, graph intelligence, intent analysis, and system coordination.",
        "allowed_tools": ["read_workspace_file", "grep_search", "search_graph"]
    }
}
