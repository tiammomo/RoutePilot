# ShuaiTravelAgent

基于 LangChain + LangGraph 的智能旅游助手，提供城市推荐、景点查询、预算估算与行程规划能力。

## 项目现状（2026-03-07）

- 架构: `frontend` (Next.js) + `web` (FastAPI) + `agent` (LangGraph)
- 前端地址: `http://localhost:33001`
- API 地址: `http://localhost:38000`
- API 文档: `http://localhost:38000/rapidoc`

## 快速开始

1. 创建并激活 Python 3.14 环境（uv）

```bash
uv python install 3.14
uv venv .venv --python 3.14
.\.venv\Scripts\activate
```

2. 安装 Python 依赖

```bash
uv pip install -r requirements.txt
```

3. 安装前端依赖

```bash
cd frontend && npm install
```

4. 准备配置文件

```bash
copy config\\llm_config.yaml.example config\\llm_config.yaml
```

5. 启动服务

```bash
start_all.bat
```

## 文档导航

- 文档总览: [docs/README.md](docs/README.md)
- 贡献规范: [CONTRIBUTING.md](CONTRIBUTING.md)
- 快速启动: [docs/getting-started/quick-start.md](docs/getting-started/quick-start.md)
- 项目结构: [docs/reference/project-structure.md](docs/reference/project-structure.md)
- API 参考: [docs/reference/api-reference.md](docs/reference/api-reference.md)
- 配置参考: [docs/reference/configuration-reference.md](docs/reference/configuration-reference.md)
- 测试指南: [docs/testing/testing-guide.md](docs/testing/testing-guide.md)

## 目录总览

```text
ShuaiTravelAgent/
├── agent/                 # Agent 核心（LangChain + LangGraph）
├── web/                   # FastAPI Web API
├── frontend/              # Next.js 前端
├── config/                # YAML 配置
├── docs/                  # 规范化文档目录
├── tests/                 # API/集成测试
├── run_api.py             # API 启动入口
└── start_*.bat            # Windows 快捷启动脚本
```
