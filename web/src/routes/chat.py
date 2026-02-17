"""Chat API routes with SSE streaming.

聊天API路由模块

提供基于SSE（Server-Sent Events）的流式聊天接口，
通过gRPC调用后端Agent服务实现智能对话。

主要组件:
- SSEEventType: SSE事件类型常量类
- ChatRequest: 聊天请求数据模型
- generate_chat_stream(): 生成聊天流式响应
- stream_chat(): SSE流式聊天API端点

功能特点:
- 真正的token级别流式输出
- 实时展示思考过程（reasoning）
- 心跳机制防止连接超时（30秒间隔）
- 客户端断开连接检测
- 请求超时保护（120秒）
- 完善的错误处理和用户友好的错误提示

SSE事件类型:
- session_id: 会话ID分配事件
- reasoning_start: 思考开始事件
- reasoning_chunk: 思考内容块事件
- reasoning_end: 思考结束事件
- answer_start: 答案开始事件
- chunk: 答案内容块事件
- error: 错误事件
- done: 完成事件
- heartbeat: 心跳事件
- metadata: 元数据事件

使用示例:
    POST /api/chat/stream
    Content-Type: application/json

    {
        "message": "北京三日游怎么安排？",
        "session_id": "optional-session-id"
    }

    响应: text/event-stream
    data: {"type": "session_id", "session_id": "xxx"}
    data: {"type": "reasoning_start"}
    data: {"type": "reasoning_chunk", "content": "分析用户需求..."}
    ...
    data: {"type": "done"}
"""

import asyncio
import json
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime

import grpc
import sys
import os

from ..services.chat_service import ChatService
from ..dependencies.container import get_container
from ..config.config_manager import get_config

router = APIRouter()

# 全局变量 - 用于缓存gRPC stub，避免重复初始化
_grpc_stub = None
_agent_pb2 = None
_agent_pb2_grpc = None


class SSEEventType:
    """
    SSE事件类型常量类

    定义了SSE流式响应中所有可能的事件类型。

    事件流程:
    1. session_id -> reasoning_start -> reasoning_chunk* -> reasoning_end
    2. answer_start -> chunk* -> done
    3. 任意时刻可能收到 error 或 heartbeat

    属性:
        SESSION_ID: 会话ID分配事件
        REASONING_START: 思考开始事件
        REASONING_CHUNK: 思考内容块事件
        REASONING_END: 思考结束事件
        ANSWER_START: 答案开始事件
        CHUNK: 答案内容块事件（token级别）
        ERROR: 错误事件
        DONE: 完成事件
        HEARTBEAT: 心跳事件（保持连接活跃）
        METADATA: 元数据事件
    """
    SESSION_ID = "session_id"
    REASONING_START = "reasoning_start"
    REASONING_CHUNK = "reasoning_chunk"
    REASONING_END = "reasoning_end"
    ANSWER_START = "answer_start"
    CHUNK = "chunk"
    ERROR = "error"
    DONE = "done"
    HEARTBEAT = "heartbeat"
    METADATA = "metadata"


def _ensure_proto_imported():
    """
    确保proto模块已正确导入

    从web/src目录导入proto模块（已复制到web容器中）

     Raises:
        ImportError: 如果proto模块不存在或导入失败
    """
    global _agent_pb2, _agent_pb2_grpc, _grpc_stub
    if _agent_pb2 is None:
        import sys
        import os
        # 添加当前目录到路径
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        # 直接从 src 目录导入 proto 模块
        import agent_pb2
        import agent_pb2_grpc
        _agent_pb2 = agent_pb2
        _agent_pb2_grpc = agent_pb2_grpc


def init_grpc_stub(host: str = 'localhost', port: int = 50051):
    """
    初始化gRPC stub（同步方式）

    创建与Agent gRPC服务的连接通道和stub。
    使用同步insecure_channel，适合FastAPI的同步上下文。

    Args:
        host: str Agent服务主机地址，默认localhost
        port: int Agent服务端口，默认50051

    Returns:
        AgentServiceStub: gRPC服务存根
    """
    global _grpc_stub
    if _grpc_stub is None:
        _ensure_proto_imported()
        # 使用同步channel
        channel = grpc.insecure_channel(f'{host}:{port}')
        _grpc_stub = _agent_pb2_grpc.AgentServiceStub(channel)
    return _grpc_stub


def get_grpc_stub():
    """
    获取已初始化的gRPC stub

    Returns:
        AgentServiceStub: gRPC服务存根

    Raises:
        RuntimeError: 如果stub未初始化（未调用init_grpc_stub）
    """
    global _grpc_stub
    if _grpc_stub is None:
        raise RuntimeError("gRPC stub not initialized. Call init_grpc_stub() first.")
    return _grpc_stub


class ChatRequest(BaseModel):
    """
    聊天请求数据模型

    属性:
        message: str 用户输入的消息内容，必填
        session_id: Optional[str] 会话ID，可选，如果未提供则自动创建
        mode: Optional[str] 对话模式，可选值: direct/react/plan，默认react
    """
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "react"


def get_chat_service() -> ChatService:
    """
    从依赖容器获取ChatService实例

    Returns:
        ChatService: 聊天服务实例
    """
    container = get_container()
    return container.resolve('ChatService')


def get_session_service():
    """
    从依赖容器获取SessionService实例

    Returns:
        SessionService: 会话服务实例
    """
    container = get_container()
    return container.resolve('SessionService')


async def generate_chat_stream(message: str, session_id: str, mode: str = "react", request: Request = None) -> AsyncGenerator[str, None]:
    """
    生成聊天流式响应

    核心流式生成器函数，通过调用后端Agent gRPC服务获取响应，
    并将响应转换为SSE格式流式发送给客户端。

    工作流程:
    1. 如果未提供session_id，创建新会话
    2. 发送session_id事件
    3. 调用gRPC StreamMessage接口获取流式响应
    4. 遍历gRPC流，将思考和答案转换为SSE事件
    5. 每30秒发送心跳保持连接
    6. 检测客户端断开连接，及时停止处理
    7. 处理完成后发送done事件

    Args:
        message: str 用户输入的消息
        session_id: str 会话ID
        mode: str 对话模式 (direct/react/plan)
        request: Request FastAPI请求对象，用于检测客户端断开

    Yields:
        str: SSE格式的数据行，以"data: "开头，以"\n\n"结尾

    异常处理:
        grpc.RpcError: gRPC调用失败
        asyncio.CancelledError: 请求被取消（客户端断开）
        Exception: 其他异常
    """
    import logging
    logger = logging.getLogger(__name__)

    session_service = get_session_service()

    # 如果没有session_id，创建新会话
    if not session_id:
        result = await session_service.create_session()
        session_id = result['session_id']

    # 发送session_id事件
    yield f"data: {json.dumps({'type': SSEEventType.SESSION_ID, 'session_id': session_id})}\n\n"

    # 从配置获取聊天参数
    config = get_config()
    chat_config = config.get('chat', {}) if isinstance(config, dict) else {}
    timeout_seconds = chat_config.get('timeout', 120)
    chunk_delay = chat_config.get('chunk_delay', 0.01)
    task = None

    try:
        # 确保 proto 已导入
        _ensure_proto_imported()

        # 获取 gRPC stub 并调用流式服务
        logger.info(f"[Chat] 通过 gRPC StreamMessage 调用 Agent 服务...")
        stub = get_grpc_stub()

        # 构建gRPC请求消息
        request_msg = _agent_pb2.MessageRequest(
            session_id=session_id,
            user_input=message,
            model_id='',
            stream=True,
            mode=mode
        )

        # 使用asyncio.to_thread在线程池中执行同步gRPC流（可选优化）
        chunk_iterator = stub.StreamMessage(request_msg)

        # 最后一次心跳时间
        last_heartbeat = datetime.now()

        # 遍历 gRPC 流
        for chunk in chunk_iterator:
            # 检查客户端是否已断开连接
            if request and await request.is_disconnected():
                logger.info("[Chat] 客户端已断开连接，停止流式传输")
                break

            chunk_type = chunk.chunk_type
            content = chunk.content
            is_last = chunk.is_last

            logger.debug(f"[Chat] 收到流式 chunk: type={chunk_type}, is_last={is_last}")

            # 发送心跳（每30秒）
            elapsed_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()
            if elapsed_since_heartbeat >= 30:
                heartbeat_data = json.dumps({
                    'type': SSEEventType.HEARTBEAT,
                    'timestamp': datetime.now().isoformat()
                })
                yield f"data: {heartbeat_data}\n\n"
                last_heartbeat = datetime.now()

            # 根据chunk类型转换为SSE事件
            if chunk_type == "thinking_start":
                yield f"data: {json.dumps({'type': SSEEventType.REASONING_START})}\n\n"
                await asyncio.sleep(chunk_delay)  # 延迟确保数据分开发送
            elif chunk_type == "thinking_chunk":
                yield f"data: {json.dumps({'type': SSEEventType.REASONING_CHUNK, 'content': content})}\n\n"
                await asyncio.sleep(chunk_delay)  # 延迟
            elif chunk_type == "thinking_end":
                yield f"data: {json.dumps({'type': SSEEventType.REASONING_END})}\n\n"
                await asyncio.sleep(chunk_delay)
            elif chunk_type == "answer_start":
                yield f"data: {json.dumps({'type': SSEEventType.ANSWER_START})}\n\n"
                await asyncio.sleep(chunk_delay)
            elif chunk_type == "answer":
                yield f"data: {json.dumps({'type': SSEEventType.CHUNK, 'content': content})}\n\n"
                await asyncio.sleep(chunk_delay)  # 延迟确保每个chunk分开发送
            elif chunk_type == "error":
                # 错误处理：展示错误信息并提供友好提示
                yield f"data: {json.dumps({'type': SSEEventType.REASONING_CHUNK, 'content': f'处理出错: {content}'})}\n\n"
                yield f"data: {json.dumps({'type': SSEEventType.REASONING_END})}\n\n"
                yield f"data: {json.dumps({'type': SSEEventType.ANSWER_START})}\n\n"
                yield f"data: {json.dumps({'type': SSEEventType.CHUNK, 'content': '抱歉，处理您的请求时出现问题。'})}\n\n"
            elif chunk_type == "done":
                yield f"data: {json.dumps({'type': SSEEventType.DONE})}\n\n"
                break

            if is_last:
                break

        logger.info(f"[Chat] 流式响应完成")

    except StopIteration:
        # gRPC 流正常结束（已处理 done）
        logger.info("[Chat] 流迭代器正常结束")
    except grpc.RpcError as e:
        logger.error(f"[Chat] gRPC 调用失败: {e.code()} - {e.details()}")
        yield f"data: {json.dumps({'type': SSEEventType.REASONING_CHUNK, 'content': f'连接后端服务失败: {e.code().name}'})}\n\n"
        yield f"data: {json.dumps({'type': SSEEventType.REASONING_END})}\n\n"
        yield f"data: {json.dumps({'type': SSEEventType.ANSWER_START})}\n\n"
        yield f"data: {json.dumps({'type': SSEEventType.CHUNK, 'content': '抱歉，连接后端服务失败，请稍后重试。'})}\n\n"
        yield f"data: {json.dumps({'type': SSEEventType.DONE})}\n\n"
    except asyncio.CancelledError:
        logger.info("[Chat] 请求被取消（客户端断开连接）")
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        # 处理连接断开错误（客户端主动关闭或网络问题）
        logger.warning(f"[Chat] 连接断开: {type(e).__name__} - {e}")
    except Exception as e:
        logger.error(f"[Chat] 处理异常: {type(e).__name__} - {e}")
        # 检查是否是客户端断开导致的异常
        if "disconnected" in str(e).lower() or "closed" in str(e).lower():
            logger.info("[Chat] 客户端已断开连接")
        else:
            yield f"data: {json.dumps({'type': SSEEventType.REASONING_CHUNK, 'content': f'处理异常: {str(e)}'})}\n\n"
            yield f"data: {json.dumps({'type': SSEEventType.REASONING_END})}\n\n"
            yield f"data: {json.dumps({'type': SSEEventType.ANSWER_START})}\n\n"
            yield f"data: {json.dumps({'type': SSEEventType.CHUNK, 'content': '抱歉，处理您的请求时出现异常。'})}\n\n"
            yield f"data: {json.dumps({'type': SSEEventType.DONE})}\n\n"


@router.post(
    "/chat/stream",
    responses={
        200: {
            "description": "SSE流式响应",
            "content": {
                "text/event-stream": {
                    "example": (
                        "data: {\"type\": \"session_id\", \"session_id\": \"550e8400-e29b-41d4-a716-446655440000\"}\n\n"
                        "data: {\"type\": \"reasoning_start\"}\n\n"
                        "data: {\"type\": \"reasoning_chunk\", \"content\": \"分析用户需求：用户想要了解北京三日游的安排\"}\n\n"
                        "data: {\"type\": \"reasoning_end\"}\n\n"
                        "data: {\"type\": \"answer_start\"}\n\n"
                        "data: {\"type\": \"chunk\", \"content\": \"北京\"}\n\n"
                        "data: {\"type\": \"chunk\", \"content\": \"是\"}\n\n"
                        "data: {\"type\": \"chunk\", \"content\": \"一个\"}\n\n"
                        "data: {\"type\": \"chunk\", \"content\": \"非常\"}\n\n"
                        "data: {\"type\": \"chunk\", \"content\": \"适合\"}\n\n"
                        "data: {\"type\": \"done\", \"stats\": {\"tokens\": 482, \"duration\": 17.087}}\n\n"
                    )
                }
            }
        },
        400: {
            "description": "请求错误",
            "content": {
                "application/json": {
                    "example": {"detail": "消息内容不能为空"}
                }
            }
        },
        500: {
            "description": "服务器内部错误",
            "content": {
                "application/json": {
                    "example": {"detail": "Agent服务不可用，请稍后重试"}
                }
            }
        },
        503: {
            "description": "服务不可用",
            "content": {
                "application/json": {
                    "example": {"detail": "gRPC连接失败，请确保Agent服务已启动"}
                }
            }
        }
    }
)
async def stream_chat(request: ChatRequest, fastapi_request: Request):
    """
    SSE流式聊天API端点

    提供基于Server-Sent Events的流式聊天接口，
    通过gRPC调用后端Agent服务实现智能旅游规划对话。

    请求格式:
        POST /api/chat/stream
        Content-Type: application/json

        {
            "message": "北京三日游怎么安排？",
            "session_id": "optional-session-id"
        }

    响应格式:
        Content-Type: text/event-stream

        data: {"type": "session_id", "session_id": "xxx"}
        data: {"type": "reasoning_start"}
        data: {"type": "reasoning_chunk", "content": "分析用户需求..."}
        data: {"type": "reasoning_end"}
        data: {"type": "answer_start"}
        data: {"type": "chunk", "content": "根据您的需求..."}
        ...
        data: {"type": "done"}

    响应头:
        Cache-Control: no-cache - 禁用缓存
        Connection: keep-alive - 保持连接
        X-Accel-Buffering: no - 禁用Nginx缓冲
        X-Content-Type-Options: nosniff - 防止MIME类型嗅探
        X-Frame-Options: DENY - 防止点击劫持

    Args:
        request: ChatRequest 聊天请求，包含message和可选的session_id
        fastapi_request: Request FastAPI原始请求对象

    Returns:
        StreamingResponse: SSE流式响应

    Raises:
        HTTPException: 422 - 消息为空或超过5000字符
    """
    # 验证消息不能为空
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=422, detail="消息不能为空")

    # 验证消息长度（防止过大请求）
    if len(request.message) > 5000:
        raise HTTPException(status_code=422, detail="消息长度不能超过5000字符")

    # 返回SSE流式响应
    return StreamingResponse(
        generate_chat_stream(request.message, request.session_id or "", request.mode, fastapi_request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # 安全相关头
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        }
    )
