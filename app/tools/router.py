"""
Tool Router: central dispatch point for all agent tools.
Integrated with workspace_manager for unified local/SSH access.
"""
import json
import logging
from typing import Dict, Any

from app.core.workspace import workspace_manager

logger = logging.getLogger("ai_runtime.tools.router")


AGENT_TOOLS_MANIFEST = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Safely execute a shell command in the OS terminal (local or SSH workspace).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full command to execute (e.g., 'ls -la' or 'python3 manage.py migrate')."
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional path to working directory inside project."
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
            "description": "Modifies code in an existing file using SEARCH/REPLACE block markup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to target file."
                    },
                    "patch_content": {
                        "type": "string",
                        "description": "Patch content with blocks: <<<<<<< SEARCH [old] ======= [new] >>>>>>> REPLACE"
                    }
                },
                "required": ["filepath", "patch_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_workspace_file",
            "description": "Reads full contents of specified file for deep context analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to file."
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_workspace_file",
            "description": "Writes a brand new file to the project working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to file to create."
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content of the file."
                    }
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_workspace",
            "description": "Recursively scans project structure with a search mask.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "File search mask (e.g., '**/*.py' or '**' for current folder)."
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_grep",
            "description": "Performs fast string or regex search inside all text files of the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search string or regex."
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional filename filter (e.g., '*.py'). Defaults to everywhere."
                    }
                },
                "required": ["query"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get git status of the workspace. Shows modified, added, deleted, untracked files.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Get unified diff for a specific file or all changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional file path. If omitted, returns diff for all changes."
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show staged (cached) diff instead of working tree diff."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a git commit with the given message. Optionally specify files to commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Commit message describing the changes."
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of file paths to commit. If omitted, commits all changes."
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Get recent git commit history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Number of commits to return (default 10)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_revert_file",
            "description": "Revert a specific file to its last committed state. Use this to undo bad changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to revert."
                    }
                },
                "required": ["path"]
            }
        }
    },
]


class ToolRouter:
    @staticmethod
    async def dispatch(name: str, arguments_json: str) -> Dict[str, Any]:
        """
        Parses arguments and routes tool calls to workspace_manager.
        Returns structured response for LLM context.
        """
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except Exception as je:
            return {"error": f"JSON decode error: {str(je)}"}

        logger.info(f"Dispatching tool: {name} with args: {args}")

        try:
            if name == "execute_command":
                command = args.get("command")
                cwd = args.get("cwd")
                return await workspace_manager.execute(command=command, cwd=cwd)

            elif name == "apply_code_patch":
                filepath = args.get("filepath")
                patch_content = args.get("patch_content")
                return await workspace_manager.apply_patch(
                    filepath=filepath,
                    patch_content=patch_content
                )

            elif name == "read_workspace_file":
                filepath = args.get("filepath")
                return await workspace_manager.read_file(filepath)

            elif name == "write_workspace_file":
                filepath = args.get("filepath")
                content = args.get("content")
                return await workspace_manager.write_file(filepath, content)

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
                return {"error": f"Tool '{name}' not registered in system."}

        except Exception as e:
            logger.error(f"Tool execution failed: {str(e)}")
            return {"error": f"Runtime execution error: {str(e)}"}


# Global singleton
router = ToolRouter()