"""
HTTP API Router for managing Provider API Keys, Selected Models, and Global AUTOSELECT.
"""
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.entitlements import feature_enabled, provider_feature_key
from app.container import get_provider_keys_repo, get_byok_key_service, get_llm_router, get_llm_discovery, get_license_service
from app.services.billing.license_service import LicenseService
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.services.byok.byok_key_service import ByokKeyService
from app.services.llm.llm_router_service import LLMRouterService
from app.services.llm.llm_discovery_service import LLMDiscoveryService
from app.core.security.aes_crypto_service import AESCryptoService
from app.api.schemas import KeysUpdatePayload

logger = logging.getLogger("runtimeforce.api.http.keys")
router = APIRouter(prefix="/api/v1/keys", tags=["keys"])

class SelectedModelsPayload(BaseModel):
    provider_id: str
    model_ids: List[str]

class AutoselectPayload(BaseModel):
    provider_id: str

async def _verified_entitlements(
    request: Request,
    license_service: LicenseService,
    provider: Optional[str] = None,
):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    token = token or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()
    entitlements = await license_service.get_entitlements(token)
    if not entitlements.get("valid"):
        raise HTTPException(status_code=403, detail="Account entitlements could not be verified")
    if provider is not None:
        feature_key = provider_feature_key(provider)
        if not feature_enabled(entitlements, feature_key):
            raise HTTPException(
                status_code=403,
                detail=f"Provider access requires the '{feature_key}' plan feature",
            )
    return entitlements


@router.post("/update")
async def update_keys(
    payload: KeysUpdatePayload,
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    license_service: LicenseService = Depends(get_license_service),
):
    for provider in payload.keys:
        if provider.lower() != "perplexity":
            await _verified_entitlements(request, license_service, provider)
    saved_count = 0
    for provider, plain_key in payload.keys.items():
        if provider.lower() == "perplexity":
            continue
        if plain_key and plain_key.strip():
            encrypted = AESCryptoService.encrypt(plain_key)
            repo.save_provider_key(provider, encrypted, user_id)
            saved_count += 1

    return {"status": "success", "message": f"Saved {saved_count} keys"}

@router.get("/status")
async def get_keys_status(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    license_service: LicenseService = Depends(get_license_service),
):
    entitlements = await _verified_entitlements(request, license_service)
    keys = repo.get_all_provider_keys(user_id)
    filtered = {
        p: True for p in keys.keys()
        if p.lower() != "perplexity"
        and feature_enabled(entitlements, provider_feature_key(p))
    }
    return {"providers": filtered}

@router.get("/selected-models")
async def get_selected_models(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    license_service: LicenseService = Depends(get_license_service),
):
    entitlements = await _verified_entitlements(request, license_service)
    selected = repo.get_all_selected_models(user_id)
    selected = {
        provider: models for provider, models in selected.items()
        if feature_enabled(entitlements, provider_feature_key(provider))
    }
    return {"selected_models": selected}

@router.post("/selected-models")
async def save_selected_models(
    payload: SelectedModelsPayload,
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    license_service: LicenseService = Depends(get_license_service),
):
    await _verified_entitlements(request, license_service, payload.provider_id)
    p_clean = payload.provider_id.lower().strip()
    if p_clean == "perplexity":
        return {"status": "ignored"}
    repo.save_selected_models(p_clean, payload.model_ids, user_id)
    return {"status": "success", "provider_id": p_clean, "count": len(payload.model_ids)}

@router.post("/autoselect")
async def autoselect_provider_models(
    payload: AutoselectPayload,
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    llm_router: LLMRouterService = Depends(get_llm_router),
    license_service: LicenseService = Depends(get_license_service),
):
    await _verified_entitlements(request, license_service, payload.provider_id)
    p_clean = payload.provider_id.lower().strip()
    if p_clean == "perplexity":
        raise HTTPException(400, "Perplexity provider is removed")

    autoselected = llm_router.autoselect_models_for_provider(p_clean)
    repo.save_selected_models(p_clean, autoselected, user_id)
    return {
        "status": "success",
        "provider_id": p_clean,
        "autoselected_models": autoselected,
        "count": len(autoselected)
    }

@router.post("/autoselect-all")
async def autoselect_all_providers(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    llm_router: LLMRouterService = Depends(get_llm_router),
    discovery: LLMDiscoveryService = Depends(get_llm_discovery),
    license_service: LicenseService = Depends(get_license_service),
):
    entitlements = await _verified_entitlements(request, license_service)
    encrypted_keys = repo.get_all_provider_keys(user_id)
    decrypted_keys = {}
    for p, key_enc in encrypted_keys.items():
        if p.lower() == "perplexity":
            continue
        try:
            decrypted_keys[p] = AESCryptoService.decrypt(key_enc)
        except Exception:
            decrypted_keys[p] = key_enc

    if "ollama" not in decrypted_keys:
        decrypted_keys["ollama"] = "http://localhost:11434"
    if "lm_studio" not in decrypted_keys:
        decrypted_keys["lm_studio"] = "http://localhost:1234"

    decrypted_keys = {
        provider: key for provider, key in decrypted_keys.items()
        if feature_enabled(entitlements, provider_feature_key(provider))
    }
    await discovery.discover_all(decrypted_keys)

    connected_providers = {
        p.lower() for p in decrypted_keys.keys()
        if feature_enabled(entitlements, provider_feature_key(p))
    }
    results = {}
    total_selected = 0

    for provider_id in connected_providers:
        autoselected = llm_router.autoselect_models_for_provider(provider_id)
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
