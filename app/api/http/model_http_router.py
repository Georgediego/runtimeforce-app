"""
HTTP API Router for LLM models, Universal Local Engine Discovery & System Hardware Diagnostics.
"""
import os
import sys
import logging
import platform
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_llm_registry, get_llm_discovery, get_provider_keys_repo
from app.services.llm.llm_registry_service import LLMRegistryService
from app.services.llm.llm_discovery_service import LLMDiscoveryService, DiscoveryError
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.core.security.aes_crypto_service import AESCryptoService
from app.core.security.entitlements import get_plan_entitlements, require_feature, provider_feature, model_allowed_by_plan

logger = logging.getLogger("runtimeforce.api.http.models")
router = APIRouter(prefix="/api/v1/models", tags=["models"])

class LocalDiscoveryRequest(BaseModel):
    base_url: str
    provider_name: Optional[str] = None

def _get_system_hardware() -> Dict[str, Any]:
    """Detect system RAM, CPU cores and GPU capability without heavy external C-extensions."""
    total_ram_gb = 4.0
    available_ram_gb = 2.0
    cpu_cores = os.cpu_count() or 2

    # Linux RAM check via /proc/meminfo
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                mem_total_kb = 0
                mem_avail_kb = 0
                for line in lines:
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail_kb = int(line.split()[1])
                if mem_total_kb:
                    total_ram_gb = round(mem_total_kb / (1024 * 1024), 1)
                if mem_avail_kb:
                    available_ram_gb = round(mem_avail_kb / (1024 * 1024), 1)
        except Exception:
            pass

    has_gpu = False
    gpu_name = None

    # Check for NVIDIA GPU
    if os.path.exists("/proc/driver/nvidia/version") or os.system("which nvidia-smi > /dev/null 2>&1") == 0:
        has_gpu = True
        gpu_name = "NVIDIA GPU Detected"

    is_low_spec = (total_ram_gb < 12.0 and not has_gpu) or (cpu_cores <= 2 and not has_gpu)

    return {
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "cpu_cores": cpu_cores,
        "has_gpu": has_gpu,
        "gpu_name": gpu_name,
        "is_low_spec": is_low_spec,
        "os": platform.system(),
        "arch": platform.machine()
    }

@router.get("/hardware")
async def get_hardware_diagnostics(user_id: str = Depends(require_authenticated_user)):
    """Return host hardware capacity to advise users on running local models vs cloud."""
    return _get_system_hardware()

@router.post("/discover-local")
async def discover_local_models(
    request: LocalDiscoveryRequest,
    user_id: str = Depends(require_authenticated_user),
    discovery: LLMDiscoveryService = Depends(get_llm_discovery),
    keys_repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    require_feature(entitlements, "local_llms")
    try:
        provider_key_name = (request.provider_name or "local").lower().strip()
        res = await discovery.discover_local_provider(request.base_url, provider_name=provider_key_name)
        keys_repo.save_provider_key(provider_key_name, request.base_url, user_id)
        return {
            "status": "success",
            "provider_type": res["type"],
            "models": res["models"],
            "base_url": request.base_url,
            "hardware": _get_system_hardware()
        }
    except DiscoveryError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/providers/{provider_name}")
async def remove_provider(
    provider_name: str,
    user_id: str = Depends(require_authenticated_user),
    keys_repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    registry: LLMRegistryService = Depends(get_llm_registry),
):
    try:
        p_clean = provider_name.lower().strip()
        keys_repo.delete_provider_key(p_clean, user_id)
        registry.clear_provider_models(p_clean)
        return {"status": "success", "message": f"Provider '{provider_name}' removed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def list_models(
    user_id: str = Depends(require_authenticated_user),
    registry: LLMRegistryService = Depends(get_llm_registry),
    discovery: LLMDiscoveryService = Depends(get_llm_discovery),
    keys_repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    encrypted_keys = keys_repo.get_all_provider_keys(user_id)
    decrypted_keys = {}
    for p, key_enc in encrypted_keys.items():
        try:
            decrypted_keys[p] = AESCryptoService.decrypt(key_enc)
        except Exception:
            decrypted_keys[p] = key_enc

    if "ollama" not in decrypted_keys:
        decrypted_keys["ollama"] = "http://localhost:11434"
    if "lm_studio" not in decrypted_keys:
        decrypted_keys["lm_studio"] = "http://localhost:1234"

    # Do not even probe providers disabled by the current plan.
    decrypted_keys = {
        provider: key for provider, key in decrypted_keys.items()
        if _provider_enabled(entitlements, provider)
    }
    await discovery.discover_all(decrypted_keys)
    models = [
        model for model in registry.get_available_models()
        if model_allowed_by_plan(entitlements, model)
    ]

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
        "providers_with_keys": list(decrypted_keys.keys()),
        "hardware": _get_system_hardware()
    }


def _provider_enabled(entitlements: Dict[str, Any], provider: str) -> bool:
    from app.core.security.entitlements import feature_enabled
    return feature_enabled(entitlements, provider_feature(provider))
