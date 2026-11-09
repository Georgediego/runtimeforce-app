"""
IWorkspaceDriver implementation for Local Filesystem with Path Traversal Sandboxing and Forced English Locale.
"""
import os
import asyncio
import logging
import signal
from typing import Dict, Any, List, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.workspace.local_driver")

class WorkspaceLocalDriver(IWorkspaceDriver):
    def __init__(self, root_path: str):
        self.root = os.path.realpath(os.path.abspath(os.path.expanduser(root_path)))
        self._active_procs: List[asyncio.subprocess.Process] = []

    def _resolve(self, path: Optional[str]) -> str:
        if not path or path in (".", "", "~"):
            return self.root
        expanded = os.path.expanduser(path)
        if os.path.isabs(expanded):
            full = os.path.abspath(expanded)
        else:
            full = os.path.abspath(os.path.join(self.root, expanded))

        real_full = os.path.realpath(full)
        if not (real_full.startswith(self.root) or full.startswith(self.root) or self.root.startswith(real_full)):
            if real_full == self.root or full == self.root:
                return self.root
            raise PermissionError(f"Path Traversal security violation: {path} escapes workspace root {self.root}")
        return full

    async def read_file(self, path: str) -> str:
        full = self._resolve(path)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_sync, full)

    def _read_sync(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    async def write_file(self, path: str, content: str) -> None:
        full = self._resolve(path)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_sync, full, content)

    def _write_sync(self, path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    async def execute_command(
        self, command: str, cwd: Optional[str] = None, timeout: float = 30.0, password: Optional[str] = None, env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        approval_service = getattr(self, "command_approval_service", None)
        if approval_service:
            await approval_service.require_approval(
                command,
                getattr(self, "command_approval_metadata", {}),
                cwd=cwd,
            )
        work_dir = self._resolve(cwd) if cwd else self.root
        exec_cmd = command

        if command.strip().startswith("sudo ") and password:
            safe_pw = password.replace("'", "'\\''")
            exec_cmd = f"echo '{safe_pw}' | sudo -S -p '' {command[5:]}"

        env_vars = os.environ.copy()
        env_vars["LC_ALL"] = "C.UTF-8"
        env_vars["LANG"] = "C.UTF-8"
        env_vars["LANGUAGE"] = "en_US:en"
        if env:
            env_vars.update(env)

        try:
            proc = await asyncio.create_subprocess_shell(
                exec_cmd,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars,
                start_new_session=True,
            )
            self._active_procs.append(proc)
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await proc.communicate()
                return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -124, "cwd": work_dir}
            except asyncio.CancelledError:
                logger.info("Stopping workspace command process group pid=%s", proc.pid)
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=1.0)
                except asyncio.TimeoutError:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    await proc.communicate()
                raise
            finally:
                if proc in self._active_procs:
                    self._active_procs.remove(proc)

            stderr_out = stderr_b.decode("utf-8", errors="replace")
            stdout_out = stdout_b.decode("utf-8", errors="replace")

            new_cwd = work_dir
            if command.strip().startswith("cd "):
                target_dir = command.strip()[3:].strip()
                try:
                    resolved_target = self._resolve(target_dir)
                    if os.path.isdir(resolved_target):
                        new_cwd = resolved_target
                except Exception:
                    pass

            return {
                "stdout": stdout_out,
                "stderr": stderr_out,
                "exit_code": proc.returncode if proc.returncode is not None else -1,
                "cwd": new_cwd,
            }
        except Exception as e:
            logger.error(f"Local exec failed: {e}")
            return {"stdout": "", "stderr": str(e), "exit_code": -1, "cwd": work_dir}

    async def list_dir(self, path: str) -> List[Dict[str, Any]]:
        full = self._resolve(path)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_sync, full)

    def _list_sync(self, path: str) -> List[Dict[str, Any]]:
        entries = []
        try:
            target = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
            if os.path.isfile(target):
                st = os.stat(target)
                return [{
                    "name": os.path.basename(target),
                    "path": target,
                    "is_dir": False,
                    "size": st.st_size
                }]
            for name in os.listdir(target):
                full = os.path.join(target, name)
                try:
                    st = os.stat(full)
                    entries.append({
                        "name": name,
                        "path": full,
                        "is_dir": os.path.isdir(full),
                        "size": st.st_size,
                    })
                except OSError:
                    continue
        except OSError as e:
            logger.warning(f"list_dir failed at {path}: {e}")
        return entries

    async def is_healthy(self) -> bool:
        return os.path.isdir(self.root)

    async def close(self) -> None:
        for proc in self._active_procs:
            try:
                if proc.returncode is None:
                    os.killpg(proc.pid, signal.SIGTERM)
            except Exception:
                pass
        self._active_procs.clear()
