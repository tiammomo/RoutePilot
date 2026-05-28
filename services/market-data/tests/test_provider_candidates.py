from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from quantpilot_market_data.api import create_app
from quantpilot_market_data.provider_candidates import (
    get_candidate_provider,
    probe_candidate_provider,
)


def test_provider_candidates_registry_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/provider-candidates")

    assert response.status_code == 200
    provider_ids = {provider["id"] for provider in response.json()["providers"]}
    assert "tencent-a-share-kline" in provider_ids
    assert "ths-public-kline" in provider_ids
    assert "baostock-a-share-history" in provider_ids
    assert "akshare-python" in provider_ids
    assert "stooq-daily" in provider_ids
    assert "yahoo-finance-chart" in provider_ids
    assert "yahoo-finance-quote-summary" in provider_ids
    assert "alpha-vantage" in provider_ids


@respx.mock
@pytest.mark.anyio
async def test_probe_yahoo_chart_provider() -> None:
    provider = get_candidate_provider("yahoo-finance-chart")
    assert provider is not None
    assert provider.probe_url is not None
    respx.get(provider.probe_url).mock(
        return_value=Response(200, json={"chart": {"result": [{"meta": {"symbol": "AAPL"}}]}})
    )

    result = await probe_candidate_provider(provider)

    assert result.ok is True
    assert result.status_code == 200
    assert "chart" in result.sample_keys


@respx.mock
@pytest.mark.anyio
async def test_probe_candidate_provider_without_key() -> None:
    provider = get_candidate_provider("tencent-a-share-kline")
    assert provider is not None
    assert provider.probe_url is not None
    respx.get(provider.probe_url).mock(
        return_value=Response(200, json={"code": 0, "data": {"sh600519": {"qfqday": []}}})
    )

    result = await probe_candidate_provider(provider)

    assert result.ok is True
    assert result.status_code == 200
    assert "code" in result.sample_keys
    assert "data" in result.sample_keys


@pytest.mark.anyio
async def test_probe_candidate_provider_requires_key() -> None:
    provider = get_candidate_provider("alpha-vantage")
    assert provider is not None

    result = await probe_candidate_provider(provider)

    assert result.ok is False
    assert result.status_code is None
    assert "API key" in (result.error or "")
