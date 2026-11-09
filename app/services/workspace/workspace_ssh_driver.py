"""
IWorkspaceDriver implementation for Remote Host Execution over SSH with Forced English Locale.
"""
import logging
from typing import Dict, Any, List, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver
from app.services.ssh.ssh_connection_pool import SSHConnection
from app.services.ssh.ssh_sftp_service import SSHSFTPService

logger = logging.getLogger("runtimeforce.workspace.ssh_driver")

class WorkspaceSSHDriver(IWorkspaceDriver):
    def __init__(self, conn: SSHConnection, root_path: str = "/"):
        self.conn = conn
        self.root = root_path.rstrip("/") or "/"

    async def _ensure_connected(self) -> None:
        if not getattr(self.conn, "_authenticated", False):
            success = await self.conn.connect()
            if not success:
                logger.error(f"SSH connection failed for {self.conn.username}@{self.conn.host}:{self.conn.port}")
                raise ConnectionError(f"Failed to connect to SSH {self.conn.host}")
            else:
                logger.info(f"SSH connection established: {self.conn.username}@{self.conn.host}:{self.conn.port}")

    async def read_file(self, path: str) -> str:
        await self._ensure_connected()
        full = path if path.startswith("/") else f"{self.root}/{path}"
        return await SSHSFTPService.read_file(self.conn, full)

    async def write_file(self, path: str, content: str) -> None:
        await self._ensure_connected()
        full = path if path.startswith("/") else f"{self.root}/{path}"
        await SSHSFTPService.write_file(self.conn, full, content)

    async def execute_command(
        self, command: str, cwd: Optional[str] = None, timeout: float = 30.0, env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        approval_service = getattr(self, "command_approval_service", None)
        if approval_service:
            await approval_service.require_approval(
                command,
                getattr(self, "command_approval_metadata", {}),
                cwd=cwd,
            )
        if env:
            raise NotImplementedError("env is not supported for SSH workspaces")
        await self._ensure_connected()
        work_dir = cwd or self.root
        env_prefix = "export LC_ALL=C.UTF-8 LANG=C.UTF-8 LANGUAGE=en_US:en; "
        full_command = f"{env_prefix}{command}"
        return await self.conn.execute(full_command, cwd=work_dir, timeout=timeout)

    async def list_dir(self, path: str) -> List[Dict[str, Any]]:
        await self._ensure_connected()
        full = path if path.startswith("/") else f"{self.root}/{path}"
        
        # First check if directory exists and is accessible
        check_res = await self.conn.execute(f"test -d '{full}' && echo 'exists' || echo 'not_exists'")
        if check_res.get("stdout", "").strip() != "exists":
            logger.error(f"SSH directory does not exist or not accessible: {full}")
            raise FileNotFoundError(f"Directory {full} does not exist or is not accessible")
        
        # Check read permissions
        perm_res = await self.conn.execute(f"test -r '{full}' && echo 'readable' || echo 'not_readable'")
        if perm_res.get("stdout", "").strip() != "readable":
            logger.error(f"SSH directory not readable: {full}")
            raise PermissionError(f"Directory {full} is not readable")
        
        # Try ls -la first for detailed info, fallback to simple ls
        res = await self.conn.execute(f"export LC_ALL=C.UTF-8; ls -1A '{full}' 2>/dev/null")
        out = res.get("stdout", "")
        exit_code = res.get("exit_code", -1)
        
        if exit_code != 0 or not out:
            # Fallback to find with simpler syntax
            res = await self.conn.execute(f"export LC_ALL=C.UTF-8; find '{full}' -maxdepth 1 -mindepth 1 2>/dev/null | xargs -n1 basename")
            out = res.get("stdout", "")
            exit_code = res.get("exit_code", -1)
        
        if exit_code != 0:
            logger.error(f"SSH list_dir failed for {full}: exit_code={exit_code}, stderr={res.get('stderr', '')}")
            return []
        
        entries = []
        if out:
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Check if it's a directory
                test_path = f"{full.rstrip('/')}/{line}"
                is_dir_res = await self.conn.execute(f"test -d '{test_path}' && echo 'dir' || echo 'file'")
                is_dir = is_dir_res.get("stdout", "").strip() == "dir"
                entries.append({
                    "name": line,
                    "path": test_path,
                    "is_dir": is_dir,
                })
        
        logger.info(f"SSH list_dir succeeded for {full}: found {len(entries)} entries")
        return entries

    async def is_healthy(self) -> bool:
        try:
            await self._ensure_connected()
            return bool(getattr(self.conn, "_authenticated", False))
        except Exception:
            return False

    async def close(self) -> None:
        await self.conn.close()
