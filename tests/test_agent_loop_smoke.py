import pytest
import asyncio
from typing import Any, AsyncGenerator, Dict, List
from app.container import ApplicationContainer
from app.services.agent.agent_loop_coordinator import AgentLoopCoordinator
from app.services.agent.architect_agent_service import ArchitectAgentService
from app.services.workspace.workspace_local_driver import WorkspaceLocalDriver

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
        yield {"status": "streaming", "content": "Hello from mock orchestrator response."}
        yield {"status": "done"}

    async def generate_with_context(self, *args, **kwargs) -> str:
        return "Mock architectural recommendation plan."

class MockRoleRouter:
    async def classify_and_route(self, **kwargs) -> Dict[str, Any]:
        return {"role": "coding", "suggested_capabilities": ["code"]}

class MockRoleSelector:
    async def select_candidate_models_for_role(self, **kwargs) -> List[Dict[str, Any]]:
        return [{"model_id": "openai/gpt-4o-mini", "provider": "openai"}]

class MockCriticAgent:
    async def validate_result(self, **kwargs) -> Dict[str, Any]:
        return {"status": "ok"}

class MockContextBuilder:
    async def build_optimal_context(self, *args, **kwargs) -> Dict[str, Any]:
        return {"compiled_memory_context": "mock memory"}

@pytest.fixture
def container():
    c = ApplicationContainer()
    c.llm_orchestrator = MockOrchestrator()
    mock_context_builder = MockContextBuilder()
    
    if hasattr(c, "agent_loop_coordinator"):
        c.agent_loop_coordinator._orchestrator = c.llm_orchestrator
        c.agent_loop_coordinator._role_router = MockRoleRouter()
        c.agent_loop_coordinator._role_selector = MockRoleSelector()
        c.agent_loop_coordinator._critic_agent = MockCriticAgent()
        c.agent_loop_coordinator._context_builder = mock_context_builder

    if hasattr(c, "architect_agent_service"):
        c.architect_agent_service._orchestrator = c.llm_orchestrator
        c.architect_agent_service._context_builder = mock_context_builder

    return c

@pytest.mark.asyncio
async def test_agent_loop_smoke_modes(container, tmp_path):
    coordinator = container.agent_loop_coordinator
    assert coordinator is not None

    driver = WorkspaceLocalDriver(root_path=str(tmp_path))
    modes = ["AUTO", "ATM", "CONSILIUM", "LOCAL", "MANUAL"]

    for mode in modes:
        messages = [{"role": "user", "content": f"Test task for mode {mode}"}]
        events = []
        try:
            async for chunk in coordinator.run_agent_loop(
                session_id=f"test_session_{mode.lower()}",
                messages=messages,
                driver=driver,
                strategy=mode,
                user_id="test_user"
            ):
                events.append(chunk)
                if len(events) > 10:
                    break
        except Exception as e:
            pytest.fail(f"Mode {mode} raised exception: {e}")
        
        assert len(events) > 0, f"No events yielded for mode {mode}"

@pytest.mark.asyncio
async def test_architect_agent_consult(container):
    architect = container.architect_agent_service
    assert architect is not None
    architect._orchestrator = MockOrchestrator()
    
    res = await architect.consult(
        user_prompt="Design a login system",
        project_id="default_project",
        user_id="test_user",
        user_plan="free"
    )
    assert isinstance(res, dict)
