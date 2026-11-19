import asyncio
from unittest.mock import MagicMock

from app.core.security.aes_crypto_service import AESCryptoService
from app.services.llm.bitnet_provider import BitNetProvider
from app.services.llm.llm_orchestrator_service import LLMOrchestratorService


def test_bitnet_critic_validation_uses_saved_server_url(monkeypatch):
    provider_keys = MagicMock()
    provider_keys.get_all_provider_keys.return_value = {"bitnet": "encrypted-server-url"}
    monkeypatch.setattr(AESCryptoService, "decrypt", lambda value: "http://127.0.0.1:8080")

    call_args = {}

    async def fake_stream_chat(self, **kwargs):
        call_args.update(kwargs)
        yield {"status": "streaming", "content": '{"passed": true, "feedback": "ok"}'}

    monkeypatch.setattr(BitNetProvider, "stream_chat", fake_stream_chat)
    service = LLMOrchestratorService(provider_keys, MagicMock())

    async def run_validation():
        return await service.validate_result(
            result={"content": "validated output"},
            context={"task_type": "coding"},
            model_id="bitnet/test-model",
            user_id="user@example.com",
        )

    result = asyncio.run(run_validation())

    assert call_args["base_url"] == "http://127.0.0.1:8080"
    assert call_args["model_id"] == "bitnet/test-model"
    assert result == {"passed": True, "feedback": "ok"}
