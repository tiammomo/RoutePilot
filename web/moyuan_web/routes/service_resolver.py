"""Shared route-layer helpers for resolving application services."""

from __future__ import annotations

from typing import Any

from ..dependencies.container import get_container
from ..services.chat_service import ChatService
from ..services.city_service import CityService
from ..services.map_service import MapService
from ..services.session_service import SessionService
from ..services.share_service import ShareService


def resolve_service(name: str) -> Any:
    """Resolve one registered application service from the shared container."""
    return get_container().resolve(name)


def get_chat_service() -> ChatService:
    """Resolve the chat service used by streaming and health routes."""
    return resolve_service("ChatService")


def get_city_service() -> CityService:
    """Resolve the city service used by city lookup routes."""
    return resolve_service("CityService")


def get_map_service() -> MapService:
    """Resolve the map service used by route preview routes."""
    return resolve_service("MapService")


def get_session_service() -> SessionService:
    """Resolve the session service used by session lifecycle routes."""
    return resolve_service("SessionService")


def get_share_service() -> ShareService:
    """Resolve the share service used by share-link routes."""
    return resolve_service("ShareService")
