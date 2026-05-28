import asyncio
import os
import logging
from typing import Dict, Any, Tuple, Optional
from app.memory.store import store

logger = logging.getLogger("ai_runtime.tools.safe_shell")

BANNED_COMMAND_PATTERNS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "shutdown", "reboot",
    "init 0", "init 6", "passwd", "chroot", "forkbomb", ":(){ :|: & };:"
]

INTERACTIVE_COMMANDS = [
    "nano", "vi", "vim", "emacs", "less", "more", "top", "htop", "ssh"
]


class SafeShell:
    def is_safe(self, command: str) -> Tuple[bool, str]:
        """Check command for safety and interactivity."""
        normalized = command.strip().lower()
        for pattern in BANNED_COMMAND_PATTERNS:
            if pattern in normalized:
                return False, f"Security block: Dangerous command detected: {pattern}"
        for cmd in INTERACTIVE_COMMANDS:
            if normalized.startswith(cmd) or f" {cmd} " in normalized:
                return False, f"Block: Command '{cmd}' requires interactive TTY"
        if "sudo " in normalized:
            if os.getenv("ALLOW_SUDO", "false").lower() != "true":
                return False, "Security block: sudo is disabled"
        return True, "Safe"

    async def execute(self, command: str, timeout: float = 60.0, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Asynchronously execute a command with safety checks and timeout."""
        is_safe, reason = self.is_safe(command)
        if not is_safe:
            store.log_command(command, -1, "", reason, "BLOCKED")
            return {"exit_code": -1, "stdout": "", "stderr": reason, "status": "blocked"}
        execution_cwd = cwd or os.getcwd()
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=execution_cwd,
                env=os.environ.copy()
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                exit_code = process.returncode
                status = "success" if exit_code == 0 else "failed"
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                stdout, stderr = await process.communicate()
                stdout = stdout.decode("utf-8", errors="replace") + "\n[Timeout: killed]"
                stderr = stderr.decode("utf-8", errors="replace")
                exit_code = -124
                status = "timeout"
            store.log_command(command, exit_code, stdout, stderr, status)
            return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr, "status": status}
        except Exception as e:
            err_msg = f"Runtime execution exception: {str(e)}"
            logger.error(err_msg)
            store.log_command(command, -99, "", err_msg, "exception")
            return {"exit_code": -99, "stdout": "", "stderr": err_msg, "status": "exception"}


safe_shell = SafeShell()
