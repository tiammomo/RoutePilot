"""Validate, deploy, and verify versioned RoutePilot V1 knowledge bundles."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from agent.travel_agent.rag import (
    LoadedKnowledgeBundle,
    VisibilityScope,
    ingestion_idempotency_key,
    load_knowledge_bundle,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    REPOSITORY_ROOT
    / "agent/travel_agent/rag/curated/routepilot-travel-basics-zh/manifest.json"
)
DEFAULT_API_URL = "http://127.0.0.1:38083/api/v1"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
JsonObject = dict[str, Any]
RequestJson = Callable[..., JsonObject]


class KnowledgeBaseToolError(RuntimeError):
    """A safe operator-facing bundle deployment or verification failure."""


def _api_base(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise KnowledgeBaseToolError("knowledge API URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise KnowledgeBaseToolError("knowledge API URL must not include credentials or query data")
    return normalized


def _request_json(
    *,
    method: str,
    url: str,
    token: str,
    payload: JsonObject | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> JsonObject:
    encoded = None
    request_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        **(headers or {}),
    }
    if payload is not None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raw_error = exc.read(64 * 1024)
        try:
            detail = json.loads(raw_error.decode("utf-8"))
            code = detail.get("detail", {}).get("code", "KNOWLEDGE_API_ERROR")
            message = detail.get("detail", {}).get("message", "knowledge API rejected request")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            code, message = "KNOWLEDGE_API_ERROR", "knowledge API rejected request"
        raise KnowledgeBaseToolError(f"{code}: {message} (HTTP {exc.code})") from exc
    except URLError as exc:
        raise KnowledgeBaseToolError("knowledge API is unreachable") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise KnowledgeBaseToolError("knowledge API response exceeds the safe size limit")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeBaseToolError("knowledge API returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise KnowledgeBaseToolError("knowledge API returned a non-object response")
    return result


def bundle_plan(bundle: LoadedKnowledgeBundle) -> JsonObject:
    """Return a content-free release plan suitable for logs and review."""

    return {
        "bundle_id": bundle.manifest.bundle_id,
        "schema_version": bundle.manifest.schema_version,
        "corpus_revision": bundle.manifest.corpus_revision,
        "visibility_scope": bundle.documents[0].request.visibility_scope.value,
        "release_digest": bundle.release_digest,
        "document_count": len(bundle.documents),
        "smoke_query_count": len(bundle.manifest.smoke_queries),
        "documents": [
            {
                "document_key": document.document_key,
                "title": document.request.title,
                "source_version": document.request.source_version,
                "content_sha256": document.content_sha256,
                "reviewed_at": document.request.metadata["review"]["reviewed_at"],
                "next_review_at": document.request.metadata["review"]["next_review_at"],
            }
            for document in bundle.documents
        ],
    }


def apply_bundle(
    bundle: LoadedKnowledgeBundle,
    *,
    api_url: str,
    token: str,
    request_json: RequestJson = _request_json,
) -> JsonObject:
    """Idempotently ingest every prevalidated document through the public API."""

    results: list[JsonObject] = []
    for document in bundle.documents:
        response = request_json(
            method="POST",
            url=f"{_api_base(api_url)}/knowledge/documents:ingest",
            token=token,
            payload=document.request.model_dump(mode="json"),
            headers={"Idempotency-Key": ingestion_idempotency_key(bundle, document.document_key)},
        )
        result = {
            "document_key": document.document_key,
            "document_id": response.get("document_id"),
            "status": response.get("status"),
            "chunk_count": response.get("chunk_count"),
            "vector_status": response.get("vector_status"),
            "idempotent_replay": response.get("idempotent_replay", False),
        }
        results.append(result)
        if result["status"] != "published" or not isinstance(result["chunk_count"], int) or result["chunk_count"] < 1:
            raise KnowledgeBaseToolError(
                f"document {document.document_key} was not published with searchable chunks"
            )
    return {
        "bundle_id": bundle.manifest.bundle_id,
        "corpus_revision": bundle.manifest.corpus_revision,
        "release_digest": bundle.release_digest,
        "documents": results,
    }


def verify_bundle(
    bundle: LoadedKnowledgeBundle,
    *,
    api_url: str,
    token: str,
    request_json: RequestJson = _request_json,
) -> JsonObject:
    """Run fixed retrieval assertions against the deployed corpus revision."""

    checks: list[JsonObject] = []
    modes: set[str] = set()
    for smoke_query in bundle.manifest.smoke_queries:
        expected = bundle.document(smoke_query.expected_document_key)
        response = request_json(
            method="POST",
            url=f"{_api_base(api_url)}/knowledge/search",
            token=token,
            payload={
                "query": smoke_query.query,
                "claim_scope": smoke_query.claim_scope,
                "corpus_revision": bundle.manifest.corpus_revision,
                "filters": {"languages": [expected.request.language]},
                "top_k": 10,
                "score_threshold": 0.05,
            },
        )
        items = response.get("items", [])
        returned_uris = [item.get("source_uri") for item in items if isinstance(item, dict)]
        trace = response.get("trace", {})
        if isinstance(trace, dict) and isinstance(trace.get("retrieval_mode"), str):
            modes.add(trace["retrieval_mode"])
        passed = expected.request.canonical_source_uri in returned_uris
        checks.append(
            {
                "query": smoke_query.query,
                "expected_document_key": expected.document_key,
                "passed": passed,
                "returned_items": len(returned_uris),
            }
        )
    failures = [check for check in checks if not check["passed"]]
    result = {
        "bundle_id": bundle.manifest.bundle_id,
        "corpus_revision": bundle.manifest.corpus_revision,
        "passed": not failures,
        "passed_queries": len(checks) - len(failures),
        "total_queries": len(checks),
        "retrieval_modes": sorted(modes),
        "checks": checks,
    }
    if failures:
        failed_keys = ", ".join(str(item["expected_document_key"]) for item in failures)
        raise KnowledgeBaseToolError(f"knowledge retrieval smoke checks failed: {failed_keys}")
    return result


def _add_bundle_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bundle",
        type=Path,
        default=DEFAULT_BUNDLE,
        help="path to a reviewed manifest.json",
    )
    parser.add_argument(
        "--visibility",
        choices=[scope.value for scope in VisibilityScope],
        help="override the manifest visibility for this deployment",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "plan"):
        command = commands.add_parser(name)
        _add_bundle_argument(command)
    for name in ("apply", "verify"):
        command = commands.add_parser(name)
        _add_bundle_argument(command)
        command.add_argument(
            "--api-url",
            default=os.environ.get("ROUTEPILOT_KNOWLEDGE_API_URL", DEFAULT_API_URL),
            help="trusted RoutePilot API base ending in /api/v1",
        )
        if name == "apply":
            command.add_argument(
                "--allow-public",
                action="store_true",
                help="acknowledge that a global admin is publishing shared knowledge",
            )
    return parser


def _load_from_args(args: argparse.Namespace) -> LoadedKnowledgeBundle:
    visibility = VisibilityScope(args.visibility) if args.visibility else None
    return load_knowledge_bundle(args.bundle, visibility_scope=visibility)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = _load_from_args(args)
        if args.command in {"validate", "plan"}:
            print(json.dumps(bundle_plan(bundle), ensure_ascii=False, indent=2))
            return 0
        token = os.environ.get("ROUTEPILOT_ACCESS_TOKEN", "").strip()
        if not token:
            raise KnowledgeBaseToolError(
                "ROUTEPILOT_ACCESS_TOKEN is required and must come from a restricted operator session"
            )
        if args.command == "apply":
            visibility = bundle.documents[0].request.visibility_scope
            if visibility is VisibilityScope.PUBLIC and not args.allow_public:
                raise KnowledgeBaseToolError(
                    "public knowledge deployment requires the explicit --allow-public acknowledgement"
                )
            result = apply_bundle(bundle, api_url=args.api_url, token=token)
        else:
            result = verify_bundle(bundle, api_url=args.api_url, token=token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KnowledgeBaseToolError, ValueError) as exc:
        print(f"[knowledge] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_BUNDLE",
    "KnowledgeBaseToolError",
    "apply_bundle",
    "build_parser",
    "bundle_plan",
    "main",
    "verify_bundle",
]
