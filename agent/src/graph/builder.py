from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, AsyncGenerator, Callable, Optional

from langchain_core.runnables import Runnable
from langchain_core.tools import Tool
from langgraph.graph import END, StateGraph

from .nodes import AgentNodes
from .runtime_config import get_runtime_config
from .state import AgentState, TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state

logger = logging.getLogger(__name__)

TOOL_RESULT_PREVIEW_LIMIT = 200
_DEFAULT_CHECKPOINTER = None


def _extract_text_from_chunk(chunk: Any) -> str:
    """Normalize LangChain 1.x chunk payload into plain text."""
    if chunk is None:
        return ""

    content = getattr(chunk, "content", chunk)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return str(content)


def _resolve_stream_events_version() -> str:
    return get_runtime_config().stream_events_version


def _is_answer_complete(answer: str) -> bool:
    text = str(answer or "").strip()
    if len(text) < 8:
        return False
    tail = text[-1]
    return tail in {"。", ".", "！", "!", "？", "?"}


class TravelAgentGraph:
    """LangGraph wrapper for travel-agent orchestration."""

    def __init__(
        self,
        llm: Runnable,
        tools: list[Tool],
        system_prompt: str = TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks: Optional[dict[str, Callable[[dict], list[dict]]]] = None,
        checkpointer: Any = None,
        routing_llm: Optional[Runnable] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.nodes = AgentNodes(llm, tools, system_prompt, planner_hooks=planner_hooks, routing_llm=routing_llm)
        self.checkpointer = checkpointer
        self._graph: Optional[StateGraph] = None

    def build(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("intent", self.nodes.intent_node)
        graph.add_node("strategy", self.nodes.strategy_node)
        graph.add_node("plan", self.nodes.plan_node)
        graph.add_node("execute", self.nodes.execute_node)
        graph.add_node("verify", self.nodes.verify_node)
        graph.add_node("answer", self.nodes.answer_node)
        graph.add_node("direct_answer", self.nodes.direct_answer_node)
        graph.add_node("self_check", self.nodes.self_check_node)

        graph.set_entry_point("intent")
        graph.add_edge("intent", "strategy")
        graph.add_conditional_edges(
            "strategy",
            self.nodes.routing_decision,
            {"plan": "plan", "direct": "direct_answer"},
        )
        graph.add_edge("plan", "execute")
        graph.add_conditional_edges(
            "execute",
            self.nodes.should_continue,
            {"execute": "execute", "answer": "verify"},
        )
        graph.add_conditional_edges(
            "verify",
            self.nodes.verify_decision,
            {"execute": "execute", "answer": "answer"},
        )
        graph.add_edge("answer", "self_check")
        graph.add_edge("direct_answer", "self_check")
        graph.add_edge("self_check", END)

        compile_kwargs = {}
        if self.checkpointer is not None:
            compile_kwargs["checkpointer"] = self.checkpointer

        self._graph = graph.compile(**compile_kwargs)
        logger.info("[Graph Builder] Graph built successfully")
        return self._graph

    @property
    def graph(self) -> StateGraph:
        if self._graph is None:
            self.build()
        return self._graph

    def _build_thread_config(self, state: dict) -> dict[str, dict[str, str]]:
        session_id = state.get("session_id")
        if not session_id:
            return {}
        return {"configurable": {"thread_id": str(session_id)}}

    def invoke(self, state: dict) -> dict:
        config = self._build_thread_config(state)
        resolved_config = config if config else None
        try:
            return self.graph.invoke(state, config=resolved_config)
        except TypeError as exc:
            if "No synchronous function provided" not in str(exc):
                raise
            logger.info("[Graph Builder] Falling back to async invoke due to async-only node execution")
            return self._run_ainvoke_sync(state, resolved_config)

    async def ainvoke(self, state: dict) -> dict:
        config = self._build_thread_config(state)
        return await self.graph.ainvoke(state, config=config if config else None)

    async def astream(self, state: dict):
        config = self._build_thread_config(state)
        async for chunk in self.graph.astream(state, stream_mode="values", config=config if config else None):
            yield chunk

    async def astream_events(self, state: dict):
        config = self._build_thread_config(state)
        async for event in self.graph.astream_events(
            state,
            version=_resolve_stream_events_version(),
            config=config if config else None,
        ):
            yield event

    def _run_ainvoke_sync(self, state: dict, config: dict | None) -> dict:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.graph.ainvoke(state, config=config))

        result_holder: dict[str, Any] = {}
        error_holder: dict[str, Exception] = {}

        def _runner() -> None:
            try:
                result_holder["result"] = asyncio.run(self.graph.ainvoke(state, config=config))
            except Exception as inner_exc:  # pragma: no cover - defensive bridge
                error_holder["error"] = inner_exc

        thread = threading.Thread(target=_runner, name="travel-agent-ainvoke-bridge", daemon=True)
        thread.start()
        thread.join()

        if "error" in error_holder:
            raise error_holder["error"]
        return dict(result_holder.get("result") or {})


def build_travel_agent(
    llm: Runnable,
    tools: list[Tool],
    system_prompt: str = TRAVEL_AGENT_SYSTEM_PROMPT,
    planner_hooks: Optional[dict[str, Callable[[dict], list[dict]]]] = None,
    checkpointer: Any = None,
    routing_llm: Optional[Runnable] = None,
) -> TravelAgentGraph:
    return TravelAgentGraph(
        llm,
        tools,
        system_prompt,
        planner_hooks=planner_hooks,
        checkpointer=checkpointer,
        routing_llm=routing_llm,
    )


def _create_default_checkpointer():
    global _DEFAULT_CHECKPOINTER
    if _DEFAULT_CHECKPOINTER is not None:
        return _DEFAULT_CHECKPOINTER
    try:
        from .persistent_checkpointer import PersistentSqliteSaver

        default_db_path = os.path.abspath(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "..",
                "data",
                "langgraph_checkpoints.sqlite3",
            )
        )
        db_path = os.getenv("AGENT_CHECKPOINT_DB", default_db_path)
        max_checkpoints = int(os.getenv("AGENT_CHECKPOINT_MAX_PER_THREAD", "200"))
        compaction_interval = int(os.getenv("AGENT_CHECKPOINT_COMPACTION_INTERVAL", "50"))
        _DEFAULT_CHECKPOINTER = PersistentSqliteSaver(
            db_path=db_path,
            max_checkpoints_per_thread_ns=max_checkpoints,
            compaction_interval=compaction_interval,
        )
        logger.info("[Graph Builder] Persistent checkpointer enabled: %s", db_path)
        return _DEFAULT_CHECKPOINTER
    except Exception as exc:
        logger.warning("[Graph Builder] Persistent checkpointer unavailable, fallback to memory: %s", exc)
        try:
            from langgraph.checkpoint.memory import InMemorySaver

            _DEFAULT_CHECKPOINTER = InMemorySaver()
            return _DEFAULT_CHECKPOINTER
        except Exception as inner_exc:
            logger.warning("[Graph Builder] Unable to create fallback checkpointer: %s", inner_exc)
            return None


async def run_travel_agent(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    system_prompt: str | None = None,
    run_id: str | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    agent = build_travel_agent(
        llm,
        tools,
        system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=_create_default_checkpointer(),
        routing_llm=routing_llm,
    )
    initial_state = create_initial_state(
        user_message=user_message,
        session_id=session_id,
        system_message=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        run_id=run_id,
    )
    result = await agent.ainvoke(initial_state)
    return {
        "success": True,
        "answer": result.get("answer", ""),
        "intent": result.get("intent"),
        "tools_used": result.get("tools_used", []),
        "reasoning": result.get("reasoning"),
        "messages": result.get("messages", []),
    }


async def run_travel_agent_streaming(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    system_prompt: str | None = None,
    run_id: str | None = None,
    on_token: Callable | None = None,
    on_tool_start: Callable | None = None,
    on_tool_end: Callable | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    agent = build_travel_agent(
        llm,
        tools,
        system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=_create_default_checkpointer(),
        routing_llm=routing_llm,
    )
    initial_state = create_initial_state(
        user_message=user_message,
        session_id=session_id,
        system_message=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        run_id=run_id,
    )

    answer = ""
    tools_used: list[str] = []

    async for event in agent.astream_events(initial_state):
        event_type = event.get("event")

        if event_type == "on_chat_model_stream":
            chunk = _extract_text_from_chunk((event.get("data") or {}).get("chunk"))
            if chunk:
                answer += chunk
                if on_token:
                    await on_token(chunk)

        elif event_type == "on_tool_start":
            tool_name = event.get("name", "")
            tools_used.append(tool_name)
            if on_tool_start:
                await on_tool_start(tool_name)

        elif event_type == "on_tool_end":
            tool_name = event.get("name", "")
            result = (event.get("data") or {}).get("output")
            if on_tool_end:
                await on_tool_end(tool_name, result)

    return {"success": True, "answer": answer, "tools_used": tools_used, "run_id": run_id}


async def run_travel_agent_with_memory(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager=None,
    system_prompt: str | None = None,
    on_token: Callable | None = None,
    on_tool_start: Callable | None = None,
    on_tool_end: Callable | None = None,
    persist_memory: bool = True,
    run_id: str | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    from .memory_integration import AgentStateWithMemory, get_agent_memory_manager

    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm, max_history=10, summary_threshold=15)

    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    if run_id:
        initial_state["run_id"] = run_id

    agent = build_travel_agent(
        llm,
        tools,
        system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=_create_default_checkpointer(),
        routing_llm=routing_llm,
    )

    answer = ""
    tools_used: list[str] = []
    async for event in agent.astream_events(initial_state):
        event_type = event.get("event")
        if event_type == "on_chat_model_stream":
            content = _extract_text_from_chunk((event.get("data") or {}).get("chunk"))
            if content:
                answer += content
                if on_token:
                    await on_token(content)
        elif event_type == "on_tool_start":
            tool_name = event.get("name", "")
            tools_used.append(tool_name)
            if on_tool_start:
                await on_tool_start(tool_name)
        elif event_type == "on_tool_end":
            tool_name = event.get("name", "")
            result = (event.get("data") or {}).get("output")
            if on_tool_end:
                await on_tool_end(tool_name, result)

    if persist_memory:
        await memory_manager.add_message(session_id, "user", user_message)
        await memory_manager.add_message(session_id, "assistant", answer)

    return {
        "success": True,
        "answer": answer,
        "tools_used": tools_used,
        "session_id": session_id,
        "run_id": run_id,
    }


async def run_travel_agent_streaming_with_memory(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager=None,
    system_prompt: str | None = None,
    persist_memory: bool = True,
    run_id: str | None = None,
    routing_llm: Runnable | None = None,
):
    from .memory_integration import AgentStateWithMemory, get_agent_memory_manager

    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm)

    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    if run_id:
        initial_state["run_id"] = run_id

    agent = build_travel_agent(
        llm,
        tools,
        system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=_create_default_checkpointer(),
        routing_llm=routing_llm,
    )

    answer = ""
    tools_used: list[str] = []
    final_state: dict[str, Any] = {}
    stage = "parse"
    progress = 5

    try:
        yield {"type": "stage", "stage": stage, "progress": progress, "label": "解析需求"}
        async for event in agent.astream_events(initial_state):
            event_type = event.get("event")

            if event_type == "on_node_start":
                node_name = event.get("name", "")
                if node_name == "intent":
                    stage = "parse"
                    progress = 10
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "解析需求"}
                    yield {"type": "reasoning", "content": "分析用户意图..."}
                elif node_name == "strategy":
                    stage = "parse"
                    progress = 18
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "选择策略"}
                    yield {"type": "reasoning", "content": "选择 ReAct 子策略..."}
                elif node_name == "plan":
                    stage = "query"
                    progress = 25
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "生成计划"}
                    yield {"type": "reasoning", "content": "制定执行计划..."}
                elif node_name == "execute":
                    stage = "query"
                    progress = 45
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "查询数据"}
                    yield {"type": "reasoning", "content": "执行工具..."}
                elif node_name in {"answer", "direct_answer"}:
                    stage = "generate"
                    progress = 80
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "生成方案"}
                elif node_name == "verify":
                    stage = "generate"
                    progress = 72
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "验证结果一致性"}
                    yield {"type": "reasoning", "content": "校验价格/政策/日期一致性..."}
                elif node_name == "self_check":
                    stage = "finalize"
                    progress = 95
                    yield {"type": "stage", "stage": stage, "progress": progress, "label": "自检答案完整性"}

            elif event_type == "on_chat_model_stream":
                content = _extract_text_from_chunk((event.get("data") or {}).get("chunk"))
                if content:
                    answer += content
                    yield {"type": "chunk", "content": content}

            elif event_type == "on_tool_start":
                tool_name = event.get("name", "")
                tools_used.append(tool_name)
                progress = min(75, progress + 5)
                yield {"type": "stage", "stage": "query", "progress": progress, "label": f"查询数据: {tool_name}"}
                yield {"type": "tool_start", "tool": tool_name, "progress": progress}

            elif event_type == "on_tool_end":
                tool_name = event.get("name", "")
                result = (event.get("data") or {}).get("output")
                yield {
                    "type": "tool_end",
                    "tool": tool_name,
                    "result": str(result)[:TOOL_RESULT_PREVIEW_LIMIT],
                    "progress": progress,
                }
            elif event_type == "on_chain_end":
                output = (event.get("data") or {}).get("output")
                if isinstance(output, dict) and ("answer" in output or "execution_stats" in output):
                    final_state = output

    except Exception:
        if persist_memory and memory_manager is not None:
            try:
                await memory_manager.add_message(session_id, "user", user_message)
                await memory_manager.add_message(session_id, "assistant", f"[INTERRUPTED]{answer}")
            except Exception:
                pass
        raise

    if persist_memory:
        await memory_manager.add_message(session_id, "user", user_message)
        await memory_manager.add_message(session_id, "assistant", answer)

    execution_stats = final_state.get("execution_stats", {})
    plan_id = final_state.get("plan_id")
    intent = final_state.get("intent")
    if not execution_stats and isinstance(final_state, dict):
        execution_stats = final_state.get("execution_stats", {})

    if not _is_answer_complete(answer):
        fallback_text = "已完成主要步骤，但当前回复可能不完整。请告诉我你希望我优先补充预算、行程还是酒店。"
        if answer:
            answer = f"{answer.rstrip()} {fallback_text}"
        else:
            answer = fallback_text

    yield {"type": "stage", "stage": "finalize", "progress": 100, "label": "完整性检查"}
    yield {
        "type": "done",
        "answer": answer,
        "tools_used": tools_used,
        "session_id": session_id,
        "run_id": run_id,
        "plan_id": plan_id,
        "intent": intent,
        "execution_stats": execution_stats,
    }


def generate_plan_preview_with_memory(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager=None,
    system_prompt: str | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    from .memory_integration import AgentStateWithMemory, get_agent_memory_manager

    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm)

    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
    )

    nodes = AgentNodes(llm, tools, system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT, routing_llm=routing_llm)
    intent_state = dict(initial_state)
    intent_state.update(nodes.intent_node(intent_state))
    plan_state = dict(intent_state)
    plan_state.update(nodes.plan_node(intent_state))

    return {
        "plan_id": plan_state.get("plan_id"),
        "intent": plan_state.get("intent"),
        "intent_detail": plan_state.get("intent_detail", {}),
        "plan_explanation": plan_state.get("plan_explanation"),
        "validation_status": plan_state.get("validation_status", "pass"),
        "validation_errors": plan_state.get("validation_errors", []),
        "plan": plan_state.get("plan", []),
    }


def get_tool_health_diagnostics() -> dict[str, Any]:
    return {
        "runtime_config": get_runtime_config().to_dict(),
        **AgentNodes.get_global_tool_health_snapshot(),
    }
