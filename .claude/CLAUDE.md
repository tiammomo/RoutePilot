# Shuai-Travel-Agent 项目说明

## 项目概述

基于自定义 ReAct Agent 架构的智能旅游助手系统，提供城市推荐、景点查询、路线规划等功能。采用 **Agent + Web + Frontend** 三层架构，通过 gRPC 实现模块间通信。

## 技术栈

- **前端**: Next.js 16 + React 19 + TypeScript + Zustand + antd 6
- **后端 Web**: FastAPI + Python 3.10+
- **Agent**: 自定义 ReAct 引擎 + gRPC
- **LLM**: MiniMax M2.5 (Anthropic 兼容 API)

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Agent (gRPC) | 50051 | AI 推理服务 |
| Web API | 48081 | FastAPI 服务 |
| Frontend | 43001 | Next.js 开发服务器 |

## 项目结构

```
Shuai-Travel-Agent/
├── agent/                      # AI Agent 模块 (gRPC 服务, 端口 50051)
│   ├── src/
│   │   ├── core/               # ReAct 引擎核心
│   │   │   ├── react_agent.py      # ReAct Agent 实现
│   │   │   ├── travel_agent.py     # 旅游Agent
│   │   │   ├── intent_recognizer.py # LLM 意图识别
│   │   │   ├── style_config.py     # 动态风格配置
│   │   │   ├── travel_tools.py     # 工具系统
│   │   │   └── response_generator.py # 响应生成
│   │   ├── di/                  # 依赖注入容器
│   │   ├── llm/                # LLM 客户端
│   │   │   ├── client.py           # LLM 客户端工厂
│   │   │   ├── factory.py          # 模块导出
│   │   │   └── manager.py          # 模型管理器 (ModelManager)
│   │   ├── memory/              # 记忆系统
│   │   ├── middleware/          # 中间件 (RAG)
│   │   ├── infrastructure/      # 基础设施
│   │   │   ├── http_pool.py      # HTTP 连接池
│   │   │   ├── llm_cache.py     # LLM 响应缓存
│   │   │   └── streaming.py      # SSE 流式输出
│   │   ├── config/             # 配置管理
│   │   └── server.py           # gRPC 服务器
│   ├── tests/                  # 单元测试
│   └── proto/                  # gRPC 协议定义
│
├── web/                        # Web API 模块 (FastAPI, 端口 48081)
│   └── src/
│       ├── routes/             # API 路由
│       ├── services/           # 业务服务
│       ├── repositories/       # 数据仓储
│       └── main.py             # FastAPI 入口
│
├── frontend/                   # 前端模块 (Next.js, 端口 43001)
│   └── src/
│       ├── app/                # App Router
│       ├── components/         # React 组件
│       ├── context/            # React Context
│       ├── hooks/              # 自定义 Hooks
│       ├── stores/             # Zustand 状态管理
│       ├── services/           # API 服务
│       ├── types/              # TypeScript 类型
│       └── utils/              # 工具函数
│
├── docs/                       # 设计文档
│   ├── prd.md                  # 产品需求文档
│   ├── api.md                  # API 接口文档
│   ├── db.md                   # 数据库设计文档
│   ├── ARCHITECTURE.md         # 架构设计文档
│   └── INFRASTRUCTURE.md       # 基础设施文档
│
├── learn_docs/                 # 学习文档
├── config/                     # 配置文件
│   ├── llm_config.yaml           # LLM 模型配置
│   ├── agent_config.yaml        # Agent 行为配置
│   └── infrastructure_config.yaml # 基础设施配置
├── .github/                    # GitHub Actions
│   └── workflows/ci.yml        # CI/CD 配置
├── .env.example                # 环境变量示例
└── requirements.txt            # Python 依赖
```

## 核心组件

### ModelManager (模型管理器)

统一管理 LLM 模型配置，支持模型切换、配置验证和状态检查。

**位置**: `agent/src/llm/manager.py`

**主要类**:
- `ModelManager`: 模型管理器主类
- `ModelInfo`: 模型信息数据类
- `ModelStatus`: 模型状态枚举 (AVAILABLE/LOADING/ERROR/DISABLED)
- `ModelConfigValidator`: 配置验证器

**功能**:
- 动态加载和更新模型配置
- 模型切换无需重启服务
- 线程安全的配置访问
- 自动验证配置有效性

```python
from llm.manager import ModelManager

manager = ModelManager('config/llm_config.yaml')
models = manager.list_models()
manager.switch_model('minimax-m2-5')
```

## 常用命令

```bash
# 启动服务 (在项目根目录)
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 启动 Agent gRPC 服务
python run_agent.py

# 启动 Web API 服务
python run_api.py

# 启动前端开发服务器
cd frontend && npm run dev

# 使用 uv agents 环境
source .venv-agents/bin/activate
uv pip install -r requirements.txt
```

## 技能 (Skills)

### 核心技能

- **ReAct Agent 开发**: 自定义 ReAct 架构实现，无第三方框架依赖
- **意图识别**: LLM 多层意图分析，支持 17+ 种细粒度意图类型
- **工具匹配**: 语义工具匹配，自动学习用户偏好
- **流式响应**: SSE token 级别实时输出
- **模型管理**: ModelManager 统一管理多模型配置

### 调试技能

- **服务调试**: 检查 gRPC/Web/Frontend 服务状态
- **日志查看**: 查看各服务日志定位问题
- **API 测试**: curl 测试 REST API 和 SSE 流式接口
- **模型调试**: 检查 llm_config.yaml 配置有效性

## 环境配置

项目使用 uv 的 agents 环境进行开发，配置在 `.claude/settings.local.json` 中。

**配置文件分层**:
- `config/llm_config.yaml`: LLM API 配置（实际使用，被 git 忽略）
- `config/llm_config.yaml.example`: 配置模板
- `config/agent_config.yaml`: Agent 行为配置
- `config/infrastructure_config.yaml`: 基础设施配置

**环境变量**:
- 复制 `.env.example` 为 `.env` 并填入实际值
- 支持 MiniMax、OpenAI、Anthropic、Google Gemini 等 API Key

## 依赖注入

项目提供依赖注入容器，支持单例和瞬态服务注册。

**位置**: `agent/src/di/__init__.py`

```python
from di import Container, get_container

# 获取全局容器
container = get_container()

# 注册单例服务
container.register_singleton(ILLMClient, AnthropicAdapter)

# ReActTravelAgent 支持依赖注入
from core.travel_agent import ReActTravelAgent

agent = ReActTravelAgent(
    config_manager=config_manager,
    memory_manager=memory_manager,
    llm_client=llm_client
)
```

## HTTP 连接池

**位置**: `agent/src/infrastructure/http_pool.py`

```python
from infrastructure.http_pool import get_http_pool

pool = get_http_pool()
response = pool.get(url)      # GET 请求（带缓存）
response = pool.post(url, json_data=data)  # POST 请求
```

## 单元测试

```bash
# 运行 ConfigManager 测试
cd agent
PYTHONPATH=src python -m pytest tests/test_config_manager.py -v

# 运行 LLM Client 测试
PYTHONPATH=src python -m pytest tests/test_llm_client.py -v
```

## 对话模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `direct` | 直接回答，无推理循环 | 简单问题 |
| `react` | 完整 ReAct 推理循环 | 需要工具调用的复杂问题 |
| `plan` | 结构化计划输出 | 长途旅行规划、多日行程 |

## ReAct 阶段流程

```
阶段一：理解任务
    ├── 解析用户意图
    └── 提取关键实体

阶段二：制定计划
    ├── 制定执行步骤
    └── 确定所需工具

阶段三：执行工具
    ├── 调用工具获取信息
    └── 观察结果并评估

阶段四：生成回答
    ├── 整合工具结果
    └── 生成最终回复
```
