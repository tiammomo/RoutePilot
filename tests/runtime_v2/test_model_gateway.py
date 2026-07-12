"""Bounded DeepSeek research-directive boundary tests."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from agent.travel_agent.runtime_v2.model_gateway import (
    DeepSeekResearchDirectiveGenerator,
    ModelGatewayError,
)
from routepilot_contracts import validate_contract
from routepilot_contracts.artifacts import TripBrief
from tests.contract.samples import build_valid_contracts


def trip_brief() -> TripBrief:
    value = validate_contract("TripBrief@1", build_valid_contracts()["TripBrief@1"])
    assert isinstance(value, TripBrief)
    return value


@pytest.mark.asyncio
async def test_deepseek_gateway_sends_one_bounded_non_thinking_json_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_tokens"] == 96
        assert payload["stream"] is False
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"place_query":"历史文化景点"}'}}
                ],
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 8,
                    "total_tokens": 38,
                },
            },
        )

    gateway = DeepSeekResearchDirectiveGenerator(
        api_key=SecretStr("test-secret"),
        transport=httpx.MockTransport(handler),
    )
    directive = await gateway.generate(trip_brief(), "规划一段轻量北京历史旅行")

    assert directive.place_query == "历史文化景点"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_deepseek_gateway_fails_safely_without_leaking_secret_or_body() -> None:
    secret = "never-leak-this-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, text=f"provider body contains {secret}")

    gateway = DeepSeekResearchDirectiveGenerator(
        api_key=SecretStr(secret),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelGatewayError) as raised:
        await gateway.generate(trip_brief(), "测试失败边界")

    assert str(raised.value) == "model request was rejected"
    assert secret not in str(raised.value)


def test_deepseek_gateway_rejects_unreviewed_models_and_insecure_endpoints() -> None:
    with pytest.raises(ValueError, match="reviewed"):
        DeepSeekResearchDirectiveGenerator(
            api_key=SecretStr("test-secret"),
            model="deepseek-chat",
        )
    with pytest.raises(ValueError, match="HTTPS"):
        DeepSeekResearchDirectiveGenerator(
            api_key=SecretStr("test-secret"),
            endpoint="http://api.deepseek.com/chat/completions",
        )
