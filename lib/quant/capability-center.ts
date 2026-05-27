import {
  DEFAULT_QUANT_CAPABILITY_ID,
  QUANT_CAPABILITY_GROUPS,
  serializeQuantCapabilities,
} from '@/lib/quant/capabilities';
import { getSkillsDashboardData } from '@/lib/quant/skills-dashboard';

type JsonRecord = Record<string, unknown>;

export interface CapabilityCenterSkillRef {
  id: string;
  name: string;
  version: string;
  status: string;
  health: string;
  requestedId: string;
  viaAlias: boolean;
}

export interface CapabilityCenterItem {
  id: string;
  name: string;
  shortName: string;
  description: string;
  inputHint: string;
  tags: string[];
  status: string;
  groupId: string;
  agentType: string;
  executionCapabilityId: string;
  requiredSkills: CapabilityCenterSkillRef[];
  missingSkills: string[];
  legacySkillAliases: Array<{
    alias: string;
    target: string;
  }>;
  dataEndpoints: string[];
  expectedArtifacts: string[];
  validationRules: string[];
  readiness: {
    status: 'ready' | 'warning' | 'blocked' | 'planned';
    summary: string;
    score: number;
  };
}

export interface CapabilityCenterDataProvider {
  id: string;
  name: string;
  category: string;
  status: string;
  description: string;
  endpoints: string[];
  cacheTtlSeconds: number | null;
  limitations: string[];
}

export interface CapabilityCenterData {
  generatedAt: string;
  defaultCapabilityId: string;
  groups: typeof QUANT_CAPABILITY_GROUPS;
  summary: {
    capabilities: number;
    readyCapabilities: number;
    plannedCapabilities: number;
    blockedCapabilities: number;
    skills: number;
    skillErrors: number;
    dataProviders: number;
    availableProviders: number;
    degradedProviders: number;
    marketApiReachable: boolean;
  };
  marketApi: {
    baseUrl: string;
    reachable: boolean;
    status: string;
    checkedAt: string;
    error: string | null;
  };
  capabilities: CapabilityCenterItem[];
  dataProviders: CapabilityCenterDataProvider[];
}

const MARKET_API_BASE_URL = process.env.QUANTPILOT_MARKET_API_BASE_URL || 'http://127.0.0.1:8000';

const FALLBACK_DATA_PROVIDERS: CapabilityCenterDataProvider[] = [
  {
    id: 'eastmoney-realtime',
    name: '东方财富实时行情',
    category: 'market-data',
    status: 'available',
    description: 'A 股实时价格、成交额、市值等快照数据。',
    endpoints: ['/api/v1/quotes/realtime/{symbol}', '/api/v1/quotes/realtime'],
    cacheTtlSeconds: 30,
    limitations: ['实时行情使用短 TTL 缓存，盘中价格可能存在数秒延迟。'],
  },
  {
    id: 'eastmoney-symbol-resolver',
    name: '东方财富证券搜索',
    category: 'symbol',
    status: 'available',
    description: '按股票代码、简称或中文名称解析证券标识和 secid。',
    endpoints: ['/api/v1/symbols/resolve'],
    cacheTtlSeconds: 86_400,
    limitations: [],
  },
  {
    id: 'eastmoney-kline',
    name: '东方财富历史 K 线 / 指数 / ETF',
    category: 'market-data',
    status: 'degraded',
    description: 'A 股个股、常见指数和 ETF 的历史行情。',
    endpoints: ['/api/v1/quotes/history/{symbol}'],
    cacheTtlSeconds: 3_600,
    limitations: ['外部源偶发断连，后续会接入更多降级源。'],
  },
  {
    id: 'quantpilot-technical-indicators',
    name: 'QuantPilot 技术指标',
    category: 'indicator',
    status: 'available',
    description: '基于历史 K 线计算均线、区间收益、最大回撤和波动率。',
    endpoints: ['/api/v1/indicators/technical/{symbol}'],
    cacheTtlSeconds: 3_600,
    limitations: [],
  },
  {
    id: 'quantpilot-ma-crossover-backtest',
    name: 'QuantPilot 均线突破回测',
    category: 'backtest',
    status: 'available',
    description: '基于历史 K 线运行单标的均线突破策略。',
    endpoints: ['/api/v1/backtests/ma-crossover/{symbol}'],
    cacheTtlSeconds: 3_600,
    limitations: ['当前为单标的、全仓/空仓、日线级回测。'],
  },
  {
    id: 'eastmoney-index-etf-market',
    name: '东方财富指数与 ETF 行情',
    category: 'index-etf',
    status: 'available',
    description: '常见指数和 ETF 的实时行情、历史 K 线与技术指标。',
    endpoints: [
      '/api/v1/symbols/resolve',
      '/api/v1/quotes/realtime/{symbol}',
      '/api/v1/quotes/history/{symbol}',
      '/api/v1/indicators/technical/{symbol}',
    ],
    cacheTtlSeconds: 3_600,
    limitations: ['指数/ETF 默认不提供个股财务摘要和公告事件。'],
  },
  {
    id: 'eastmoney-financial-summary',
    name: '东方财富财务摘要',
    category: 'fundamental',
    status: 'available',
    description: '上市公司主要财务指标、营收、归母净利润、ROE、毛利率等。',
    endpoints: ['/api/v1/fundamentals/financials/{symbol}'],
    cacheTtlSeconds: 86_400,
    limitations: [],
  },
  {
    id: 'quantpilot-fundamental-indicators',
    name: 'QuantPilot 财务衍生指标',
    category: 'fundamental',
    status: 'available',
    description: '基于财务摘要计算净利率、平均 ROE、毛利率和最近报告期核心指标。',
    endpoints: ['/api/v1/indicators/fundamental/{symbol}'],
    cacheTtlSeconds: 86_400,
    limitations: [],
  },
  {
    id: 'eastmoney-announcements',
    name: '东方财富公告事件',
    category: 'event',
    status: 'available',
    description: '上市公司公告标题、公告日期、栏目和详情链接。',
    endpoints: ['/api/v1/events/announcements/{symbol}'],
    cacheTtlSeconds: 86_400,
    limitations: ['公告全文解析后续单独增强。'],
  },
];

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function normalizeProvider(value: unknown): CapabilityCenterDataProvider | null {
  if (!isRecord(value)) return null;
  const id = typeof value.id === 'string' ? value.id : '';
  const name = typeof value.name === 'string' ? value.name : id;
  if (!id || !name) return null;
  return {
    id,
    name,
    category: typeof value.category === 'string' ? value.category : 'unknown',
    status: typeof value.status === 'string' ? value.status : 'unknown',
    description: typeof value.description === 'string' ? value.description : '',
    endpoints: asStringArray(value.endpoints),
    cacheTtlSeconds: typeof value.cache_ttl_seconds === 'number'
      ? value.cache_ttl_seconds
      : typeof value.cacheTtlSeconds === 'number'
      ? value.cacheTtlSeconds
      : null,
    limitations: asStringArray(value.limitations),
  };
}

async function fetchMarketRegistry(): Promise<{
  reachable: boolean;
  status: string;
  error: string | null;
  providers: CapabilityCenterDataProvider[];
}> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2_500);
  try {
    const healthResponse = await fetch(`${MARKET_API_BASE_URL}/health`, {
      cache: 'no-store',
      signal: controller.signal,
    });
    const registryResponse = await fetch(`${MARKET_API_BASE_URL}/api/v1/registry`, {
      cache: 'no-store',
      signal: controller.signal,
    });
    const registry = await registryResponse.json().catch((): JsonRecord => ({}));
    const providerValues = isRecord(registry) && Array.isArray(registry.providers) ? registry.providers : [];
    const providers = providerValues.length
      ? providerValues.map(normalizeProvider).filter((provider): provider is CapabilityCenterDataProvider => Boolean(provider))
      : [];

    return {
      reachable: healthResponse.ok && registryResponse.ok,
      status: healthResponse.ok && registryResponse.ok ? 'online' : 'degraded',
      error: healthResponse.ok && registryResponse.ok ? null : `market API returned ${healthResponse.status}/${registryResponse.status}`,
      providers: providers.length ? providers : FALLBACK_DATA_PROVIDERS,
    };
  } catch (error) {
    return {
      reachable: false,
      status: 'offline',
      error: error instanceof Error ? error.message : String(error),
      providers: FALLBACK_DATA_PROVIDERS,
    };
  } finally {
    clearTimeout(timeout);
  }
}

function buildReadiness(params: {
  status: string;
  missingSkills: string[];
  skillErrors: number;
  endpointCount: number;
}): CapabilityCenterItem['readiness'] {
  if (params.status === 'planned') {
    return {
      status: 'planned',
      score: Math.max(30, 70 - params.missingSkills.length * 8 - params.skillErrors * 6),
      summary: '规划能力，会降级到已验证执行能力。',
    };
  }
  if (params.missingSkills.length || params.skillErrors) {
    return {
      status: params.missingSkills.length ? 'blocked' : 'warning',
      score: Math.max(0, 88 - params.missingSkills.length * 14 - params.skillErrors * 7),
      summary: params.missingSkills.length
        ? `缺少 ${params.missingSkills.length} 个依赖 Skill。`
        : `${params.skillErrors} 个依赖 Skill 健康异常。`,
    };
  }
  if (!params.endpointCount) {
    return {
      status: 'warning',
      score: 78,
      summary: '能力可用，但未声明数据端点。',
    };
  }
  return {
    status: 'ready',
    score: 100,
    summary: '依赖 Skill、数据端点和产物契约已声明。',
  };
}

export async function getCapabilityCenterData(): Promise<CapabilityCenterData> {
  const [skillsData, market] = await Promise.all([
    getSkillsDashboardData(),
    fetchMarketRegistry(),
  ]);
  const skillMap = new Map(skillsData.skills.map((skill) => [skill.id, skill]));
  const aliasMap = new Map(Object.entries(skillsData.legacyAliases ?? {}));
  const capabilities = serializeQuantCapabilities().map((capability): CapabilityCenterItem => {
    const requiredSkillIds = asStringArray(capability.requiredSkills);
    const requiredSkills = requiredSkillIds.flatMap((skillId) => {
      const resolvedSkillId = aliasMap.get(skillId) ?? skillId;
      const skill = skillMap.get(resolvedSkillId);
      if (!skill) return [];
      return [{
        id: skill.id,
        name: skill.name,
        version: skill.version,
        status: skill.status,
        health: skill.health.status,
        requestedId: skillId,
        viaAlias: resolvedSkillId !== skillId,
      }];
    });
    const missingSkills = requiredSkillIds.filter((skillId) => !skillMap.has(aliasMap.get(skillId) ?? skillId));
    const legacySkillAliases = requiredSkillIds.flatMap((skillId) => {
      const target = aliasMap.get(skillId);
      return target ? [{ alias: skillId, target }] : [];
    });
    const skillErrors = requiredSkills.filter((skill) => skill.health === 'error').length;
    const dataEndpoints = asStringArray(capability.dataEndpoints);
    return {
      id: capability.id,
      name: capability.name,
      shortName: capability.shortName,
      description: capability.description,
      inputHint: capability.inputHint,
      tags: capability.tags,
      status: capability.status,
      groupId: capability.groupId,
      agentType: capability.agentType,
      executionCapabilityId: capability.executionCapabilityId,
      requiredSkills,
      missingSkills,
      legacySkillAliases,
      dataEndpoints,
      expectedArtifacts: asStringArray(capability.expectedArtifacts),
      validationRules: asStringArray(capability.validationRules),
      readiness: buildReadiness({
        status: capability.status,
        missingSkills,
        skillErrors,
        endpointCount: dataEndpoints.length,
      }),
    };
  });

  const summary = capabilities.reduce(
    (acc, capability) => {
      acc.capabilities += 1;
      if (capability.status === 'ready') acc.readyCapabilities += 1;
      if (capability.status === 'planned') acc.plannedCapabilities += 1;
      if (capability.readiness.status === 'blocked') acc.blockedCapabilities += 1;
      return acc;
    },
    {
      capabilities: 0,
      readyCapabilities: 0,
      plannedCapabilities: 0,
      blockedCapabilities: 0,
      skills: skillsData.totals.total,
      skillErrors: skillsData.totals.error,
      dataProviders: market.providers.length,
      availableProviders: market.providers.filter((provider) => provider.status === 'available').length,
      degradedProviders: market.providers.filter((provider) => provider.status === 'degraded').length,
      marketApiReachable: market.reachable,
    },
  );

  return {
    generatedAt: new Date().toISOString(),
    defaultCapabilityId: DEFAULT_QUANT_CAPABILITY_ID,
    groups: QUANT_CAPABILITY_GROUPS,
    summary,
    marketApi: {
      baseUrl: MARKET_API_BASE_URL,
      reachable: market.reachable,
      status: market.status,
      checkedAt: new Date().toISOString(),
      error: market.error,
    },
    capabilities,
    dataProviders: market.providers,
  };
}
