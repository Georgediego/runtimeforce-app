"""
Keys API router.
Endpoint: POST /api/v1/keys/update
"""
import logging
from fastapi import APIRouter, HTTPException

from app.api.schemas import KeysUpdatePayload
from app.core.llm import orchestrator

logger = logging.getLogger("ai_runtime.api.keys")
router = APIRouter(prefix="/api/v1", tags=["keys"])


@router.post("/keys/update")
async def update_runtime_keys(payload: KeysUpdatePayload):
    """Hot-reload API keys without instance restart."""
    try:
        orchestrator.update_provider_keys(payload.keys)
        return {"status": "success", "message": "API Keys applied securely."}
    except Exception as e:
        logger.error(f"Failed to update keys: {e}")
        raise HTTPException(status_code=400, detail=str(e))
