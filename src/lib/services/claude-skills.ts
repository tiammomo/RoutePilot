import fs from 'fs/promises';
import path from 'path';
import { getTravelCapability } from '@/lib/travel/capabilities';
import { serializeTravelVisualizationTemplate } from '@/lib/travel/visualization-templates';

const TRAVEL_SKILLS = [
  'travel-run-planner',
  'travel-poi-retrieval',
  'travel-ugc-evidence',
  'travel-route-optimizer',
  'travel-visualization-html',
  'travel-constraint-validator',
];

type TravelManifest = {
  travel?: {
    capabilityId?: string;
    agentType?: string;
    subAgentKey?: string;
    requiredSkills?: string[];
    dataEndpoints?: string[];
    expectedArtifacts?: string[];
    validationRules?: string[];
  };
};

type TravelRunPlan = {
  capabilityId?: string;
  requestedCapabilityId?: string;
  executionCapabilityId?: string;
  dataRequirements?: string[];
  expectedArtifacts?: string[];
  validationRules?: string[];
  visualization?: {
    templateId?: string;
    name?: string;
    scenario?: string;
    panels?: string[];
    painPoints?: string[];
    dataSignals?: string[];
  };
};

export async function getDefaultClaudeSkills(): Promise<string[]> {
  return TRAVEL_SKILLS;
}

export async function ensureClaudeSkillsForProject(projectPath: string): Promise<string[]> {
  await fs.mkdir(path.join(projectPath, '.claude', 'skills'), { recursive: true });
  return TRAVEL_SKILLS;
}

export async function readQuantPilotManifest(projectPath: string): Promise<TravelManifest | null> {
  try {
    const content = await fs.readFile(path.join(projectPath, '.travelpilot', 'manifest.json'), 'utf8');
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? (parsed as TravelManifest) : null;
  } catch {
    return null;
  }
}

async function readTravelRunPlan(projectPath: string): Promise<TravelRunPlan | null> {
  try {
    const content = await fs.readFile(path.join(projectPath, '.travelpilot', 'run_plan.json'), 'utf8');
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? (parsed as TravelRunPlan) : null;
  } catch {
    return null;
  }
}

function listText(items: string[] | undefined, fallback = '无') {
  return items?.length ? items.join('；') : fallback;
}

async function buildCapabilityContext(manifest: TravelManifest | null, runPlan: TravelRunPlan | null) {
  const manifestTravel = manifest?.travel;
  const runCapabilityId = runPlan?.requestedCapabilityId ?? runPlan?.capabilityId;
  const capability = getTravelCapability(runCapabilityId ?? manifestTravel?.capabilityId);
  const shouldInheritManifest = !runCapabilityId || manifestTravel?.capabilityId === capability.id;
  const requiredSkills =
    shouldInheritManifest && manifestTravel?.requiredSkills?.length
      ? manifestTravel.requiredSkills
      : capability.requiredSkills;
  const dataEndpoints = runPlan?.dataRequirements?.length
    ? runPlan.dataRequirements
    : shouldInheritManifest && manifestTravel?.dataEndpoints?.length
      ? manifestTravel.dataEndpoints
      : capability.dataEndpoints;
  const expectedArtifacts = runPlan?.expectedArtifacts?.length
    ? runPlan.expectedArtifacts
    : shouldInheritManifest && manifestTravel?.expectedArtifacts?.length
      ? manifestTravel.expectedArtifacts
      : capability.expectedArtifacts;
  const validationRules = runPlan?.validationRules?.length
    ? runPlan.validationRules
    : shouldInheritManifest && manifestTravel?.validationRules?.length
      ? manifestTravel.validationRules
      : capability.validationRules;
  const template = serializeTravelVisualizationTemplate(capability.id);

  return `当前北京旅游路线能力：
- capability_id: ${capability.id}
- requested_capability_id: ${runPlan?.requestedCapabilityId ?? capability.id}
- execution_capability_id: ${runPlan?.executionCapabilityId ?? capability.executionCapabilityId}
- agent_type: ${shouldInheritManifest ? manifestTravel?.agentType ?? capability.agentType : capability.agentType}
- sub_agent_key: ${shouldInheritManifest ? manifestTravel?.subAgentKey ?? capability.subAgentKey : capability.subAgentKey}
- 名称：${capability.name}
- 说明：${capability.description}
- 必需规划模块：${listText(requiredSkills)}
- 可用数据接口：${listText(dataEndpoints)}
- 预期产物：${listText(expectedArtifacts)}
- 验证规则：${listText(validationRules)}
- 能力指导：${listText(capability.promptGuidance)}
- 可视化模板：${runPlan?.visualization?.templateId ?? template.templateId}；${runPlan?.visualization?.name ?? template.name}
- 必备组件：${listText(runPlan?.visualization?.panels ?? template.requiredComponents)}
- 数据信号：${listText(runPlan?.visualization?.dataSignals ?? template.dataSignals)}`;
}

export async function buildQuantPilotTaskPrompt(
  instruction: string,
  projectPath: string,
  manifest: TravelManifest | null = null,
): Promise<string> {
  const normalizedProjectPath = path.resolve(projectPath);
  const runPlan = await readTravelRunPlan(normalizedProjectPath);
  const capabilityContext = await buildCapabilityContext(manifest, runPlan);

  return `${instruction}

北京旅游 Agent 执行约束：
- 当前生成项目根目录是：${normalizedProjectPath}
- ${capabilityContext}
- 所有文件读取、创建、修改和删除都必须限定在当前生成项目根目录内。
- 不要修改父级北京旅游 Agent 平台工程文件。
- 如果当前任务是北京旅游路线规划，先生成或更新 .travelpilot/run_plan.json，记录城市、区域、路线模式、时间、预算、步行、排队偏好、预期图表和验证项。
- 获取 POI/UGC 数据、生成 final 数据、修改页面、验证结果时，将可见摘要追加到 .travelpilot/events.jsonl。
- 如果用户问题缺少城市/区域、时长、预算或路线偏好等关键输入，先设置 status=needs_clarification，向用户提出 1-3 个澄清问题并停止。
- 涉及北京路线、POI、餐饮、UGC 或可视化时，优先调用 /api/v1/travel/parse-and-plan、/api/v1/travel/plan、/api/v1/travel/replan 获取本地规划结果。
- 队列风险和通勤时间都是静态/历史估算，不要表述为实时事实。
- 生成路线页面前，写入 evidence/sources.json、evidence/data_quality.json 和 data_file/final/itinerary-data.json。
- 路线页面必须包含方案对比、时间轴、POI 卡片、预算/时长/步行估算、UGC 证据和风险提示。
- 最终用中文输出简洁执行摘要。`;
}

export function buildQuantPilotSystemPrompt(): string {
  return `You are an expert web developer building a Beijing travel route planning application for 北京旅游 Agent.
- Use Next.js App Router and TypeScript.
- Only work inside the generated project directory passed as cwd.
- Never edit the parent Beijing travel Agent platform repository.
- Build an actual usable Beijing itinerary planning interface, not a placeholder page.
- Use local Travel APIs under /api/v1/travel/** as the source of truth.
- Treat queue risk and commute time as static/local estimates, not real-time facts.
- For visualization tasks, create a real itinerary dashboard with proposal comparison, timeline, POI cards, budget/duration/walking, UGC evidence, and risk notes.
- Write clean, production-ready code and stop after a concise Chinese execution summary.`;
}
