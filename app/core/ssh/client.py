"""
SSH client manager with credential-aware connection pooling.
Works with both password and private key authentication.
"""
import logging
import asyncio
from typing import Optional, Dict, Any, List
from paramiko import SSHClient, AutoAddPolicy, AuthenticationException, SSHException
from paramiko.sftp_client import SFTPClient
import io

logger = logging.getLogger("ai_runtime.ssh")


class SSHConnection:
    """Represents a single SSH connection to a remote host."""

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
        self.sftp: Optional[SFTPClient] = None
        self._authenticated = False
        self._connect_lock = asyncio.Lock()

    async def connect(self, timeout: float = 10.0) -> bool:
        """Establish SSH connection with retry logic."""
        async with self._connect_lock:
            if self._authenticated and self.client:
                # Verify connection is still alive
                try:
                    stdin, stdout, stderr = self.client.exec_command("echo OK", timeout=2)
                    if stdout.channel.recv_exit_status() == 0:
                        return True
                except Exception:
                    pass
                # Connection dead, reconnect
                await self.close()

            try:
                self.client = SSHClient()
                self.client.set_missing_host_key_policy(AutoAddPolicy())

                # Prepare authentication parameters
                kwargs: Dict[str, Any] = {
                    "hostname": self.host,
                    "port": self.port,
                    "username": self.username,
                    "timeout": timeout,
                    "allow_agent": False,
                    "look_for_keys": False,
                }

                # Add password if present
                if self.password:
                    kwargs["password"] = self.password

                # Add private key if present
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

                # Connect with authentication
                self.client.connect(**kwargs)

                # Verify authentication succeeded
                transport = self.client.get_transport()
                if transport and transport.is_authenticated():
                    self._authenticated = True
                    logger.info(f"SSH connected: {self.username}@{self.host}:{self.port}")
                    return True
                else:
                    raise AuthenticationException("Authentication failed")

            except AuthenticationException as e:
                logger.error(f"SSH auth failed for {self.username}@{self.host}: {e}")
                await self.close()
                return False
            except SSHException as e:
                logger.error(f"SSH connection error for {self.username}@{self.host}: {e}")
                await self.close()
                return False
            except Exception as e:
                logger.error(f"Unexpected SSH error for {self.username}@{self.host}: {type(e).__name__}: {e}")
                await self.close()
                return False

    async def close(self):
        """Close SSH connection and clean up resources."""
        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
            self.sftp = None
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self._authenticated = False

    async def execute(self, command: str, cwd: Optional[str] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """Execute a shell command on the remote host."""
        if not self._authenticated or not self.client:
            if not await self.connect():
                return {"exit_code": -1, "stdout": "", "stderr": "Connection failed", "status": "error"}

        try:
            # Change to working directory if specified
            full_command = command
            if cwd:
                full_command = f"cd '{cwd}' 2>/dev/null && {command}"

            stdin, stdout, stderr = self.client.exec_command(full_command, timeout=timeout)

            # Read output with timeout
            stdout_data = stdout.read().decode("utf-8", errors="replace")
            stderr_data = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()

            return {
                "exit_code": exit_code,
                "stdout": stdout_data,
                "stderr": stderr_data,
                "status": "success" if exit_code == 0 else "error",
            }

        except asyncio.TimeoutError:
            logger.warning(f"Command timed out: {command[:50]}...")
            return {"exit_code": -1, "stdout": "", "stderr": "Command timed out", "status": "timeout"}
        except Exception as e:
            logger.error(f"Command execution failed: {type(e).__name__}: {e}")
            return {"exit_code": -1, "stdout": "", "stderr": str(e), "status": "error"}

    async def read_file(self, filepath: str) -> str:
        """Read file content via SFTP."""
        if not self._authenticated or not self.client:
            if not await self.connect():
                raise ConnectionError("SSH connection failed")

        try:
            # Try SFTP first (more reliable for binary/large files)
            if not self.sftp:
                self.sftp = self.client.open_sftp()

            with self.sftp.open(filepath, "r") as f:
                return f.read()

        except Exception as sftp_error:
            logger.warning(f"SFTP read failed, falling back to cat: {sftp_error}")
            # Fallback to shell command
            result = await self.execute(f"cat '{filepath}'")
            if result["exit_code"] != 0:
                raise FileNotFoundError(f"Cannot read {filepath}: {result['stderr']}")
            return result["stdout"]

    async def write_file(self, filepath: str, content: str):
        """Write file content via SFTP."""
        if not self._authenticated or not self.client:
            if not await self.connect():
                raise ConnectionError("SSH connection failed")

        try:
            # Ensure directory exists
            dirname = "/".join(filepath.split("/")[:-1])
            if dirname:
                await self.execute(f"mkdir -p '{dirname}'")

            # Try SFTP first
            if not self.sftp:
                self.sftp = self.client.open_sftp()

            with self.sftp.open(filepath, "w") as f:
                f.write(content)

        except Exception as sftp_error:
            logger.warning(f"SFTP write failed, falling back to shell: {sftp_error}")
            # Fallback to shell command with heredoc
            safe_content = content.replace("'", "'\"'\"'")
            result = await self.execute(f"cat > '{filepath}' << 'ENDOFFILE'\n{safe_content}\nENDOFFILE")
            if result["exit_code"] != 0:
                raise IOError(f"Cannot write {filepath}: {result['stderr']}")

    async def list_dir(self, dirpath: str) -> List[Dict[str, Any]]:
        """List directory contents via SFTP or shell fallback."""
        if not self._authenticated or not self.client:
            if not await self.connect():
                return []

        entries = []

        try:
            # Try SFTP first
            if not self.sftp:
                self.sftp = self.client.open_sftp()

            for entry in self.sftp.listdir_attr(dirpath):
                entries.append({
                    "name": entry.filename,
                    "path": f"{dirpath.rstrip('/')}/{entry.filename}",
                    "is_dir": entry.st_mode is not None and (entry.st_mode & 0o170000) == 0o040000,
                    "size": entry.st_size if hasattr(entry, "st_size") else 0,
                    "mtime": entry.st_mtime if hasattr(entry, "st_mtime") else 0,
                })
            return entries

        except Exception as e:
            logger.warning(f"SFTP list failed, falling back to ls: {e}")
            # Fallback to shell command
            result = await self.execute(f"ls -la '{dirpath}'")
            if result["exit_code"] != 0:
                return []

            # Parse ls output (basic parser)
            for line in result["stdout"].splitlines()[1:]:  # Skip total line
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    perm, _, _, _, size, _, _, date, name = parts
                    is_dir = perm.startswith("d")
                    entries.append({
                        "name": name,
                        "path": f"{dirpath.rstrip('/')}/{name}",
                        "is_dir": is_dir,
                        "size": int(size) if size.isdigit() else 0,
                        "mtime": 0,  # Would need date parsing
                    })
            return entries

    async def get_tree(self, root: str, max_depth: int = 3, current_depth: int = 0) -> Dict[str, Any]:
        """Build directory tree recursively."""
        name = root.split("/")[-1] or root
        node: Dict[str, Any] = {"name": name, "path": root}

        if current_depth >= max_depth:
            return node

        try:
            entries = await self.list_dir(root)
            if not entries:
                return node

            # Separate dirs and files
            dirs = [e for e in entries if e["is_dir"]]
            files = [e for e in entries if not e["is_dir"]]

            children = []

            # Add directories recursively
            for d in dirs[:20]:  # Limit to avoid huge trees
                child = await self.get_tree(d["path"], max_depth, current_depth + 1)
                children.append(child)

            # Add files (no recursion)
            for f in files[:50]:  # Limit files per directory
                children.append({
                    "name": f["name"],
                    "path": f["path"],
                    "is_dir": False,
                })

            if children:
                node["children"] = children

        except Exception as e:
            logger.warning(f"Tree build failed at {root}: {e}")

        return node

    @property
    def is_authenticated(self) -> bool:
        """Check if connection is authenticated and alive."""
        return self._authenticated and self.client is not None


class SSHManager:
    """Connection pool manager for SSH connections."""

    def __init__(self):
        self._connections: Dict[str, SSHConnection] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, workspace_id: str) -> asyncio.Lock:
        if workspace_id not in self._locks:
            self._locks[workspace_id] = asyncio.Lock()
        return self._locks[workspace_id]

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
        """
        Get existing connection or create new one.
        CRITICAL: If credentials differ from cached connection, create new one.
        """
        existing = self._connections.get(workspace_id)

        # If existing connection has different credentials, close it
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
                logger.info(f"Credentials changed for {workspace_id}, closing old connection")
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
        """Close and remove connection for a workspace."""
        conn = self._connections.pop(workspace_id, None)
        if conn:
            await conn.close()
            logger.info(f"Closed SSH connection for {workspace_id}")

    async def close_all(self):
        """Close all connections."""
        for wid in list(self._connections.keys()):
            await self.close(wid)
        logger.info("All SSH connections closed")


# Singleton instance
ssh_manager = SSHManager()