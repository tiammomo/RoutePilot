# Quick Start

## 前置条件

- uv
- Python 3.14
- Node.js 18+
- npm 9+

## 1. 创建虚拟环境（Python 3.14）

```bash
uv python install 3.14
uv venv .venv --python 3.14
.\.venv\Scripts\activate
```

## 2. 安装依赖

```bash
uv pip install -r requirements.txt
cd frontend && npm install
```

## 3. 准备配置

```bash
copy config\\llm_config.yaml.example config\\llm_config.yaml
```

`config/server_config.yaml` 已在仓库中提供默认端口配置。

## 4. 启动

### 方式 A（推荐，Windows）

```bash
start_all.bat
```

### 方式 B（分开启动）

```bash
start_api.bat
start_frontend.bat
```

## 5. 访问地址

- Frontend: `http://localhost:33001`
- API: `http://localhost:38000`
- API Docs: `http://localhost:38000/rapidoc`
- Health: `http://localhost:38000/api/health`
