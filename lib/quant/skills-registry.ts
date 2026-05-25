import fs from 'fs/promises';
import path from 'path';

export type QuantSkillStatus = 'stable' | 'planned' | 'deprecated';

export interface QuantCoreSkill {
  id: string;
  name: string;
  version: string;
  status: QuantSkillStatus;
  boundary: string;
  inputs?: string[];
  outputs?: string[];
  scripts?: string[];
  endpoints?: string[];
  legacyAliases?: string[];
  validation?: string[];
}

export interface QuantSkillsRegistry {
  schemaVersion: 1;
  policy: {
    targetCoreSkillCount: number;
    allowLegacyAliases: boolean;
    installLegacyByDefault?: boolean;
    packageFormat?: 'tgz';
    packageDir?: string;
    description: string;
  };
  coreSkills: QuantCoreSkill[];
  legacyAliases: Record<string, string>;
}

const REGISTRY_PATH = path.join(process.cwd(), '.claude', 'skills.registry.json');

const FALLBACK_CORE_SKILLS: QuantCoreSkill[] = [
  {
    id: 'quant-run-planner',
    name: '运行规划',
    version: '0.1.0',
    status: 'stable',
    boundary: '意图澄清、任务拆解和 run_plan 生成。',
  },
  {
    id: 'quant-data-registry',
    name: '数据注册与信源选择',
    version: '0.1.0',
    status: 'stable',
    boundary: '查询后端数据能力和信源选择。',
  },
  {
    id: 'quant-symbol-resolver',
    name: '标的解析',
    version: '0.1.0',
    status: 'stable',
    boundary: '把名称和代码解析为标准证券标识。',
  },
  {
    id: 'quant-market-data',
    name: '行情数据',
    version: '0.1.0',
    status: 'stable',
    boundary: '实时行情、K 线和指数/ETF 数据。',
  },
  {
    id: 'quant-data-quality',
    name: '数据质量',
    version: '0.1.0',
    status: 'stable',
    boundary: '生成来源、质量和限制证据。',
  },
  {
    id: 'quant-visualization-html',
    name: '可视化看板',
    version: '0.1.0',
    status: 'stable',
    boundary: '基于 final 数据生成 Next.js 看板。',
  },
];

const FALLBACK_REGISTRY: QuantSkillsRegistry = {
  schemaVersion: 1,
  policy: {
    targetCoreSkillCount: 9,
    allowLegacyAliases: true,
    installLegacyByDefault: false,
    packageFormat: 'tgz',
    packageDir: '.claude/skill-packages',
    description: 'Fallback QuantPilot skills registry.',
  },
  coreSkills: FALLBACK_CORE_SKILLS,
  legacyAliases: {},
};

let cachedRegistry: QuantSkillsRegistry | null = null;

function asRegistry(value: unknown): QuantSkillsRegistry | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const registry = value as QuantSkillsRegistry;
  if (registry.schemaVersion !== 1 || !Array.isArray(registry.coreSkills)) {
    return null;
  }

  return registry;
}

export async function readQuantSkillsRegistry(): Promise<QuantSkillsRegistry> {
  if (cachedRegistry) {
    return cachedRegistry;
  }

  try {
    const content = await fs.readFile(REGISTRY_PATH, 'utf8');
    const parsed = asRegistry(JSON.parse(content));
    cachedRegistry = parsed ?? FALLBACK_REGISTRY;
  } catch {
    cachedRegistry = FALLBACK_REGISTRY;
  }

  return cachedRegistry;
}

export function getCoreQuantSkillIds(registry: QuantSkillsRegistry): string[] {
  return registry.coreSkills.map((skill) => skill.id);
}

export function getLegacyQuantSkillIds(registry: QuantSkillsRegistry): string[] {
  return Object.keys(registry.legacyAliases ?? {});
}

export function getDefaultQuantSkillIds(
  registry: QuantSkillsRegistry,
  options: { includeLegacy?: boolean } = {}
): string[] {
  const ids = new Set(getCoreQuantSkillIds(registry));
  const includeLegacy = options.includeLegacy ?? registry.policy.installLegacyByDefault ?? false;

  if (includeLegacy) {
    for (const alias of getLegacyQuantSkillIds(registry)) {
      ids.add(alias);
    }
  }

  return Array.from(ids);
}

export function getQuantSkillPackagePath(registry: QuantSkillsRegistry, skillId: string): string {
  const packageDir = registry.policy.packageDir ?? '.claude/skill-packages';
  return path.join(process.cwd(), packageDir, `${skillId}.tgz`);
}

export function describeQuantSkillsForPrompt(registry: QuantSkillsRegistry): string {
  const coreLines = registry.coreSkills.map((skill) => {
    const aliasText = skill.legacyAliases?.length
      ? `；兼容别名：${skill.legacyAliases.join(', ')}`
      : '';
    const scriptText = skill.scripts?.length ? `；脚本：${skill.scripts.join(', ')}` : '';
    return `- ${skill.id}（${skill.name}，${skill.status}，v${skill.version}）：${skill.boundary}${aliasText}${scriptText}`;
  });

  return [
    'QuantPilot skills 治理：',
    `- 目标核心 skill 数量：${registry.policy.targetCoreSkillCount}`,
    `- 默认安装 legacy alias：${registry.policy.installLegacyByDefault ? '是' : '否'}`,
    `- 规则：${registry.policy.description}`,
    ...coreLines,
  ].join('\n');
}
