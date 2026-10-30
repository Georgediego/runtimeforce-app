import pytest

from app.services.agent.agent_loop_coordinator import AgentLoopCoordinator
from app.services.llm.llm_orchestrator_service import LLMOrchestratorService
from app.services.llm.llm_rotation_service import LLMRotationService
from app.services.workspace.workspace_local_driver import WorkspaceLocalDriver


class _Cursor:
    def execute(self, _query):
        return None

    def fetchone(self):
        return {"cnt": 0}


class _Connection:
    def cursor(self):
        return _Cursor()


class _ProviderKeys:
    db = type("_DB", (), {"get_connection": staticmethod(lambda: _Connection())})()

    def get_all_selected_models(self, _user_id):
        return {}

    def get_all_provider_keys(self, _user_id):
        return {}


class _LocalProviderKeys(_ProviderKeys):
    def get_all_provider_keys(self, _user_id):
        return {"gemini": "test-local-key"}


class _NoLocalRoute:
    def build_route(self, **_kwargs):
        raise ValueError("No enabled local models")


class _LocalRoute:
    def build_route(self, **_kwargs):
        return ["gemini/gemini-2.5-flash"]


class _RoleRouter:
    async def classify_and_route(self, **_kwargs):
        return {"role": "Engineer", "mode": "MANUAL"}


class _ManagedOrchestrator:
    def __init__(self):
        self.calls = []

    async def stream_completion(self, **kwargs):
        self.calls.append(kwargs)
        yield {"status": "streaming", "content": "Managed Studio answer"}
        yield {"status": "done"}


class _PartialFailureOrchestrator(_ManagedOrchestrator):
    async def stream_completion(self, **kwargs):
        self.calls.append(kwargs)
        yield {"status": "streaming", "content": "partial answer"}
        yield {"status": "error", "error_code": "MANAGED_AI_FAILED", "error": "provider disconnected"}


class _ManagedAuthFailureOrchestrator(_ManagedOrchestrator):
    async def stream_completion(self, **kwargs):
        self.calls.append(kwargs)
        yield {
            "status": "error",
            "error_code": "MANAGED_AI_FAILED",
            "error": "All server models failed (upstream failures: openai: AuthenticationError (provider_auth))",
        }


def test_auto_managed_strategy_uses_code_intent_in_latest_user_message():
    strategy = LLMOrchestratorService._managed_strategy(
        "auto",
        [
            {"role": "system", "content": "You can write code and inspect the repository."},
            {"role": "user", "content": "Исправь баг в Python функции"},
        ],
    )
    assert strategy == "code"


def test_auto_managed_strategy_ignores_system_prompt_for_task_classification():
    strategy = LLMOrchestratorService._managed_strategy(
        "auto",
        [
            {"role": "system", "content": "You can write code and inspect the repository."},
            {"role": "user", "content": "Explain the history of the Roman Empire"},
        ],
    )
    assert strategy == "auto"


def test_auto_managed_strategy_detects_analytics_tasks():
    strategy = LLMOrchestratorService._managed_strategy(
        "auto", [{"role": "user", "content": "Сделай анализ данных и сравни метрики"}]
    )
    assert strategy == "analytics"


@pytest.mark.asyncio
async def test_studio_manual_auto_uses_managed_server_when_no_local_keys(tmp_path):
    orchestrator = _ManagedOrchestrator()
    coordinator = AgentLoopCoordinator(
        orchestrator_service=orchestrator,
        provider_keys_repo=_ProviderKeys(),
        role_router=_RoleRouter(),
        llm_router=_NoLocalRoute(),
    )
    events = [event async for event in coordinator.run_agent_loop(
        session_id="studio-managed-route",
        messages=[{"role": "user", "content": "Review this Python change"}],
        driver=WorkspaceLocalDriver(root_path=str(tmp_path)),
        strategy="MANUAL",
        plan="studio",
        user_id="studio-user",
        managed_ai_token="server-issued-test-token",
    )]

    assert any(event.get("status") == "streaming" and event.get("content") == "Managed Studio answer" for event in events)
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["provider"] == "runtimeforce-managed"
    assert orchestrator.calls[0]["model_id"] == "runtimeforce-managed/auto"
    assert orchestrator.calls[0]["managed_ai_token"] == "server-issued-test-token"


@pytest.mark.asyncio
async def test_managed_route_does_not_trust_stale_local_free_plan_claim(tmp_path):
    orchestrator = _ManagedOrchestrator()
    coordinator = AgentLoopCoordinator(
        orchestrator_service=orchestrator,
        provider_keys_repo=_ProviderKeys(),
        role_router=_RoleRouter(),
        llm_router=_NoLocalRoute(),
    )

    events = [event async for event in coordinator.run_agent_loop(
        session_id="studio-stale-local-plan-claim",
        messages=[{"role": "user", "content": "Check my Managed AI route"}],
        driver=WorkspaceLocalDriver(root_path=str(tmp_path)),
        strategy="AUTO",
        plan="free",  # The server, not this unsigned local claim, decides entitlement.
        user_id="studio-user",
        managed_ai_token="server-issued-test-token",
    )]

    assert any(event.get("status") == "streaming" for event in events)
    assert orchestrator.calls[0]["provider"] == "runtimeforce-managed"


@pytest.mark.asyncio
async def test_studio_auto_prefers_managed_server_before_local_byok(tmp_path):
    orchestrator = _ManagedOrchestrator()
    coordinator = AgentLoopCoordinator(
        orchestrator_service=orchestrator,
        provider_keys_repo=_LocalProviderKeys(),
        role_router=_RoleRouter(),
        llm_router=_LocalRoute(),
    )
    events = [event async for event in coordinator.run_agent_loop(
        session_id="studio-managed-priority",
        messages=[{"role": "user", "content": "Implement this Python feature"}],
        driver=WorkspaceLocalDriver(root_path=str(tmp_path)),
        strategy="AUTO",
        plan="studio",
        user_id="studio-user",
        managed_ai_token="server-issued-test-token",
    )]

    assert any(event.get("status") == "streaming" for event in events)
    assert orchestrator.calls[0]["provider"] == "runtimeforce-managed"
    assert orchestrator.calls[0]["model_id"] == "runtimeforce-managed/auto"


@pytest.mark.asyncio
async def test_explicit_managed_catalog_model_stays_locked_to_server(tmp_path):
    orchestrator = _ManagedOrchestrator()
    coordinator = AgentLoopCoordinator(
        orchestrator_service=orchestrator,
        provider_keys_repo=_ProviderKeys(),
        role_router=_RoleRouter(),
        llm_router=_NoLocalRoute(),
    )
    events = [event async for event in coordinator.run_agent_loop(
        session_id="studio-managed-lock",
        messages=[{"role": "user", "content": "Review this change"}],
        driver=WorkspaceLocalDriver(root_path=str(tmp_path)),
        strategy="MANUAL",
        model_lock="runtimeforce-managed/openai/gpt-4o-mini",
        plan="studio",
        user_id="studio-user",
        managed_ai_token="server-issued-test-token",
    )]

    assert any(event.get("status") == "streaming" for event in events)
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["provider"] == "runtimeforce-managed"
    assert orchestrator.calls[0]["model_id"] == "runtimeforce-managed/openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_managed_stream_failure_after_output_does_not_mix_fallback_answer(tmp_path):
    orchestrator = _PartialFailureOrchestrator()
    coordinator = AgentLoopCoordinator(
        orchestrator_service=orchestrator,
        provider_keys_repo=_LocalProviderKeys(),
        role_router=_RoleRouter(),
        llm_router=_LocalRoute(),
    )
    events = [event async for event in coordinator.run_agent_loop(
        session_id="studio-partial-stream-failure",
        messages=[{"role": "user", "content": "Implement this Python feature"}],
        driver=WorkspaceLocalDriver(root_path=str(tmp_path)),
        strategy="AUTO",
        plan="studio",
        user_id="studio-user",
        managed_ai_token="server-issued-test-token",
    )]

    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["provider"] == "runtimeforce-managed"
    assert any(event.get("status") == "error" and event.get("error_code") == "PARTIAL_RESPONSE_FAILURE" for event in events)


@pytest.mark.asyncio
async def test_managed_upstream_auth_error_does_not_permanently_disable_proxy(tmp_path):
    orchestrator = _ManagedAuthFailureOrchestrator()
    rotation = LLMRotationService()
    coordinator = AgentLoopCoordinator(
        orchestrator_service=orchestrator,
        provider_keys_repo=_ProviderKeys(),
        role_router=_RoleRouter(),
        llm_router=_NoLocalRoute(),
        rotation_service=rotation,
    )
    events = [event async for event in coordinator.run_agent_loop(
        session_id="studio-managed-upstream-auth",
        messages=[{"role": "user", "content": "Ответь только ОК"}],
        driver=WorkspaceLocalDriver(root_path=str(tmp_path)),
        strategy="MANUAL",
        plan="studio",
        user_id="studio-user",
        managed_ai_token="server-issued-test-token",
    )]

    assert any(event.get("status") == "error" and "openai" in event.get("error", "") for event in events)
    assert orchestrator.calls[0]["provider"] == "runtimeforce-managed"
    assert rotation.is_provider_available("runtimeforce-managed")
    assert "runtimeforce-managed" not in rotation.get_status()["permanent_failures"]
