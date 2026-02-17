"""
================================================================================
基础设施层 - SSE 流式响应 (Server-Sent Events Streaming)

提供 Server-Sent Events (SSE) 流式响应支持，适用于 LLM 流式输出场景。

功能特点:
- SSE 协议实现
- 流式数据编码
- 心跳保持连接
- 断线自动重连
- 异步流式支持

使用示例:
```python
from infrastructure.streaming import SSEStreamer, StreamEvent

streamer = SSEStreamer()
async for event in streamer.stream_data(data_generator):
    yield f"data: {event}\n\n"
```

================================================================================
"""

import asyncio
import json
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, AsyncGenerator, Callable, Optional, List
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型"""
    MESSAGE = "message"       # 普通消息
    THINKING = "thinking"    # 思考过程
    TOOL_CALL = "tool_call"  # 工具调用
    TOOL_RESULT = "tool_result"  # 工具结果
    DONE = "done"           # 完成信号
    ERROR = "error"         # 错误
    HEARTBEAT = "heartbeat" # 心跳


@dataclass
class StreamEvent:
    """流事件"""
    type: EventType
    data: Any
    event_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_sse_format(self) -> str:
        """转换为 SSE 格式"""
        lines = []

        if self.event_id:
            lines.append(f"id: {self.event_id}")

        lines.append(f"event: {self.type.value}")

        # 序列化数据
        if isinstance(self.data, str):
            content = self.data
        else:
            content = json.dumps(self.data, ensure_ascii=False)

        # 多行数据
        for line in content.split('\n'):
            lines.append(f"data: {line}")

        # 添加元数据（可选）
        if self.metadata:
            meta_str = json.dumps(self.metadata, ensure_ascii=False)
            lines.append(f"meta: {meta_str}")

        # 结束标记
        lines.append("")
        return '\n'.join(lines) + '\n'

    @classmethod
    def message(cls, content: str, event_id: str = None) -> 'StreamEvent':
        """创建消息事件"""
        return cls(type=EventType.MESSAGE, data=content, event_id=event_id)

    @classmethod
    def thinking(cls, thought: str, step: int = None) -> 'StreamEvent':
        """创建思考事件"""
        return cls(
            type=EventType.THINKING,
            data={"thought": thought, "step": step},
            metadata={"step": step}
        )

    @classmethod
    def tool_call(cls, tool_name: str, parameters: Dict = None) -> 'StreamEvent':
        """创建工具调用事件"""
        return cls(
            type=EventType.TOOL_CALL,
            data={"tool": tool_name, "parameters": parameters or {}}
        )

    @classmethod
    def tool_result(cls, tool_name: str, result: Any) -> 'StreamEvent':
        """创建工具结果事件"""
        return cls(
            type=EventType.TOOL_RESULT,
            data={"tool": tool_name, "result": result}
        )

    @classmethod
    def done(cls, final_answer: str = None) -> 'StreamEvent':
        """创建完成事件"""
        return cls(
            type=EventType.DONE,
            data={"answer": final_answer} if final_answer else {"status": "complete"}
        )

    @classmethod
    def error(cls, error_message: str, error_code: str = None) -> 'StreamEvent':
        """创建错误事件"""
        return cls(
            type=EventType.ERROR,
            data={"message": error_message, "code": error_code}
        )

    @classmethod
    def heartbeat(cls) -> 'StreamEvent':
        """创建心跳事件"""
        return cls(type=EventType.HEARTBEAT, data={"timestamp": datetime.now().isoformat()})


class StreamingConfig:
    """流式配置"""

    def __init__(
        self,
        heartbeat_interval: float = 15.0,  # 心跳间隔（秒）
        max_buffer_size: int = 1000,        # 最大缓冲事件数
        reconnect_timeout: float = 300.0,   # 重连超时（秒）
        enable_compression: bool = True,     # 启用压缩
        encoding: str = "utf-8"             # 编码
    ):
        self.heartbeat_interval = heartbeat_interval
        self.max_buffer_size = max_buffer_size
        self.reconnect_timeout = reconnect_timeout
        self.enable_compression = enable_compression
        self.encoding = encoding


class SSEStreamer:
    """
    SSE 流式输出器

    管理 SSE 连接的创建、事件发送和连接维护。
    """

    def __init__(self, config: StreamingConfig = None):
        """
        初始化流式输出器

        Args:
            config: 流式配置
        """
        self.config = config or StreamingConfig()
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._consumers: List[asyncio.Queue] = []
        self._running = False
        self._event_count = 0
        self._start_time: Optional[float] = None

    @property
    def is_running(self) -> bool:
        """检查是否运行中"""
        return self._running

    @property
    def event_count(self) -> int:
        """获取事件数"""
        return self._event_count

    async def start(self) -> None:
        """启动流式服务"""
        self._running = True
        self._start_time = time.time()
        self._event_count = 0
        logger.info("[SSEStreamer] 流式服务已启动")

    async def stop(self) -> None:
        """停止流式服务"""
        self._running = False
        elapsed = time.time() - self._start_time if self._start_time else 0
        logger.info(f"[SSEStreamer] 流式服务已停止，运行时间: {elapsed:.2f}秒，事件数: {self._event_count}")

    async def push_event(self, event: StreamEvent) -> None:
        """
        推送事件

        Args:
            event: 流事件
        """
        if not self._running:
            logger.warning("[SSEStreamer] 服务未运行，事件被丢弃")
            return

        # 生成事件 ID
        if event.event_id is None:
            self._event_count += 1
            event.event_id = f"evt_{self._event_count}"

        # 添加到队列
        try:
            await self._event_queue.put(event)
        except asyncio.QueueFull:
            logger.warning("[SSEStreamer] 事件队列已满，丢弃旧事件")
            try:
                await self._event_queue.get()
                await self._event_queue.put(event)
            except:
                pass

    async def stream_events(
        self,
        client_queue: asyncio.Queue = None
    ) -> AsyncGenerator[str, None]:
        """
        生成 SSE 事件流

        Args:
            client_queue: 客户端队列，用于接收客户端消息

        Yields:
            str: SSE 格式的事件字符串
        """
        last_heartbeat = time.time()
        client_messages = []

        while self._running:
            try:
                # 等待事件，超时发送心跳
                timeout = self.config.heartbeat_interval
                if time.time() - last_heartbeat > timeout / 2:
                    timeout = 0.5

                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=timeout
                )

                # 发送事件
                sse_data = event.to_sse_format()
                yield sse_data

                # 检查是否需要发送心跳
                current_time = time.time()
                if current_time - last_heartbeat > self.config.heartbeat_interval:
                    heartbeat = StreamEvent.heartbeat()
                    yield heartbeat.to_sse_format()
                    last_heartbeat = current_time

                # 检查是否完成
                if event.type == EventType.DONE:
                    break

            except asyncio.TimeoutError:
                # 发送心跳
                if time.time() - last_heartbeat > self.config.heartbeat_interval:
                    heartbeat = StreamEvent.heartbeat()
                    yield heartbeat.to_sse_format()
                    last_heartbeat = time.time()

            except asyncio.CancelledError:
                logger.info("[SSEStreamer] 流式连接已取消")
                break

            except Exception as e:
                logger.error(f"[SSEStreamer] 流式错误: {e}")
                error_event = StreamEvent.error(str(e))
                yield error_event.to_sse_format()

    async def stream_text(self, text_generator: AsyncGenerator[str, None]) -> AsyncGenerator[StreamEvent, None]:
        """
        将文本生成器转换为事件流

        Args:
            text_generator: 文本生成器

        Yields:
            StreamEvent: 消息事件
        """
        async for text in text_generator:
            yield StreamEvent.message(text)

        yield StreamEvent.done()

    async def stream_with_thinking(
        self,
        text_generator: AsyncGenerator[str, None],
        thought_provider: Callable[[], Any] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        带思考过程的流式输出

        Args:
            text_generator: 文本生成器
            thought_provider: 思考内容提供者

        Yields:
            StreamEvent: 事件流
        """
        buffer = ""

        async for text in text_generator:
            buffer += text

            # 分块发送（避免过小的块）
            if len(buffer) >= 10 or text in ['。', '！', '？', '\n']:
                yield StreamEvent.message(buffer)
                buffer = ""

        # 发送剩余内容
        if buffer:
            yield StreamEvent.message(buffer)

        yield StreamEvent.done()

    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "running": self._running,
            "event_count": self._event_count,
            "elapsed_seconds": elapsed,
            "queue_size": self._event_queue.qsize(),
            "heartbeat_interval": self.config.heartbeat_interval
        }


class StreamManager:
    """
    流式连接管理器

    管理多个并发的 SSE 连接。
    """

    def __init__(self, config: StreamingConfig = None):
        """
        初始化管理器

        Args:
            config: 流式配置
        """
        self.config = config or StreamingConfig()
        self._streams: Dict[str, SSEStreamer] = {}
        self._lock = asyncio.Lock()

    async def create_stream(self, stream_id: str = None) -> SSEStreamer:
        """
        创建新的流

        Args:
            stream_id: 流 ID，为空则自动生成

        Returns:
            SSEStreamer: 流式输出器
        """
        if stream_id is None:
            import uuid
            stream_id = str(uuid.uuid4())[:8]

        async with self._lock:
            if stream_id in self._streams:
                raise ValueError(f"流已存在: {stream_id}")

            streamer = SSEStreamer(self.config)
            self._streams[stream_id] = streamer
            await streamer.start()

            logger.info(f"[StreamManager] 创建流: {stream_id}")
            return streamer

    async def get_stream(self, stream_id: str) -> Optional[SSEStreamer]:
        """
        获取流

        Args:
            stream_id: 流 ID

        Returns:
            SSEStreamer: 流式输出器，不存在返回 None
        """
        return self._streams.get(stream_id)

    async def close_stream(self, stream_id: str) -> bool:
        """
        关闭流

        Args:
            stream_id: 流 ID

        Returns:
            bool: 是否成功关闭
        """
        async with self._lock:
            streamer = self._streams.pop(stream_id, None)
            if streamer:
                await streamer.stop()
                logger.info(f"[StreamManager] 关闭流: {stream_id}")
                return True
            return False

    async def close_all(self) -> None:
        """关闭所有流"""
        async with self._lock:
            for stream_id in list(self._streams.keys()):
                await self.close_stream(stream_id)

    def list_streams(self) -> List[str]:
        """列出所有流 ID"""
        return list(self._streams.keys())

    def get_all_info(self) -> List[Dict[str, Any]]:
        """获取所有流信息"""
        return [
            {"stream_id": sid, **streamer.get_connection_info()}
            for sid, streamer in self._streams.items()
        ]


class ChunkProcessor:
    """
    文本分块处理器

    将长文本分割成适合流式传输的块。
    """

    def __init__(
        self,
        chunk_size: int = 20,
        delimiters: str = "。！？；：,.\n"
    ):
        """
        初始化分块器

        Args:
            chunk_size: 默认块大小
            delimiters: 分隔符
        """
        self.chunk_size = chunk_size
        self.delimiters = delimiters

    def process(self, text: str) -> List[str]:
        """
        处理文本

        Args:
            text: 输入文本

        Returns:
            List[str]: 文本块列表
        """
        if not text:
            return []

        chunks = []
        current = ""

        for char in text:
            current += char

            # 检查是否到达分隔符
            if char in self.delimiters:
                chunks.append(current)
                current = ""
            # 检查是否达到最大块大小
            elif len(current) >= self.chunk_size * 2:
                # 在适当位置断开
                chunks.append(current[:self.chunk_size])
                current = current[self.chunk_size:]

        # 添加剩余内容
        if current:
            chunks.append(current)

        return chunks if chunks else [text]

    def process_words(self, text: str, word_count: int = 10) -> List[str]:
        """
        按词数分块

        Args:
            text: 输入文本
            word_count: 每块词数

        Returns:
            List[str]: 文本块列表
        """
        words = text.split()
        chunks = []
        current = []

        for word in words:
            current.append(word)
            if len(current) >= word_count:
                chunks.append(' '.join(current))
                current = []

        if current:
            chunks.append(' '.join(current))

        return chunks


# 便捷函数
def create_sse_streamer(config: StreamingConfig = None) -> SSEStreamer:
    """创建 SSE 流式输出器"""
    return SSEStreamer(config)


def create_stream_manager(config: StreamingConfig = None) -> StreamManager:
    """创建流式连接管理器"""
    return StreamManager(config)


def create_chunk_processor(
    chunk_size: int = 20,
    delimiters: str = "。！？；：,.\n"
) -> ChunkProcessor:
    """创建文本分块处理器"""
    return ChunkProcessor(chunk_size, delimiters)
