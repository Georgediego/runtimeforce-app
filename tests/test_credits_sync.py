import pytest
from unittest.mock import AsyncMock, patch
from app.services.billing.credit_balance_service import CreditBalanceService

@pytest.mark.asyncio
async def test_credits_sync_success():
    service = CreditBalanceService(saas_base_url="https://runtimeforce.dev")
    user_id = "user_test_credits"
    
    mock_data = {
        "plan": "pro",
        "status": "active",
        "trial_days": 14,
        "included_credits": 5000,
        "used_credits": 100,
        "remaining_credits": 4900,
        "reset_date": "2026-11-01T00:00:00Z",
        "offline_grace_hours": 48
    }

    class MockResponse:
        status_code = 200
        def json(self):
            return mock_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockResponse()

        account = await service.get_account_details(user_id, token="fake-token")
        assert account["plan"] == "pro"
        assert account["remaining_credits"] == 4900
        assert account["is_stale"] is False

        balance = await service.get_balance(user_id, token="fake-token")
        assert balance["credits_remaining"] == 4900
        assert balance["total_allocated"] == 5000
        assert balance["is_stale"] is False

@pytest.mark.asyncio
async def test_credits_sync_offline_fallback_stale():
    service = CreditBalanceService(saas_base_url="https://runtimeforce.dev")
    user_id = "user_test_cache"

    mock_data = {
        "plan": "studio",
        "status": "active",
        "trial_days": 0,
        "included_credits": 15000,
        "used_credits": 500,
        "remaining_credits": 14500,
        "reset_date": "2026-11-01T00:00:00Z",
        "offline_grace_hours": 48
    }

    class MockResponse200:
        status_code = 200
        def json(self):
            return mock_data

    class MockResponse500:
        status_code = 500

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockResponse200()
        await service.get_account_details(user_id, token="fake-token")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockResponse500()

        account = await service.get_account_details(user_id, token="fake-token")
        assert account["plan"] == "studio"
        assert account["remaining_credits"] == 14500
        assert account["is_stale"] is True

@pytest.mark.asyncio
async def test_credits_sync_missing_contract_no_cache():
    service = CreditBalanceService(saas_base_url="https://runtimeforce.dev")
    user_id = "user_test_nocache"

    class MockResponse404:
        status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockResponse404()

        with pytest.raises(Exception) as exc_info:
            await service.get_account_details(user_id, token="fake-token")
        assert "Missing contract" in str(exc_info.value)
