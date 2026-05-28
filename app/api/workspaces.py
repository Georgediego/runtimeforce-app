"""
Workspaces API router.
"""
import os
import uuid
import time
import logging
from fastapi import APIRouter, HTTPException

from app.api.schemas import WorkspaceCreatePayload
from app.memory.store import store
from app.core.workspace.manager import workspace_manager
from app.core.ssh import ssh_manager
from app.core.crypto import encrypt, decrypt

logger = logging.getLogger("ai_runtime.api.workspaces")
router = APIRouter(prefix="/api/v1", tags=["workspaces"])

_tree_cache: dict = {}
TREE_CACHE_TTL = 30


# ─── СТАТИЧНЫЕ МАРШРУТЫ (Должны быть строго ВЫШЕ параметрических) ───

@router.get("/workspaces/active")
async def get_active_workspace():
    ws = workspace_manager.get_active()
    if not ws:
        return {"active": None}
    ws_copy = ws.copy()
    ws_copy.pop("password_enc", None)
    ws_copy.pop("key_id", None)
    return {"active": ws_copy}


@router.get("/workspaces/tree")
async def get_tree():
    ws = workspace_manager.get_active()
    if not ws:
        raise HTTPException(404, "No active workspace")
    wid = ws["id"]
    now = time.time()
    cached = _tree_cache.get(wid)
    if cached and (now - cached["ts"]) < TREE_CACHE_TTL:
        return {"tree": cached["tree"], "cached": True}
    try:
        tree = await workspace_manager.get_tree()
        _tree_cache[wid] = {"tree": tree, "ts": now}
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
                "children": []
            }, 
            "cached": False, 
            "empty": True
        }


@router.get("/workspaces/tree/children")
async def get_tree_children(path: str):
    try:
        res = await workspace_manager.get_tree_children(path)
        return res
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/workspaces/file")
async def read_file(path: str):
    try:
        content = await workspace_manager.read_file(path)
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── ДИНАМИЧЕСКИЕ И БАЗОВЫЕ МАРШРУТЫ (Ниже статичных) ───

@router.get("/workspaces")
async def list_workspaces():
    ws = store.get_all_workspaces()
    for w in ws:
        w.pop("password_enc", None)
        w.pop("key_id", None)
    return {"workspaces": ws}


@router.post("/workspaces")
async def create_workspace(payload: WorkspaceCreatePayload):
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
            encrypt(payload.passphrase) if payload.passphrase else None
        )
    ws = {
        "id": wid,
        "name": payload.name,
        "type": payload.type,
        "path": payload.path,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "password_enc": pw_enc,
        "key_id": kid,
        "is_active": False
    }
    store.save_workspace(ws)
    return ws


@router.delete("/workspaces/{wid}")
async def delete_workspace(wid: str):
    ws = store.get_workspace(wid)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    store.delete_workspace(wid)
    return {"status": "success"}


@router.post("/workspaces/{wid}/activate")
async def activate_workspace(wid: str):
    ws = store.get_workspace(wid)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    workspace_manager.set_active(wid)
    return {"status": "success", "active_id": wid}


@router.post("/workspaces/{wid}/test")
async def test_workspace(wid: str):
    ws = store.get_workspace(wid)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    if ws.get("type") != "ssh":
        return {"status": "success", "message": "Local workspace is always valid"}
    
    current_active = workspace_manager.get_active()
    try:
        # Вызов _get_ssh сам правильно дешифрует ключ в str и авторизуется
        conn = await workspace_manager._get_ssh(ws)
        
        if current_active:
            store.set_active_workspace(current_active["id"])
            
        return {"status": "success", "message": f"Connected to {ws.get('host') or ws.get('ssh_host')}"}
    except Exception as e:
        return {"status": "failed", "message": str(e)}

@router.post("/workspaces/file")
async def write_file(payload: dict):
    try:
        await workspace_manager.write_file(payload["path"], payload["content"])
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))
