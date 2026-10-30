import httpx
import pytest

from app.services.llm.managed_ai_proxy_client import ManagedAIProxyClient


@pytest.mark.asyncio
async def test_managed_proxy_sends_bearer_and_forwards_stream_events():
    captured = {}

    def handle(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = request.read()
        return httpx.Response(
            200,
            text=(
                'data: {"status":"model_try","model":"openai/gpt-4o-mini","provider":"openai"}\n\n'
                'data: {"status":"streaming","content":"hello"}\n\n'
                'data: {"status":"done"}\n\n'
            ),
            headers={"Content-Type": "text/event-stream"},
        )

    client = ManagedAIProxyClient("https://server.example", httpx.MockTransport(handle))
    events = [event async for event in client.stream_completion(
        token="valid-test-token",
        model="auto",
        strategy="code",
        messages=[{"role": "user", "content": "write code"}],
        tools=[{"type": "function", "function": {"name": "scan_workspace"}}],
    )]

    assert captured["url"] == "https://server.example/api/v1/chat/stream"
    assert captured["authorization"] == "Bearer valid-test-token"
    assert b'"strategy": "code"' in captured["payload"]
    assert any(event.get("status") == "model_try" and event.get("model") == "openai/gpt-4o-mini" for event in events)
    assert any(event.get("status") == "streaming" and event.get("content") == "hello" for event in events)
    assert events[-1]["status"] == "done"


@pytest.mark.asyncio
async def test_managed_proxy_reports_authorization_failure():
    client = ManagedAIProxyClient(
        "https://server.example",
        httpx.MockTransport(lambda request: httpx.Response(403, json={"detail": "Plan required"})),
    )
    events = [event async for event in client.stream_completion(
        token="token", model="auto", strategy="auto", messages=[{"role": "user", "content": "hello"}]
    )]
    assert events[0]["status"] == "error"
    assert events[0]["http_status"] == 403
    assert "Plan required" in events[0]["error"]


@pytest.mark.asyncio
async def test_managed_proxy_reports_server_fallback_as_a_progress_phase():
    client = ManagedAIProxyClient(
        "https://server.example",
        httpx.MockTransport(lambda request: httpx.Response(
            200,
            text=(
                'data: {"status":"fallback","model":"openai/gpt-4o-mini"}\n\n'
                'data: {"status":"model_try","model":"openai/gpt-4o"}\n\n'
                'data: {"status":"streaming","content":"answer"}\n\n'
                'data: {"status":"done"}\n\n'
            ),
            headers={"Content-Type": "text/event-stream"},
        )),
    )
    events = [event async for event in client.stream_completion(
        token="token", model="auto", strategy="auto", messages=[{"role": "user", "content": "hello"}]
    )]

    assert any(event.get("status") == "phase" and "next server model" in event.get("label", "") for event in events)
    assert any(event.get("status") == "streaming" and event.get("content") == "answer" for event in events)


@pytest.mark.asyncio
async def test_managed_proxy_preserves_safe_upstream_failure_types():
    client = ManagedAIProxyClient(
        "https://server.example",
        httpx.MockTransport(lambda request: httpx.Response(
            200,
            text=(
                'data: {"status":"model_try","model":"openai/gpt-4o-mini"}\n\n'
                'data: {"status":"fallback","model":"openai/gpt-4o-mini","provider":"openai","error":"AuthenticationError","reason":"provider_auth","fallback_count":0}\n\n'
                'data: {"status":"failed","error":"All configured models failed."}\n\n'
            ),
            headers={"Content-Type": "text/event-stream"},
        )),
    )
    events = [event async for event in client.stream_completion(
        token="token", model="openai/gpt-4o-mini", strategy="manual", messages=[{"role": "user", "content": "hello"}]
    )]

    assert events[-1]["status"] == "error"
    assert "AuthenticationError" in events[-1]["error"]
    assert "openai" in events[-1]["error"]
    assert "provider_auth" in events[-1]["error"]
    assert any("no other server model" in event.get("label", "") for event in events if event.get("status") == "phase")
