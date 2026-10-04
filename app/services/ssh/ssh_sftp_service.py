"""
SFTP Operations Service over active SSH Connection.
"""
import logging
from app.services.ssh.ssh_connection_pool import SSHConnection

logger = logging.getLogger("runtimeforce.service.ssh.sftp")

class SSHSFTPService:
    @staticmethod
    async def read_file(conn: SSHConnection, filepath: str) -> str:
        if not conn._authenticated or not conn.client:
            if not await conn.connect():
                raise ConnectionError("SSH connection failed")
        try:
            sftp = conn.client.open_sftp()
            try:
                with sftp.open(filepath, "r") as f:
                    return f.read().decode("utf-8", errors="replace")
            finally:
                sftp.close()
        except Exception as e:
            logger.warning(f"SFTP read failed, falling back to cat: {e}")
            res = await conn.execute(f"cat '{filepath}'")
            if res["exit_code"] != 0:
                raise FileNotFoundError(f"Cannot read {filepath}: {res['stderr']}")
            return res["stdout"]

    @staticmethod
    async def write_file(conn: SSHConnection, filepath: str, content: str):
        if not conn._authenticated or not conn.client:
            if not await conn.connect():
                raise ConnectionError("SSH connection failed")
        dirname = "/".join(filepath.rstrip("/").split("/")[:-1])
        if dirname:
            await conn.execute(f"mkdir -p '{dirname}'")

        try:
            sftp = conn.client.open_sftp()
            try:
                with sftp.open(filepath, "w") as f:
                    f.write(content.encode("utf-8"))
            finally:
                sftp.close()
        except Exception as e:
            logger.warning(f"SFTP write failed, falling back to shell: {e}")
            safe_content = content.replace("'", "'\\''")
            res = await conn.execute(f"cat > '{filepath}' << 'ENDOFFILE'\n{safe_content}\nENDOFFILE")
            if res["exit_code"] != 0:
                raise IOError(f"Cannot write {filepath}: {res['stderr']}")
