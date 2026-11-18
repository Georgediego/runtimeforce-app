from app.services.llm.llm_discovery_service import LLMDiscoveryService
from app.services.llm.llm_registry_service import LLMRegistryService, ModelMetadata


def test_bitnet_openai_compatible_models_are_registered_with_provider_prefix():
    registry = LLMRegistryService()
    discovery = LLMDiscoveryService(registry)

    models = discovery._parse_openai_format(
        [
            {"id": "BitNet-b1.58-2B-4T"},
            {"id": "bitnet/custom-model"},
        ],
        "bitnet",
    )

    assert [model["id"] for model in models] == [
        "bitnet/BitNet-b1.58-2B-4T",
        "bitnet/custom-model",
    ]

    for model in models:
        registry.register_model(
            ModelMetadata(
                id=model["id"],
                provider="bitnet",
                name=model["name"],
                context_window=model["context_window"],
                max_output_tokens=model["max_output_tokens"],
                tier="local",
                capabilities=model["capabilities"],
                description=model["description"],
                supports_function_calling=True,
            )
        )

    registered = registry.get_available_models(provider_filter="bitnet")
    assert {model.id for model in registered} == {
        "bitnet/BitNet-b1.58-2B-4T",
        "bitnet/custom-model",
    }
    assert all(model.tier == "local" for model in registered)


def test_bitnet_discovery_skips_empty_and_batch_model_ids():
    registry = LLMRegistryService()
    discovery = LLMDiscoveryService(registry)

    models = discovery._parse_openai_format(
        [
            {"id": ""},
            {"id": "training-job:batch"},
            {},
            {"id": "BitNet-2B"},
        ],
        "bitnet",
    )

    assert [model["id"] for model in models] == ["bitnet/BitNet-2B"]
