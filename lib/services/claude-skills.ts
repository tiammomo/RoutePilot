import fs from 'fs/promises';
import path from 'path';
import { getQuantCapability } from '@/lib/quant/capabilities';

const SKILLS_DIR = path.join(process.cwd(), '.claude', 'skills');

export const DEFAULT_CLAUDE_SKILLS = [
  'quant-run-planner',
  'quant-data-registry',
  'quant-data-quality',
  'quant-symbol-resolver',
  'quant-market-data',
  'quant-a-share-history',
  'quant-index-etf-market',
  'quant-technical-indicators',
  'quant-fundamental-financials',
  'quant-fundamental-indicators',
  'quant-announcement-events',
  'quant-visualization-html',
];

export async function ensureClaudeSkillsForProject(projectPath: string): Promise<string[]> {
  const projectClaudeDir = path.join(projectPath, '.claude');
  const projectSkillsDir = path.join(projectClaudeDir, 'skills');

  await fs.mkdir(projectSkillsDir, { recursive: true });

  const skillNames: string[] = [];
  const entries = await fs.readdir(SKILLS_DIR, { withFileTypes: true }).catch(() => []);

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const sourceDir = path.join(SKILLS_DIR, entry.name);
    const targetDir = path.join(projectSkillsDir, entry.name);
    await fs.cp(sourceDir, targetDir, { recursive: true, force: true });
    skillNames.push(entry.name);
  }

  return skillNames.length > 0 ? skillNames : DEFAULT_CLAUDE_SKILLS;
}

type QuantManifest = {
  quant?: {
    capabilityId?: string;
    agentType?: string;
    subAgentKey?: string;
    requiredSkills?: string[];
    dataEndpoints?: string[];
    expectedArtifacts?: string[];
    validationRules?: string[];
  };
};

export async function readQuantPilotManifest(projectPath: string): Promise<QuantManifest | null> {
  try {
    const content = await fs.readFile(path.join(projectPath, '.quantpilot', 'manifest.json'), 'utf8');
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? (parsed as QuantManifest) : null;
  } catch {
    return null;
  }
}

function buildCapabilityContext(manifest: QuantManifest | null): string {
  const quant = manifest?.quant;
  const capability = getQuantCapability(quant?.capabilityId);
  const requiredSkills = quant?.requiredSkills?.length ? quant.requiredSkills : capability.requiredSkills;
  const dataEndpoints = quant?.dataEndpoints?.length ? quant.dataEndpoints : capability.dataEndpoints;
  const expectedArtifacts = quant?.expectedArtifacts?.length ? quant.expectedArtifacts : capability.expectedArtifacts;
  const validationRules = quant?.validationRules?.length ? quant.validationRules : capability.validationRules;

  return `当前量化能力：
- capability_id: ${capability.id}
- agent_type: ${quant?.agentType ?? capability.agentType}
- sub_agent_key: ${quant?.subAgentKey ?? capability.subAgentKey}
- 名称：${capability.name}
- 说明：${capability.description}
- 必需 skills：${requiredSkills.join(', ')}
- 可用数据接口：${dataEndpoints.join('；')}
- 预期产物：${expectedArtifacts.join('；')}
- 验证规则：${validationRules.join('；')}
- 能力指导：${capability.promptGuidance.join('；')}`;
}

export function buildQuantPilotTaskPrompt(
  instruction: string,
  projectPath: string,
  manifest: QuantManifest | null = null
): string {
  const normalizedProjectPath = path.resolve(projectPath);
  const capabilityContext = buildCapabilityContext(manifest);

  return `${instruction}

QuantPilot 执行约束：
- 当前生成项目根目录是：${normalizedProjectPath}
- ${capabilityContext}
- 所有文件读取、创建、修改和删除都必须限定在当前生成项目根目录内。
- 不要修改父级 QuantPilot 平台工程文件，也不要把页面代码写入平台根目录。
- 如果当前任务是量化分析，先基于当前量化能力生成或更新 .quantpilot/run_plan.json，记录标的、时间范围、所需数据、预期图表和验证项。
- 获取数据、生成 final 数据、修改页面、验证结果时，将可见摘要追加到 .quantpilot/events.jsonl。
- 如果任务涉及股票、行情、量化分析或可视化，先使用对应数据 skill 获取真实数据，再使用 quant-visualization-html 生成可视化看板。
- 获取真实数据后、生成看板前，必须使用 quant-data-quality 写入 evidence/sources.json 和 evidence/data_quality.json，记录来源、时间、缺失字段和限制。
- 如果用户要求可视化或看板，必须实际修改 app/page.tsx，不能只输出文字说明。
- A 股趋势类页面必须优先包含 K 线/量价/均线/风险指标；历史接口失败时也要生成 K 线面板、真实错误和重试入口。
- 最终数据优先写入 data_file/final/dashboard-data.json，页面应读取真实数据或同源 API，不得硬编码样例行情。
- Agent 执行完成后平台会自动验证 Next.js build、预览 HTTP 200、data_file/final 数据文件、页面图表和 /api/market 代理；请按这些验收项完成产物。
- 默认输出中文可见执行过程摘要；开始时用 <thinking>...</thinking> 包裹任务拆解、执行计划和当前状态，执行中用简短中文说明 skill、取数、写文件和验证进展，不要暴露隐藏推理链。
- 不要留下 Next.js 默认页；最终必须生成实际可访问的量化分析界面。`;
}

export function buildQuantPilotSystemPrompt(): string {
  return `You are an expert web developer building a QuantPilot quantitative analysis application.
- Use Next.js 16 App Router
- Use TypeScript
- Use plain CSS in app/globals.css by default; only use Tailwind CSS if the current generated project already has a working local Tailwind/PostCSS setup
- Only work inside the generated project directory passed as cwd
- Never edit the parent QuantPilot platform repository
- Build the actual usable quantitative analysis interface, not a placeholder page
- By default, write visible Chinese process narration for quantitative tasks. Start with <thinking>...</thinking> containing task decomposition, execution plan, and current status; during execution, briefly summarize skills, data requests, file writes, and validation progress. Do not reveal hidden chain-of-thought
- For quantitative analysis tasks, first use the quant-run-planner skill and update .quantpilot/run_plan.json before fetching data or editing app/page.tsx
- For stock data tasks, first use the quant-market-data skill to fetch required market data from http://127.0.0.1:8000
- For broad financial data tasks, first use quant-data-registry to select the right data endpoint
- After fetching market, K-line, financial, or event data, use quant-data-quality before visualization and write evidence/sources.json plus evidence/data_quality.json
- Resolve ambiguous stock names or tickers with quant-symbol-resolver before fetching data
- Use quant-a-share-history for historical K-line analysis
- Use quant-index-etf-market for index and ETF tasks such as 沪深300、创业板指、中证500、科创50 or 510300 ETF
- Use quant-technical-indicators for moving averages, returns, drawdown, volatility, and volume metrics
- Use quant-fundamental-financials for revenue, profit, ROE, margin, and growth analysis
- Use quant-fundamental-indicators for derived profitability, margin, ROE, and financial quality metrics
- Use quant-announcement-events for announcement/event-driven context
- For visualization tasks, use the quant-visualization-html skill and actually edit app/page.tsx into a usable dashboard
- A-share visualization dashboards must include real chart panels; for trend tasks include candlestick/OHLC or an explicit K-line error panel, volume, moving averages, and risk metrics
- Prefer same-origin API routes in generated projects to proxy http://127.0.0.1:8000 instead of direct browser calls
- Do not hard-code stock quote data; fetch it before analysis and keep refresh capability in the generated page
- Before finishing a quantitative dashboard, ensure data_file/final/dashboard-data.json exists, app/page.tsx reads real data or same-origin APIs, and /api/market/** proxies the local market backend
- Include loading, error, and empty states for market data
- Display source, quote_time, and fetched_at when showing live stock data
- Use A-share color convention: red for gains and green for losses
- If no symbols are specified, default to 600519, 000001, and 300750
- Do not add styling dependencies or create @import "tailwindcss" unless explicitly requested
- Write clean, production-ready code
- Follow best practices
- The platform automatically installs dependencies and manages the preview dev server. Do not run package managers or dev-server commands yourself; rely on the existing preview.
- Keep all project files directly in the project root. Never scaffold frameworks into subdirectories.
- Never override ports or start your own development server processes. Rely on the managed preview service which assigns ports from the approved pool.
- When sharing a preview link, read the actual NEXT_PUBLIC_APP_URL instead of assuming a default port.
- Prefer giving the user the live preview link that is actually running rather than written instructions.`;
}
