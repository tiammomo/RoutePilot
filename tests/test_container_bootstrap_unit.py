"""Unit tests for dependency-container bootstrap wiring."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.bootstrap_container import initialize_dependency_container  # noqa: E402
from moyuan_web.bootstrap_services import register_default_services  # noqa: E402
from moyuan_web.dependencies.container import Container, build_default_container  # noqa: E402
from moyuan_web.services.chat_service import ChatService  # noqa: E402
from moyuan_web.services.city_service import CityService  # noqa: E402
from moyuan_web.services.map_service import MapService  # noqa: E402
from moyuan_web.services.share_service import ShareService  # noqa: E402


def test_register_default_services_registers_expected_provider_names():
    container = Container()
    register_default_services(container)

    assert container.has_provider("SessionRepository") is True
    assert container.has_provider("SessionService") is True
    assert container.has_provider("ChatService") is True
    assert container.has_provider("CityService") is True
    assert container.has_provider("MapService") is True
    assert container.has_provider("ShareService") is True
    assert container.has_provider("TravelAgent") is True


def test_build_default_container_resolves_singletons():
    container = build_default_container()

    city_service = container.resolve("CityService")
    map_service = container.resolve("MapService")
    share_service = container.resolve("ShareService")
    chat_service = container.resolve("ChatService")

    assert isinstance(city_service, CityService)
    assert isinstance(map_service, MapService)
    assert isinstance(share_service, ShareService)
    assert isinstance(chat_service, ChatService)
    assert container.resolve("CityService") is city_service
    assert container.resolve("MapService") is map_service
    assert container.resolve("ShareService") is share_service
    assert container.resolve("ChatService") is chat_service


def test_initialize_dependency_container_returns_shared_container():
    first = initialize_dependency_container()
    second = initialize_dependency_container()

    assert first is second
    assert first.has_provider("SessionService") is True
