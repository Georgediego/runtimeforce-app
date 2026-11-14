"""
HTTP API Router for managing Provider API Keys, Selected Models, and Global AUTOSELECT.
"""
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_provider_keys_repo, get_byok_key_service, get_llm_router, get_llm_discovery
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.services.byok.byok_key_service import ByokKeyService
from app.services.llm.llm_router_service import LLMRouterService
from app.services.llm.llm_discovery_service import LLMDiscoveryService
from app.core.security.aes_crypto_service import AESCryptoService
from app.core.security.entitlements import get_plan_entitlements, require_feature, provider_feature, model_allowed_by_plan
from app.container import container
from app.api.schemas import KeysUpdatePayload

logger = logging.getLogger("runtimeforce.api.http.keys")
router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


def _provider_allowed(entitlements: Dict[str, Any], provider: str) -> bool:
    from app.core.security.entitlements import feature_enabled
    return feature_enabled(entitlements, provider_feature(provider))


class SelectedModelsPayload(BaseModel):
    provider_id: str
    model_ids: List[str]

class AutoselectPayload(BaseModel):
    provider_id: str

@router.post("/update")
async def update_keys(
    payload: KeysUpdatePayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    saved_count = 0
    for provider, plain_key in payload.keys.items():
        if plain_key and plain_key.strip():
            require_feature(entitlements, provider_feature(provider))
        if provider.lower() == "perplexity":
            continue
        if plain_key and plain_key.strip():
            encrypted = AESCryptoService.encrypt(plain_key)
            repo.save_provider_key(provider, encrypted, user_id)
            saved_count += 1

    return {"status": "success", "message": f"Saved {saved_count} keys"}

@router.get("/status")
async def get_keys_status(
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    keys = repo.get_all_provider_keys(user_id)
    filtered = {
        p: True for p in keys.keys()
        if p.lower() != "perplexity" and _provider_allowed(entitlements, p)
    }
    return {"providers": filtered}

@router.get("/selected-models")
async def get_selected_models(
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    selected = repo.get_all_selected_models(user_id)
    filtered = {}
    for provider, model_ids in selected.items():
        if not _provider_allowed(entitlements, provider):
            continue
        allowed = [
            model_id for model_id in model_ids
            if (model := container.llm_registry.get_model(model_id)) is not None
            and model_allowed_by_plan(entitlements, model)
        ]
        if allowed:
            filtered[provider] = allowed
    return {"selected_models": filtered}

@router.post("/selected-models")
async def save_selected_models(
    payload: SelectedModelsPayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    p_clean = payload.provider_id.lower().strip()
    require_feature(entitlements, provider_feature(p_clean))
    for model_id in payload.model_ids:
        model = container.llm_registry.get_model(model_id)
        if model is None or not model_allowed_by_plan(entitlements, model):
            raise HTTPException(403, detail={"code": "model_not_in_plan", "model": model_id, "message": f"Model '{model_id}' is not available on this plan."})
    if p_clean == "perplexity":
        return {"status": "ignored"}
    repo.save_selected_models(p_clean, payload.model_ids, user_id)
    return {"status": "success", "provider_id": p_clean, "count": len(payload.model_ids)}

@router.post("/autoselect")
async def autoselect_provider_models(
    payload: AutoselectPayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    llm_router: LLMRouterService = Depends(get_llm_router),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements)
):
    p_clean = payload.provider_id.lower().strip()
    require_feature(entitlements, provider_feature(p_clean))
    if p_clean == "perplexity":
        raise HTTPException(400, "Perplexity provider is removed")

    autoselected = [
        model_id for model_id in llm_router.autoselect_models_for_provider(p_clean)
        if (model := container.llm_registry.get_model(model_id)) is not None
        and model_allowed_by_plan(entitlements, model)
    ]
    repo.save_selected_models(p_clean, autoselected, user_id)
    return {
        "status": "success",
        "provider_id": p_clean,
        "autoselected_models": autoselected,
        "count": len(autoselected)
    }

@router.post("/autoselect-all")
async def autoselect_all_providers(
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    llm_router: LLMRouterService = Depends(get_llm_router),
    discovery: LLMDiscoveryService = Depends(get_llm_discovery),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements)
):
    encrypted_keys = {
        provider: key for provider, key in repo.get_all_provider_keys(user_id).items()
        if _provider_allowed(entitlements, provider)
    }
    decrypted_keys = {}
    for p, key_enc in encrypted_keys.items():
        if p.lower() == "perplexity":
            continue
        try:
            decrypted_keys[p] = AESCryptoService.decrypt(key_enc)
        except Exception:
            decrypted_keys[p] = key_enc

    if _provider_allowed(entitlements, "ollama") and "ollama" not in decrypted_keys:
        decrypted_keys["ollama"] = "http://localhost:11434"
    if _provider_allowed(entitlements, "lm_studio") and "lm_studio" not in decrypted_keys:
        decrypted_keys["lm_studio"] = "http://localhost:1234"

    await discovery.discover_all(decrypted_keys)

    connected_providers = set(p.lower() for p in decrypted_keys.keys())
    results = {}
    total_selected = 0

    for provider_id in connected_providers:
        autoselected = [
            model_id for model_id in llm_router.autoselect_models_for_provider(provider_id)
            if (model := container.llm_registry.get_model(model_id)) is not None
            and model_allowed_by_plan(entitlements, model)
        ]
        if autoselected:
            repo.save_selected_models(provider_id, autoselected, user_id)
            results[provider_id] = len(autoselected)
            total_selected += len(autoselected)

    return {
        "status": "success",
        "results": results,
        "total_selected": total_selected
    }

@router.post("/reencrypt")
async def reencrypt_keys(
    user_id: str = Depends(require_authenticated_user),
    byok_service: ByokKeyService = Depends(get_byok_key_service)
):
    return byok_service.reencrypt_all_keys(user_id)

@router.delete("/{provider}")
async def delete_key(
    provider: str,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo)
):
    repo.delete_provider_key(provider.lower().strip(), user_id)
    return {"status": "success", "message": f"Deleted {provider}"}
