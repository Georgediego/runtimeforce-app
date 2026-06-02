"""
Unified workspace abstraction over local filesystem and SSH.
"""
import os
import logging
import asyncio
import base64
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from app.memory.store import store
from app.core.ssh import ssh_manager
from app.core.crypto import decrypt
from app.core.git.operations import GitOps

logger = logging.getLogger("ai_runtime.workspace")

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    ".pytest_cache", "staticfiles", "media", ".cache",
}


class WorkspaceManager:
    def __init__(self):
        self._active_workspace_id: Optional[str] = None
        self._git_ops: Optional[GitOps] = None

    @property
    def git(self) -> GitOps:
        if self._git_ops is None:
            self._git_ops = GitOps(self)
        return self._git_ops

    def get_active(self, user_id: str = "anonymous") -> Optional[Dict[str, Any]]:
        if self._active_workspace_id:
            ws = store.get_workspace(self._active_workspace_id, user_id=user_id)
            if ws:
                return ws
        active = store.get_active_workspace(user_id=user_id)
        if active:
            self._active_workspace_id = active["id"]
            return active
            
        # УЛЬТИМАТИВНЫЙ ФОЛБЭК НА УРОВНЕ МЕНЕДЖЕРА:
        # Если активный воркспейс вообще не определен (например, при вызове инструментов ИИ из фонового цикла),
        # берем первый попавшийся из списка всех доступных
        all_ws = store.get_all_workspaces(user_id=user_id)
        if all_ws:
            self._active_workspace_id = all_ws[0]["id"]
            return all_ws[0]
            
        return None

    def set_active(self, workspace_id: str):
        store.set_active_workspace(workspace_id)
        self._active_workspace_id = workspace_id

    def _is_ssh(self, ws: Dict[str, Any]) -> bool:
        return ws.get("type") == "ssh" or bool(ws.get("ssh_host")) or bool(ws.get("host"))

    async def _get_ssh(self, ws: Dict[str, Any]):
        pw = None
        if ws.get("password_enc"):
            try:
                pw = decrypt(ws["password_enc"])
            except Exception as e:
                logger.error(f"Password decrypt failed: {e}")

        pk, pp = None, None
        if ws.get("key_id"):
            try:
                # Передаем user_id для выборки изолированного ключа
                kr = store.get_ssh_key(ws["key_id"], user_id=ws.get("user_id"))
                if kr:
                    raw_pk = kr.get("private_key_enc") or kr.get("key_enc")
                    if raw_pk:
                        dec_pk = decrypt(raw_pk)
                        if isinstance(dec_pk, bytes):
                            dec_pk = dec_pk.decode("utf-8")
                        pk = dec_pk

                    raw_pp = kr.get("passphrase_enc") or kr.get("pass_enc")
                    if raw_pp:
                        dec_pp = decrypt(raw_pp)
                        if isinstance(dec_pp, bytes):
                            dec_pp = dec_pp.decode("utf-8")
                        pp = dec_pp
            except Exception as e:
                logger.error(f"Key decrypt failed: {e}")

        existing = ssh_manager._connections.get(ws["id"])
        if existing and not getattr(existing, "_authenticated", False):
            await ssh_manager.close(ws["id"])

        conn = ssh_manager.get_or_create(
            workspace_id=ws["id"],
            host=ws.get("host") or ws.get("ssh_host"),
            port=ws.get("port") or ws.get("ssh_port", 22),
            username=ws.get("username") or ws.get("ssh_user"),
            password=pw,
            private_key=pk,
            passphrase=pp,
        )

        if not getattr(conn, "_authenticated", False):
            await conn.connect()
            conn._authenticated = True

        return conn

    async def execute(self, cmd: str, cwd: Optional[str] = None, timeout: float = 30.0, user_id: str = "anonymous") -> Dict[str, Any]:
        ws = self.get_active(user_id=user_id)
        if not ws:
            return {"exit_code": 1, "stdout": "", "stderr": "No active workspace"}

        if cwd:
            cmd = f"cd '{cwd}' && {cmd}"

        if self._is_ssh(ws):
            try:
                conn = await self._get_ssh(ws)
                result = await conn.execute(cmd)
                if isinstance(result, dict):
                    return result
                return {"exit_code": 0, "stdout": result or "", "stderr": ""}
            except Exception as e:
                logger.error(f"SSH execute failed: {e}")
                return {"exit_code": 1, "stdout": "", "stderr": str(e)}
        else:
            root = cwd or ws.get("path") or os.getcwd()
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd, cwd=root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return {
                    "exit_code": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                }
            except asyncio.TimeoutError:
                return {"exit_code": 1, "stdout": "", "stderr": "Timeout"}
            except Exception as e:
                return {"exit_code": 1, "stdout": "", "stderr": str(e)}

    async def get_tree(self, max_depth: int = 3, user_id: str = "anonymous") -> Dict[str, Any]:
        ws = self.get_active(user_id=user_id)
        if not ws:
            raise HTTPException(status_code=404, detail="No active workspace")

        root = ws.get("path") or "/"
        root_name = os.path.basename(root.rstrip("/")) or root

        if self._is_ssh(ws):
            conn = await self._get_ssh(ws)
            node = {"name": root_name, "path": root, "type": "directory", "is_dir": True, "children": []}
            try:
                cmd = f"ls -1Ap '{root}' 2>/dev/null"
                output = await conn.execute(cmd)
                output_text = output.get("stdout", "") if isinstance(output, dict) else (output or "")
                if output_text:
                    for line in output_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        is_dir = line.endswith('/')
                        name = line.rstrip('/')

                        if name.startswith('.') or name in SKIP_DIRS:
                            continue

                        child_path = os.path.join(root, name).replace("\\", "/")
                        child = {
                            "name": name,
                            "path": child_path,
                            "is_dir": is_dir,
                            "type": "directory" if is_dir else "file"
                        }
                        if is_dir:
                            child["children"] = []
                        node["children"].append(child)
                return node
            except Exception as e:
                logger.error(f"SSH tree failed at {root}: {e}")
                return node
        else:
            return self._build_local_tree(root, max_depth=max_depth)

    async def get_tree_children(self, path: str, user_id: str = "anonymous") -> Dict[str, Any]:
        ws = self.get_active(user_id=user_id)
        if not ws:
            raise HTTPException(status_code=404, detail="No active workspace")

        root = ws.get("path") or "/"
        if not path.startswith(root):
            raise HTTPException(status_code=403, detail="Path outside workspace")

        if self._is_ssh(ws):
            conn = await self._get_ssh(ws)
            children = []
            try:
                cmd = f"ls -1Ap '{path}' 2>/dev/null"
                output = await conn.execute(cmd)
                output_text = output.get("stdout", "") if isinstance(output, dict) else (output or "")
                if output_text:
                    for line in output_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        is_dir = line.endswith('/')
                        name = line.rstrip('/')

                        if name.startswith('.') or name in SKIP_DIRS:
                            continue

                        children.append({
                            "name": name,
                            "path": os.path.join(path, name).replace("\\", "/"),
                            "is_dir": is_dir,
                            "type": "directory" if is_dir else "file"
                        })
            except Exception as e:
                logger.error(f"SSH list_dir failed at {path}: {e}")
            return {"path": path, "children": children}
        else:
            return self._list_local_dir(path)

    def _build_local_tree(self, root: str, max_depth: int = 3, current_depth: int = 0) -> Dict[str, Any]:
        name = os.path.basename(root) or root
        node = {"name": name, "path": root, "type": "directory", "is_dir": True}

        if current_depth >= max_depth:
            return node

        try:
            entries = []
            for entry_name in os.listdir(root):
                entry_path = os.path.join(root, entry_name)
                if entry_name.startswith('.') or entry_name in SKIP_DIRS:
                    continue
                is_dir = os.path.isdir(entry_path)
                entries.append({
                    "name": entry_name,
                    "path": entry_path,
                    "is_dir": is_dir,
                    "type": "directory" if is_dir else "file"
                })

            dirs = [e for e in entries if e["is_dir"]]
            files = [e for e in entries if not e["is_dir"]]

            children = []
            for d in dirs[:30]:
                child = self._build_local_tree(d["path"], max_depth, current_depth + 1)
                children.append(child)
            for f in files[:50]:
                children.append({"name": f["name"], "path": f["path"], "is_dir": False, "type": "file"})

            if children:
                node["children"] = children
        except PermissionError:
            pass
        except Exception as e:
            logger.warning(f"Local tree build failed at {root}: {e}")

        return node

    def _list_local_dir(self, path: str) -> Dict[str, Any]:
        children = []
        try:
            for name in os.listdir(path):
                if name.startswith('.') or name in SKIP_DIRS:
                    continue
                full_path = os.path.join(path, name)
                is_dir = os.path.isdir(full_path)
                children.append({
                    "name": name,
                    "path": full_path,
                    "is_dir": is_dir,
                    "type": "directory" if is_dir else "file"
                })
        except Exception as e:
            logger.warning(f"Local list_dir failed at {path}: {e}")
        return {"path": path, "children": children}

    async def read_file(self, path: str, user_id: str = "anonymous") -> str:
        ws = self.get_active(user_id=user_id)
        if not ws:
            raise HTTPException(status_code=404, detail="No active workspace")
        if self._is_ssh(ws):
            conn = await self._get_ssh(ws)
            result = await conn.execute(f"cat '{path}'")
            return result.get("stdout", "") if isinstance(result, dict) else (result or "")
        else:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    async def write_file(self, path: str, content: str, user_id: str = "anonymous") -> bool:
        ws = self.get_active(user_id=user_id)
        if not ws:
            raise HTTPException(status_code=404, detail="No active workspace")
        if self._is_ssh(ws):
            conn = await self._get_ssh(ws)
            b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            await conn.execute(f"echo '{b64_content}' | base64 -d > {path}")
            return True
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True

    async def grep(self, query: str, file_pattern: str = "**/*", user_id: str = "anonymous") -> Dict[str, Any]:
        ws = self.get_active(user_id=user_id)
        if not ws:
            return {"error": "No active workspace", "matches": [], "count": 0}

        root = ws.get("path") or os.getcwd()
        safe_query = query.replace("'", "'\\''")
        cmd = f"grep -rn --include='{file_pattern}' '{safe_query}' '{root}' 2>/dev/null | head -100"

        if self._is_ssh(ws):
            try:
                conn = await self._get_ssh(ws)
                result = await conn.execute(cmd)
                output = result.get("stdout", "") if isinstance(result, dict) else (result or "")
                matches = self._parse_grep_output(output, root)
                return {"matches": matches, "count": len(matches), "query": query}
            except Exception as e:
                return {"error": str(e), "matches": [], "count": 0}
        else:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd, cwd=root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                matches = self._parse_grep_output(stdout.decode("utf-8", errors="replace"), root)
                return {"matches": matches, "count": len(matches), "query": query}
            except Exception as e:
                return {"error": str(e), "matches": [], "count": 0}

    def _parse_grep_output(self, output: str, root: str) -> List[Dict[str, str]]:
        matches = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path, line_num, content = parts[0], parts[1], parts[2].strip()
                matches.append({
                    "file": file_path.replace(root, "").lstrip("/"),
                    "line": line_num,
                    "content": content[:200]
                })
        return matches[:100]

    async def scan_files(self, pattern: str = "**/*", user_id: str = "anonymous") -> Dict[str, Any]:
        ws = self.get_active(user_id=user_id)
        if not ws:
            return {"error": "No active workspace", "files": [], "count": 0}

        root = ws.get("path") or os.getcwd()
        cmd = f"find '{root}' -type f -path '{pattern}' 2>/dev/null | head -300"

        if self._is_ssh(ws):
            try:
                conn = await self._get_ssh(ws)
                result = await conn.execute(cmd)
                output = result.get("stdout", "") if isinstance(result, dict) else (result or "")
                files = [f.replace(root, "").lstrip("/") for f in output.splitlines() if f.strip()]
                return {"files": files, "count": len(files), "pattern": pattern}
            except Exception as e:
                return {"error": str(e), "files": [], "count": 0}
        else:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd, cwd=root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                files = [f.replace(root, "").lstrip("/") for f in stdout.decode("utf-8", errors="replace").splitlines() if f.strip()]
                return {"files": files, "count": len(files), "pattern": pattern}
            except Exception as e:
                return {"error": str(e), "files": [], "count": 0}

    async def apply_patch(self, filepath: str, patch_content: str, user_id: str = "anonymous") -> Dict[str, Any]:
        try:
            current = await self.read_file(filepath, user_id=user_id)
            blocks = patch_content.split("<<<<<<< SEARCH")
            result = current
            applied_count = 0

            for block in blocks[1:]:
                if "=======" not in block or ">>>>>>> REPLACE" not in block:
                    continue
                search_part, replace_part = block.split("=======", 1)
                replace_part = replace_part.split(">>>>>>> REPLACE", 1)[0]

                search_text = search_part.strip("\n")
                replace_text = replace_part.strip("\n")

                if search_text in result:
                    result = result.replace(search_text, replace_text, 1)
                    applied_count += 1
                else:
                    return {
                        "success": False,
                        "error": f"SEARCH block not found in {filepath}",
                        "applied": applied_count
                    }

            if applied_count == 0:
                return {"success": False, "error": "No valid SEARCH/REPLACE blocks found", "applied": 0}

            await self.write_file(filepath, result, user_id=user_id)
            return {
                "success": True,
                "message": f"Applied {applied_count} block(s) to {filepath}",
                "applied": applied_count
            }
        except Exception as e:
            return {"success": False, "error": str(e), "applied": 0}


workspace_manager = WorkspaceManager()