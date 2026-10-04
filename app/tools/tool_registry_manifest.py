"""
JSON Schema Manifest declarations for all agent tools.
"""
AGENT_TOOLS_MANIFEST = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute shell command in terminal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_workspace_file",
            "description": "Read full file content from workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_workspace_file",
            "description": "Write/overwrite content to file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_workspace",
            "description": "Scan workspace files matching glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_grep",
            "description": "Search text pattern across workspace files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "file_pattern": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_code_patch",
            "description": "Modify file using SEARCH/REPLACE blocks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "patch_content": {"type": "string"},
                },
                "required": ["filepath", "patch_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get git status of workspace.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Get git diff of changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "staged": {"type": "boolean"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage and commit changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Get commit history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
]
