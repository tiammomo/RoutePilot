"""Default dependency-container bootstrap helpers for web services."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from .bootstrap import PROJECT_ROOT, ensure_project_paths

ensure_project_paths()

if TYPE_CHECKING:
    from .dependencies.container import Container


_storage: Any | None = None
_repository: Any | None = None
_session_service: Any | None = None
_chat_service: Any | None = None
_city_service: Any | None = None
_map_service: Any | None = None
_share_service: Any | None = None


def _get_storage():
    """Create or reuse the file-backed session storage singleton."""
    global _storage
    if _storage is None:
        from .storage.session_storage import FileSessionStorage

        session_file = os.path.join(str(PROJECT_ROOT), "data", "sessions", "sessions.json")
        _storage = FileSessionStorage(session_file)
    return _storage


def provide_session_repository():
    """Create or reuse the session repository singleton."""
    global _repository
    if _repository is None:
        from .repositories.session_repository_impl import SessionRepositoryImpl

        _repository = SessionRepositoryImpl(_get_storage())
    return _repository


def provide_session_service():
    """Create or reuse the session service singleton with memory integration."""
    global _session_service
    if _session_service is None:
        from .services.session_service import SessionService

        _session_service = SessionService(provide_session_repository())
    return _session_service


def provide_chat_service():
    """Create or reuse the chat service singleton."""
    global _chat_service
    if _chat_service is None:
        from .services.chat_service import ChatService

        _chat_service = ChatService(provide_session_repository())
    return _chat_service


def provide_city_service():
    """Create or reuse the city service singleton."""
    global _city_service
    if _city_service is None:
        from .services.city_service import CityService

        _city_service = CityService()
    return _city_service


def provide_map_service():
    """Create or reuse the map service singleton."""
    global _map_service
    if _map_service is None:
        from .services.map_service import MapService

        _map_service = MapService()
    return _map_service


def provide_share_service():
    """Create or reuse the share service singleton."""
    global _share_service
    if _share_service is None:
        from .services.share_service import ShareService

        _share_service = ShareService()
    return _share_service


def provide_travel_agent():
    """Build one travel agent instance using configured LLM and tools."""
    from .config.runtime import get_llm_config_path
    from agent.travel_agent.graph.builder import build_travel_agent
    from agent.travel_agent.llm.langchain_adapter import create_from_yaml_config
    from agent.travel_agent.tools.travel_tools import get_travel_tools

    config_path = get_llm_config_path()
    llm_adapter = create_from_yaml_config(config_path)
    llm = llm_adapter.chat_model
    tools = get_travel_tools()
    return build_travel_agent(llm, tools)


def register_default_services(container: "Container") -> None:
    """Register the default web-service providers on the dependency container."""
    container.register("SessionRepository", provide_session_repository)
    container.register("SessionService", provide_session_service)
    container.register("ChatService", provide_chat_service)
    container.register("CityService", provide_city_service)
    container.register("MapService", provide_map_service)
    container.register("ShareService", provide_share_service)
    container.register("TravelAgent", provide_travel_agent)
