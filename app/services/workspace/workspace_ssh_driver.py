"""
IWorkspaceDriver implementation for Remote Host Execution over SSH with Forced English Locale.
"""
from typing import Dict, Any, List, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver
from app.services.ssh.ssh_connection_pool import SSHConnection
from app.services.ssh.ssh_sftp_service import SSHSFTPService

class WorkspaceSSHDriver(IWorkspaceDriver):
    def __init__(self, conn: SSHConnection, root_path: str = "/"):
        self.conn = conn
        self.root = root_path.rstrip("/") or "/"

    async def _ensure_connected(self) -> None:
        if not getattr(self.conn, "_authenticated", False):
            await self.conn.connect()

    async def read_file(self, path: str) -> str:
        await self._ensure_connected()
        full = path if path.startswith("/") else f"{self.root}/{path}"
        return await SSHSFTPService.read_file(self.conn, full)

    async def write_file(self, path: str, content: str) -> None:
        await self._ensure_connected()
        full = path if path.startswith("/") else f"{self.root}/{path}"
        await SSHSFTPService.write_file(self.conn, full, content)

    async def execute_command(
        self, command: str, cwd: Optional[str] = None, timeout: float = 30.0
    ) -> Dict[str, Any]:
        await self._ensure_connected()
        work_dir = cwd or self.root
        env_prefix = "export LC_ALL=C.UTF-8 LANG=C.UTF-8 LANGUAGE=en_US:en; "
        full_command = f"{env_prefix}{command}"
        return await self.conn.execute(full_command, cwd=work_dir, timeout=timeout)

    async def list_dir(self, path: str) -> List[Dict[str, Any]]:
        await self._ensure_connected()
        full = path if path.startswith("/") else f"{self.root}/{path}"
        res = await self.conn.execute(f"export LC_ALL=C.UTF-8; ls -1Ap '{full}' 2>/dev/null")
        entries = []
        out = res.get("stdout", "")
        if out:
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                is_dir = line.endswith("/")
                name = line.rstrip("/")
                entries.append({
                    "name": name,
                    "path": f"{full.rstrip('/')}/{name}",
                    "is_dir": is_dir,
                })
        return entries

    async def is_healthy(self) -> bool:
        try:
            await self._ensure_connected()
            return bool(getattr(self.conn, "_authenticated", False))
        except Exception:
            return False

    async def close(self) -> None:
        await self.conn.close()
