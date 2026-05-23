import fs from 'fs/promises';
import path from 'path';

const SKILLS_DIR = path.join(process.cwd(), '.claude', 'skills');

export const DEFAULT_CLAUDE_SKILLS = [
  'quant-data-registry',
  'quant-symbol-resolver',
  'quant-market-data',
  'quant-a-share-history',
  'quant-fundamental-financials',
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

export function buildQuantPilotTaskPrompt(instruction: string, projectPath: string): string {
  const normalizedProjectPath = path.resolve(projectPath);

  return `${instruction}

QuantPilot 执行约束：
- 当前生成项目根目录是：${normalizedProjectPath}
- 所有文件读取、创建、修改和删除都必须限定在当前生成项目根目录内。
- 不要修改父级 QuantPilot 平台工程文件，也不要把页面代码写入平台根目录。
- 如果任务涉及股票、行情、量化分析或可视化，先使用对应数据 skill 获取真实数据，再使用 quant-visualization-html 生成可视化看板。
- 如果用户要求可视化或看板，必须实际修改 app/page.tsx，不能只输出文字说明。
- A 股趋势类页面必须优先包含 K 线/量价/均线/风险指标；历史接口失败时也要生成 K 线面板、真实错误和重试入口。
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
- When the user asks for visible thinking or process narration, write a concise execution summary inside <thinking>...</thinking>; do not reveal hidden chain-of-thought
- For stock data tasks, first use the quant-market-data skill to fetch required market data from http://127.0.0.1:8000
- For broad financial data tasks, first use quant-data-registry to select the right data endpoint
- Resolve ambiguous stock names or tickers with quant-symbol-resolver before fetching data
- Use quant-a-share-history for historical K-line analysis
- Use quant-fundamental-financials for revenue, profit, ROE, margin, and growth analysis
- Use quant-announcement-events for announcement/event-driven context
- For visualization tasks, use the quant-visualization-html skill and actually edit app/page.tsx into a usable dashboard
- A-share visualization dashboards must include real chart panels; for trend tasks include candlestick/OHLC or an explicit K-line error panel, volume, moving averages, and risk metrics
- Prefer same-origin API routes in generated projects to proxy http://127.0.0.1:8000 instead of direct browser calls
- Do not hard-code stock quote data; fetch it before analysis and keep refresh capability in the generated page
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
