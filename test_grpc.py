#!/usr/bin/env python3
"""gRPC 客户端测试脚本"""

import grpc
import sys
import os

os.chdir('/home/ubuntu/learn_projects/Shuai-Travel-Agent')
sys.path.insert(0, '/home/ubuntu/learn_projects/Shuai-Travel-Agent/agent')
from proto import agent_pb2, agent_pb2_grpc

def test_grpc_health():
    """测试 gRPC 健康检查"""
    print("=== 测试 gRPC 健康检查 ===")
    try:
        channel = grpc.insecure_channel('localhost:50051')
        stub = agent_pb2_grpc.AgentServiceStub(channel)

        request = agent_pb2.HealthRequest()
        response = stub.HealthCheck(request, timeout=5)

        print(f"健康: {response.healthy}")
        print(f"版本: {response.version}")
        channel.close()
        return True
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_grpc_chat():
    """测试 gRPC 聊天"""
    print("\n=== 测试 gRPC 聊天 ===")
    try:
        channel = grpc.insecure_channel('localhost:50051')
        stub = agent_pb2_grpc.AgentServiceStub(channel)

        request = agent_pb2.MessageRequest(
            session_id="test-session-001",
            user_input="推荐一个旅游城市",
            mode="react"
        )

        response = stub.ProcessMessage(request, timeout=60)
        print(f"成功: {response.success}")
        print(f"回答: {response.answer[:300]}..." if len(response.answer) > 300 else f"回答: {response.answer}")
        if hasattr(response.reasoning, 'thinking') and response.reasoning.thinking:
            thinking = response.reasoning.thinking
            print(f"思考: {thinking[:200]}..." if len(thinking) > 200 else f"思考: {thinking}")
        if response.error:
            print(f"错误: {response.error}")
        channel.close()
        return True
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_grpc_health()
    test_grpc_chat()
