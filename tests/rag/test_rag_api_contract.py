"""FastAPI contract tests for RAG authentication and tenant administration."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from agent.travel_agent.rag import InMemoryKnowledgeRepository, KnowledgeService
from backend.moyuan_web.v1.models import Principal
from backend.moyuan_web.v1.rag_routes import router


def build_app(*, authenticated: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.routepilot_knowledge_service = KnowledgeService(InMemoryKnowledgeRepository())
    if authenticated:

        async def authenticate(request: Request) -> Principal:
            return Principal(
                tenant_id=request.headers.get("X-Test-Tenant", "tenant-a"),
                user_id=request.headers.get("X-Test-User", "user-a"),
                roles=frozenset(
                    role
                    for role in request.headers.get("X-Test-Roles", "viewer").split(",")
                    if role
                ),
            )

        app.state.routepilot_v1_authenticator = authenticate
    return app


def payload(*, visibility: str = "tenant") -> dict:
    return {
        "canonical_source_uri": "https://travel.example.com/beijing/policy",
        "source_type": "official_policy",
        "source_version": "2026-07-12",
        "title": "北京参观政策",
        "content": "故宫参观需要预约。",
        "visibility_scope": visibility,
        "geo_entities": ["北京"],
        "tags": ["文化"],
        "corpus_revision": "beijing-2026-07",
        "trust_tier": "official",
        "license": {
            "license_id": "official-policy",
            "usage_policy": "May index and cite.",
        },
    }


@pytest.mark.asyncio
async def test_rag_api_denies_anonymous_and_non_admin_ingestion():
    anonymous = build_app(authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=anonymous),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "故宫", "corpus_revision": "beijing-2026-07"},
        )
    assert response.status_code == 401

    app = build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        denied = await client.post(
            "/api/v1/knowledge/documents:ingest",
            json=payload(),
            headers={"Idempotency-Key": "api-ingest-001"},
        )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "KNOWLEDGE_ADMIN_ROLE_REQUIRED"


@pytest.mark.asyncio
async def test_rag_api_ingest_search_and_cross_tenant_isolation():
    app = build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        ingested = await client.post(
            "/api/v1/knowledge/documents:ingest",
            json=payload(),
            headers={
                "Idempotency-Key": "api-ingest-002",
                "X-Test-Roles": "tenant_admin",
            },
        )
        assert ingested.status_code == 201

        own = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "故宫 预约", "corpus_revision": "beijing-2026-07"},
        )
        hidden = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "故宫 预约", "corpus_revision": "beijing-2026-07"},
            headers={"X-Test-Tenant": "tenant-b"},
        )
    assert own.status_code == 200
    assert len(own.json()["items"]) == 1
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []
    assert own.json()["result_type"] == "knowledge_retrieval"
    assert own.json()["trace"]["retrieval_mode"] == "lexical"
    assert own.json()["trace"]["vector_status"] == "disabled"


@pytest.mark.asyncio
async def test_rag_api_public_ingest_requires_global_admin_and_rejects_tenant_override():
    app = build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.post(
            "/api/v1/knowledge/documents:ingest",
            json=payload(visibility="public"),
            headers={
                "Idempotency-Key": "api-ingest-003",
                "X-Test-Roles": "tenant_admin",
            },
        )
        forged = payload()
        forged["tenant_id"] = "tenant-b"
        invalid = await client.post(
            "/api/v1/knowledge/documents:ingest",
            json=forged,
            headers={
                "Idempotency-Key": "api-ingest-004",
                "X-Test-Roles": "tenant_admin",
            },
        )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "PUBLIC_KNOWLEDGE_ADMIN_REQUIRED"
    assert invalid.status_code == 422
