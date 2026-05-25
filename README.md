# QuantPilot

QuantPilot 是基于 Claudable 2.0.0 改造的量化专精 AI 工作台。当前阶段保留原有的应用生成、项目预览、Agent 调用、GitHub/Vercel/Supabase 集成能力，并将默认模型运行方式调整为 Claude Code 运行时直连 MiniMax 的 Anthropic-compatible 接口。

后续开发重点会逐步转向量化投研、因子研究、策略编排、回测分析、风险评估和交易执行辅助。

## 当前定位

- **项目底座**：Next.js 16 + React 19 + TypeScript 6，开发预览默认使用 Next 官方 Turbopack，主应用生产构建保留 Rspack 优化。
- **默认 Agent**：Claude Code。
- **默认模型**：MiniMax M2.7。
- **模型接入方式**：通过 `ANTHROPIC_BASE_URL` 指向 MiniMax Anthropic-compatible API。
- **量化数据后端**：FastAPI + Python 3.14 + uv，默认提供东方财富实时行情、K 线、财务与公告数据。
- **本地数据**：Prisma + SQLite，默认写入 `data/`，不提交到 Git。
- **本地预览**：主应用默认 `3000`，生成项目预览默认从 `3100` 开始分配。

## 基本组件

启动项目本体需要：

- Node.js >= 20.19.0
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

# 构建 standalone 产物，桌面打包和发布时使用
npm run build:standalone

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

## 质量门与持续升级

仓库已加入 GitHub Actions 质量门：

- 前端：`npm ci`、`npm run lint`、`npm run type-check`、`npm run build`。
- 后端：`uv sync --locked --all-groups`、`uv run ruff check .`、`uv run pytest`。

Dependabot 会每周检查三类依赖：

- 根目录 `npm` 依赖。
- `backend/market_data` 的 `uv` 依赖。
- `.github/workflows` 里的 GitHub Actions。

日常升级建议先走自动 PR，由 CI 验证后再合并；本地需要手动升级时可以执行：

```bash
# 前端依赖
npm outdated --long
npm install <package>@latest
npm run lint
npm run type-check
npm run build

# 后端依赖
cd backend/market_data
uv tree --outdated --depth 1
uv lock --upgrade-package <package>
uv sync --locked --all-groups
uv run ruff check .
uv run pytest
```

主应用和生成项目都通过 Next.js 官方命令入口启动，避免再回到 webpack。日常开发预览默认走 Turbopack，生成项目模板会自动写入稳定的 `next dev --turbo` 启动脚本，优先保证 Agent 生成看板时能稳定启动和预览。主应用的生产构建仍保留 Rspack 接入，用于继续观察和优化构建速度。

日常 `npm run build` 是快速验证构建，会跳过服务端 route 的 per-route output tracing，避免 Next 在 `.git`、`.next`、`data/projects` 等工作区目录上做耗时追踪；这个命令适合本地开发、CI 快速检查和修复页面 build error。桌面打包、发布或需要 `.next/standalone` 时使用 `npm run build:standalone`，它会保留完整 route tracing 和 standalone 输出。如果临时需要让普通 build 也执行完整追踪，可以运行：

```bash
QUANTPILOT_SKIP_ROUTE_TRACING=0 npm run build
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
| 均线突破回测 | `GET /api/v1/backtests/ma-crossover/{symbol}?fast_window=20&slow_window=60&limit=250&fee_bps=5` |
| 指数/ETF 行情 | 复用实时行情、历史 K 线和技术指标接口，例如 `000300`、`399006`、`510300` |
| 财务报表 | `GET /api/v1/fundamentals/financials/{symbol}?limit=8` |
| 财务衍生指标 | `GET /api/v1/indicators/fundamental/{symbol}?limit=8` |
| 公告事件 | `GET /api/v1/events/announcements/{symbol}?limit=20` |

示例：

```bash
curl "http://127.0.0.1:8000/api/v1/symbols/resolve?query=贵州茅台&count=5"
curl "http://127.0.0.1:8000/api/v1/quotes/history/600519?period=daily&adjustment=qfq&limit=20"
curl "http://127.0.0.1:8000/api/v1/fundamentals/financials/600519?limit=8"
curl "http://127.0.0.1:8000/api/v1/quotes/history/000300?period=daily&adjustment=qfq&limit=120"
curl "http://127.0.0.1:8000/api/v1/backtests/ma-crossover/510300?fast_window=20&slow_window=60&limit=250&fee_bps=5"
```

接口响应会包含 `fetch.cache_status`、`fetch.cache_ttl_seconds`、`fetch.cached_at` 和 `fetch.expires_at`。实时行情默认短缓存 5 秒，K 线和技术指标默认缓存 30 分钟，财务数据默认缓存 6 小时，公告默认缓存 10 分钟。可通过 `QUANTPILOT_MARKET_CACHE_DIR` 指定缓存目录，或用 `QUANTPILOT_MARKET_CACHE_ENABLED=0` 临时关闭缓存。

指数和 ETF 会通过 `asset_type` 标识为 `index` 或 `etf`。当前内置常见别名包括沪深300、创业板指、中证500、科创50、沪深300ETF；这类标的默认不拉取个股财务报表和公告事件。

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

新建生成项目会自动带上 QuantPilot 金融看板基础模板：

- `app/page.tsx`：读取 `data_file/final/dashboard-data.json`，内置行情卡片、指标卡片、SVG 趋势图和最近 K 线表。
- `app/globals.css`：内置金融工作台样式，使用 A 股红涨绿跌配色。
- `app/api/market/[...path]/route.ts`：同源转发到 `http://127.0.0.1:8000/api/v1/**`。

模型生成可视化时应在这个模板上增强，而不是退回默认页或重复创建冲突代理。

## 首页能力目录

首页已经从通用样例入口调整为量化能力目录，能力定义统一来自 `lib/quant/capabilities.ts`。目前分为三组：

- **核心分析**：个股诊断、技术分析、基本面分析，已接入确定性 run plan、预取数据、证据和看板验证链路。
- **横向研究**：多标的对比、行业/板块分析，当前先映射到已验证的单标的或指数/ETF 链路，页面和 run plan 会提示待补齐能力边界。
- **策略风控**：策略研究、回测复盘、组合风险，当前作为产品入口和规划任务入口，后续继续接入正式回测与组合风险计算。

能力状态分为 `ready` 和 `planned`。`planned` 能力不会假装已经完整实现，而是通过 `executionCapabilityId` 先走当前最接近的已验证链路，并在 `.quantpilot/run_plan.json` 中记录 `requestedCapabilityId` 与 `executionCapabilityId`。

## Skills 集中管理

Claude Code 使用的项目级 skills 统一放在 `.claude/skills/`，生成项目时会被复制到对应项目目录中，方便 Agent 在任务执行过程中读取和调用。

Skills 治理原则见 `docs/quantpilot-skill-governance.md`。后续不建议继续增加碎片化顶层 skill，而是逐步合并为规划、数据注册、标的解析、行情数据、基本面、指标计算、回测、可视化和数据质量这几类稳定能力。需要确定性计算时，优先在 skill 内配套 Python 脚本，例如意图槽位检测、收益/回撤/波动计算、schema 校验和信源探针。

核心 skill、兼容别名、脚本、接口和验证边界统一记录在 `.claude/skills.registry.json`。修改 skills 后可以运行：

```bash
npm run check:skills
```

每个 skill 也可以打包成独立压缩包，默认位置是 `.claude/skill-packages/<skill-id>.tgz`。生成项目时平台默认只安装 9 个核心 skill，优先解压压缩包到 `<project>/.claude/skills/`，压缩包不存在时回退复制源码目录：

```bash
npm run package:skills
npm run package:skills -- quant-run-planner quant-market-data
```

需要同时打包或安装旧 alias 时：

```bash
npm run package:skills -- --include-legacy
npm run check:skills -- --include-legacy
QUANTPILOT_INSTALL_LEGACY_SKILLS=1 npm run dev
```

当前已内置的量化 skills：

- `quant-data-registry`：查询当前可用数据源和接口能力。
- `quant-symbol-resolver`：把中文股票名、简称或代码解析成标准证券代码。
- `quant-market-data`：获取实时价格、涨跌幅、成交额、盘口等行情信息。
- `quant-a-share-history`：获取 A 股历史 K 线、成交量、均线和阶段表现数据。
- `quant-index-etf-market`：获取指数与 ETF 的实时行情、K 线和技术指标。
- `quant-technical-indicators`：获取后端标准化 MA、收益率、回撤、波动率和成交量指标。
- `quant-backtest`：调用后端均线突破回测，获取净值、回撤、交易明细、胜率和费用参数。
- `quant-fundamental-financials`：获取营收、利润、现金流、ROE 等财务指标。
- `quant-fundamental-indicators`：获取净利率、平均 ROE、平均毛利率等财务衍生指标。
- `quant-announcement-events`：获取上市公司公告和事件信息。
- `quant-data-quality`：在取数后生成 `evidence/sources.json` 与 `evidence/data_quality.json`，记录来源、时间戳、缺失字段、警告和限制。
- `quant-visualization-html`：基于已获取的数据生成可视化 HTML/Next.js 看板。

量化分析任务的推荐链路是：先生成 run plan，再由平台预取真实数据和证据文件，然后调用可视化 skill 生成页面。涉及 A 股走势时，可视化应优先包含 K 线、成交量、均线、涨跌幅、关键指标和数据表，并遵循 A 股红涨绿跌的颜色习惯。

当用户问题缺少关键输入时，`quant-run-planner` 会先进入意图澄清状态：例如没有给股票/指数/ETF 标的、对比任务没有给至少两个标的，或投资建议类问题缺少周期和风险偏好。此时平台会写入 `status: "needs_clarification"` 的 `.quantpilot/run_plan.json`，向用户提出 1-3 个澄清问题，并停止取数和页面生成，避免用默认假设生成错误看板。

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

本地排查 UI 时可以用截图脚本确认页面已经完成客户端水合，并且生成项目的右侧预览真正展示了金融看板：

```bash
npm run check:homepage
PROJECT_ID=<project_id> npm run check:project-visual
```

截图会写入 `tmp/visual-checks/`。检查项目看板时请使用 `http://localhost:3000`，这也是用户实际访问地址；不要混用 `127.0.0.1:3000` 做截图判断，避免 dev server 的客户端接管表现不一致。

## 量化回归评测

固定问句和预期产物定义位于 `benchmarks/quantpilot/cases.json`。回归脚本会创建临时项目，执行 run plan、平台预取、evidence 生成、默认看板模板和自动验证，不直接依赖模型输出。

运行全部用例：

```bash
npm run benchmark:quant
```

运行指定用例：

```bash
npm run benchmark:quant -- --case stock-fundamental-maotai
npm run benchmark:quant -- --case index-technical-hs300 --case etf-technical-300etf
```

评测报告写入 `tmp/quantpilot-benchmark-reports/`，该目录不进入 Git。当前内置用例覆盖贵州茅台基本面、沪深300技术趋势、沪深300ETF趋势和 510300 均线突破回测。

默认情况下，评测完成后会删除 `data/projects/benchmark-*` 临时项目并停止对应预览端口，避免污染本地 `3100+` 预览端口。需要保留现场时可以增加：

```bash
npm run benchmark:quant -- --keep-projects
```

## 后端演进建议

当前后端继续保持 `Python 3.14 + FastAPI + uv` 是合适的：它适合快速封装金融数据源，异步 HTTP 取数能力够用，uv 的锁文件和托管 Python 能保证本地与 CI 环境一致。

下一阶段建议按数据平台思路演进：

- **数据源分层**：保留东方财富作为默认源，同时逐步接入 AKShare、Tushare、交易日历和指数行业源，所有源统一映射到现有响应契约。
- **候选信源池**：后端已提供 `/api/v1/provider-candidates` 和 `/api/v1/provider-candidates/probe`，用于测试腾讯股票 K 线、新浪实时行情、Stooq、Alpha Vantage、Finnhub、Twelve Data、Nasdaq Data Link、Marketstack 等免费或免费层来源。
- **降级策略**：实时行情、K 线、财务、公告都应有主备源、超时、重试、缓存和数据质量标记，失败时让 Agent 明确知道哪些数据不可用。
- **存储策略**：短期继续 JSON TTL 缓存；中期可以引入 DuckDB/Parquet 保存历史 K 线、财务快照和分析中间结果，便于回测和离线复现。
- **观测能力**：补请求耗时、数据源命中率、缓存命中率、失败率和外部接口错误摘要，前端和 Agent 都可以据此展示数据可信度。
- **API 契约**：继续以 Pydantic 模型为中心，所有新增接口必须携带 `source`、`as_of`、`fetched_at`、`fetch` 和 `data_quality`。

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
