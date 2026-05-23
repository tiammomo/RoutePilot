# QuantPilot

QuantPilot 是基于 Claudable 2.0.0 改造的量化专精 AI 工作台。当前阶段保留原有的应用生成、项目预览、Agent 调用、GitHub/Vercel/Supabase 集成能力，并将默认模型运行方式调整为 Claude Code 运行时直连 MiniMax 的 Anthropic-compatible 接口。

后续开发重点会逐步转向量化投研、因子研究、策略编排、回测分析、风险评估和交易执行辅助。

## 当前定位

- **项目底座**：Next.js 16 + React 19 + TypeScript。
- **默认 Agent**：Claude Code。
- **默认模型**：MiniMax M2.7。
- **模型接入方式**：通过 `ANTHROPIC_BASE_URL` 指向 MiniMax Anthropic-compatible API。
- **量化数据后端**：FastAPI + Python 3.14 + uv，默认提供东方财富实时行情、K 线、财务与公告数据。
- **本地数据**：Prisma + SQLite，默认写入 `data/`，不提交到 Git。
- **本地预览**：主应用默认 `3000`，生成项目预览默认从 `3100` 开始分配。

## 基本组件

启动项目本体需要：

- Node.js >= 20.0.0
- npm >= 10.0.0
- Python >= 3.14
- uv
- Git
- Claude Code CLI
- MiniMax API Token

可选集成：

- Codex CLI
- Cursor CLI
- Qwen Code
- GLM CLI
- GitHub Token
- Vercel Token
- Supabase 凭据

## 环境变量

仓库提供 `.env.example` 作为模板。真实密钥只放在本地 `.env` 或 `.env.local`，这两个文件已加入 `.gitignore`。

Claude Code 直连 MiniMax 的关键配置：

```env
ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"
ANTHROPIC_AUTH_TOKEN="replace-with-your-minimax-token"
API_TIMEOUT_MS=3000000
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
ANTHROPIC_MODEL="MiniMax-M2.7"
ANTHROPIC_SMALL_FAST_MODEL="MiniMax-M2.7"
ANTHROPIC_DEFAULT_SONNET_MODEL="MiniMax-M2.7"
ANTHROPIC_DEFAULT_OPUS_MODEL="MiniMax-M2.7"
ANTHROPIC_DEFAULT_HAIKU_MODEL="MiniMax-M2.7"
```

本地数据库与预览端口配置：

```env
DATABASE_URL="file:../data/cc.db"
PROJECTS_DIR="./data/projects"
ENCRYPTION_KEY="replace-with-a-64-character-hex-secret"
PORT=3000
WEB_PORT=3000
NEXT_PUBLIC_APP_URL="http://localhost:3000"
PREVIEW_PORT_START=3100
PREVIEW_PORT_END=3999
```

量化数据后端默认端口配置，可按需覆盖：

```env
QUANTPILOT_MARKET_HOST="127.0.0.1"
QUANTPILOT_MARKET_PORT=8000
QUANTPILOT_MARKET_RELOAD=0
```

## 端口约定

| 服务 | 默认地址 | 说明 |
| --- | --- | --- |
| QuantPilot 主前端 | `http://localhost:3000` | 当前项目入口和聊天工作台 |
| 量化数据后端 | `http://127.0.0.1:8000` | Python/FastAPI，本地提供行情和金融数据能力 |
| 生成项目预览 | `http://localhost:3100` 起 | 每个生成项目自动分配独立端口 |

主前端约定优先使用 `3000`。如果启动脚本自动切到 `3001`，通常说明 `3000` 已被占用；建议先释放 `3000`，再重新执行 `npm run dev`，避免聊天链接、预览代理和本地配置不一致。

## 项目如何拉起

### 1. 准备前端环境

在项目根目录执行：

```bash
npm install
cp .env.example .env
cp .env.example .env.local
```

然后把 `.env` 和 `.env.local` 中的 `ANTHROPIC_AUTH_TOKEN` 改成自己的 MiniMax Token。

### 2. 启动量化数据后端

新开一个终端，进入后端目录：

```bash
cd backend/market_data
uv sync
uv run quantpilot-market-api
```

默认监听：

```text
http://127.0.0.1:8000
```

快速检查：

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/api/v1/quotes/realtime/600519"
```

### 3. 启动主前端

再开一个终端，回到项目根目录：

```bash
npm run dev
```

默认访问：

```text
http://localhost:3000
```

### 4. 使用顺序

推荐先确认 `8000` 后端健康，再进入 `3000` 前端创建或打开项目。Claude Code 在生成页面时，会通过集中管理的量化 skills 获取行情、财务、公告等数据，再生成对应的可视化页面。

## Claude Code 接 MiniMax

安装 Claude Code CLI：

```bash
npm install -g @anthropic-ai/claude-code
```

写入 Claude Code 的本机配置：

```bash
bash claude_code_minimax_env.sh
```

脚本会把 MiniMax 的接口地址、Token、超时时间和默认模型写入 `~/.claude/settings.json`，并标记 Claude Code 已完成初始化。这里使用 Claude Code 作为本地运行时，不依赖原生 Anthropic Claude 登录。

也可以手动在 VS Code 的 Claude Code 扩展设置中配置同样的环境变量。

## 常用命令

```bash
# Web 开发模式
npm run dev
npm run dev:web

# 桌面端开发模式
npm run dev:desktop

# 构建 Web 应用
npm run build

# 启动生产构建
npm run start

# 类型检查
npm run type-check

# Prisma
npm run prisma:generate
npm run prisma:push
npm run prisma:migrate
npm run prisma:studio
npm run prisma:reset

# 检查 Claude Code 与 MiniMax 配置
npm run check-cli

# 量化数据后端
cd backend/market_data
uv sync
uv run quantpilot-market-api
uv run pytest
uv run ruff check
```

## 初始化过程

`npm install` 会触发 `postinstall`，自动执行：

```bash
npm run ensure:env
```

该脚本会创建或更新：

- `.env`
- `.env.local`
- `data/cc.db`
- `data/projects/`
- `prisma/data/`

`npm run dev` 启动时会检查 SQLite 数据库状态，并在需要时执行：

```bash
npx prisma db push
```

## 量化数据后端

后端代码位于 `backend/market_data`，当前用于给 Agent 和生成页面提供本地金融数据接口。默认优先使用东方财富数据源，历史 K 线在东方财富接口异常时会尝试腾讯 K 线兜底。

当前主要接口：

| 能力 | 方法与路径 |
| --- | --- |
| 健康检查 | `GET /health` |
| 数据源注册表 | `GET /api/v1/registry` |
| 股票名称/代码解析 | `GET /api/v1/symbols/resolve?query=贵州茅台&count=5` |
| 单只实时行情 | `GET /api/v1/quotes/realtime/{symbol}` |
| 批量实时行情 | `POST /api/v1/quotes/realtime` |
| 历史 K 线 | `GET /api/v1/quotes/history/{symbol}?period=daily&adjustment=qfq&limit=120` |
| 技术指标 | `GET /api/v1/indicators/technical/{symbol}?period=daily&adjustment=qfq&limit=120` |
| 财务报表 | `GET /api/v1/fundamentals/financials/{symbol}?limit=8` |
| 财务衍生指标 | `GET /api/v1/indicators/fundamental/{symbol}?limit=8` |
| 公告事件 | `GET /api/v1/events/announcements/{symbol}?limit=20` |

示例：

```bash
curl "http://127.0.0.1:8000/api/v1/symbols/resolve?query=贵州茅台&count=5"
curl "http://127.0.0.1:8000/api/v1/quotes/history/600519?period=daily&adjustment=qfq&limit=20"
curl "http://127.0.0.1:8000/api/v1/fundamentals/financials/600519?limit=8"
```

接口响应会包含 `fetch.cache_status`、`fetch.cache_ttl_seconds`、`fetch.cached_at` 和 `fetch.expires_at`。实时行情默认短缓存 5 秒，K 线和技术指标默认缓存 30 分钟，财务数据默认缓存 6 小时，公告默认缓存 10 分钟。可通过 `QUANTPILOT_MARKET_CACHE_DIR` 指定缓存目录，或用 `QUANTPILOT_MARKET_CACHE_ENABLED=0` 临时关闭缓存。

生成项目中如果要从浏览器请求后端，优先使用同源代理，例如 `/api/market/quotes/realtime/600519`，再由生成项目的 API route 转发到 `http://127.0.0.1:8000/api/v1/...`，这样可以减少跨端口 CORS 和浏览器网络限制问题。

量化任务开始时，平台会根据 `.quantpilot/run_plan.json` 先调用 `8000` 后端预取真实数据，并落盘到生成项目：

- `data_file/raw/<run_id>/quote.json`
- `data_file/raw/<run_id>/kline-daily-qfq.json`
- `data_file/raw/<run_id>/technical-indicators.json`
- `data_file/raw/<run_id>/financials.json`
- `data_file/raw/<run_id>/fundamental-indicators.json`
- `data_file/raw/<run_id>/announcements.json`
- `data_file/final/dashboard-data.json`
- `evidence/sources.json`
- `evidence/data_quality.json`

Claude Code 随后基于这些确定性产物生成或更新页面，避免只依赖模型临时执行 curl。

## Skills 集中管理

Claude Code 使用的项目级 skills 统一放在 `.claude/skills/`，生成项目时会被复制到对应项目目录中，方便 Agent 在任务执行过程中读取和调用。

当前已内置的量化 skills：

- `quant-data-registry`：查询当前可用数据源和接口能力。
- `quant-symbol-resolver`：把中文股票名、简称或代码解析成标准证券代码。
- `quant-market-data`：获取实时价格、涨跌幅、成交额、盘口等行情信息。
- `quant-a-share-history`：获取 A 股历史 K 线、成交量、均线和阶段表现数据。
- `quant-technical-indicators`：获取后端标准化 MA、收益率、回撤、波动率和成交量指标。
- `quant-fundamental-financials`：获取营收、利润、现金流、ROE 等财务指标。
- `quant-fundamental-indicators`：获取净利率、平均 ROE、平均毛利率等财务衍生指标。
- `quant-announcement-events`：获取上市公司公告和事件信息。
- `quant-data-quality`：在取数后生成 `evidence/sources.json` 与 `evidence/data_quality.json`，记录来源、时间戳、缺失字段、警告和限制。
- `quant-visualization-html`：基于已获取的数据生成可视化 HTML/Next.js 看板。

量化分析任务的推荐链路是：先生成 run plan，再由平台预取真实数据和证据文件，然后调用可视化 skill 生成页面。涉及 A 股走势时，可视化应优先包含 K 线、成交量、均线、涨跌幅、关键指标和数据表，并遵循 A 股红涨绿跌的颜色习惯。

## 自动验证链路

Agent 执行完成后，QuantPilot 会自动对生成项目执行一轮验收，并把摘要写回聊天记录。验证报告保存在生成项目的 `.quantpilot/validation.json`，同时会在 `.quantpilot/events.jsonl` 记录 `validation_started` 和 `validation_completed` 事件。

验证阶段会优先检查 Agent 写入的 evidence 文件；如果缺失或结构不完整，但 `data_file/final/dashboard-data.json` 已包含真实数据，平台会自动生成一份基础 evidence，保证后续验证和页面追溯有确定性。

当前验证项：

- `npm run build`，并在验证时固定 `NODE_ENV=production`。
- 生成项目预览首页返回 HTTP 200。
- `data_file/final/dashboard-data.json` 或 `data_file/final/*.json` 存在，且包含真实行情、K 线、财务或来源字段。
- `evidence/sources.json` 与 `evidence/data_quality.json` 存在，且包含来源、端点、时间戳、样本长度、缺失字段、警告或限制说明。
- evidence 中会保留后端 `fetch` 元信息，用于判断数据来自实时拉取还是本地缓存。
- `app/page.tsx` 已绑定最终数据文件或同源 `/api/market` 接口，没有停留在 Next.js 默认页。
- 页面中存在金融图表实现，例如 SVG/canvas/K 线/成交量/财务趋势。
- 生成项目提供 `/api/market/**` 同源代理，并能访问本地 `8000` 后端实时行情。

也可以手动触发或读取某个项目的验证结果：

```bash
curl -X POST "http://localhost:3000/api/projects/<project_id>/quant/validation"
curl "http://localhost:3000/api/projects/<project_id>/quant/validation"
```

## 模型管理

前端模型选项来自 `lib/constants/cliModels.ts` 及各 CLI 的模型定义文件。Claude Code 当前默认映射到 `MiniMax-M2.7`，并保留 Anthropic-compatible 的外部模型接入能力。

后续新增外部模型时，建议同步处理：

- 模型定义与展示名。
- CLI 默认模型。
- 环境变量说明。
- 设置页中的模型选择项。
- 运行时传入 Claude Code 的真实模型 ID。

## GitHub 整理原则

以下内容不会提交：

- `.env`
- `.env.local`
- `data/`
- `prisma/data/`
- `backend/market_data/.venv/`
- `public/uploads/`
- `node_modules/`
- `.next/`
- 构建产物与本地缓存

这些目录都是本地运行数据或生成物，克隆仓库后会在安装和启动过程中重新生成。

## 故障排查

### 端口被占用

主前端优先使用 `3000`。如果启动脚本自动选择了其他端口，先检查并释放 `3000`：

```bash
lsof -i :3000
```

量化数据后端默认使用 `8000`。如果被占用，可以释放端口，或临时改用：

```bash
QUANTPILOT_MARKET_PORT=8001 uv run quantpilot-market-api
```

### 数据库结构冲突

如果本地 SQLite 数据库结构与 Prisma schema 不一致，可以执行：

```bash
npm run prisma:push
```

如果需要完全重置数据库：

```bash
npm run prisma:reset
```

注意：重置会删除本地数据库数据。

### Claude Code 找不到 MiniMax 配置

确认 `.env`、`.env.local` 或 `~/.claude/settings.json` 中已经配置：

- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_MODEL`

然后重启开发服务。

### Claude 生成页面没有拿到行情数据

先确认后端可用：

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/api/v1/quotes/realtime/600519"
```

再确认生成项目目录中存在 `.claude/skills/`。如果缺失，重新打开或重新生成项目，让主应用同步项目级 skills。

### 可视化页面没有生成预期图表

检查 Agent 执行过程是否先调用了行情、K 线、财务等数据接口，再调用 `quant-visualization-html`。对于金融看板，预期至少包含真实数据驱动的图表区域、关键指标和数据表；如果只有静态文案，通常说明数据获取或可视化 skill 没有被完整执行。

## 许可证

MIT License
