"""
Keys API router.
Endpoints: POST/GET/DELETE /api/v1/keys/*
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional

from app.api.schemas import KeysUpdatePayload
from app.core.llm import orchestrator, model_registry
from app.core.crypto import encrypt, decrypt
from app.memory.store import store

logger = logging.getLogger("ai_runtime.api.keys")
router = APIRouter(prefix="/api/v1", tags=["keys"])


class KeyStatusResponse(BaseModel):
    providers: Dict[str, bool]


@router.post("/keys/update")
async def update_runtime_keys(payload: KeysUpdatePayload):
    try:
        saved_count = 0
        # Передаем флаг force_allow в реестр моделей перед обновлением
        model_registry.force_allow = payload.force_allow

        for provider, plain_key in payload.keys.items():
            if plain_key and plain_key.strip():
                encrypted = encrypt(plain_key)
                store.save_provider_key(provider, encrypted)
                saved_count += 1
                logger.info(f"Saved encrypted key for {provider}")

        encrypted_keys = store.get_all_provider_keys()
        decrypted_keys = {}
        for provider, key_enc in encrypted_keys.items():
            try:
                decrypted_keys[provider] = decrypt(key_enc)
            except Exception as e:
                logger.warning(f"Failed to decrypt key for {provider}: {e}")

        orchestrator.set_provider_keys(decrypted_keys)
        logger.info(f"Updated {saved_count} keys, orchestrator has {len(decrypted_keys)} keys")

        # Принудительно вызываем обновление моделей с валидацией
        await model_registry.refresh_all(orchestrator.provider_keys, force=True)

        return {
            "status": "success",
            "message": f"Saved {saved_count} keys securely",
            "providers": list(decrypted_keys.keys())
        }
    except ValueError as ve:
        # Перехватываем ошибку валидации слабых моделей и отдаем как 400 Bad Request
        logger.error(f"Validation failed: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to update keys: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/keys/status", response_model=KeyStatusResponse)
async def get_keys_status():
    try:
        encrypted_keys = store.get_all_provider_keys()
        providers = {provider: True for provider in encrypted_keys.keys()}
        return {"providers": providers}
    except Exception as e:
        logger.error(f"Failed to get keys status: {e}")
        return {"providers": {}}


@router.delete("/keys/{provider}")
async def delete_provider_key(provider: str):
    try:
        store.delete_provider_key(provider)
        encrypted_keys = store.get_all_provider_keys()
        decrypted_keys = {}
        for p, key_enc in encrypted_keys.items():
            try:
                decrypted_keys[p] = decrypt(key_enc)
            except Exception as e:
                logger.warning(f"Failed to decrypt key for {p}: {e}")
        orchestrator.set_provider_keys(decrypted_keys)
        logger.info(f"Deleted key for {provider}")
        return {"status": "success", "message": f"Deleted {provider}"}
    except Exception as e:
        logger.error(f"Failed to delete key: {e}")
        raise HTTPException(status_code=400, detail=str(e))