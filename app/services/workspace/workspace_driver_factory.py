import os
import logging
from typing import Dict, Any, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver
from app.core.interfaces.workspace_driver_factory_interface import IWorkspaceDriverFactory
from app.services.workspace.workspace_local_driver import WorkspaceLocalDriver
from app.services.workspace.workspace_ssh_driver import WorkspaceSSHDriver
from app.services.ssh.ssh_connection_pool import SSHConnectionPool
from app.core.security.aes_crypto_service import AESCryptoService

logger = logging.getLogger("runtimeforce.service.workspace.factory")

class WorkspaceDriverFactory(IWorkspaceDriverFactory):
    def __init__(self, ssh_keys_repo: Any, ssh_pool: SSHConnectionPool):
        self.ssh_keys_repo = ssh_keys_repo
        self.ssh_pool = ssh_pool

    def create_driver(self, ws: Dict[str, Any], user_id: str) -> Optional[IWorkspaceDriver]:
        ws_type = ws.get("type", "local")
        path = ws.get("path") or "~"

        if ws_type == "local":
            return WorkspaceLocalDriver(path)

        elif ws_type == "ssh":
            pw = None
            if ws.get("password_enc"):
                try:
                    pw = AESCryptoService.decrypt(ws["password_enc"])
                except Exception as e:
                    logger.error(f"Password decrypt failed: {e}")

            pk, pp = None, None
            if ws.get("key_id"):
                key_record = self.ssh_keys_repo.get_ssh_key(ws["key_id"], user_id)
                if key_record:
                    if key_record.get("private_key_enc"):
                        pk = AESCryptoService.decrypt(key_record["private_key_enc"])
                    if key_record.get("passphrase_enc"):
                        pp = AESCryptoService.decrypt(key_record["passphrase_enc"])

            conn = self.ssh_pool.get_or_create(
                workspace_id=ws["id"],
                host=ws.get("host") or ws.get("ssh_host", ""),
                port=ws.get("port", 22),
                username=ws.get("username") or ws.get("ssh_user", ""),
                password=pw,
                private_key=pk,
                passphrase=pp,
            )
            return WorkspaceSSHDriver(conn, root_path=path)

        return None
