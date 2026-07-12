"""Pluggable semantic embedding boundary and a test-only deterministic provider."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr


MAX_EMBEDDING_BATCH = 64
MAX_EMBEDDING_TEXT_BYTES = 32_768
MAX_EMBEDDING_REQUEST_BYTES = 512 * 1024
MAX_EMBEDDING_RESPONSE_BYTES = 4 * 1024 * 1024


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Embedding implementation supplied by the deployment composition root."""

    model_id: str
    model_version: str
    dimension: int
    semantic_capable: bool

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document chunks."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed one search query."""


class OpenAICompatibleEmbeddingProvider:
    """Bounded server-side client for an OpenAI-compatible embeddings endpoint.

    The endpoint is deployment configuration, never model-controlled input. It
    must be HTTPS outside local/test environments and redirects are rejected so
    bearer credentials cannot be forwarded to another origin.
    """

    semantic_capable = True

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: SecretStr | None,
        model_id: str,
        model_version: str,
        dimension: int = 384,
        timeout_seconds: float = 10.0,
        allow_http: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ({"https", "http"} if allow_http else {"https"}):
            raise ValueError("embedding endpoint must use HTTPS")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("embedding endpoint must be an absolute URL without credentials or query data")
        if len(endpoint) > 2_048:
            raise ValueError("embedding endpoint is too long")
        if not model_id.strip() or len(model_id) > 200:
            raise ValueError("embedding model_id is invalid")
        if not model_version.strip() or len(model_version) > 200:
            raise ValueError("embedding model_version is invalid")
        if dimension < 8 or dimension > 4_096:
            raise ValueError("embedding dimension must be between 8 and 4096")
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("embedding timeout must be between 0 and 60 seconds")
        self.endpoint = endpoint
        self.api_key = api_key
        self.model_id = model_id.strip()
        self.model_version = model_version.strip()
        self.dimension = dimension
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> list[str]:
        values = list(texts)
        if not values or len(values) > MAX_EMBEDDING_BATCH:
            raise ValueError("embedding batch must contain between 1 and 64 texts")
        total = 0
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("embedding input must contain non-empty strings")
            size = len(value.encode("utf-8"))
            if size > MAX_EMBEDDING_TEXT_BYTES:
                raise ValueError("embedding input text exceeds 32 KiB")
            total += size
        if total > MAX_EMBEDDING_REQUEST_BYTES:
            raise ValueError("embedding request exceeds 512 KiB")
        return values

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a bounded batch while preserving provider indices."""

        values = self._validate_texts(texts)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key is not None and self.api_key.get_secret_value():
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        request = self._client.build_request(
            "POST",
            self.endpoint,
            headers=headers,
            json={"model": self.model_id, "input": values, "dimensions": self.dimension},
        )
        response = await self._client.send(request, stream=True)
        try:
            if 300 <= response.status_code < 400:
                raise RuntimeError("embedding provider redirects are forbidden")
            response.raise_for_status()
            declared = int(response.headers.get("content-length") or 0)
            if declared > MAX_EMBEDDING_RESPONSE_BYTES:
                raise RuntimeError("embedding response exceeds size limit")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_EMBEDDING_RESPONSE_BYTES:
                    raise RuntimeError("embedding response exceeds size limit")
        finally:
            await response.aclose()
        try:
            payload = json.loads(bytes(body))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("embedding provider returned invalid JSON") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(values):
            raise RuntimeError("embedding provider returned an invalid result count")
        indexed: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                raise RuntimeError("embedding provider returned an invalid result item")
            index = item["index"]
            vector = item.get("embedding")
            if index in indexed or not isinstance(vector, list):
                raise RuntimeError("embedding provider returned duplicate or invalid indices")
            try:
                indexed[index] = validate_embedding(vector, expected_dimension=self.dimension)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("embedding provider returned an invalid vector") from exc
        if set(indexed) != set(range(len(values))):
            raise RuntimeError("embedding provider result indices are incomplete")
        return [indexed[index] for index in range(len(values))]

    async def embed_query(self, text: str) -> list[float]:
        """Embed one query through the same bounded path."""

        return (await self.embed_documents([text]))[0]

    async def close(self) -> None:
        """Close only the HTTP client owned by this provider."""

        if self._owns_client:
            await self._client.aclose()


def build_embedding_provider_from_env() -> EmbeddingProvider | None:
    """Build the optional production semantic provider from explicit settings."""

    endpoint = os.getenv("ROUTEPILOT_EMBEDDING_ENDPOINT", "").strip()
    model_id = os.getenv("ROUTEPILOT_EMBEDDING_MODEL", "").strip()
    api_key = os.getenv("ROUTEPILOT_EMBEDDING_API_KEY", "").strip()
    configured = [bool(endpoint), bool(model_id)]
    if not any(configured):
        return None
    if not all(configured):
        raise RuntimeError(
            "ROUTEPILOT_EMBEDDING_ENDPOINT and ROUTEPILOT_EMBEDDING_MODEL must be configured together"
        )
    environment = os.getenv("ENVIRONMENT", "dev").strip().lower()
    dimension_raw = os.getenv("ROUTEPILOT_EMBEDDING_DIMENSION", "384").strip()
    timeout_raw = os.getenv("ROUTEPILOT_EMBEDDING_TIMEOUT_SECONDS", "10").strip()
    try:
        dimension = int(dimension_raw)
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise RuntimeError("embedding dimension and timeout must be numeric") from exc
    return OpenAICompatibleEmbeddingProvider(
        endpoint=endpoint,
        api_key=SecretStr(api_key) if api_key else None,
        model_id=model_id,
        model_version=os.getenv("ROUTEPILOT_EMBEDDING_MODEL_VERSION", model_id).strip(),
        dimension=dimension,
        timeout_seconds=timeout_seconds,
        allow_http=environment in {"dev", "development", "local", "test"},
    )


class DeterministicHashEmbeddingProvider:
    """Non-semantic deterministic vectors exclusively for tests.

    These vectors are useful for persistence and dimensionality tests.  The
    provider intentionally advertises ``semantic_capable = False`` so the
    retrieval layer can never report its results as semantic matches.
    """

    model_id = "routepilot-test-hash"
    model_version = "test-only@1"
    semantic_capable = False

    def __init__(self, *, dimension: int = 384, testing_only: bool = False):
        if not testing_only:
            raise ValueError("deterministic hash embeddings require testing_only=True")
        if dimension < 8 or dimension > 4_096:
            raise ValueError("embedding dimension must be between 8 and 4096")
        self.dimension = dimension

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each string using the deterministic test projection."""

        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a query using the deterministic test projection."""

        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"\w+|[^\s]", text.lower(), flags=re.UNICODE)
        for token in tokens or [text]:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = -1.0 if digest[4] & 1 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def validate_embedding(vector: Sequence[float], *, expected_dimension: int) -> list[float]:
    """Validate dimensionality and reject non-finite provider output."""

    if len(vector) != expected_dimension:
        raise ValueError(
            f"embedding dimension mismatch: expected {expected_dimension}, got {len(vector)}"
        )
    result = [float(value) for value in vector]
    if any(not math.isfinite(value) for value in result):
        raise ValueError("embedding contains a non-finite value")
    return result


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity for already validated vectors."""

    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))


__all__ = [
    "DeterministicHashEmbeddingProvider",
    "EmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "build_embedding_provider_from_env",
    "cosine_similarity",
    "validate_embedding",
]
