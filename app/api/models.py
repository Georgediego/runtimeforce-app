"""
Models API router.
Endpoint: GET /api/v1/models

Returns discovered models from providers that have valid API keys.
Models are discovered dynamically via provider APIs (no hardcoded list).
"""
import logging
from fastapi import APIRouter

from app.core.llm import orchestrator, model_registry

logger = logging.getLogger("ai_runtime.api.models")
router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/models")
async def list_models():
    """
    Returns all discovered models grouped by provider.
    Refreshes from provider APIs if cache is stale.
    """
    try:
        await model_registry.refresh_all(orchestrator.provider_keys)
    except Exception as e:
        logger.error(f"Model refresh failed: {e}")

    models = model_registry.get_available_models()
    by_provider = {}
    for m in models:
        by_provider.setdefault(m.provider, []).append({
            "id": m.id,
            "name": m.name,
            "tier": m.tier,
            "context_window": m.context_window,
            "max_output_tokens": m.max_output_tokens,
            "pricing": m.pricing,
            "capabilities": m.capabilities,
            "description": m.description,
        })

    return {
        "models": by_provider,
        "providers_with_keys": list(orchestrator.provider_keys.keys()),
        "cooldowns": list(orchestrator.cooldown_models.keys()),
    }
