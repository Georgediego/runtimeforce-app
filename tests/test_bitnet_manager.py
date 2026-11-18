from app.services.llm.bitnet_manager import BitNetManager


def test_bitnet_model_ids_normalize_provider_prefix():
    assert BitNetManager.normalize_model_id("bitnet/bitnet-b1.58-2b-4t") == "bitnet-b1.58-2b-4t"
    assert BitNetManager.normalize_model_id("Falcon3-7B-Instruct-1.58bit") == "falcon3-7b-instruct-1.58bit"


def test_bitnet_catalog_contains_supported_chat_models():
    manager = BitNetManager()
    catalog = {item["key"]: item for item in manager.catalog()}
    assert "bitnet-b1.58-2b-4t" in catalog
    assert "falcon3-7b-instruct-1.58bit" in catalog
    assert catalog["bitnet-b1.58-2b-4t"]["id"].startswith("bitnet/")


def test_bitnet_hardware_reports_safe_thread_count():
    hardware = BitNetManager().hardware()
    assert hardware["threads"] >= 1
    assert isinstance(hardware["avx2"], bool)
    assert hardware["kernel"] == "i2_s"
