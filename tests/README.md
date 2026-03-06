# Tests Directory

## 目录结构

```
tests/
├── README.md                    # 本文件
├── RUN_TESTS.md                # 完整测试运行指南
├── conftest.py                 # pytest 配置和 fixtures
├── test_api_integration.py    # API 集成测试 ✅
├── test_sse_streaming.py       # SSE 流式测试 ✅
└── test_e2e_streaming.py      # 端到端测试 ✅
```

## 快速运行

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_api_integration.py -v
```

## 测试文件说明

| 文件 | 说明 | 状态 |
|------|------|------|
| `test_api_integration.py` | API 集成测试 | ✅ 活跃 |
| `test_sse_streaming.py` | SSE 流式响应测试 | ✅ 活跃 |
| `test_e2e_streaming.py` | 端到端测试 | ✅ 活跃 |

## 测试要求

- Web API 运行在端口 38000
- Python 3.10+
- pytest-asyncio
- httpx

## v3.x 变化

| 对比项 | v2.x | v3.x |
|--------|------|------|
| Agent | 独立 gRPC | 集成到 Web API |
| 端口 | 50051 (gRPC) | 无需 |
| 依赖 | Redis/Milvus/Nacos | 内存存储 |

## Agent 模块测试

Agent 测试位于 `agent/tests/` 目录，包括:
- `test_config_manager.py` - 配置管理器
- `test_langchain_graph.py` - LangGraph 图结构
- `test_infrastructure_modules.py` - 基础设施模块 (部分需要外部服务)
