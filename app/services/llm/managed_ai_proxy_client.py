"""Client for the server-authoritative Managed AI streaming endpoint."""
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger("runtimeforce.service.llm.managed_proxy")
UPSTREAM_FAILURE_REASONS = {
    "billing_or_quota",
    "context_limit",
    "empty_response",
    "model_not_found",
    "provider_auth",
    "provider_error",
    "provider_unavailable",
    "rate_limit",
}


class ManagedAIProxyClient:
    def __init__(self, base_url: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = (base_url or os.getenv("SAAS_URL", "https://runtimeforce.dev")).rstrip("/")
        self.transport = transport

    async def stream_completion(
        self,
        token: str,
        model: str,
        strategy: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not token:
            yield {"status": "error", "error_code": "MANAGED_AI_AUTH_REQUIRED", "error": "Managed AI requires an authenticated RuntimeForce account."}
            return

        payload = {
            "model": model or "auto",
            "strategy": strategy or "auto",
            "messages": messages,
            "tools": tools or None,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        timeout = httpx.Timeout(120.0, connect=10.0, write=15.0, pool=10.0)
        upstream_failures = []

        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/v1/chat/stream",
                    headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        detail = "Managed AI request was rejected."
                        try:
                            decoded = json.loads(body)
                            detail = str(decoded.get("detail") or detail)
                        except (json.JSONDecodeError, AttributeError):
                            pass
                        yield {
                            "status": "error",
                            "error_code": "MANAGED_AI_REJECTED",
                            "error": detail[:300],
                            "http_status": response.status_code,
                        }
                        return

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        event_data = line[5:].strip()
                        if not event_data or event_data == "[DONE]":
                            continue
                        try:
                            event = json.loads(event_data)
                        except json.JSONDecodeError:
                            logger.warning("Ignoring malformed Managed AI event")
                            continue

                        event_status = event.get("status")
                        if event_status == "fallback":
                            failure_type = event.get("error")
                            if (
                                isinstance(failure_type, str)
                                and failure_type
                                and failure_type.replace("_", "").isalnum()
                            ):
                                provider = event.get("provider")
                                provider = (
                                    provider[:64]
                                    if isinstance(provider, str)
                                    and provider
                                    and all(char.isascii() and (char.isalnum() or char in "._-") for char in provider)
                                    else ""
                                )
                                reason = event.get("reason")
                                reason = reason if isinstance(reason, str) and reason in UPSTREAM_FAILURE_REASONS else ""
                                failure_summary = " ".join(part for part in (
                                    f"{provider}:" if provider else "",
                                    failure_type[:64],
                                    f"({reason})" if reason else "",
                                ) if part)
                                upstream_failures.append(failure_summary)
                                logger.warning("Managed AI upstream model failed (%s)", failure_summary)
                            yield {
                                "status": "phase",
                                "label": (
                                    "Configured model unavailable; no other server model is available."
                                    if event.get("fallback_count") == 0
                                    else "Configured model unavailable; trying the next server model..."
                                ),
                                "role": "Router",
                            }
                        elif event_status == "failed":
                            detail = str(event.get("error") or "All server-configured models failed.")[:300]
                            if upstream_failures:
                                details = ", ".join(dict.fromkeys(upstream_failures))
                                detail = f"{detail} (upstream failures: {details})"
                            yield {
                                "status": "error",
                                "error_code": "MANAGED_AI_FAILED",
                                "error": detail,
                            }
                            return
                        else:
                            yield event
                        if event_status == "done":
                            return
        except httpx.TimeoutException:
            yield {
                "status": "error",
                "error_code": "MANAGED_AI_TIMEOUT",
                "error": "Managed AI server did not respond before the timeout.",
                "retry_after": 30,
            }
        except httpx.HTTPError as exc:
            logger.warning("Managed AI server request failed (%s)", type(exc).__name__)
            yield {
                "status": "error",
                "error_code": "MANAGED_AI_UNAVAILABLE",
                "error": "Managed AI server is temporarily unavailable.",
                "retry_after": 30,
            }
