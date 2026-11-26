import asyncio
from unittest.mock import MagicMock

from app.services.llm.llm_orchestrator_service import LLMOrchestratorService


class CooldownRotation:
    def __init__(self, status):
        self.status = status

    def is_provider_available(self, provider):
        return False

    def get_status(self):
        return self.status


def collect_events(service):
    async def run():
        return [
            event async for event in service.stream_completion(
                messages=[],
                model_id="openai/gpt-4o-mini",
                provider="openai",
            )
        ]

    return asyncio.run(run())


def test_provider_cooldown_is_a_recoverable_provider_level_error():
    service = LLMOrchestratorService(
        MagicMock(),
        MagicMock(),
        CooldownRotation({"provider_cooldowns": {"openai": 37}, "permanent_failures": []}),
    )

    events = collect_events(service)

    assert events == [{
        "status": "error",
        "error_code": "PROVIDER_COOLDOWN",
        "error": "Provider 'openai' is temporarily unavailable due to a rate limit or billing cooldown.",
        "provider": "openai",
        "permanent": False,
        "retry_after": 37,
    }]


def test_provider_auth_failure_is_not_reported_as_a_temporary_cooldown():
    service = LLMOrchestratorService(
        MagicMock(),
        MagicMock(),
        CooldownRotation({"provider_cooldowns": {}, "permanent_failures": ["openai"]}),
    )

    events = collect_events(service)

    assert events[0]["error_code"] == "PROVIDER_AUTH_FAILURE"
    assert events[0]["permanent"] is True
    assert "authentication failure" in events[0]["error"]
