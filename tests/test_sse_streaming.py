"""
SSE 流式传输测试用例

测试完整的流式传输链路：
1. gRPC 服务器流式输出
2. Web API SSE 流式输出
3. Token 级别流式效果验证
"""

import pytest
import httpx
import json
import time
import asyncio
from typing import List, Tuple


class TestSSEStreaming:
    """SSE 流式传输测试类"""

    @pytest.fixture
    def api_url(self) -> str:
        """API 基础 URL"""
        return "http://localhost:38000/api/chat/stream"

    @pytest.fixture
    def sample_query(self) -> str:
        """测试查询"""
        return "北京旅游推荐"

    @pytest.mark.asyncio
    async def test_sse_connection(self, api_url: str, sample_query: str):
        """测试 SSE 连接建立"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                'POST', api_url,
                json={'message': sample_query, 'session_id': 'test-connection'}
            ) as response:
                assert response.status_code == 200
                assert response.headers.get("content-type", "").startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_sse_response_format(self, api_url: str):
        """测试 SSE 响应格式"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                'POST', api_url,
                json={'message': '内蒙古', 'session_id': 'test-format'}
            ) as response:
                events = []
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        events.append(data.get('type'))

                # 验证基本事件类型
                assert 'answer_start' in events
                assert 'chunk' in events
                assert 'done' in events

    @pytest.mark.asyncio
    async def test_token_streaming(self, api_url: str):
        """测试 Token 级别流式输出"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            start_time = time.time()
            chunks: List[Tuple[float, str]] = []

            async with client.stream(
                'POST', api_url,
                json={'message': '上海旅游', 'session_id': 'test-streaming'}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        elapsed = time.time() - start_time
                        data = json.loads(line[6:])
                        msg_type = data.get('type')

                        if msg_type == 'chunk':
                            content = data.get('content', '')
                            chunks.append((elapsed, content))

                        elif msg_type == 'done':
                            break

            # 验证流式效果
            assert len(chunks) > 1, "应该收到多个 chunks 才能证明是流式传输"
            assert all(len(c[1]) > 0 for c in chunks), "每个 chunk 应该包含内容"

            # 计算时间间隔
            if len(chunks) > 1:
                intervals = [chunks[i][0] - chunks[i-1][0] for i in range(1, min(6, len(chunks)))]
                avg_interval = sum(intervals) / len(intervals)
                assert avg_interval > 0, "应该有时间间隔才能证明是流式"

    @pytest.mark.asyncio
    async def test_session_persistence(self, api_url: str):
        """测试会话 ID 持久化"""
        session_id = "test-session-123"

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                'POST', api_url,
                json={'message': '杭州', 'session_id': session_id}
            ) as response:
                received_session_id = None
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('type') == 'session_id':
                            received_session_id = data.get('session_id')
                            break

                assert received_session_id == session_id, "会话 ID 应该保持一致"

    @pytest.mark.asyncio
    async def test_streaming_completion(self, api_url: str):
        """测试流式传输完整结束"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                'POST', api_url,
                json={'message': '成都美食', 'session_id': 'test-completion'}
            ) as response:
                completed = False
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('type') == 'done':
                            completed = True
                            break

                assert completed, "应该收到完成信号"


class TestSSEEventTypes:
    """SSE 事件类型测试"""

    @pytest.fixture
    def api_url(self) -> str:
        return "http://localhost:38000/api/chat/stream"

    @pytest.mark.asyncio
    async def test_answer_start_event(self, api_url: str):
        """测试答案开始事件"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                'POST', api_url,
                json={'message': '三亚', 'session_id': 'test-start'}
            ) as response:
                found_start = False
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('type') == 'answer_start':
                            found_start = True
                            break
                assert found_start

    @pytest.mark.asyncio
    async def test_chunk_event_content(self, api_url: str):
        """测试 chunk 事件内容"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                'POST', api_url,
                json={'message': '西安历史', 'session_id': 'test-chunk'}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('type') == 'chunk':
                            content = data.get('content', '')
                            assert isinstance(content, str), "chunk 内容应该是字符串"
                            break


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
