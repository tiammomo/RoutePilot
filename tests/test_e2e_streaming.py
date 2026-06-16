"""
端到端集成测试

测试完整的系统集成（v3.x）：
1. Web API 服务器 (含 Agent)
2. SSE 流式响应
"""

import pytest
import httpx
import json
import time
import asyncio
import socket


def _is_local_api_up(host: str = "localhost", port: int = 38083, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _is_local_api_up(),
    reason="requires local API server at localhost:38083",
)


class TestEndToEndStreaming:
    """端到端流式传输测试"""

    @pytest.fixture
    def web_port(self) -> int:
        """Web API 服务器端口"""
        return 38083

    @pytest.fixture
    def web_url(self) -> str:
        """Web API URL (v3.x - Agent 集成到 Web API)"""
        return "http://localhost:38083"

    @pytest.mark.asyncio
    async def test_web_health(self, web_url: str):
        """测试 Web 服务器健康检查"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{web_url}/api/health")
            assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_full_streaming_pipeline(self, web_url: str):
        """测试完整流式管道"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            start_time = time.time()
            event_times = {}

            async with client.stream(
                'POST', f"{web_url}/api/chat/stream",
                json={
                    'message': '云南丽江旅游攻略',
                    'session_id': 'e2e-test-001'
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        elapsed = time.time() - start_time
                        data = json.loads(line[6:])
                        event_type = data.get('type')

                        if event_type not in event_times:
                            event_times[event_type] = []

                        if event_type == 'chunk':
                            event_times[event_type].append({
                                'time': elapsed,
                                'content': data.get('content', '')
                            })
                        else:
                            event_times[event_type] = elapsed

                # 验证管道完整性
                assert 'answer_start' in event_times
                assert 'chunk' in event_times
                assert 'done' in event_times

                # 验证流式特性
                chunks = event_times.get('chunk', [])
                assert len(chunks) > 1, "应该有多个 chunks 证明流式传输"

    @pytest.mark.asyncio
    async def test_multiple_sequential_requests(self, web_url: str):
        """测试多个连续请求"""
        queries = [
            "青岛海鲜",
            "厦门鼓浪屿",
            "哈尔滨冰雪"
        ]

        results = []
        for query in queries:
            async with httpx.AsyncClient(timeout=120.0) as client:
                chunk_count = 0
                async with client.stream(
                    'POST', f"{web_url}/api/chat/stream",
                    json={'message': query, 'session_id': f'seq-{query}'}
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            data = json.loads(line[6:])
                            if data.get('type') == 'chunk':
                                chunk_count += 1
                            elif data.get('type') == 'done':
                                break

                results.append(chunk_count)

        # 验证每个请求都有多个 chunks
        assert all(c > 0 for c in results), "每个请求都应该收到 chunks"
        print(f"Query results: {dict(zip(queries, results))}")


class TestStreamingPerformance:
    """流式性能测试"""

    @pytest.fixture
    def web_url(self) -> str:
        return "http://localhost:38083"

    @pytest.mark.asyncio
    async def test_first_token_latency(self, web_url: str):
        """测试首 token 延迟"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            start_time = time.time()

            async with client.stream(
                'POST', f"{web_url}/api/chat/stream",
                json={'message': '张家界', 'session_id': 'latency-test'}
            ) as response:
                first_chunk_time = None
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        elapsed = time.time() - start_time
                        data = json.loads(line[6:])
                        if data.get('type') == 'chunk':
                            first_chunk_time = elapsed
                            break

                assert first_chunk_time is not None
                print(f"First token latency: {first_chunk_time:.3f}s")

    @pytest.mark.asyncio
    async def test_throughput(self, web_url: str):
        """测试吞吐量"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            start_time = time.time()
            total_chars = 0

            async with client.stream(
                'POST', f"{web_url}/api/chat/stream",
                json={'message': '桂林山水甲天下', 'session_id': 'throughput-test'}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('type') == 'chunk':
                            total_chars += len(data.get('content', ''))
                        elif data.get('type') == 'done':
                            break

            elapsed = time.time() - start_time
            throughput = total_chars / elapsed if elapsed > 0 else 0

            print(f"Total chars: {total_chars}")
            print(f"Elapsed: {elapsed:.3f}s")
            print(f"Throughput: {throughput:.2f} chars/s")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
