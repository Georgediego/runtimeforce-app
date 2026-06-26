"""
Workspaces API router with per-user data isolation and terminal execution support.
"""
import os
import uuid
import time
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.api.schemas import WorkspaceCreatePayload
from app.memory.store import store
from app.core.workspace.manager import workspace_manager
from app.core.crypto import encrypt, decrypt
from app.core.auth import get_current_user, require_authenticated_user

logger = logging.getLogger("ai_runtime.api.workspaces")
router = APIRouter(prefix="/api/v1", tags=["workspaces"])

_tree_cache: dict = {}
TREE_CACHE_TTL = 0


# ─── СТАТИЧНЫЕ МАРШРУТЫ (Должны быть строго ВЫШЕ параметрических) ───

@router.get("/workspaces/active")
async def get_active_workspace(user_id: str = Depends(get_current_user)):
    ws = store.get_active_workspace(user_id=user_id)
    if not ws:
        return {"active": None}
    ws_copy = ws.copy()
    ws_copy.pop("password_enc", None)
    ws_copy.pop("key_id", None)
    ws_copy.pop("user_id", None)
    return {"active": ws_copy}


@router.get("/workspaces/tree")
async def get_tree(user_id: str = Depends(require_authenticated_user)):
    ws = store.get_active_workspace(user_id=user_id)
    if not ws:
        raise HTTPException(404, "No active workspace")

    wid = ws["id"]
    cache_key = f"{user_id}:{wid}"
    now = time.time()
    cached = _tree_cache.get(cache_key)

    if cached and (now - cached["ts"]) < TREE_CACHE_TTL:
        return {"tree": cached["tree"], "cached": True}

    try:
        tree = await workspace_manager.get_tree(user_id=user_id)
        _tree_cache[cache_key] = {"tree": tree, "ts": now}
        return {"tree": tree, "cached": False}
    except Exception as e:
        logger.error(f"Failed to fetch live tree: {e}")
        if cached:
            return {"tree": cached["tree"], "cached": True, "fallback": True}
        return {
            "tree": {
                "name": ws.get("name", "Root"),
                "path": ws.get("path", "/"),
                "is_dir": True,
                "children": [],
            },
            "cached": False,
            "empty": True,
        }


@router.get("/workspaces/tree/children")
async def get_tree_children(path: str, user_id: str = Depends(require_authenticated_user)):
    try:
        res = await workspace_manager.get_tree_children(path, user_id=user_id)
        return res
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/workspaces/file")
async def read_file(path: str, user_id: str = Depends(require_authenticated_user)):
    try:
        content = await workspace_manager.read_file(path, user_id=user_id)
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── ДИНАМИЧЕСКИЕ И БАЗОВЫЕ МАРШРУТЫ (Ниже статичных) ───

@router.get("/workspaces")
async def list_workspaces(user_id: str = Depends(get_current_user)):
    if user_id == "anonymous":
        return {"workspaces": []}
    ws = store.get_all_workspaces(user_id=user_id)
    for w in ws:
        w.pop("password_enc", None)
        w.pop("key_id", None)
        w.pop("user_id", None)
    return {"workspaces": ws}


@router.post("/workspaces")
async def create_workspace(
    payload: WorkspaceCreatePayload,
    user_id: str = Depends(require_authenticated_user),
):
    wid = str(uuid.uuid4())

    if payload.type == "ssh" and (not payload.host or not payload.username):
        raise HTTPException(400, "SSH requires host+username")

    pw_enc = encrypt(payload.password) if payload.password else None
    kid = None

    if payload.type == "ssh" and payload.auth_type == "key" and payload.private_key:
        kid = str(uuid.uuid4())
        store.save_ssh_key(
            kid, f"{payload.name}-key",
            encrypt(payload.private_key),
            encrypt(payload.passphrase) if payload.passphrase else None,
            user_id=user_id,
        )

    success = store.create_workspace(
        workspace_id=wid,
        user_id=user_id,
        name=payload.name,
        type=payload.type,
        path=payload.path,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        auth_type=payload.auth_type,
        password_enc=pw_enc,
        key_id=kid,
        is_active=False,
    )

    if not success:
        if kid:
            store.delete_ssh_key(kid, user_id=user_id)
        raise HTTPException(500, "Failed to save workspace")

    return {
        "workspace_id": wid,
        "id": wid,
        "name": payload.name,
        "type": payload.type,
        "status": "created",
    }


@router.delete("/workspaces/{wid}")
async def delete_workspace(wid: str, user_id: str = Depends(require_authenticated_user)):
    ws = store.get_workspace(wid, user_id=user_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    if ws.get("key_id"):
        store.delete_ssh_key(ws["key_id"], user_id=user_id)
    store.delete_workspace(wid, user_id=user_id)
    return {"status": "success"}


@router.post("/workspaces/{wid}/activate")
async def activate_workspace(wid: str, user_id: str = Depends(require_authenticated_user)):
    ws = store.get_workspace(wid, user_id=user_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
        
    # ИСПРАВЛЕНО: Теперь передаем user_id в менеджер ворксейсов
    workspace_manager.set_active(wid, user_id=user_id)
    store.set_active_workspace(wid, user_id=user_id)
    
    # Сбрасываем старый кэш дерева для этого пользователя, чтобы данные обновились
    cache_key = f"{user_id}:{wid}"
    if cache_key in _tree_cache:
        _tree_cache.pop(cache_key, None)
        
    return {"status": "success", "active_id": wid}


@router.post("/workspaces/{wid}/test")
async def test_workspace(wid: str, user_id: str = Depends(require_authenticated_user)):
    ws = store.get_workspace(wid, user_id=user_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")

    if ws.get("type") != "ssh":
        return {"status": "success", "message": "Local workspace is always valid"}

    try:
        conn = await workspace_manager._get_ssh(ws)
        return {
            "status": "success",
            "message": f"Connected to {ws.get('host') or ws.get('ssh_host')}",
        }
    except Exception as e:
        return {"status": "failed", "message": str(e)}


@router.post("/workspaces/file")
async def write_file(payload: dict, user_id: str = Depends(require_authenticated_user)):
    try:
        # Передаем user_id
        await workspace_manager.write_file(payload["path"], payload["content"], user_id=user_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

# Добавить в самый конец файла app/api/workspaces.py на клиенте
@router.post("/workspaces/execute")
async def execute_command(payload: dict):
    """Выполняет произвольную терминальную команду в активном ворксейсе с CWD."""
    command = payload.get("command")
    cwd = payload.get("cwd")
    if not command:
        raise HTTPException(400, "Command is required")
    try:
        # Выполняем напрямую для локального терминала без ограничений Depends
        res = await workspace_manager.execute(command, cwd=cwd)
        return res
    except Exception as e:
        raise HTTPException(500, str(e))