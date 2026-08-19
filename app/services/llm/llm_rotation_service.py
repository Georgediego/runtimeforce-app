"""
LLM Rotation Service — Robust Quota Exceeded (429) & Model Fallback Engine.
"""
import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Set
from app.core.interfaces.rotation_service_interface import IRotationService
from app.core.events.event_bus import EventBus

logger = logging.getLogger("runtimeforce.service.llm.rotation")

INITIAL_RATE_LIMIT_COOLDOWN = 60
MAX_RATE_LIMIT_COOLDOWN = 300
TIMEOUT_COOLDOWN = 300
GENERIC_COOLDOWN = 180

PROVIDER_ERROR_THRESHOLD = 5
PROVIDER_DEGRADATION_SECONDS = 180

BILLING_ERROR_MARKERS = [
    "credit_balance", "insufficient_funds", "insufficient_quota",
    "payment_required", "payment required", "402", "requires more credits", "a payment method is required"
]

STRONG_RATE_LIMIT_MARKERS = [
    "rate_limit_exceeded", "tokens per minute", "requests per minute",
    "(tpm)", "(rpm)", "too large for model", "please reduce your message size",
    "429", "ratelimit", "free-models-per-day", "quota_exceeded", "quota exceeded",
    "resource_exhausted", "resourceexhausted", "quota metric", "generativelanguage.googleapis.com"
]

PERMANENT_FAILURE_MARKERS = [
    "invalid_api_key", "authentication", "unauthorized", "401", "api_key_invalid"
]

MODEL_SPECIFIC_ERROR_MARKERS = [
    "terms acceptance", "model_not_found", "does not exist", "not found",
    "badrequesterror", "invalid_argument", "unsupported_parameter", "only available through the batch api"
]

TIMEOUT_MARKERS = [
    "timeout", "timed out", "deadline", "readtimeout", "connecttimeout",
    "upstream idle", "midstreamfallbackerror", "mid_stream", "stream dropped"
]

class LLMRotationService(IRotationService):
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._model_cooldowns: Dict[str, float] = {}
        self._provider_cooldowns: Dict[str, float] = {}
        self._provider_permanent_failures: set = set()
        self._provider_error_counts: Dict[str, List[float]] = {}
        self._model_failure_streaks: Dict[str, int] = {}
        self._session_blacklisted_models: Set[str] = set()
        self._billing_blacklisted_models: Set[str] = set()
        self._event_bus = event_bus

        if self._event_bus:
            self._event_bus.subscribe("byok.key.updated", self._on_byok_key_updated)

    async def _on_byok_key_updated(self, **kwargs):
        provider = kwargs.get("provider", "").lower()
        logger.info(f"[Rotation] BYOK key updated for '{provider}'. Clearing blacklists...")
        if provider:
            to_remove = [m for m in self._billing_blacklisted_models if m.startswith(f"{provider}/")]
            for m in to_remove:
                self._billing_blacklisted_models.remove(m)
            self._provider_permanent_failures.discard(provider)
        else:
            self._billing_blacklisted_models.clear()
            self._provider_permanent_failures.clear()

    @staticmethod
    def classify_error(error_str: str) -> str:
        if not error_str:
            return "generic"
        e = error_str.lower()

        if any(marker in e for marker in STRONG_RATE_LIMIT_MARKERS):
            return "rate_limit"

        if any(marker in e for marker in MODEL_SPECIFIC_ERROR_MARKERS):
            return "model_specific"

        if "midstreamfallbackerror" in e or "mid_stream" in e or "midstream" in e or "stream dropped" in e:
            return "midstream"

        if any(marker in e for marker in BILLING_ERROR_MARKERS):
            return "billing_error"

        for marker in PERMANENT_FAILURE_MARKERS:
            if marker in e:
                return "auth"

        for marker in TIMEOUT_MARKERS:
            if marker in e:
                return "timeout"

        return "generic"

    def report_failure(self, model_id: str, provider: str, error: str) -> Dict[str, Any]:
        err_type = self.classify_error(error)
        p = (provider or "").lower()

        if err_type in ("model_specific", "billing_error"):
            self._session_blacklisted_models.add(model_id)
            logger.warning(f"[Rotation] Model {model_id} blacklisted for this session ({err_type}). Other models of '{p}' remain active.")
            self._publish_event_safe("orchestrator.model_blacklisted", model_id=model_id, reason=err_type)
            return {"cooldown": 86400, "type": err_type}

        if err_type == "rate_limit":
            # Cooldown target model for 180s on quota limit (429) to trigger instant rotation
            duration = 180
            self._model_cooldowns[model_id] = time.time() + duration
            logger.warning(f"[Rotation] Rate limit / quota reached on {model_id}. Cooling down {duration}s to rotate.")
            self._publish_event_safe("orchestrator.rate_limited", model_id=model_id, provider=provider, cooldown=duration)
            return {"cooldown": duration, "type": "rate_limit"}

        if err_type == "midstream":
            duration = 180
            self._model_cooldowns[model_id] = time.time() + duration
            self._publish_event_safe("orchestrator.stream_dropped", model_id=model_id, provider=provider)
            return {"cooldown": duration, "type": "midstream"}

        if err_type == "auth":
            self.mark_provider_permanent_failure(provider)
            return {"cooldown": 86400, "type": "auth"}

        streak = self._model_failure_streaks.get(model_id, 0) + 1
        self._model_failure_streaks[model_id] = streak

        duration = TIMEOUT_COOLDOWN if err_type == "timeout" else GENERIC_COOLDOWN
        self._model_cooldowns[model_id] = time.time() + duration
        logger.info(f"[Rotation] Model cooldown: {model_id} for {duration}s ({err_type}, streak={streak})")

        return {"cooldown": duration, "type": err_type}

    def mark_model_failed(self, model_id: str, provider: str, error: str) -> None:
        self.report_failure(model_id, provider, error)

    def is_model_available(self, model_id: str) -> bool:
        if model_id in self._session_blacklisted_models or model_id in self._billing_blacklisted_models:
            return False

        if model_id in self._model_cooldowns:
            if time.time() < self._model_cooldowns[model_id]:
                return False
            del self._model_cooldowns[model_id]

        provider = model_id.split("/", 1)[0] if "/" in model_id else "unknown"
        if provider in self._provider_permanent_failures:
            return False
        if provider in self._provider_cooldowns:
            if time.time() < self._provider_cooldowns[provider]:
                return False
        return True

    def is_provider_available(self, provider: str) -> bool:
        p = (provider or "").lower()
        if p in self._provider_permanent_failures:
            return False
        if p in self._provider_cooldowns and time.time() < self._provider_cooldowns[p]:
            return False
        return True

    def is_provider_degraded(self, provider: str) -> bool:
        return (provider or "").lower() in self._provider_cooldowns

    def _publish_event_safe(self, event_name: str, **kwargs) -> None:
        if not self._event_bus:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(event_name, **kwargs))
        except RuntimeError:
            logger.debug(f"[Rotation] No running event loop to publish '{event_name}'")

    def mark_provider_permanent_failure(self, provider: str) -> None:
        p = (provider or "").lower()
        if p not in self._provider_permanent_failures:
            self._provider_permanent_failures.add(p)
            logger.warning(f"[Rotation] Provider '{p}' marked PERMANENTLY failed (auth)")
            self._publish_event_safe("rotation.provider_permanent_failure", provider=p)

    def mark_provider_cooldown(self, provider: str, duration: float) -> None:
        p = (provider or "").lower()
        self._provider_cooldowns[p] = time.time() + duration
        logger.info(f"[Rotation] Provider cooldown: {p} for {duration}s")

    def get_available_models(self, all_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        available = [m for m in all_models if self.is_model_available(m.get("model_id", ""))]
        by_provider: Dict[str, List[Dict[str, Any]]] = {}
        for m in available:
            p = m.get("provider", "unknown")
            by_provider.setdefault(p, []).append(m)
        providers = list(by_provider.keys())
        if len(providers) <= 1:
            return available
        result = []
        max_len = max(len(lst) for lst in by_provider.values())
        for i in range(max_len):
            for p in providers:
                if i < len(by_provider[p]):
                    result.append(by_provider[p][i])
        return result

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "model_cooldowns": {
                k: max(0, int(v - now)) for k, v in self._model_cooldowns.items() if v > now
            },
            "provider_cooldowns": {
                k: max(0, int(v - now)) for k, v in self._provider_cooldowns.items() if v > now
            },
            "permanent_failures": list(self._provider_permanent_failures),
            "blacklisted_models": list(self._session_blacklisted_models),
            "billing_blacklisted_models": list(self._billing_blacklisted_models)
        }
