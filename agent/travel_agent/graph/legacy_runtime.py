"""Legacy graph execution entrypoints kept outside the graph assembly module."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from langchain_core.runnables import Runnable
from langchain_core.tools import Tool

from ..contracts import (
    SupervisorChunkEvent,
    SupervisorDoneEvent,
    SupervisorPlanPreview,
    SupervisorPlanPreviewRequest,
    SupervisorReasoningEvent,
    SupervisorRunRequest,
    SupervisorRuntimeContext,
    SupervisorStageEvent,
    SupervisorToolEndEvent,
    SupervisorToolStartEvent,
)
from .nodes import AgentNodes
from .runtime_config import get_runtime_config
from .state import TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state

TOOL_RESULT_PREVIEW_LIMIT = 200
_DEFAULT_CHECKPOINTER = None


async def stream_supervisor_run(
    *,
    request: SupervisorRunRequest,
    context: SupervisorRuntimeContext,
):
    """Bridge one supervisor-stream request into the legacy graph runtime shim."""
    async for event in run_travel_agent_streaming_with_memory(
        user_message=request.user_message,
        llm=context.llm,
        tools=context.tools,
        session_id=request.session_id,
        memory_manager=context.memory_manager,
        system_prompt=request.system_prompt,
        persist_memory=request.persist_memory,
        run_id=request.run_id,
        chat_mode=request.chat_mode,
        routing_llm=context.routing_llm,
    ):
        yield event


def generate_supervisor_plan_preview(
    *,
    request: SupervisorPlanPreviewRequest,
    context: SupervisorRuntimeContext,
) -> SupervisorPlanPreview:
    """Bridge one supervisor preview request into the legacy graph runtime shim."""
    return SupervisorPlanPreview.from_dict(
        generate_plan_preview_with_memory(
            user_message=request.user_message,
            llm=context.llm,
            tools=context.tools,
            session_id=request.session_id,
            memory_manager=context.memory_manager,
            system_prompt=request.system_prompt,
            chat_mode=request.chat_mode,
            routing_llm=context.routing_llm,
        )
    )


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


def _is_answer_complete(answer: str) -> bool:
    """Heuristically detect whether generated answer text appears complete for early-stop control."""
    text = str(answer or "").strip()
    if len(text) < 8:
        return False
    tail = text[-1]
    return tail in {"。", ".", "！", "!", "？", "?"}


def _create_default_checkpointer():
    """Create default checkpointer with persistent-first and memory-fallback strategy."""
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
        return _DEFAULT_CHECKPOINTER
    except Exception:
        try:
            from langgraph.checkpoint.memory import InMemorySaver

            _DEFAULT_CHECKPOINTER = InMemorySaver()
            return _DEFAULT_CHECKPOINTER
        except Exception:
            return None


async def run_travel_agent(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    system_prompt: str | None = None,
    run_id: str | None = None,
    chat_mode: str | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    """Run the graph once in non-streaming mode and return final answer/result fields."""
    from .builder import build_travel_agent

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
        chat_mode=chat_mode,
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
    chat_mode: str | None = None,
    on_token: Callable | None = None,
    on_tool_start: Callable | None = None,
    on_tool_end: Callable | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    """Run the graph in streaming mode and yield normalized chunks for UI consumption."""
    from .builder import build_travel_agent

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
        chat_mode=chat_mode,
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
    chat_mode: str | None = None,
    on_token: Callable | None = None,
    on_tool_start: Callable | None = None,
    on_tool_end: Callable | None = None,
    persist_memory: bool = True,
    run_id: str | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    """Run non-streaming graph execution with memory context injection."""
    from .builder import build_travel_agent
    from .memory_integration import AgentStateWithMemory, get_agent_memory_manager

    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm, max_history=10, summary_threshold=15)

    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        chat_mode=chat_mode,
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
    chat_mode: str | None = None,
    routing_llm: Runnable | None = None,
):
    """Run streaming graph execution with memory context and normalized event payloads."""
    from .builder import build_travel_agent
    from .memory_integration import AgentStateWithMemory, get_agent_memory_manager

    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm)

    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        chat_mode=chat_mode,
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
        yield SupervisorStageEvent(stage=stage, progress=progress, label="解析需求").to_dict()
        async for event in agent.astream_events(initial_state):
            event_type = event.get("event")

            if event_type == "on_node_start":
                node_name = event.get("name", "")
                if node_name == "intent":
                    stage = "parse"
                    progress = 10
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="解析需求").to_dict()
                    yield SupervisorReasoningEvent(content="分析用户意图...").to_dict()
                elif node_name == "strategy":
                    stage = "parse"
                    progress = 18
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="选择策略").to_dict()
                    yield SupervisorReasoningEvent(content="选择 ReAct 子策略...").to_dict()
                elif node_name == "plan":
                    stage = "query"
                    progress = 25
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="生成计划", subagent="planning").to_dict()
                    yield SupervisorReasoningEvent(content="制定执行计划...").to_dict()
                elif node_name == "react":
                    stage = "query"
                    progress = 25
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="ReAct 执行计划", subagent="planning").to_dict()
                    yield SupervisorReasoningEvent(content="进入 ReAct 工具编排...").to_dict()
                elif node_name == "execute":
                    stage = "query"
                    progress = 45
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="查询数据", subagent="research").to_dict()
                    yield SupervisorReasoningEvent(content="执行工具...").to_dict()
                elif node_name in {"answer", "direct_answer"}:
                    stage = "generate"
                    progress = 80
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="生成方案").to_dict()
                elif node_name == "verify":
                    stage = "generate"
                    progress = 72
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="验证结果一致性", subagent="verification").to_dict()
                    yield SupervisorReasoningEvent(content="校验价格/政策/日期一致性...").to_dict()
                elif node_name == "self_check":
                    stage = "finalize"
                    progress = 95
                    yield SupervisorStageEvent(stage=stage, progress=progress, label="自检答案完整性").to_dict()

            elif event_type == "on_chat_model_stream":
                content = _extract_text_from_chunk((event.get("data") or {}).get("chunk"))
                if content:
                    answer += content
                    yield SupervisorChunkEvent(content=content).to_dict()

            elif event_type == "on_tool_start":
                tool_name = event.get("name", "")
                tools_used.append(tool_name)
                progress = min(75, progress + 5)
                yield SupervisorStageEvent(stage="query", progress=progress, label=f"查询数据: {tool_name}").to_dict()
                yield SupervisorToolStartEvent(tool=tool_name, progress=progress).to_dict()

            elif event_type == "on_tool_end":
                tool_name = event.get("name", "")
                result = (event.get("data") or {}).get("output")
                yield SupervisorToolEndEvent(
                    tool=tool_name,
                    result=str(result)[:TOOL_RESULT_PREVIEW_LIMIT],
                    progress=progress,
                ).to_dict()
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
    execution_summary = final_state.get("execution_summary", {}) or {}
    verify_result = final_state.get("verify_result", {}) or {}
    strategy_detail = final_state.get("strategy_detail", {}) or {}
    tool_results = final_state.get("tool_results", {}) or {}
    plan_id = final_state.get("plan_id")
    intent = final_state.get("intent")
    if not execution_stats and isinstance(final_state, dict):
        execution_stats = final_state.get("execution_stats", {})
    verification_passed: Optional[bool]
    if isinstance(verify_result, dict) and "passed" in verify_result:
        verification_passed = bool(verify_result.get("passed"))
    elif bool(strategy_detail.get("requires_verification", False)):
        verification_passed = False
    else:
        verification_passed = True

    fallback_steps = int(execution_summary.get("fallback_steps", 0) or 0)
    if fallback_steps <= 0 and isinstance(execution_stats, dict):
        stats_steps = list(execution_stats.get("steps", []) or [])
        fallback_steps = sum(1 for item in stats_steps if bool(item.get("fallback_used", False)))

    stale_result_count = sum(
        1
        for result in (tool_results.values() if isinstance(tool_results, dict) else [])
        if isinstance(result, dict) and bool(result.get("success")) and bool(result.get("is_stale", False))
    )

    if not _is_answer_complete(answer):
        fallback_text = "已完成主要步骤，但当前回复可能不完整。请告诉我你希望我优先补充预算、行程还是酒店。"
        if answer:
            answer = f"{answer.rstrip()} {fallback_text}"
        else:
            answer = fallback_text

    yield SupervisorStageEvent(stage="finalize", progress=100, label="完整性检查").to_dict()
    yield SupervisorDoneEvent(
        answer=answer,
        tools_used=tools_used,
        session_id=session_id,
        run_id=run_id,
        plan_id=plan_id,
        intent=intent,
        execution_stats=execution_stats,
        verification_passed=verification_passed,
        stale_result_count=stale_result_count,
        fallback_steps=fallback_steps,
    ).to_dict()


def generate_plan_preview_with_memory(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager=None,
    system_prompt: str | None = None,
    chat_mode: str | None = None,
    routing_llm: Runnable | None = None,
) -> dict:
    """Generate a memory-aware plan preview without executing full tool orchestration."""
    from .memory_integration import AgentStateWithMemory, get_agent_memory_manager

    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm)

    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT,
        chat_mode=chat_mode,
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
    """Return aggregated tool-health diagnostics for monitoring and health endpoints."""
    return {
        "runtime_config": get_runtime_config().to_dict(),
        **AgentNodes.get_global_tool_health_snapshot(),
    }
