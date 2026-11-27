from types import SimpleNamespace

from app.services.agent.agent_loop_coordinator import AgentLoopCoordinator


class _Registry:
    def __init__(self, metadata):
        self.metadata = metadata

    def get_model(self, model_id):
        return self.metadata.get(model_id)


class _Router:
    def __init__(self, metadata):
        self.registry = _Registry(metadata)


def _coordinator(model_id="groq/test-model", context_window=0, max_input_tokens=7000):
    metadata = SimpleNamespace(
        context_window=context_window,
        max_output_tokens=4096,
        max_input_tokens=max_input_tokens,
    )
    instance = AgentLoopCoordinator.__new__(AgentLoopCoordinator)
    instance._llm_router = _Router({model_id: metadata})
    instance._model_request_limits = {}
    return instance


def test_groq_request_budget_is_below_observed_tpm_limit():
    coordinator = _coordinator()
    assert coordinator._request_limit_for_model("groq/test-model", "groq") == 7000


def test_preflight_counts_tool_schemas_as_part_of_full_request():
    coordinator = _coordinator()
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "task"}]
    without_tools = coordinator._estimate_request_tokens(messages, [])
    with_tools = coordinator._estimate_request_tokens(
        messages, [{"type": "function", "function": {"name": "large_tool", "description": "x" * 5000}}]
    )
    assert with_tools > without_tools


def test_compaction_removes_old_chat_history_but_preserves_active_task_and_tool_results():
    coordinator = _coordinator(max_input_tokens=1800)
    messages = [
        {"role": "system", "content": "system rules"},
        {"role": "user", "content": "old task " + ("x" * 3000)},
        {"role": "assistant", "content": "old answer " + ("y" * 3000)},
        {"role": "user", "content": "current task"},
        {"role": "tool", "tool_call_id": "tool-1", "content": "current tool result"},
    ]
    prepared, estimate, limit, removed = coordinator._prepare_messages_for_model(
        messages, "groq/test-model", "groq", []
    )
    assert removed == 2
    assert estimate <= limit
    assert prepared[0]["role"] == "system"
    assert any(m.get("content") == "current task" for m in prepared)
    assert any(m.get("role") == "tool" and m.get("content") == "current tool result" for m in prepared)


def test_oversized_active_prompt_is_not_silently_truncated():
    coordinator = _coordinator(max_input_tokens=1200)
    messages = [
        {"role": "system", "content": "system rules"},
        {"role": "user", "content": "current task " + ("important " * 1000)},
    ]
    prepared, estimate, limit, removed = coordinator._prepare_messages_for_model(
        messages, "groq/test-model", "groq", []
    )
    assert estimate > limit
    assert removed == 0
    assert prepared[-1]["content"] == messages[-1]["content"]
