"""LangChain 版 Chat API 路由

基于 LangChain + LangGraph 的聊天 API。
支持：
- 真正的 LLM token 级别流式输出
- 工具调用过程流式展示
- Session 持久化
- 会话历史记忆
- 对话摘要压缩
"""

import asyncio
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# 添加 agent 模块路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(project_root, 'agent', 'src'))

# 导入 LangChain 组件
from llm.langchain_adapter import create_from_yaml_config
from tools.travel_tools import get_travel_tools
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 导入 LangGraph
try:
    from graph import (
        build_travel_agent,
        create_initial_state,
        get_agent_memory_manager,
        run_travel_agent_streaming_with_memory,
        TRAVEL_AGENT_SYSTEM_PROMPT
    )
    LANGGRAPH_AVAILABLE = True
except ImportError as e:
    LANGGRAPH_AVAILABLE = False
    logging.warning(f"LangGraph not available: {e}")

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================================
# Session 持久化配置
# ============================================================================
SESSION_DIR = os.path.join(project_root, 'data', 'sessions')
SESSION_FILE = os.path.join(SESSION_DIR, 'sessions.json')
SESSION_EXPIRE_HOURS = 24

_sessions: dict = {}
_session_lock = asyncio.Lock()
_save_lock = threading.Lock()

# LangChain 组件（延迟初始化）
_llm_adapter = None
_llm = None
_tools = None
_agent_graph = None
_memory_manager = None


def _ensure_session_dir():
    Path(SESSION_DIR).mkdir(parents=True, exist_ok=True)


def load_sessions() -> dict:
    _ensure_session_dir()
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_sessions(sessions: dict):
    _ensure_session_dir()
    with _save_lock:
        try:
            with open(SESSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(sessions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")


def cleanup_expired_sessions(sessions: dict):
    now = datetime.now()
    expired = [k for k, s in sessions.items()
               if (now - datetime.fromisoformat(s.get('last_active', now))) > timedelta(hours=SESSION_EXPIRE_HOURS)]
    for k in expired:
        del sessions[k]
    return sessions


def init_langchain():
    """初始化 LangChain 组件"""
    global _llm_adapter, _llm, _tools, _agent_graph, _memory_manager

    if _llm is not None:
        return True

    try:
        # 加载配置
        config_path = os.path.join(project_root, 'config', 'llm_config.yaml')
        _llm_adapter = create_from_yaml_config(config_path)
        _llm = _llm_adapter.chat_model
        logger.info(f"[*] LLM initialized: {_llm_adapter.config.get('name')}")

        # 获取工具
        _tools = get_travel_tools()
        logger.info(f"[*] Loaded {len(_tools)} tools")

        # 构建 Agent（如果 LangGraph 可用）
        if LANGGRAPH_AVAILABLE:
            _agent_graph = build_travel_agent(_llm, _tools)
            logger.info("[*] LangGraph Agent built")

            # 初始化记忆管理器
            _memory_manager = get_agent_memory_manager(
                llm=_llm,
                max_history=10,
                summary_threshold=20
            )
            logger.info("[*] Memory manager initialized")

        return True

    except Exception as e:
        logger.error(f"[!] Failed to initialize LangChain: {e}")
        return False


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "react"


class SSEvent:
    SESSION_ID = "session_id"
    REASONING_START = "reasoning_start"
    REASONING_CHUNK = "reasoning_chunk"
    REASONING_END = "reasoning_end"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    ANSWER_START = "answer_start"
    CHUNK = "chunk"
    ERROR = "error"
    DONE = "done"
    HEARTBEAT = "heartbeat"
    METADATA = "metadata"


async def generate_chat_stream(message: str, session_id: str, mode: str = "react") -> AsyncGenerator[str, None]:
    """生成聊天流式响应 - 使用完整的 LangGraph Agent"""
    global _sessions, _agent_graph, _memory_manager

    # 初始化 LangChain
    if not init_langchain():
        yield f"data: {json.dumps({'type': SSEvent.ERROR, 'content': 'LLM 初始化失败'})}\n\n"
        yield f"data: {json.dumps({'type': SSEvent.DONE})}\n\n"
        return

    # 创建/获取会话
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
        async with _session_lock:
            _sessions[session_id] = {
                "session_id": session_id,
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat()
            }
        save_sessions(_sessions.copy())

    yield f"data: {json.dumps({'type': SSEvent.SESSION_ID, 'session_id': session_id})}\n\n"

    try:
        # 保存用户消息
        async with _session_lock:
            if session_id in _sessions:
                _sessions[session_id]["messages"].append({"role": "user", "content": message})
                _sessions[session_id]["last_active"] = datetime.now().isoformat()

        # 使用带记忆的 LangGraph Agent 流式执行
        if LANGGRAPH_AVAILABLE and _memory_manager:
            answer_content = ""
            answer_started = False  # 标记是否已开始生成答案
            tools_used = []

            try:
                # 发送推理开始
                yield f"data: {json.dumps({'type': SSEvent.REASONING_START})}\n\n"

                # 使用带记忆的 Agent
                async for event in run_travel_agent_streaming_with_memory(
                    user_message=message,
                    llm=_llm,
                    tools=_tools,
                    session_id=session_id,
                    memory_manager=_memory_manager,
                    system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT
                ):
                    event_type = event.get("type")

                    if event_type == "reasoning":
                        yield f"data: {json.dumps({'type': SSEvent.REASONING_CHUNK, 'content': event.get('content', '')})}\n\n"

                    elif event_type == "tool_start":
                        tool_name = event.get("tool", "")
                        tools_used.append(tool_name)
                        yield f"data: {json.dumps({'type': SSEvent.TOOL_START, 'tool': tool_name})}\n\n"

                    elif event_type == "tool_end":
                        tool_name = event.get("tool", "")
                        result = event.get("result", "")
                        yield f"data: {json.dumps({'type': SSEvent.TOOL_END, 'tool': tool_name, 'result': result})}\n\n"

                    elif event_type == "chunk":
                        # 首次收到 chunk 时发射 answer_start
                        if not answer_started:
                            answer_started = True
                            yield f"data: {json.dumps({'type': SSEvent.ANSWER_START})}\n\n"
                        content = event.get("content", "")
                        answer_content += content
                        yield f"data: {json.dumps({'type': SSEvent.CHUNK, 'content': content})}\n\n"

                    elif event_type == "done":
                        # 保存助手消息
                        answer_content = event.get("answer", answer_content)
                        async with _session_lock:
                            if session_id in _sessions:
                                _sessions[session_id]["messages"].append(
                                    {"role": "assistant", "content": answer_content}
                                )

            except Exception as e:
                logger.error(f"Agent execution error: {e}")
                yield f"data: {json.dumps({'type': SSEvent.ERROR, 'content': str(e)})}\n\n"

        else:
            # 回退：使用简单 LLM 流式
            yield f"data: {json.dumps({'type': SSEvent.REASONING_START})}\n\n"

            # 获取历史消息
            async with _session_lock:
                session = _sessions.get(session_id, {"messages": []})
                history = session.get("messages", [])[-10:]

            messages = [
                SystemMessage(content=TRAVEL_AGENT_SYSTEM_PROMPT)
            ]
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

            messages.append(HumanMessage(content=message))

            yield f"data: {json.dumps({'type': SSEvent.REASONING_END})}\n\n"
            yield f"data: {json.dumps({'type': SSEvent.ANSWER_START})}\n\n"

            answer_content = ""
            try:
                async for chunk in _llm.astream(messages):
                    if chunk.content:
                        answer_content += chunk.content
                        yield f"data: {json.dumps({'type': SSEvent.CHUNK, 'content': chunk.content})}\n\n"
            except Exception as e:
                logger.error(f"LLM streaming error: {e}")
                yield f"data: {json.dumps({'type': SSEvent.ERROR, 'content': str(e)})}\n\n"

            # 保存助手消息
            async with _session_lock:
                if session_id in _sessions:
                    _sessions[session_id]["messages"].append(
                        {"role": "assistant", "content": answer_content}
                    )

        # 定期保存
        if len(_sessions.get(session_id, {}).get("messages", [])) % 5 == 0:
            save_sessions(_sessions.copy())

        yield f"data: {json.dumps({'type': SSEvent.DONE})}\n\n"

    except Exception as e:
        logger.error(f"Chat error: {e}")
        yield f"data: {json.dumps({'type': SSEvent.ERROR, 'content': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': SSEvent.DONE})}\n\n"


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest, fastapi_request: Request):
    """SSE 流式聊天端点"""
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=422, detail="消息不能为空")
    if len(request.message) > 5000:
        raise HTTPException(status_code=422, detail="消息长度不能超过5000字符")

    return StreamingResponse(
        generate_chat_stream(request.message, request.session_id or "", request.mode),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# 启动时初始化
@router.on_event("startup")
async def startup():
    """启动时初始化"""
    try:
        if init_langchain():
            global _sessions
            _sessions = cleanup_expired_sessions(load_sessions())
            logger.info(f"[*] Loaded {len(_sessions)} sessions")
    except Exception as e:
        logger.warning(f"[!] Startup init warning: {e}")


@router.on_event("shutdown")
async def shutdown():
    """关闭时保存"""
    save_sessions(_sessions.copy())
    logger.info("[*] Sessions saved")
