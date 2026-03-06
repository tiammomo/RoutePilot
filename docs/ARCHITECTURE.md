# 系统架构设计

## 1. 架构概述

小帅旅游助手采用 **三层架构设计**：

1. **Frontend (前端层)** - Next.js + React 用户界面
2. **Web API (API 层)** - FastAPI 提供 REST API
3. **Agent (Agent 层)** - LangChain + LangGraph 智能推理

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                       │
│                  http://localhost:33001                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   ChatArea  │  │   Sidebar   │  │ MessageList │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP + SSE
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Web API (FastAPI)                      │
│                  http://localhost:38000                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ /chat/stream │  │  /sessions   │  │   /health   │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│         │                │                                  │
│         ▼                ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LangGraph Agent                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │   │
│  │  │  Intent  │─▶│   Plan   │─▶│ Execute  │      │   │
│  │  │  Router  │  │  Builder │  │  Tools   │      │   │
│  │  └──────────┘  └──────────┘  └──────────┘      │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM Providers                            │
│              MiniMax M2.5, OpenAI, Claude                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | Next.js | 16.x |
| UI 组件 | antd | 6.x |
| 状态管理 | Zustand | 5.x |
| 后端框架 | FastAPI | 0.109+ |
| Agent 框架 | LangChain + LangGraph | 0.3+ |
| LLM | MiniMax M2.5 | - |

---

## 4. 核心模块

### 4.1 Agent 模块 (`agent/src/`)

```
agent/src/
├── config/           # 配置管理
│   ├── config_manager.py    # YAML 配置加载
│   └── settings.py          # 配置模型
├── graph/           # LangGraph 核心
│   ├── state.py            # AgentState 状态定义
│   ├── nodes.py            # 节点实现 (Intent, Plan, Execute)
│   ├── builder.py          # 图构建器
│   └── memory_integration.py # 记忆集成
├── llm/             # LLM 客户端
│   ├── client.py           # HTTP 客户端
│   ├── langchain_adapter.py # LangChain 适配器
│   └── factory.py          # 工厂函数
├── memory/          # 记忆系统
│   └── chat_history.py     # 对话历史管理
└── tools/           # 工具
    ├── travel_tools.py     # @tool 装饰器工具
    └── travel_api.py       # API 客户端
```

### 4.2 Web API 模块 (`web/src/`)

```
web/src/
├── main.py                # FastAPI 应用入口
├── routes/               # API 路由
│   ├── chat_langchain.py  # SSE 流式聊天
│   ├── session.py         # 会话管理
│   ├── health.py          # 健康检查
│   └── model.py          # 模型管理
├── services/            # 业务逻辑
├── repositories/        # 数据访问
└── storage/            # 存储层
```

### 4.3 前端模块 (`frontend/src/`)

```
frontend/src/
├── app/
│   ├── page.tsx         # 主页面
│   └── globals.css      # 全局样式
├── components/
│   ├── ChatArea.tsx     # 聊天区域
│   ├── MessageList.tsx  # 消息列表
│   ├── Sidebar.tsx      # 侧边栏
│   └── ...
├── context/
│   └── AppContext.tsx   # 全局状态
└── services/
    └── api.ts           # API 调用
```

---

## 5. LangGraph 工作流

### 5.1 节点类型

| 节点 | 功能 | 说明 |
|------|------|------|
| Intent | 意图识别 | 分析用户输入，确定意图 |
| Plan | 计划构建 | 生成执行计划 (plan 模式) |
| Execute | 工具执行 | 调用旅行工具获取信息 |
| Answer | 答案生成 | 组织最终回复 |

### 5.2 对话模式

| 模式 | 行为 |
|------|------|
| `direct` | 直接生成答案 |
| `react` | ReAct 推理循环 |
| `plan` | 先计划后执行 |

---

## 6. API 接口

### 6.1 聊天接口

```
POST /api/chat/stream
Content-Type: application/json

{
  "message": "推荐一个城市",
  "session_id": "xxx",
  "mode": "react"
}

Response: SSE (text/event-stream)
```

### 6.2 会话接口

```
GET  /api/sessions           # 获取会话列表
POST /api/sessions           # 创建会话
GET  /api/sessions/{id}      # 获取会话详情
PUT  /api/sessions/{id}/name # 更新会话名称
DELETE /api/sessions/{id}    # 删除会话
POST /api/clear/{id}         # 清除会话记录
```

### 6.3 健康检查

```
GET /api/health     # 详细健康状态
GET /api/ready     # 就绪检查
GET /api/live      # 存活检查
GET /api/health/llm # LLM 状态
```

---

## 7. 数据流

```
用户输入
    │
    ▼
ChatArea (前端)
    │
    ▼ fetch('/api/chat/stream')
    │
    ▼
Web API /chat/stream
    │
    ▼ SSE
LangGraph Agent
    │
    ├─▶ Intent Recognition
    ├─▶ Tool Execution (可选)
    └─▶ Answer Generation
    │
    ▼ SSE events
    │
ChatArea (前端)
    │
    ▼
MessageList 渲染
```

---

## 8. 配置管理

### 8.1 LLM 配置 (`config/llm_config.yaml`)

```yaml
models:
  minimax-m2-5:
    name: "MiniMax M2.5"
    provider: anthropic
    model: "MiniMax-M2.5"
    api_base: "https://api.minimaxi.com/anthropic"
    api_key: "your-key"
```

### 8.2 服务配置 (`config/server_config.yaml`)

```yaml
web:
  host: "0.0.0.0"
  port: 38000
```

---

## 9. 启动方式

```bash
# 方式1: 一键启动
start_all.bat

# 方式2: 分别启动
start_api.bat      # API 服务 (端口 38000)
start_frontend.bat # 前端服务 (端口 33001)
```

---

## 10. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v3.2.0 | 2024-xx-xx | LangChain + LangGraph 架构 |
| v3.0.0 | - | 移除 gRPC，集成到 Web API |
| v2.x | - | 五层架构设计 |
