"""Shared runtime-source adapters for the typed supervisor execution seam."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from config import server_config

if TYPE_CHECKING:
    from .contracts import (
        SupervisorPlanPreviewRequest,
        SupervisorRunRequest,
        SupervisorRuntimeContext,
    )
    from langchain_core.runnables import Runnable
    from langchain_core.tools import Tool
else:
    SupervisorPlanPreviewRequest = Any
    SupervisorRunRequest = Any
    SupervisorRuntimeContext = Any
    Runnable = Any
    Tool = Any

_DEFAULT_CHECKPOINTER = None
_DEFAULT_CHECKPOINTER_SIGNATURE = None


@dataclass(slots=True)
class GraphRuntimeSource:
    """Carry one compiled graph plus the initial state used by runtime execution."""

    agent: Any
    initial_state: dict[str, Any]
    memory_manager: Any


@dataclass(slots=True)
class PlanPreviewSource:
    """Carry one planner-node adapter plus preview state for preview execution."""

    nodes: AgentNodes
    initial_state: dict[str, Any]
    memory_manager: Any


@dataclass(frozen=True, slots=True)
class CheckpointerConfig:
    """Normalized checkpoint backend settings shared by runtime and ops scripts."""

    backend: str
    target: str
    max_checkpoints_per_thread_ns: int
    compaction_interval: int
    pool_min: int = 1
    pool_max: int = 5

    def signature(self) -> tuple[Any, ...]:
        """Return immutable cache key for the configured backend."""

        if self.backend == "postgres":
            return (
                self.backend,
                self.target,
                self.pool_min,
                self.pool_max,
                self.max_checkpoints_per_thread_ns,
                self.compaction_interval,
            )
        return (
            self.backend,
            self.target,
            self.max_checkpoints_per_thread_ns,
            self.compaction_interval,
        )


def build_travel_agent(*args, **kwargs):
    """Lazily import the graph builder to avoid module-import cycles."""

    from .graph.builder import build_travel_agent as _build_travel_agent

    return _build_travel_agent(*args, **kwargs)


def get_agent_memory_manager(*, llm, **kwargs):
    """Lazily import the memory-manager factory for testability and cycle safety."""

    from .graph.memory_integration import get_agent_memory_manager as _get_agent_memory_manager

    return _get_agent_memory_manager(llm=llm, **kwargs)


class AgentStateWithMemory:
    """Lazy proxy that preserves the test monkeypatch surface."""

    @staticmethod
    def create(*args, **kwargs):
        """Delegate state construction to the real memory-integrated state type."""

        from .graph.memory_integration import AgentStateWithMemory as _AgentStateWithMemory

        return _AgentStateWithMemory.create(*args, **kwargs)


class AgentNodes:
    """Lazy proxy that preserves the test monkeypatch surface."""

    def __new__(cls, *args, **kwargs):
        """Instantiate the real graph node container after lazy import."""

        from .graph.nodes import AgentNodes as _AgentNodes

        return _AgentNodes(*args, **kwargs)


def _default_system_prompt() -> str:
    """Return the canonical travel-agent system prompt."""

    from .graph.state import TRAVEL_AGENT_SYSTEM_PROMPT

    return TRAVEL_AGENT_SYSTEM_PROMPT


def _default_sqlite_checkpoint_path() -> str:
    """Return the default on-disk SQLite checkpoint database path."""

    return os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "data",
            "langgraph_checkpoints.sqlite3",
        )
    )


def _parse_positive_int(raw_value: Any, default: int, minimum: int = 1) -> int:
    """Parse a bounded positive integer while falling back to a safe default."""

    try:
        parsed = int(raw_value)
    except Exception:
        return default
    return parsed if parsed >= minimum else default


def _normalize_checkpoint_backend(raw_value: Any) -> str:
    """Normalize checkpoint backend names to the supported runtime set."""

    raw = str(raw_value or "").strip().lower()
    return raw if raw in {"sqlite", "postgres"} else "sqlite"


def _infer_checkpoint_backend(target: Any) -> str | None:
    """Infer checkpoint backend type from a DSN or file URL-like target."""

    raw = str(target or "").strip().lower()
    if not raw:
        return None
    if raw.startswith("postgresql://") or raw.startswith("postgresql+psycopg://"):
        return "postgres"
    if raw.startswith("sqlite"):
        return "sqlite"
    return None


def _checkpoint_pool_sizes() -> tuple[int, int]:
    """Resolve configured database pool bounds for checkpoint persistence."""

    pool_min = _parse_positive_int(os.getenv("MOYUAN_DB_POOL_MIN", server_config.db_pool_min), 1)
    pool_max = _parse_positive_int(os.getenv("MOYUAN_DB_POOL_MAX", server_config.db_pool_max), 5)
    return pool_min, max(pool_min, pool_max)


def resolve_checkpointer_config(
    *,
    backend_override: str | None = None,
    target_override: str | None = None,
    dsn_override: str | None = None,
    max_checkpoints_override: int | None = None,
    compaction_interval_override: int | None = None,
    pool_min_override: int | None = None,
    pool_max_override: int | None = None,
) -> CheckpointerConfig:
    """Resolve one normalized checkpoint backend config from overrides and defaults."""

    backend_source = (
        backend_override
        or ("postgres" if dsn_override else None)
        or _infer_checkpoint_backend(target_override)
        or os.getenv("AGENT_CHECKPOINT_BACKEND", "sqlite")
    )
    backend = _normalize_checkpoint_backend(backend_source)
    max_checkpoints = _parse_positive_int(
        max_checkpoints_override
        if max_checkpoints_override is not None
        else os.getenv("AGENT_CHECKPOINT_MAX_PER_THREAD", "200"),
        200,
    )
    compaction_interval = _parse_positive_int(
        compaction_interval_override
        if compaction_interval_override is not None
        else os.getenv("AGENT_CHECKPOINT_COMPACTION_INTERVAL", "50"),
        50,
    )
    if backend == "postgres":
        database_url = str(
            dsn_override
            or target_override
            or os.getenv("AGENT_CHECKPOINT_DSN")
            or os.getenv("MOYUAN_POSTGRES_DSN")
            or server_config.postgres_dsn
        ).strip()
        if not database_url:
            raise ValueError(
                "AGENT_CHECKPOINT_BACKEND=postgres requires AGENT_CHECKPOINT_DSN or database.postgres_dsn"
            )
        default_pool_min, default_pool_max = _checkpoint_pool_sizes()
        pool_min = _parse_positive_int(
            pool_min_override if pool_min_override is not None else default_pool_min,
            default_pool_min,
        )
        pool_max = _parse_positive_int(
            pool_max_override if pool_max_override is not None else default_pool_max,
            default_pool_max,
        )
        return CheckpointerConfig(
            backend="postgres",
            target=database_url,
            pool_min=pool_min,
            pool_max=max(pool_min, pool_max),
            max_checkpoints_per_thread_ns=max_checkpoints,
            compaction_interval=compaction_interval,
        )

    db_path = os.path.abspath(str(target_override or os.getenv("AGENT_CHECKPOINT_DB", _default_sqlite_checkpoint_path())))
    return CheckpointerConfig(
        backend="sqlite",
        target=db_path,
        max_checkpoints_per_thread_ns=max_checkpoints,
        compaction_interval=compaction_interval,
    )


def create_checkpointer(config: CheckpointerConfig) -> Any:
    """Construct one checkpointer instance from normalized config."""

    if config.backend == "postgres":
        from .graph.postgres_checkpointer import PersistentPostgresSaver

        return PersistentPostgresSaver(
            config.target,
            pool_min=config.pool_min,
            pool_max=config.pool_max,
            max_checkpoints_per_thread_ns=config.max_checkpoints_per_thread_ns,
            compaction_interval=config.compaction_interval,
        )

    from .graph.persistent_checkpointer import PersistentSqliteSaver

    return PersistentSqliteSaver(
        db_path=config.target,
        max_checkpoints_per_thread_ns=config.max_checkpoints_per_thread_ns,
        compaction_interval=config.compaction_interval,
    )


def _dispose_checkpointer(checkpointer: Any) -> None:
    """Dispose a checkpointer-owned SQLAlchemy engine when present."""

    engine = getattr(checkpointer, "_engine", None)
    if engine is None or not hasattr(engine, "dispose"):
        return
    try:
        engine.dispose()
    except Exception:
        return


def close_checkpointer(checkpointer: Any) -> None:
    """Release backend resources held by one checkpointer instance."""

    _dispose_checkpointer(checkpointer)


def reset_default_checkpointer() -> None:
    """Reset the cached default checkpointer so config changes take effect."""

    global _DEFAULT_CHECKPOINTER, _DEFAULT_CHECKPOINTER_SIGNATURE
    if _DEFAULT_CHECKPOINTER is not None:
        _dispose_checkpointer(_DEFAULT_CHECKPOINTER)
    _DEFAULT_CHECKPOINTER = None
    _DEFAULT_CHECKPOINTER_SIGNATURE = None


def create_default_checkpointer() -> Any:
    """Create the shared runtime checkpointer with persistent-first fallback behavior."""

    global _DEFAULT_CHECKPOINTER, _DEFAULT_CHECKPOINTER_SIGNATURE
    config = resolve_checkpointer_config()
    signature = config.signature()
    if _DEFAULT_CHECKPOINTER is not None and signature == _DEFAULT_CHECKPOINTER_SIGNATURE:
        return _DEFAULT_CHECKPOINTER

    if _DEFAULT_CHECKPOINTER is not None:
        _dispose_checkpointer(_DEFAULT_CHECKPOINTER)
        _DEFAULT_CHECKPOINTER = None
        _DEFAULT_CHECKPOINTER_SIGNATURE = None

    try:
        _DEFAULT_CHECKPOINTER = create_checkpointer(config)
        _DEFAULT_CHECKPOINTER_SIGNATURE = signature
        return _DEFAULT_CHECKPOINTER
    except Exception:
        if config.backend == "postgres":
            raise
        try:
            from langgraph.checkpoint.memory import InMemorySaver

            _DEFAULT_CHECKPOINTER = InMemorySaver()
            _DEFAULT_CHECKPOINTER_SIGNATURE = ("memory",)
            return _DEFAULT_CHECKPOINTER
        except Exception:
            return None


def build_memory_graph_source(
    *,
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager: Any = None,
    system_prompt: Optional[str] = None,
    chat_mode: Optional[str] = None,
    run_id: Optional[str] = None,
    routing_llm: Optional[Runnable] = None,
    manager_defaults: dict[str, Any] | None = None,
) -> GraphRuntimeSource:
    """Build the memory-aware graph source used by runtime execution."""

    resolved_system_prompt = system_prompt or _default_system_prompt()
    resolved_manager = memory_manager or get_agent_memory_manager(
        llm=llm,
        **(manager_defaults or {}),
    )
    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=resolved_manager,
        system_prompt=resolved_system_prompt,
        chat_mode=chat_mode,
    )
    if run_id:
        initial_state["run_id"] = run_id

    agent = build_travel_agent(
        llm,
        tools,
        resolved_system_prompt,
        checkpointer=create_default_checkpointer(),
        routing_llm=routing_llm,
    )
    return GraphRuntimeSource(
        agent=agent,
        initial_state=initial_state,
        memory_manager=resolved_manager,
    )


def build_memory_plan_preview_source(
    *,
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager: Any = None,
    system_prompt: Optional[str] = None,
    chat_mode: Optional[str] = None,
    routing_llm: Optional[Runnable] = None,
    manager_defaults: dict[str, Any] | None = None,
) -> PlanPreviewSource:
    """Build the memory-aware preview source used by typed preview paths."""

    resolved_system_prompt = system_prompt or _default_system_prompt()
    resolved_manager = memory_manager or get_agent_memory_manager(
        llm=llm,
        **(manager_defaults or {}),
    )
    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=resolved_manager,
        system_prompt=resolved_system_prompt,
        chat_mode=chat_mode,
    )
    nodes = AgentNodes(llm, tools, resolved_system_prompt, routing_llm=routing_llm)
    return PlanPreviewSource(
        nodes=nodes,
        initial_state=initial_state,
        memory_manager=resolved_manager,
    )


def build_supervisor_streaming_source(
    *,
    request: SupervisorRunRequest,
    context: SupervisorRuntimeContext,
) -> GraphRuntimeSource:
    """Build the memory-aware source for the typed supervisor streaming seam."""

    return build_memory_graph_source(
        user_message=request.user_message,
        llm=context.llm,
        tools=context.tools,
        session_id=request.session_id,
        memory_manager=context.memory_manager,
        system_prompt=request.resolved_system_prompt(_default_system_prompt()),
        chat_mode=request.chat_mode,
        run_id=request.run_id,
        routing_llm=context.routing_llm,
    )


def build_supervisor_plan_preview_source(
    *,
    request: SupervisorPlanPreviewRequest,
    context: SupervisorRuntimeContext,
) -> PlanPreviewSource:
    """Build the memory-aware source for the typed supervisor preview seam."""

    return build_memory_plan_preview_source(
        user_message=request.user_message,
        llm=context.llm,
        tools=context.tools,
        session_id=request.session_id,
        memory_manager=context.memory_manager,
        system_prompt=request.resolved_system_prompt(_default_system_prompt()),
        chat_mode=request.chat_mode,
        routing_llm=context.routing_llm,
    )
