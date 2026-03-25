"""Chat orchestration facade composed from stream, history, and health slices."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from threading import Lock
from typing import Any

from ..repositories.session_repository import SessionRepository
from .chat import ChatHealthMixin, ChatHistoryMixin, ChatStreamMixin

logger = logging.getLogger(__name__)


class ChatService(ChatStreamMixin, ChatHistoryMixin, ChatHealthMixin):
    """Application service facade for end-to-end chat orchestration."""

    VALID_MODES = {"direct", "react", "plan"}
    DEFAULT_HEALTH_WINDOW_MINUTES = 60
    DEFAULT_SLO_THRESHOLDS = {
        "timeout_rate": 0.1,
        "failure_rate": 0.2,
        "fallback_rate": 0.5,
    }

    def __init__(self, repository: SessionRepository):
        """Initialize chat orchestration dependencies and runtime state."""
        self._repository = repository
        self._init_lock = asyncio.Lock()
        self._initialized = False

        self._llm_adapter: Any = None
        self._llm: Any = None
        self._router_llm: Any = None
        self._tools: list[Any] | None = None
        self._memory_manager: Any = None
        self._agent_runtime: Any = None
        self._health_window_minutes = self._parse_int_env(
            "AGENT_HEALTH_WINDOW_MINUTES",
            self.DEFAULT_HEALTH_WINDOW_MINUTES,
            minimum=5,
        )
        self._slo_thresholds = {
            "timeout_rate": self._parse_float_env(
                "AGENT_SLO_TIMEOUT_RATE_THRESHOLD",
                self.DEFAULT_SLO_THRESHOLDS["timeout_rate"],
            ),
            "failure_rate": self._parse_float_env(
                "AGENT_SLO_FAILURE_RATE_THRESHOLD",
                self.DEFAULT_SLO_THRESHOLDS["failure_rate"],
            ),
            "fallback_rate": self._parse_float_env(
                "AGENT_SLO_FALLBACK_RATE_THRESHOLD",
                self.DEFAULT_SLO_THRESHOLDS["fallback_rate"],
            ),
        }
        self._health_metrics_lock = Lock()
        self._health_metrics: deque[dict[str, Any]] = deque()

    async def initialize(self) -> None:
        """Lazily initialize LLM adapter, router model, tool registry, and memory manager."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            from ..bootstrap import ensure_project_paths
            from ..config.runtime import get_llm_config_path
            from agent.travel_agent.graph import TRAVEL_AGENT_SYSTEM_PROMPT
            from agent.travel_agent.llm.langchain_adapter import create_from_yaml_config
            from agent.travel_agent.runtime import AgentRuntime
            from agent.travel_agent.tools.travel_tools import get_travel_tools
            from agent.travel_agent.graph.memory_integration import get_agent_memory_manager

            ensure_project_paths()

            config_path = get_llm_config_path()
            self._llm_adapter = create_from_yaml_config(config_path)
            self._llm = self._llm_adapter.chat_model
            router_cfg = os.getenv("AGENT_ROUTER_LLM_CONFIG", "").strip()
            if router_cfg:
                try:
                    router_adapter = create_from_yaml_config(router_cfg)
                    self._router_llm = router_adapter.chat_model
                except Exception as exc:
                    logger.warning("Failed to initialize router llm from %s: %s", router_cfg, exc)
                    self._router_llm = self._llm
            else:
                self._router_llm = self._llm
            self._tools = get_travel_tools()
            self._memory_manager = get_agent_memory_manager(
                max_history=10,
                summary_threshold=20,
            )
            self._agent_runtime = AgentRuntime(
                llm=self._llm,
                tools=self._tools,
                system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
                memory_manager=self._memory_manager,
                routing_llm=self._router_llm,
            )
            self._initialized = True
            logger.info(
                "Chat runtime initialized with model=%s tools=%d",
                self._llm_adapter.config.get("name"),
                len(self._tools),
            )
