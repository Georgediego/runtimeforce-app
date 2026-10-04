"""
Async Connection Pool Manager for Paramiko SSH sessions with auto-reconnection and stale handle cleanup.
"""
import logging
import asyncio
import io
from typing import Optional, Dict, Any
from paramiko import SSHClient, AutoAddPolicy, AuthenticationException, SSHException

logger = logging.getLogger("runtimeforce.service.ssh.pool")

class SSHConnection:
    def __init__(
        self,
        workspace_id: str,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        passphrase: Optional[str] = None,
    ):
        self.workspace_id = workspace_id
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.passphrase = passphrase

        self.client: Optional[SSHClient] = None
        self._authenticated = False
        self._connect_lock = asyncio.Lock()

    async def is_active(self) -> bool:
        if not self._authenticated or not self.client:
            return False
        try:
            transport = self.client.get_transport()
            if transport and transport.is_active():
                return True
        except Exception:
            pass
        return False

    async def connect(self, timeout: float = 10.0) -> bool:
        async with self._connect_lock:
            if await self.is_active():
                return True

            await self.close()

            try:
                self.client = SSHClient()
                self.client.set_missing_host_key_policy(AutoAddPolicy())

                kwargs: Dict[str, Any] = {
                    "hostname": self.host,
                    "port": self.port,
                    "username": self.username,
                    "timeout": timeout,
                    "allow_agent": False,
                    "look_for_keys": False,
                }

                if self.password:
                    kwargs["password"] = self.password

                if self.private_key:
                    key_file = io.StringIO(self.private_key)
                    for key_class in [
                        lambda f, p=None: __import__("paramiko").RSAKey.from_private_key(f, password=p),
                        lambda f, p=None: __import__("paramiko").Ed25519Key.from_private_key(f, password=p),
                        lambda f, p=None: __import__("paramiko").ECDSAKey.from_private_key(f, password=p),
                        lambda f, p=None: __import__("paramiko").DSSKey.from_private_key(f, password=p),
                    ]:
                        try:
                            key_file.seek(0)
                            key = key_class(key_file, self.passphrase)
                            kwargs["pkey"] = key
                            break
                        except Exception:
                            key_file.seek(0)
                            continue

                self.client.connect(**kwargs)
                transport = self.client.get_transport()
                if transport and transport.is_authenticated():
                    self._authenticated = True
                    logger.info(f"SSH connected successfully: {self.username}@{self.host}:{self.port}")
                    return True
                else:
                    raise AuthenticationException("SSH Authentication failed")

            except Exception as e:
                logger.error(f"SSH connection error for {self.username}@{self.host}: {e}")
                await self.close()
                return False

    async def close(self):
        if self.client:
            try:
                transport = self.client.get_transport()
                if transport:
                    transport.close()
                self.client.close()
            except Exception as e:
                logger.debug(f"SSH close transport cleanup error: {e}")
            finally:
                self.client = None
        self._authenticated = False

    async def execute(
        self, command: str, cwd: Optional[str] = None, timeout: float = 30.0, password: Optional[str] = None
    ) -> Dict[str, Any]:
        if not await self.is_active():
            if not await self.connect():
                return {"exit_code": -1, "stdout": "", "stderr": "SSH Connection failed", "status": "error"}

        try:
            full_command = f"cd '{cwd}' 2>/dev/null && {command}" if cwd else command
            if command.strip().startswith("sudo ") and password:
                safe_pw = password.replace("'", "'\\''")
                full_command = f"echo '{safe_pw}' | sudo -S -p '' {command[5:]}"

            stdin, stdout, stderr = self.client.exec_command(full_command, timeout=timeout)
            stdout_data = stdout.read().decode("utf-8", errors="replace")
            stderr_data = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()

            return {
                "exit_code": exit_code,
                "stdout": stdout_data,
                "stderr": stderr_data,
                "status": "success" if exit_code == 0 else "error",
            }
        except Exception as e:
            logger.error(f"SSH Command execution failed: {e}")
            await self.close()
            return {"exit_code": -1, "stdout": "", "stderr": str(e), "status": "error"}

class SSHConnectionPool:
    def __init__(self):
        self._connections: Dict[str, SSHConnection] = {}

    def get_or_create(
        self,
        workspace_id: str,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        passphrase: Optional[str] = None,
    ) -> SSHConnection:
        existing = self._connections.get(workspace_id)
        if existing:
            creds_changed = (
                existing.password != password or
                existing.private_key != private_key or
                existing.passphrase != passphrase or
                existing.host != host or
                existing.port != port or
                existing.username != username
            )
            if creds_changed:
                asyncio.create_task(existing.close())
                del self._connections[workspace_id]
                existing = None

        if existing is None:
            self._connections[workspace_id] = SSHConnection(
                workspace_id=workspace_id,
                host=host,
                port=port,
                username=username,
                password=password,
                private_key=private_key,
                passphrase=passphrase,
            )

        return self._connections[workspace_id]

    async def close(self, workspace_id: str):
        conn = self._connections.pop(workspace_id, None)
        if conn:
            await conn.close()

    async def close_all(self):
        for wid in list(self._connections.keys()):
            await self.close(wid)
