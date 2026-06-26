"""
Tool Router: central dispatch point for all agent tools.
"""
import json
import logging
from typing import Dict, Any
from app.core.workspace.manager import workspace_manager

logger = logging.getLogger("ai_runtime.tools.router")

AGENT_TOOLS_MANIFEST = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Safely execute a shell command in the OS terminal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full command to execute."
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_code_patch",
            "description": "Modifies code using SEARCH/REPLACE block markup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to target file."},
                    "patch_content": {"type": "string", "description": "Patch content."}
                },
                "required": ["filepath", "patch_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_workspace_file",
            "description": "Reads file contents.",
            "parameters": {
                "type": "object",
                "properties": {"filepath": {"type": "string"}},
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_workspace_file",
            "description": "Writes a new file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_workspace",
            "description": "Scans project structure.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_grep",
            "description": "Search inside files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "file_pattern": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get git status.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Get unified diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "staged": {"type": "boolean"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create git commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Get commit history.",
            "parameters": {
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_revert_file",
            "description": "Revert file to last commit.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
]


class ToolRouter:
    @staticmethod
    async def dispatch(name: str, arguments_json: str) -> Dict[str, Any]:
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except Exception as je:
            return {"error": f"JSON decode error: {str(je)}"}

        logger.info(f"Dispatching tool: {name} with args: {args}")

        try:
            if name == "execute_command":
                command = args.get("command")
                cwd = args.get("cwd")
                return await workspace_manager.execute(cmd=command, cwd=cwd)

            elif name == "apply_code_patch":
                filepath = args.get("filepath")
                patch_content = args.get("patch_content")
                return await workspace_manager.apply_patch(filepath=filepath, patch_content=patch_content)

            elif name == "read_workspace_file":
                filepath = args.get("filepath")
                content = await workspace_manager.read_file(filepath)
                return {"path": filepath, "content": content}

            elif name == "write_workspace_file":
                filepath = args.get("filepath")
                content = args.get("content")
                await workspace_manager.write_file(filepath, content)
                return {"success": True, "path": filepath}

            elif name == "scan_workspace":
                pattern = args.get("pattern", "**/*")
                return await workspace_manager.scan_files(pattern)

            elif name == "search_grep":
                query = args.get("query", "")
                file_pattern = args.get("file_pattern", "**/*")
                return await workspace_manager.grep(query, file_pattern)

            elif name == "git_status":
                wm = workspace_manager
                is_repo = await wm.git.is_repo()
                if not is_repo:
                    return {"error": "Not a git repository"}
                entries = await wm.git.status()
                return {"entries": entries, "count": len(entries)}

            elif name == "git_diff":
                wm = workspace_manager
                path = args.get("path")
                staged = args.get("staged", False)
                is_repo = await wm.git.is_repo()
                if not is_repo:
                    return {"error": "Not a git repository"}
                diff_text = await wm.git.diff(path=path, staged=staged)
                return {"diff": diff_text, "path": path or "(all)"}

            elif name == "git_commit":
                wm = workspace_manager
                message = args.get("message", "")
                paths = args.get("paths")
                if not message:
                    return {"error": "Commit message is required"}
                is_repo = await wm.git.is_repo()
                if not is_repo:
                    return {"error": "Not a git repository"}
                result = await wm.git.commit(message, paths=paths)
                return result

            elif name == "git_log":
                wm = workspace_manager
                n = args.get("n", 10)
                is_repo = await wm.git.is_repo()
                if not is_repo:
                    return {"error": "Not a git repository"}
                commits = await wm.git.log(n=n)
                return {"commits": commits, "count": len(commits)}

            elif name == "git_revert_file":
                wm = workspace_manager
                path = args.get("path", "")
                if not path:
                    return {"error": "File path is required"}
                is_repo = await wm.git.is_repo()
                if not is_repo:
                    return {"error": "Not a git repository"}
                result = await wm.git.revert_file(path)
                return result

            else:
                return {"error": f"Tool '{name}' not registered."}

        except Exception as e:
            logger.error(f"Tool execution failed: {str(e)}")
            return {"error": f"Runtime execution error: {str(e)}"}


router = ToolRouter()