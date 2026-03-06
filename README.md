# 小帅旅游助手 - 智能AI旅游推荐系统

## 项目概述

基于 **LangChain + LangGraph** 的智能旅游助手系统，提供城市推荐、景点查询、路线规划等功能。

### 核心特性 (v3.2.0)

- **LangGraph Agent** - 基于 LangGraph 的智能推理引擎
- **SSE 流式响应** - Token 级别实时输出
- **MiniMax M2.5 支持** - Anthropic 兼容 API
- **多协议 LLM 支持** - OpenAI、Claude 等
- **多会话管理** - 独立对话历史

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16 + React 19 + TypeScript + Zustand + antd 6 |
| 后端 Web | FastAPI + Python 3.10+ |
| Agent | LangChain + LangGraph |
| LLM | MiniMax M2.5, OpenAI |

---

## 项目结构

```
ShuaiTravelAgent/
├── agent/                      # AI Agent 模块
│   └── src/
│       ├── config/            # 配置管理
│       ├── graph/             # LangGraph 核心
│       ├── llm/              # LLM 客户端
│       ├── memory/           # 记忆系统
│       └── tools/            # 旅行工具
├── web/                       # Web API (FastAPI)
│   └── src/
│       ├── main.py           # 应用入口
│       ├── routes/           # API 路由
│       ├── services/         # 业务逻辑
│       ├── repositories/     # 数据访问
│       └── storage/         # 存储层
├── frontend/                  # 前端 (Next.js)
├── config/                   # 配置文件
└── run_api.py               # 启动脚本
```

---

## 快速开始

### 1. 安装依赖

```bash
# 创建并激活虚拟环境
conda create -n agents python=3.10
conda activate agents

# 安装依赖
pip install -r requirements.txt

# 安装前端依赖
cd frontend && npm install
```

### 2. 配置

```bash
# 复制配置示例
cp config/llm_config.yaml.example config/llm_config.yaml
cp config/server_config.yaml.example config/server_config.yaml

# 编辑配置文件，填入 API Key
```

### 3. 启动服务

```bash
# 方式1: 一键启动 (Windows)
start_all.bat

# 方式2: 分别启动
# 终端1: 启动 Web API
start_api.bat
# 或: python run_api.py

# 终端2: 启动前端
start_frontend.bat
# 或: cd frontend && npm run dev
```

### 4. 访问

- 前端: http://localhost:33001
- API: http://localhost:38000
- 文档: http://localhost:38000/rapidoc

---

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/chat/stream` | POST | SSE 流式聊天 |
| `/api/sessions` | GET/POST | 会话管理 |
| `/api/models` | GET | 可用模型列表 |
| `/api/cities` | GET | 城市列表 |

---

## 开发

### 代码结构

```
agent/src/
├── config/        # 配置管理
│   ├── config_manager.py   # 配置管理器
│   └── settings.py         # 设置
├── graph/        # LangGraph
│   ├── state.py            # 状态定义
│   ├── nodes.py            # 节点实现
│   └── builder.py         # 图构建器
├── llm/          # LLM 客户端
│   ├── client.py          # HTTP 客户端
│   ├── langchain_adapter.py # LangChain 适配器
│   └── factory.py         # 工厂函数
├── memory/       # 记忆系统
│   └── chat_history.py    # 对话历史
└── tools/        # 工具
    ├── travel_tools.py    # @tool 装饰器工具
    └── travel_api.py     # API 客户端
```

### 测试

```bash
# 运行测试
cd agent && PYTHONPATH=agent/src python -m pytest tests/ -v
```

---

## 配置说明

### LLM 配置 (config/llm_config.yaml)

```yaml
models:
  minimax-m2-5:
    name: "MiniMax M2.5"
    provider: anthropic
    model: "MiniMax-M2.5"
    api_base: "https://api.minimaxi.com/anthropic"
    api_key: "your-api-key"
```

### 服务配置 (config/server_config.yaml)

```yaml
web:
  host: "0.0.0.0"
  port: 38000
```

---

## 许可证

MIT License
