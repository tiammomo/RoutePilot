"""Production semantic embedding client boundary tests."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from agent.travel_agent.rag import (
    OpenAICompatibleEmbeddingProvider,
    build_embedding_provider_from_env,
)


@pytest.mark.asyncio
async def test_embedding_provider_bounds_request_and_restores_provider_order() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "semantic-v1",
                "data": [
                    {"index": 1, "embedding": [0.0] * 7 + [1.0]},
                    {"index": 0, "embedding": [1.0] + [0.0] * 7},
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://embeddings.example.test/v1/embeddings",
        api_key=SecretStr("server-secret-key"),
        model_id="semantic-v1",
        model_version="semantic-v1@2026-07",
        dimension=8,
        client=client,
    )
    vectors = await provider.embed_documents(["故宫", "无障碍路线"])

    assert vectors[0][0] == 1.0
    assert vectors[1][-1] == 1.0
    assert seen == {
        "url": "https://embeddings.example.test/v1/embeddings",
        "authorization": "Bearer server-secret-key",
        "payload": {
            "model": "semantic-v1",
            "input": ["故宫", "无障碍路线"],
            "dimensions": 8,
        },
    }
    await provider.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_embedding_provider_rejects_redirects_invalid_vectors_and_oversize_input() -> None:
    async def redirect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"Location": "https://attacker.example/collect"})

    redirect_client = httpx.AsyncClient(transport=httpx.MockTransport(redirect))
    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://embeddings.example.test/v1/embeddings",
        api_key=None,
        model_id="semantic-v1",
        model_version="semantic-v1@1",
        dimension=8,
        client=redirect_client,
    )
    with pytest.raises(RuntimeError, match="redirects"):
        await provider.embed_query("北京")
    with pytest.raises(ValueError, match="32 KiB"):
        await provider.embed_query("x" * 32_769)
    await redirect_client.aclose()

    async def invalid(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    invalid_client = httpx.AsyncClient(transport=httpx.MockTransport(invalid))
    invalid_provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://embeddings.example.test/v1/embeddings",
        api_key=None,
        model_id="semantic-v1",
        model_version="semantic-v1@1",
        dimension=8,
        client=invalid_client,
    )
    with pytest.raises(RuntimeError, match="invalid vector"):
        await invalid_provider.embed_query("北京")
    await invalid_client.aclose()


def test_embedding_environment_builder_is_explicit_and_https_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "ROUTEPILOT_EMBEDDING_ENDPOINT",
        "ROUTEPILOT_EMBEDDING_MODEL",
        "ROUTEPILOT_EMBEDDING_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert build_embedding_provider_from_env() is None

    monkeypatch.setenv("ROUTEPILOT_EMBEDDING_ENDPOINT", "https://embed.example/v1/embeddings")
    with pytest.raises(RuntimeError, match="configured together"):
        build_embedding_provider_from_env()

    monkeypatch.setenv("ROUTEPILOT_EMBEDDING_MODEL", "semantic-v1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ROUTEPILOT_EMBEDDING_ENDPOINT", "http://embed.internal/v1/embeddings")
    with pytest.raises(ValueError, match="HTTPS"):
        build_embedding_provider_from_env()
