"""Bounded model assistance for one low-token research directive per Run."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from routepilot_contracts.artifacts import TripBrief

logger = logging.getLogger(__name__)


class ModelGatewayError(RuntimeError):
    """A safe model failure that never contains provider response text."""


class ResearchDirective(BaseModel):
    """Narrow model output; it may influence retrieval but is never evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    place_query: str = Field(min_length=1, max_length=32)


class ResearchDirectiveGenerator(Protocol):
    async def generate(self, brief: TripBrief, goal: str) -> ResearchDirective: ...


class DeepSeekResearchDirectiveGenerator:
    """Call DeepSeek once with JSON output, no thinking, and a small token cap."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        endpoint: str = "https://api.deepseek.com/chat/completions",
        model: str = "deepseek-v4-flash",
        max_output_tokens: int = 96,
        timeout_seconds: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if model != "deepseek-v4-flash":
            raise ValueError("RoutePilot V1 only enables the reviewed deepseek-v4-flash profile")
        parsed_endpoint = httpx.URL(endpoint)
        if parsed_endpoint.scheme != "https" or not parsed_endpoint.host:
            raise ValueError("model endpoint must be an absolute HTTPS URL")
        if not api_key.get_secret_value().strip():
            raise ValueError("model API key cannot be empty")
        self.api_key = api_key
        self.endpoint = str(parsed_endpoint)
        self.model = model
        self.max_output_tokens = max(32, min(int(max_output_tokens), 128))
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 15.0))
        self.transport = transport

    async def generate(self, brief: TripBrief, goal: str) -> ResearchDirective:
        preferences = [item.value for item in brief.preferences[:5]]
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是旅行检索词生成器。只返回 JSON："
                        '{"place_query":"一个1到16字的POI检索词"}。'
                        "不得输出解释，不得编造地点，不得包含个人信息。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "destination": brief.destination.display_name[:100],
                            "preferences": preferences,
                            "request": goal[:300],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        raise ModelGatewayError("model request was rejected")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 64 * 1024:
                            raise ModelGatewayError("model response exceeded the size limit")
        except ModelGatewayError:
            raise
        except (httpx.HTTPError, TimeoutError):
            raise ModelGatewayError("model request failed") from None
        try:
            envelope = json.loads(body)
            choices = envelope["choices"]
            content = choices[0]["message"]["content"]
            directive = ResearchDirective.model_validate_json(content)
            usage: dict[str, Any] = envelope.get("usage") or {}
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise ModelGatewayError("model returned an invalid directive") from None
        logger.info(
            "research directive generated model=%s prompt_tokens=%d "
            "completion_tokens=%d total_tokens=%d",
            self.model,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
            int(usage.get("total_tokens") or 0),
        )
        return directive


def build_research_directive_generator_from_env() -> ResearchDirectiveGenerator | None:
    """Build the optional server-only model boundary; absence means deterministic search."""

    raw_key = os.getenv("ROUTEPILOT_LLM_API_KEY", "").strip()
    if not raw_key:
        return None
    raw_tokens = os.getenv("ROUTEPILOT_LLM_MAX_OUTPUT_TOKENS", "96")
    try:
        max_tokens = int(raw_tokens)
    except ValueError:
        raise RuntimeError("ROUTEPILOT_LLM_MAX_OUTPUT_TOKENS must be an integer") from None
    return DeepSeekResearchDirectiveGenerator(
        api_key=SecretStr(raw_key),
        endpoint=os.getenv(
            "ROUTEPILOT_LLM_ENDPOINT",
            "https://api.deepseek.com/chat/completions",
        ).strip(),
        model=os.getenv("ROUTEPILOT_LLM_MODEL", "deepseek-v4-flash").strip(),
        max_output_tokens=max_tokens,
    )


__all__ = [
    "DeepSeekResearchDirectiveGenerator",
    "ModelGatewayError",
    "ResearchDirective",
    "ResearchDirectiveGenerator",
    "build_research_directive_generator_from_env",
]
