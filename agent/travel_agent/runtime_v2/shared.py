"""Shared provenance and immutable Artifact helpers for Runtime V2."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from routepilot_contracts.common import (
    ActorRef,
    ArtifactBase,
    ArtifactRef,
    ArtifactType,
    SourceKind,
    SourceRef,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Return a contract-safe, non-sequential identifier."""

    return f"{prefix}_{secrets.token_hex(12)}"


def system_actor(component: str) -> ActorRef:
    return ActorRef(actor_type="service", actor_id=f"service:{component}")


def system_source(component: str, version: str) -> SourceRef:
    now = utc_now()
    return SourceRef(
        source_id=f"source:{component}",
        kind=SourceKind.SYSTEM,
        name=component,
        version=version,
        retrieved_at=now,
        publisher="RoutePilot",
        license="internal",
    )


def artifact_ref(artifact: ArtifactBase, artifact_type: ArtifactType) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=artifact_type,
        artifact_id=artifact.artifact_id,
        schema_version=artifact.schema_version,
        version=artifact.version,
    )
