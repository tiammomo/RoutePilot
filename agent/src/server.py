"""
gRPC 服务器模块

本模块提供Agent服务的gRPC服务器实现，支持同步和流式两种消息处理模式。
采用多线程架构处理并发请求，通过队列机制实现思考过程的实时流式输出。

主要组件:
- AsyncThoughtStreamer: 异步思考流式输出器（预留）
- ThoughtStreamer: 同步思考流式输出器，用于实时传递思考过程
- AgentServicer: Agent服务实现类，处理gRPC请求
- serve(): 服务器启动函数

功能特点:
- 真正的token级别流式输出
- 思考过程实时展示
- 线程安全的回调机制
- 自动资源清理，防止内存泄漏
- 支持120秒超时控制

gRPC服务定义:
    - ProcessMessage: 同步处理单条消息
    - StreamMessage: 流式处理消息，实时返回思考和答案
    - HealthCheck: 健康检查接口

运行说明:
    Python 路径应在启动脚本（run_agent.py）中统一配置
    请从项目根目录运行：python run_agent.py
"""

import grpc
from concurrent import futures
import json
import logging
import asyncio
import queue
import threading
import sys
import io
from typing import Iterator
from datetime import datetime

from proto import agent_pb2, agent_pb2_grpc

from core.travel_agent import ReActTravelAgent, ChatMode
from config.config_manager import ConfigManager

# 配置日志，使用 UTF-8 编码以支持中文
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 使用统一的日志配置
from config.logging_config import setup_logging, get_logger
setup_logging(level="INFO", log_dir="logs", env="dev")
logger = get_logger(__name__)


class AsyncThoughtStreamer:
    """
    异步思考流式输出器 - 用于实时传递思考过程（异步版本）

    预留的异步实现，使用asyncio队列进行线程安全的异步通信。
    适用于future的异步gRPC场景。

    属性:
        _queue: asyncio.Queue 异步队列，存储待发送的内容
        _done: bool 标记流式传输是否完成
        _answer_started: bool 标记答案是否已开始发送

    方法:
        put_thought(): 放入思考内容
        put_answer_chunk(): 放入答案内容块（token级别）
        put_answer(): 放入完整答案内容
        put_done(): 标记完成
        put_error(): 放入错误信息
        get(): 获取下一个内容块
        is_done(): 检查是否完成
    """

    def __init__(self):
        self._queue = asyncio.Queue()
        self._done = False
        self._answer_started = False

    async def put_thought(self, content: str, elapsed: float) -> None:
        """放入思考内容"""
        await self._queue.put({"type": "thinking", "content": content, "elapsed": elapsed})

    async def put_answer_chunk(self, chunk: str) -> None:
        """放入答案内容块（用于token级别流式）"""
        await self._queue.put({"type": "answer_chunk", "content": chunk})

    async def put_answer(self, content: str) -> None:
        """放入完整答案内容"""
        await self._queue.put({"type": "answer", "content": content})

    async def put_done(self) -> None:
        """标记完成"""
        self._done = True
        await self._queue.put(None)  # 放入 None 作为完成标记

    async def put_error(self, error: str) -> None:
        """放入错误"""
        await self._queue.put({"type": "error", "content": error})

    async def get(self) -> dict:
        """获取下一个内容块"""
        if self._done and self._queue.empty():
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            return None

    def is_done(self) -> bool:
        return self._done and self._queue.empty()


class ThoughtStreamer:
    """
    思考流式输出器 - 用于实时传递思考过程

    使用threading.Queue实现线程安全的同步队列，
    用于在agent处理线程和gRPC流式输出线程之间传递数据。

    工作流程:
    1. Agent处理过程中，通过回调函数将思考内容和答案块放入队列
    2. gRPC流式输出线程从队列中读取数据并发送给客户端
    3. 处理完成后发送完成信号

    属性:
        _queue: queue.Queue 线程安全队列
        _done: bool 标记流式传输是否完成

    方法:
        put_thought(): 放入思考内容和耗时
        put_answer_chunk(): 放入答案内容块
        put_answer(): 放入完整答案
        put_done(): 标记完成
        put_error(): 放入错误信息
        get(): 获取下一个内容块
        is_done(): 检查是否完成
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._done = False

    def put_thought(self, content: str, elapsed: float) -> None:
        """放入思考内容"""
        self._queue.put({"type": "thinking", "content": content, "elapsed": elapsed})

    def put_answer_chunk(self, chunk: str) -> None:
        """放入答案内容块（用于token级别流式）"""
        self._queue.put({"type": "answer_chunk", "content": chunk})

    def put_answer(self, content: str) -> None:
        """放入完整答案内容"""
        self._queue.put({"type": "answer", "content": content})

    def put_done(self) -> None:
        """标记完成"""
        self._done = True

    def put_error(self, error: str) -> None:
        """放入错误"""
        self._queue.put({"type": "error", "content": error})

    def get(self, timeout: float = None):
        """获取下一个内容块"""
        if self._done and self._queue.empty():
            return None
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_done(self) -> bool:
        return self._done and self._queue.empty()


class AgentServicer:
    """
    Agent gRPC服务实现类

    继承自生成的agent_pb2_grpc.AgentServiceServicer，
    实现所有gRPC服务方法。

    设计特点:
    - 单例模式管理线程池，提高资源利用率
    - 每个请求使用独立的request_id进行追踪和清理
    - 回调机制实现思考过程的实时流式输出
    - 线程安全的异步处理架构

    属性:
        config_path: str 配置文件路径
        agent: ReActTravelAgent Agent实例
        _instances: dict 类变量，存储活跃请求的流式器
        _thread_pool: ThreadPoolExecutor 类变量，共享线程池

    gRPC方法:
        ProcessMessage(): 同步处理单条消息
        StreamMessage(): 流式处理消息
        HealthCheck(): 健康检查
    """

    _instances = {}  # 存储每个请求的流式器
    _thread_pool = None  # 线程池

    def __init__(self, config_path: str = "config/llm_config.yaml"):
        """
        初始化Agent服务

        Args:
            config_path: str LLM配置文件路径，默认为"config/llm_config.yaml"
        """
        self.config_path = config_path
        self.agent = ReActTravelAgent(config_path=config_path)
        logger.info("Agent 服务已初始化")

    @classmethod
    def get_thread_pool(cls):
        """
        获取线程池（单例模式）

        使用ThreadPoolExecutor创建线程池，最大10个工作线程。
        线程名称前缀为"agent_worker"，便于调试和监控。

        Returns:
            ThreadPoolExecutor: 共享的线程池实例
        """
        if cls._thread_pool is None:
            cls._thread_pool = futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="agent_worker")
            logger.info("Agent 线程池已初始化")
        return cls._thread_pool

    @classmethod
    def cleanup_instance(cls, request_id: str):
        """
        安全清理实例，防止内存泄漏

        在流式请求完成后调用，清理该请求的流式器实例。

        Args:
            request_id: str 请求的唯一标识符
        """
        if request_id in cls._instances:
            del cls._instances[request_id]
            logger.debug(f"[Stream-{request_id}] 实例已清理")

    def ProcessMessage(self, request, context):
        """
        处理消息（非流式）

        同步处理单条消息，等待完整结果后返回。
        适用于不需要实时展示思考过程的场景。

        Args:
            request: MessageRequest gRPC请求消息，包含session_id和user_input
            context: grpc.ServicerContext gRPC上下文

        Returns:
            MessageResponse: 包含处理结果的响应消息
        """
        try:
            result = self.agent.process_sync(request.user_input)
            return self._build_response(result, context)
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return self._build_error_response(str(e), context)

    def StreamMessage(self, request, context) -> Iterator:
        """
        处理消息（流式）- 使用线程和队列实现真正流式

        核心流式处理方法，通过多线程和队列实现：
        1. 在独立线程中运行agent处理
        2. 通过回调函数实时收集思考过程和答案
        3. 使用队列在线程间传递数据
        4. 主循环实时读取队列并yield给客户端

        流式输出的内容类型:
        - thinking_start: 思考开始信号
        - thinking_chunk: 思考内容块
        - thinking_end: 思考结束信号
        - answer_start: 答案开始信号
        - answer: 答案内容块（token级别）
        - done: 完成信号
        - error: 错误信息

        Args:
            request: MessageRequest gRPC请求消息
            context: grpc.ServicerContext gRPC上下文

        Yields:
            StreamChunk: 流式数据块
        """
        import uuid
        import time as time_module
        request_id = str(uuid.uuid4())[:8]

        logger.info(f"[Stream-{request_id}] 开始处理流式请求: {request.user_input[:50]}...")

        try:
            # 加载配置
            config = ConfigManager("config/llm_config.yaml")
            chat_config = config.config.get('chat', {})
            chunk_delay = chat_config.get('chunk_delay', 0.02)

            user_input = request.user_input
            mode = request.mode if hasattr(request, 'mode') and request.mode else "react"
            logger.info(f"[Stream-{request_id}] 使用模式: {mode}")

            # 发送思考开始信号
            yield agent_pb2.StreamChunk(chunk_type="thinking_start", content="", is_last=False)

            answer_started = False
            chunk_count = 0
            thinking_sent = False

            # 创建同步队列
            answer_queue = queue.Queue()
            thinking_queue = queue.Queue()
            done_event = threading.Event()
            error_holder = {"error": None}

            # 回调函数
            def on_think(content, elapsed):
                thinking_queue.put((content, elapsed))

            def on_answer_chunk(chunk):
                answer_queue.put(chunk)

            def on_done(result):
                if not result.get("success"):
                    error_holder["error"] = result.get("error", "未知错误")
                done_event.set()

            # 设置回调
            self.agent.react_agent.set_think_stream_callback(on_think)

            # 在线程中运行 agent
            def run_agent():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    # 将字符串模式转换为 ChatMode 枚举
                    try:
                        mode_enum = ChatMode(mode) if isinstance(mode, str) else mode
                    except ValueError:
                        mode_enum = ChatMode.REACT
                    loop.run_until_complete(
                        self.agent.process_with_mode(
                            user_input,
                            mode=mode_enum,
                            answer_callback=on_answer_chunk,
                            done_callback=on_done,
                            thinking_callback=on_think
                        )
                    )
                    loop.close()
                except Exception as e:
                    logger.error(f"[Stream-{request_id}] agent 错误: {e}")
                    error_holder["error"] = str(e)
                    done_event.set()

            # 启动 agent 线程
            thread = threading.Thread(target=run_agent, daemon=True)
            thread.start()

            # 主循环：使用阻塞方式读取队列
            # 这确保了当队列为空时会阻塞，直到 agent 放入新数据
            while True:
                # 首先检查思考队列（带超时）
                try:
                    content, elapsed = thinking_queue.get(timeout=0.05)
                    thinking_text = f"{content}"
                    yield agent_pb2.StreamChunk(chunk_type="thinking_chunk", content=thinking_text, is_last=False)
                    thinking_sent = True
                except queue.Empty:
                    pass

                # 检查答案队列
                try:
                    chunk = answer_queue.get(timeout=0.05)
                    if not answer_started:
                        if thinking_sent:
                            yield agent_pb2.StreamChunk(chunk_type="thinking_end", content="", is_last=False)
                        yield agent_pb2.StreamChunk(chunk_type="answer_start", content="", is_last=False)
                        answer_started = True
                    chunk_count += 1
                    yield agent_pb2.StreamChunk(chunk_type="answer", content=chunk, is_last=False)
                    time_module.sleep(chunk_delay)
                except queue.Empty:
                    pass

                # 检查是否完成
                if done_event.is_set():
                    # 继续读取剩余数据
                    while not answer_queue.empty():
                        try:
                            chunk = answer_queue.get_nowait()
                            if not answer_started:
                                if thinking_sent:
                                    yield agent_pb2.StreamChunk(chunk_type="thinking_end", content="", is_last=False)
                                yield agent_pb2.StreamChunk(chunk_type="answer_start", content="", is_last=False)
                                answer_started = True
                            chunk_count += 1
                            yield agent_pb2.StreamChunk(chunk_type="answer", content=chunk, is_last=False)
                            time_module.sleep(0.02)
                        except queue.Empty:
                            break
                    break

            # 清理
            self.agent.react_agent.set_think_stream_callback(None)

            # 检查错误
            if error_holder["error"]:
                if not answer_started:
                    yield agent_pb2.StreamChunk(chunk_type="thinking_end", content="", is_last=False)
                yield agent_pb2.StreamChunk(chunk_type="error", content=error_holder["error"], is_last=True)
                AgentServicer.cleanup_instance(request_id)
                return

            # 发送完成信号
            yield agent_pb2.StreamChunk(chunk_type="done", content="", is_last=True)
            AgentServicer.cleanup_instance(request_id)
            logger.info(f"[Stream-{request_id}] 流式响应完成 (共 {chunk_count} 个分块)")

        except Exception as e:
            logger.error(f"[Stream-{request_id}] 流式处理异常: {e}")
            yield agent_pb2.StreamChunk(chunk_type="error", content=str(e), is_last=True)
            AgentServicer.cleanup_instance(request_id)

    def _build_response(self, result, context):
        """
        构建响应消息

        将agent处理结果转换为gRPC响应消息格式。

        Args:
            result: dict agent处理结果，包含success、answer、reasoning、history等字段
            context: grpc.ServicerContext gRPC上下文

        Returns:
            MessageResponse: gRPC响应消息
        """
        if result.get("success", False):
            reasoning = result.get("reasoning", {})
            history = result.get("history", [])
            return agent_pb2.MessageResponse(
                success=True,
                answer=result.get("answer", ""),
                reasoning=agent_pb2.ReasoningInfo(
                    text=reasoning.get("text", ""),
                    total_steps=reasoning.get("total_steps", 0),
                    tools_used=reasoning.get("tools_used", [])
                ),
                history=[
                    agent_pb2.HistoryStep(
                        step=step.get("step", 0),
                        thought=agent_pb2.ThoughtInfo(
                            id=step.get("thought", {}).get("id", ""),
                            type=step.get("thought", {}).get("type", ""),
                            content=step.get("thought", {}).get("content", ""),
                            confidence=step.get("thought", {}).get("confidence", 0.0),
                            decision=step.get("thought", {}).get("decision", "")
                        ),
                        action=agent_pb2.ActionInfo(
                            id=step.get("action", {}).get("id", ""),
                            tool_name=step.get("action", {}).get("tool_name", ""),
                            status=step.get("action", {}).get("status", ""),
                            duration=step.get("action", {}).get("duration", 0)
                        ),
                        evaluation=agent_pb2.EvaluationInfo(
                            success=step.get("evaluation", {}).get("success", False),
                            duration=step.get("evaluation", {}).get("duration", 0)
                        )
                    )
                    for step in history
                ]
            )
        else:
            return agent_pb2.MessageResponse(
                success=False,
                error=result.get("error", "未知错误")
            )

    def _build_error_response(self, error: str, context):
        """
        构建错误响应消息

        Args:
            error: str 错误信息
            context: grpc.ServicerContext gRPC上下文

        Returns:
            MessageResponse: 包含错误信息的gRPC响应
        """
        return agent_pb2.MessageResponse(
            success=False,
            error=error
        )

    def HealthCheck(self, request, context):
        """
        健康检查接口

        用于监控服务状态和版本信息。

        Args:
            request: HealthRequest 健康检查请求（空）
            context: grpc.ServicerContext gRPC上下文

        Returns:
            HealthResponse: 包含服务状态、版本和运行状态的响应
        """
        return agent_pb2.HealthResponse(healthy=True, version="1.0.0", status="running")


def serve(config_path: str = "config/llm_config.yaml", port: int = 50051):
    """
    启动 gRPC 服务器

    创建并启动gRPC服务器，注册AgentServicer服务实现。

    Args:
        config_path: str LLM配置文件路径
        port: int 服务监听端口，默认为50051

    Returns:
        grpc.Server: 运行的gRPC服务器实例

    示例:
        >>> server = serve("config/llm_config.yaml", 50051)
        >>> server.wait_for_termination()  # 等待服务器终止
    """
    # 使用同步服务器
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # 添加服务
    agent_servicer = AgentServicer(config_path)
    # 注册 gRPC 服务
    agent_pb2_grpc.add_AgentServiceServicer_to_server(agent_servicer, server)

    server.add_insecure_port(f'[::]:{port}')
    server.start()

    logger.info(f"Agent gRPC 服务器已启动，端口: {port}")
    return server


if __name__ == '__main__':
    import argparse

    # Get project root (parent of agent/)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description='ShuaiTravelAgent gRPC Server')
    parser.add_argument('--config', type=str,
                        default=os.path.join(project_root, 'config', 'llm_config.yaml'),
                        help='Path to config file')
    parser.add_argument('--port', type=int, default=50051,
                        help='Port to listen on')
    args = parser.parse_args()

    config_path = args.config

    logger.info("Starting Agent gRPC Server...")
    logger.info(f"Config: {config_path}")
    logger.info(f"Port: {args.port}")

    server = serve(config_path, args.port)
    logger.info(f"Agent gRPC Server started on port {args.port}")
    logger.info("Press Ctrl+C to stop")
    server.wait_for_termination()
