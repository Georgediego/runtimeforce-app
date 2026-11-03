import pytest
from app.core.security.jwt_auth_service import JWTAuthService
import asyncio
from typing import Any, AsyncGenerator, Dict, List
from app.container import ApplicationContainer
from app.repository.db_connection import DatabaseConnectionManager
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.services.workspace.workspace_local_driver import WorkspaceLocalDriver
from app.services.llm.llm_registry_service import LLMRegistryService, ModelMetadata
from app.services.llm.llm_discovery_service import LLMDiscoveryService
from app.services.llm.llm_router_service import LLMRouterService
from app.services.llm.llm_rotation_service import LLMRotationService

class MockOrchestrator:
    async def stream_completion(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        provider: str,
        temperature: float = 0.2,
        user_id: str = "default_user",
        tools: Any = None,
        strategy: str = "auto"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"status": "streaming", "content": f"Response using model {model_id}"}
        yield {"status": "done"}

    async def generate_with_context(self, *args, **kwargs) -> str:
        return "Mock architectural recommendation plan."

class MockContextBuilder:
    async def build_optimal_context(
        self,
        user_prompt: str,
        session_id: str,
        user_id: str,
        project_id: str,
        max_token_budget: int = 128000,
        max_context_tokens: int = 8000
    ) -> Dict[str, Any]:
        return {"compiled_memory_context": "mock memory"}

@pytest.fixture
def temp_container(tmp_path):
    c = ApplicationContainer()
    db_path = str(tmp_path / "test_manual.db")
    db_manager = DatabaseConnectionManager(db_path=db_path)
    db_manager.init_db()
    
    provider_keys_repo = ProviderKeysDBRepository(db_manager)
    c.provider_keys_repo = provider_keys_repo
    c.agent_loop_coordinator._provider_keys_repo = provider_keys_repo
    
    c.llm_orchestrator = MockOrchestrator()
    mock_context_builder = MockContextBuilder()
    c.agent_loop_coordinator._context_builder = mock_context_builder
    if hasattr(c, "architect_agent_service"):
        c.architect_agent_service._orchestrator = c.llm_orchestrator
        c.architect_agent_service._context_builder = mock_context_builder

    return c, db_manager, tmp_path

@pytest.mark.asyncio
async def test_manual_model_ignored_and_warning(temp_container):
    c, db_manager, tmp_path = temp_container
    coordinator = c.agent_loop_coordinator
    repo = c.provider_keys_repo
    
    user_id = "user_1"
    # Seed DB with allowed model
    repo.save_selected_models("openai", ["openai/gpt-4o-mini"], user_id)
    
    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    messages = [{"role": "user", "content": "Hello"}]
    
    # 1. Client sends model not in provider_selected_models
    events = []
    async for event in coordinator.run_agent_loop(
        session_id="session_1",
        messages=messages,
        driver=driver,
        strategy="MANUAL",
        model_lock="openai/unauthorized-model",
        user_id=user_id,
        enabled_models=["openai/unauthorized-model"]
    ):
        events.append(event)
    
    warning_event = next((e for e in events if e.get("status") == "warning"), None)
    assert warning_event is not None
    assert "Manual model ignored" in warning_event.get("warning", "")

@pytest.mark.asyncio
async def test_enabled_models_missing_takes_from_db(temp_container):
    c, db_manager, tmp_path = temp_container
    coordinator = c.agent_loop_coordinator
    repo = c.provider_keys_repo
    
    user_id = "user_2"
    repo.save_selected_models("openai", ["openai/gpt-4o-mini"], user_id)
    
    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    events = []
    # enabled_models=None (missing)
    async for event in coordinator.run_agent_loop(
        session_id="session_2",
        messages=[{"role": "user", "content": "Test"}],
        driver=driver,
        strategy="AUTO",
        enabled_models=None,
        user_id=user_id
    ):
        events.append(event)
    
    assert any(e.get("status") == "done" for e in events)

@pytest.mark.asyncio
async def test_manual_with_valid_model_lock(temp_container):
    c, db_manager, tmp_path = temp_container
    coordinator = c.agent_loop_coordinator
    repo = c.provider_keys_repo
    
    user_id = "user_3"
    repo.save_selected_models("openai", ["openai/gpt-4o-mini"], user_id)
    
    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    events = []
    async for event in coordinator.run_agent_loop(
        session_id="session_3",
        messages=[{"role": "user", "content": "Test"}],
        driver=driver,
        strategy="MANUAL",
        model_lock="openai/gpt-4o-mini",
        user_id=user_id
    ):
        events.append(event)
    
    assert any(e.get("status") == "done" for e in events)

@pytest.mark.asyncio
async def test_atm_with_different_models_for_roles(temp_container):
    c, db_manager, tmp_path = temp_container
    coordinator = c.agent_loop_coordinator
    repo = c.provider_keys_repo
    
    user_id = "user_4"
    repo.save_selected_models("openai", ["openai/gpt-4o-mini", "openai/gpt-4o"], user_id)
    
    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    events = []
    async for event in coordinator.run_agent_loop(
        session_id="session_4",
        messages=[{"role": "user", "content": "Build feature"}],
        driver=driver,
        strategy="ATM",
        atm_architect_model="openai/gpt-4o",
        atm_engineer_model="openai/gpt-4o-mini",
        user_id=user_id
    ):
        events.append(event)
    
    assert any(e.get("status") == "done" for e in events)

@pytest.mark.asyncio
async def test_user_isolation_selected_models(temp_container):
    c, db_manager, tmp_path = temp_container
    coordinator = c.agent_loop_coordinator
    repo = c.provider_keys_repo
    
    user_a = "alice"
    user_b = "bob"
    
    repo.save_selected_models("openai", ["openai/gpt-4o-mini"], user_a)
    # bob has no selected models
    
    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    events = []
    # bob tries to use alice's model lock without selecting it
    async for event in coordinator.run_agent_loop(
        session_id="session_5",
        messages=[{"role": "user", "content": "Test"}],
        driver=driver,
        strategy="MANUAL",
        model_lock="openai/gpt-4o-mini",
        user_id=user_b
    ):
        events.append(event)
    
    # Should get warning because bob has no models in db
    warning_event = next((e for e in events if e.get("status") == "warning"), None)
    assert warning_event is not None

@pytest.mark.asyncio
async def test_without_manual_fields_default_behavior(temp_container):
    c, db_manager, tmp_path = temp_container
    coordinator = c.agent_loop_coordinator
    
    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    events = []
    async for event in coordinator.run_agent_loop(
        session_id="session_6",
        messages=[{"role": "user", "content": "Default test"}],
        driver=driver,
        strategy="AUTO",
        user_id="default_user"
    ):
        events.append(event)
    
    assert any(e.get("status") == "done" for e in events)

 
 
def test_openai_discovery_excludes_non_chat_and_deprecated_models():
    registry = LLMRegistryService()
    discovery = LLMDiscoveryService(registry)
    discovery._parse_openai("openai", {"data": [
        {"id": "gpt-4o"},
        {"id": "gpt-4o-transcribe-diarize"},
        {"id": "o3-mini"},
        {"id": "o3-mini-2025-01-31"},
    ]})

    model_ids = {model.id for model in registry.get_available_models(provider_filter="openai")}
    assert "openai/gpt-4o" in model_ids
    assert "openai/gpt-4o-transcribe-diarize" not in model_ids
    assert "openai/o3-mini" not in model_ids
    assert "openai/o3-mini-2025-01-31" not in model_ids


def test_openai_autoselection_does_not_match_transcription_model_substrings():
    registry = LLMRegistryService()
    for model_id in (
        "openai/gpt-4o-transcribe-diarize",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
    ):
        registry.register_model(ModelMetadata(
            id=model_id,
            provider="openai",
            name=model_id.rsplit("/", 1)[-1],
            tier="standard",
            capabilities=["chat_completion", "text", "code"],
        ))

    router = LLMRouterService(registry)
    selected = router.autoselect_models_for_provider("openai")
    assert "openai/gpt-4o" in selected
    assert "openai/gpt-4o-mini" in selected
    assert "openai/gpt-4o-transcribe-diarize" not in selected

 
 
def test_auto_route_ignores_stale_manual_model_lock():
    registry = LLMRegistryService()
    for model_id in ("openai/gpt-4o-mini", "openai/gpt-4o"):
        registry.register_model(ModelMetadata(
            id=model_id,
            provider="openai",
            name=model_id.rsplit("/", 1)[-1],
            tier="standard",
            capabilities=["chat_completion", "text", "code"],
        ))

    router = LLMRouterService(registry)
    route = router.build_route(
        strategy="AUTO",
        model_lock="openai/gpt-4o-mini",
        plan="studio",
        provider_keys={"openai": "test-key"},
        scores={},
    )

    assert set(route) == {"openai/gpt-4o-mini", "openai/gpt-4o"}


def test_manual_route_requires_an_explicit_model():
    router = LLMRouterService(LLMRegistryService())
    with pytest.raises(ValueError, match="MANUAL strategy requires a specific model"):
        router.build_route(
            strategy="MANUAL",
            model_lock=None,
            plan="studio",
            provider_keys={},
            scores={},
        )


def test_openai_no_credits_cools_down_provider_not_just_one_model():
    rotation = LLMRotationService()
    error = "litellm.RateLimitError: You have no credits remaining. Add credits to continue."

    assert rotation.classify_error(error) == "billing_error"
    rotation.report_failure("openai/gpt-4o", "openai", error)

    assert rotation.is_provider_available("openai") is False
    assert rotation.is_model_available("openai/gpt-4o-mini") is False


def test_deprecated_model_error_is_model_specific():
    rotation = LLMRotationService()
    error = "litellm.NotFoundError: The model o3-mini has been deprecated."

    assert rotation.classify_error(error) == "model_specific"
    rotation.report_failure("openai/o3-mini", "openai", error)

    assert rotation.is_model_available("openai/o3-mini") is False
    assert rotation.is_provider_available("openai") is True


@pytest.mark.asyncio
async def test_cloud_orchestrator_requires_saved_byok_key():
    from app.services.llm.llm_orchestrator_service import LLMOrchestratorService
    from app.services.llm.llm_registry_service import LLMRegistryService

    class EmptyProviderKeys:
        def get_all_provider_keys(self, user_id):
            return {}

    service = LLMOrchestratorService(
        provider_keys_repo=EmptyProviderKeys(),
        llm_registry=LLMRegistryService(),
    )
    events = [
        event async for event in service.stream_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model_id="gemini/gemini-2.5-flash",
            provider="gemini",
            user_id="test-user",
        )
    ]

    assert events
    assert events[0]["status"] == "error"
    assert events[0]["error_code"] == "MISSING_API_KEY"


def test_websocket_local_identity_uses_normalized_verified_email():
    user = {"id": "saas-uuid", "email": "  George@Example.com  "}
    assert JWTAuthService.get_local_user_id(user) == "george@example.com"


def test_local_model_timeout_allows_slow_cpu_generation():
    from app.services.llm.llm_orchestrator_service import STREAM_LOCAL_TIMEOUT
    assert STREAM_LOCAL_TIMEOUT == 900.0
