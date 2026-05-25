import fs from 'fs/promises';
import path from 'path';
import { spawn } from 'child_process';
import { getQuantCapability } from '@/lib/quant/capabilities';
import {
  describeQuantSkillsForPrompt,
  getDefaultQuantSkillIds,
  getQuantSkillPackagePath,
  readQuantSkillsRegistry,
} from '@/lib/quant/skills-registry';

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
  'quant-comparison',
  'quant-visualization-html',
];

export async function getDefaultClaudeSkills(): Promise<string[]> {
  const registry = await readQuantSkillsRegistry();
  return getDefaultQuantSkillIds(registry, {
    includeLegacy: process.env.QUANTPILOT_INSTALL_LEGACY_SKILLS === '1',
  });
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function runTar(args: string[], cwd: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn('tar', args, { cwd, stdio: 'ignore' });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`tar exited with code ${code}`));
      }
    });
  });
}

async function installSkillPackage(params: {
  skillId: string;
  packagePath: string;
  projectSkillsDir: string;
}): Promise<boolean> {
  if (!(await pathExists(params.packagePath))) {
    return false;
  }

  await fs.rm(path.join(params.projectSkillsDir, params.skillId), { recursive: true, force: true });
  await runTar(['-xzf', params.packagePath, '-C', params.projectSkillsDir], process.cwd());
  return pathExists(path.join(params.projectSkillsDir, params.skillId, 'SKILL.md'));
}

export async function ensureClaudeSkillsForProject(projectPath: string): Promise<string[]> {
  const projectClaudeDir = path.join(projectPath, '.claude');
  const projectSkillsDir = path.join(projectClaudeDir, 'skills');
  const registry = await readQuantSkillsRegistry();
  const requestedSkillIds = getDefaultQuantSkillIds(registry, {
    includeLegacy: process.env.QUANTPILOT_INSTALL_LEGACY_SKILLS === '1',
  });

  await fs.mkdir(projectSkillsDir, { recursive: true });

  const skillNames: string[] = [];
  const installed = new Set<string>();

  for (const skillId of requestedSkillIds) {
    const packagePath = getQuantSkillPackagePath(registry, skillId);
    const installedFromPackage = await installSkillPackage({
      skillId,
      packagePath,
      projectSkillsDir,
    }).catch((error) => {
      console.warn(`[ClaudeSkills] Failed to install skill package ${skillId}:`, error);
      return false;
    });

    if (installedFromPackage) {
      installed.add(skillId);
      skillNames.push(skillId);
      continue;
    }

    const sourceDir = path.join(SKILLS_DIR, skillId);
    const targetDir = path.join(projectSkillsDir, skillId);
    if (await pathExists(path.join(sourceDir, 'SKILL.md'))) {
      await fs.cp(sourceDir, targetDir, { recursive: true, force: true });
      installed.add(skillId);
      skillNames.push(skillId);
    }
  }

  if (skillNames.length > 0) {
    return skillNames;
  }

  return requestedSkillIds;
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

async function buildCapabilityContext(manifest: QuantManifest | null): Promise<string> {
  const quant = manifest?.quant;
  const capability = getQuantCapability(quant?.capabilityId);
  const requiredSkills = quant?.requiredSkills?.length ? quant.requiredSkills : capability.requiredSkills;
  const dataEndpoints = quant?.dataEndpoints?.length ? quant.dataEndpoints : capability.dataEndpoints;
  const expectedArtifacts = quant?.expectedArtifacts?.length ? quant.expectedArtifacts : capability.expectedArtifacts;
  const validationRules = quant?.validationRules?.length ? quant.validationRules : capability.validationRules;
  const skillsRegistry = await readQuantSkillsRegistry();
  const skillsContext = describeQuantSkillsForPrompt(skillsRegistry);

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
- 能力指导：${capability.promptGuidance.join('；')}

${skillsContext}`;
}

export async function buildQuantPilotTaskPrompt(
  instruction: string,
  projectPath: string,
  manifest: QuantManifest | null = null
): Promise<string> {
  const normalizedProjectPath = path.resolve(projectPath);
  const capabilityContext = await buildCapabilityContext(manifest);

  return `${instruction}

QuantPilot 执行约束：
- 当前生成项目根目录是：${normalizedProjectPath}
- ${capabilityContext}
- 所有文件读取、创建、修改和删除都必须限定在当前生成项目根目录内。
- 不要修改父级 QuantPilot 平台工程文件，也不要把页面代码写入平台根目录。
- 如果当前任务是量化分析，先基于当前量化能力生成或更新 .quantpilot/run_plan.json，记录标的、时间范围、所需数据、预期图表和验证项。
- 获取数据、生成 final 数据、修改页面、验证结果时，将可见摘要追加到 .quantpilot/events.jsonl。
- 如果用户问题缺少标的、对比范围或投资周期/风险偏好等关键输入，先使用 quant-run-planner 写入 status=needs_clarification，向用户提出 1-3 个澄清问题并停止，不要取数或生成页面。
- 如果任务文本包含“承接上一轮澄清”“原始问题”“用户补充”，将原始问题和补充信息合并为完整任务继续执行；补充后仍不清楚时只追问剩余缺口。
- 如果任务涉及股票、行情、量化分析或可视化，先使用对应数据 skill 获取真实数据，再使用 quant-visualization-html 生成可视化看板。
- 调用本地 HTTP API 且参数包含中文时，必须使用 curl -G --data-urlencode，不要把中文直接拼接到 URL 查询串。
- 获取真实数据后、生成看板前，必须使用 quant-data-quality 写入 evidence/sources.json 和 evidence/data_quality.json，记录来源、时间、缺失字段和限制。
- 如果用户要求可视化或看板，必须实际修改 app/page.tsx，不能只输出文字说明。
- 修改源码、CSS、JSON 或 evidence 时必须使用 Write/Edit 工具；不要用 Bash 的 cat、tee、echo、printf、python/node 脚本、重定向或 heredoc 写文件。
- A 股趋势类页面必须优先包含 K 线/量价/均线/风险指标；历史接口失败时也要生成 K 线面板、真实错误和重试入口。
- 最终数据优先写入 data_file/final/dashboard-data.json，页面应读取真实数据或同源 API，不得硬编码样例行情。
- .quantpilot/run_plan.json 的 symbols 必须保持为证券代码字符串数组，例如 ["600519"]；如果需要名称、市场、secid，请写入 resolvedSymbols[] 或 final 数据，避免平台预取链路无法识别。
- dashboard-data.json 使用标准契约：quote.price/change_percent/quote_time、kline.bars[].date/open/high/low/close/volume/amount、technicalIndicators.summary 或 computedMetrics；多标的使用 assets[] 和 comparison.rows[]。
- 页面优先保留平台标准模板中的 DATA_FILE、readDashboardData、getBars、TrendChart 和 data-source-file={DATA_FILE} 结构，在此基础上增强展示，不要改成无法验证的自定义数据入口。
- Agent 执行完成后平台会自动验证 Next.js build、预览 HTTP 200、data_file/final 数据文件、页面图表和 /api/market 代理；请按这些验收项完成产物。
- 当 .quantpilot/run_plan.json、data_file/final/dashboard-data.json、evidence/sources.json、evidence/data_quality.json 和 app/page.tsx 已经完成后，立即输出中文执行摘要并结束；不要继续运行 whoami、echo、hello world、临时文件写入或无关 Bash 测试。
- 默认输出中文可见执行过程摘要；开始时直接用 Markdown 输出任务拆解、执行计划和当前状态，执行中必须按阶段解释每个 skill、数据请求、文件读写和验证结果，不要只连续输出工具调用，不要使用 <thinking> 标签，不要暴露隐藏推理链。
- 每次调用 skill 前先写“现在使用 \`skill-name\` ...”，说明本步目的；调用后说明得到的数据、文件或校验结论。若只是平台已经确认过的澄清追问，不要输出无价值的“已返回结果，正在进入下一步处理”。
- 每组 Bash/Read/Write/Edit 前后都写 1-2 句中文说明，包含接口、标的、时间范围、记录数、关键字段、数据质量或下一步。
- Todo List 要持续更新，已完成项用 ✅，失败或待处理项用 ❌/⏳ 并写明原因；最终验证要逐项说明 build、HTTP、数据文件、图表和 /api/market 代理。
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
- By default, write visible Chinese process narration for quantitative tasks as normal Markdown. Start with task decomposition, execution plan, and current status; during execution, explain every skill, data request, file read/write, and validation result as staged user-visible progress. Do not emit only raw tool calls. Do not use <thinking> tags and do not reveal hidden chain-of-thought
- Before each skill call, write a short Chinese sentence in the form "现在使用 \`skill-name\` ..." explaining the purpose; after the call, summarize the resulting data, artifact, or validation conclusion
- Around Bash/Read/Write/Edit groups, write 1-2 Chinese sentences with endpoint, symbol, time range, row count, key fields, data quality, or next step
- Keep Todo List updated with ✅/❌/⏳ status and explain failures or pending items; final validation must cover build, HTTP, data files, chart presence, and /api/market proxy
- For quantitative analysis tasks, first use the quant-run-planner skill and update .quantpilot/run_plan.json before fetching data or editing app/page.tsx
- If the user request is missing critical inputs such as target symbol/name, comparison universe, or investment horizon/risk preference for recommendation-like tasks, use quant-run-planner to set run_plan.status to needs_clarification, ask 1-3 concise Chinese clarification questions, and stop. Do not fetch data or generate pages while clarification is required
- If the prompt includes "承接上一轮澄清", "原始问题", and "用户补充", merge the original question and the clarification response into one complete task before planning. If the merged task is clear, continue with planned data fetching and dashboard generation; if not, ask only the remaining clarification questions
- For stock data tasks, first use the quant-market-data skill to fetch required market data from http://127.0.0.1:8000
- For broad financial data tasks, first use quant-data-registry to select the right data endpoint
- For Chinese query parameters in local HTTP requests, use curl -G --data-urlencode. Do not concatenate raw Chinese text into URLs
- After fetching market, K-line, financial, or event data, use quant-data-quality before visualization and write evidence/sources.json plus evidence/data_quality.json
- Resolve ambiguous stock names or tickers with quant-symbol-resolver before fetching data
- Use quant-comparison for multi-symbol questions. When dashboard-data.json contains assets[] and comparison, render all assets instead of only the primary symbol
- Use quant-a-share-history for historical K-line analysis
- Use quant-index-etf-market for index and ETF tasks such as 沪深300、创业板指、中证500、科创50 or 510300 ETF
- Use quant-technical-indicators for moving averages, returns, drawdown, volatility, and volume metrics
- Use quant-fundamental-financials for revenue, profit, ROE, margin, and growth analysis
- Use quant-fundamental-indicators for derived profitability, margin, ROE, and financial quality metrics
- Use quant-announcement-events for announcement/event-driven context
- For visualization tasks, use the quant-visualization-html skill and actually edit app/page.tsx into a usable dashboard
- Use Write/Edit tools for source, CSS, JSON, and evidence file changes. Do not use Bash cat/tee/echo/printf, redirection, heredoc, python/node scripts, or touch to write files
- A-share visualization dashboards must include real chart panels; for trend tasks include candlestick/OHLC or an explicit K-line error panel, volume, moving averages, and risk metrics
- Prefer same-origin API routes in generated projects to proxy http://127.0.0.1:8000 instead of direct browser calls
- Do not hard-code stock quote data; fetch it before analysis and keep refresh capability in the generated page
- Before finishing a quantitative dashboard, ensure data_file/final/dashboard-data.json exists, app/page.tsx reads real data or same-origin APIs, and /api/market/** proxies the local market backend
- Keep .quantpilot/run_plan.json symbols as an array of ticker strings. Store rich resolved symbol objects elsewhere, not in symbols
- Keep dashboard-data.json schema-compatible with quote, kline.bars, technicalIndicators.summary/computedMetrics, and assets[]/comparison for multi-symbol dashboards
- Once .quantpilot/run_plan.json, data_file/final/dashboard-data.json, evidence/sources.json, evidence/data_quality.json, and app/page.tsx are complete, immediately provide a concise Chinese execution summary and stop. Do not run unrelated Bash checks such as whoami, echo, hello-world scripts, temporary file writes, or ad-hoc process tests
- Include loading, error, and empty states for market data
- Display source, quote_time, and fetched_at when showing live stock data
- Use A-share color convention: red for gains and green for losses
- If no symbols are specified, default to 600519, 000001, and 300750
- Do not default missing symbols when the user request is genuinely unclear. Default symbols are only allowed for explicit demos, benchmark checks, or when the user asks for a generic sample dashboard
- Do not add styling dependencies or create @import "tailwindcss" unless explicitly requested
- Write clean, production-ready code
- Follow best practices
- The platform automatically installs dependencies and manages the preview dev server. Do not run package managers or dev-server commands yourself; rely on the existing preview.
- Keep all project files directly in the project root. Never scaffold frameworks into subdirectories.
- Never override ports or start your own development server processes. Rely on the managed preview service which assigns ports from the approved pool.
- When sharing a preview link, read the actual NEXT_PUBLIC_APP_URL instead of assuming a default port.
- Prefer giving the user the live preview link that is actually running rather than written instructions.`;
}
