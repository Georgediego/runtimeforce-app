"""
Tool Dispatcher Service with Safe Argument Unpacking and Sudo Password Forwarding.
"""
import json
import logging
from typing import Dict, Any, Optional
from app.core.interfaces.tool_executor_interface import IToolExecutor
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver
from app.tools.tool_file_executors import ToolFileExecutors
from app.tools.tool_shell_executors import ToolShellExecutors
from app.tools.tool_patch_executor import ToolPatchExecutor
from app.tools.tool_git_executors import ToolGitExecutors

logger = logging.getLogger("runtimeforce.tools.dispatcher")

class ToolDispatcherService(IToolExecutor):
    def __init__(self, command_filter: Optional[Any] = None):
        self.command_filter = command_filter

    @classmethod
    async def dispatch(
        cls,
        name: str,
        arguments_json: str,
        driver: IWorkspaceDriver,
    ) -> Dict[str, Any]:
        instance = cls()
        return await instance.execute(name, arguments_json, driver)

    async def execute(
        self,
        tool_name: str,
        arguments_json: str,
        driver: IWorkspaceDriver
    ) -> Dict[str, Any]:
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except Exception as e:
            return {"error": f"JSON decode error: {e}"}

        try:
            if tool_name == "execute_command":
                return await ToolShellExecutors.execute_command(
                    driver,
                    command=args.get("command", ""),
                    cwd=args.get("cwd"),
                    password=args.get("password"),
                    command_filter=self.command_filter
                )
            elif tool_name == "read_workspace_file":
                return await ToolFileExecutors.read_file(driver, args.get("filepath"))
            elif tool_name == "write_workspace_file":
                return await ToolFileExecutors.write_file(driver, args.get("filepath"), args.get("content", ""))
            elif tool_name == "scan_workspace":
                return await ToolFileExecutors.scan_workspace(driver, args.get("pattern", "**/*"))
            elif tool_name == "search_grep":
                return await ToolFileExecutors.search_grep(driver, args.get("query", ""), args.get("file_pattern", "**/*"))
            elif tool_name == "apply_code_patch":
                return await ToolPatchExecutor.apply_code_patch(driver, args.get("filepath"), args.get("patch_content", ""))
            elif tool_name == "git_status":
                return await ToolGitExecutors.git_status(driver)
            elif tool_name == "git_diff":
                return await ToolGitExecutors.git_diff(driver, path=args.get("path"), staged=args.get("staged", False))
            elif tool_name == "git_commit":
                return await ToolGitExecutors.git_commit(driver, message=args.get("message", ""), paths=args.get("paths"))
            elif tool_name == "git_log":
                return await ToolGitExecutors.git_log(driver, n=args.get("n", 10))
            else:
                return {"error": f"Tool '{tool_name}' not found."}
        except Exception as e:
            logger.error(f"Tool execution exception for '{tool_name}': {e}")
            return {"error": str(e)}
