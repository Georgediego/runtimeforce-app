import pytest
import asyncio
import ast
import os
import inspect
from typing import Any, AsyncGenerator, Dict, List
from app.container import ApplicationContainer
from app.services.agent.agent_loop_coordinator import AgentLoopCoordinator
from app.services.agent.architect_agent_service import ArchitectAgentService
from app.services.agent.role_router_service import RoleRouterService
from app.services.memory.context_builder_service import ContextBuilderService
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
def container():
    c = ApplicationContainer()
    c.llm_orchestrator = MockOrchestrator()
    mock_context_builder = MockContextBuilder()
    
    if hasattr(c, "architect_agent_service"):
        c.architect_agent_service._orchestrator = c.llm_orchestrator
        c.architect_agent_service._context_builder = mock_context_builder

    if hasattr(c, "agent_loop_coordinator"):
        c.agent_loop_coordinator._orchestrator = c.llm_orchestrator
        c.agent_loop_coordinator._context_builder = mock_context_builder

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
        except Exception as e:
            pytest.fail(f"Mode {mode} raised exception: {e}")
        
        assert len(events) > 0, f"No events yielded for mode {mode}"
        assert any(e.get("status") == "done" for e in events), f"Mode {mode} did not reach 'done' status"

@pytest.mark.asyncio
async def test_role_router_bilingual_classification():
    router = RoleRouterService()
    
    res_en = await router.classify_and_route(user_prompt="Please make a nice UI design for button")
    assert res_en["role"] == "Designer"

    res_ru = await router.classify_and_route(user_prompt="Сделай дизайн кнопки пожалуйста")
    assert res_ru["role"] == "Designer"

    res_impl = await router.classify_and_route(user_prompt="Исправь баг и напиши код")
    assert res_impl["role"] == "Implementer"

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

def test_ast_no_unassigned_self_attributes():
    agent_dir = "app/services/agent"
    for root, dirs, files in os.walk(agent_dir):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=filepath)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        assigned = set()
                        used = set()
                        methods = set()
                        for subnode in ast.walk(node):
                            if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                methods.add(subnode.name)
                        for body_item in node.body:
                            if isinstance(body_item, ast.Assign):
                                for target in body_item.targets:
                                    if isinstance(target, ast.Name):
                                        assigned.add(target.id)
                        for subnode in ast.walk(node):
                            if isinstance(subnode, ast.Assign):
                                for target in subnode.targets:
                                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                                        assigned.add(target.attr)
                            elif isinstance(subnode, ast.Attribute) and isinstance(subnode.value, ast.Name) and subnode.value.id == 'self':
                                if isinstance(subnode.ctx, ast.Load):
                                    used.add(subnode.attr)
                                elif isinstance(subnode.ctx, ast.Store):
                                    assigned.add(subnode.attr)
                        unassigned = used - assigned - methods
                        unassigned = {attr for attr in unassigned if not attr.startswith('__')}
                        assert not unassigned, f"Class {node.name} in {filepath} uses unassigned self._ attributes: {sorted(unassigned)}"

def test_ast_inspect_method_signatures():
    # Verify build_optimal_context signature against ContextBuilderService
    sig = inspect.signature(ContextBuilderService.build_optimal_context)
    required_params = [
        name for name, param in sig.parameters.items()
        if param.default == inspect.Parameter.empty and name != 'self'
    ]
    # Check that required parameters include user_prompt, session_id, user_id, project_id
    for req in ['user_prompt', 'session_id', 'user_id', 'project_id']:
        assert req in required_params, f"Required parameter {req} missing in build_optimal_context"
