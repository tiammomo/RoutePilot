import {
  DEFAULT_TRAVEL_CAPABILITY_ID,
  TRAVEL_CAPABILITIES,
  TRAVEL_CAPABILITY_GROUPS,
} from '@/lib/travel/capabilities';
import { travelHealth } from '@/lib/travel/planner';

export interface TravelCapabilityCenterData {
  generatedAt: string;
  defaultCapabilityId: string;
  groups: typeof TRAVEL_CAPABILITY_GROUPS;
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
    poiCount: number;
    reviewFeatureCount: number;
    travelApiReachable: boolean;
  };
  travelApi: {
    baseUrl: string;
    reachable: boolean;
    status: string;
    checkedAt: string;
    error: string | null;
  };
  marketApi: {
    baseUrl: string;
    reachable: boolean;
    status: string;
    checkedAt: string;
    error: string | null;
  };
  capabilities: Array<{
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
    requiredSkills: Array<{ id: string; name: string; version: string; status: string; health: string; requestedId: string; viaAlias: boolean }>;
    missingSkills: string[];
    legacySkillAliases: Array<{ alias: string; target: string }>;
    dataEndpoints: string[];
    expectedArtifacts: string[];
    validationRules: string[];
    readiness: { status: 'ready' | 'warning' | 'blocked' | 'planned'; summary: string; score: number };
  }>;
  dataProviders: Array<{
    id: string;
    name: string;
    category: string;
    status: string;
    description: string;
    endpoints: string[];
    cacheTtlSeconds: number | null;
    limitations: string[];
  }>;
}

export async function getTravelCapabilityCenterData(): Promise<TravelCapabilityCenterData> {
  const health = await travelHealth();
  const providers = [
    {
      id: 'beijing-poi-processed',
      name: '北京 POI 本地数据集',
      category: 'poi-data',
      status: 'available',
      description: '来自仓库内 travel-data/processed 的文化、餐饮、娱乐 POI 与规划实体。',
      endpoints: ['/api/v1/travel/pois', '/api/v1/travel/options'],
      cacheTtlSeconds: null,
      limitations: ['本地静态数据，不代表实时营业或实时导航。'],
    },
    {
      id: 'beijing-ugc-features',
      name: 'UGC 评论特征聚合',
      category: 'ugc-evidence',
      status: 'available',
      description: '覆盖排队风险、性价比、亲子友好和环境质量等评论语义信号。',
      endpoints: ['/api/v1/travel/evidence/{poi_id}'],
      cacheTtlSeconds: null,
      limitations: ['UGC 特征来自历史评论，不代表当前排队状态。'],
    },
    {
      id: 'travel-route-planner',
      name: '本地路线规划引擎',
      category: 'route-planning',
      status: 'available',
      description: '基于 POI、坐标、营业时间、预算和 UGC 信号生成三套路线方案。',
      endpoints: ['/api/v1/travel/parse-and-plan', '/api/v1/travel/plan', '/api/v1/travel/replan'],
      cacheTtlSeconds: null,
      limitations: ['转移时间按坐标估算，不接入实时地图路径。'],
    },
  ];
  return {
    generatedAt: new Date().toISOString(),
    defaultCapabilityId: DEFAULT_TRAVEL_CAPABILITY_ID,
    groups: TRAVEL_CAPABILITY_GROUPS,
    summary: {
      capabilities: TRAVEL_CAPABILITIES.length,
      readyCapabilities: TRAVEL_CAPABILITIES.filter((item) => item.status === 'ready').length,
      plannedCapabilities: 0,
      blockedCapabilities: 0,
      skills: 6,
      skillErrors: 0,
      dataProviders: providers.length,
      availableProviders: providers.filter((item) => item.status === 'available').length,
      degradedProviders: 0,
      marketApiReachable: health.status === 'ok',
      poiCount: health.counts.planner_entities,
      reviewFeatureCount: health.counts.review_aggregates,
      travelApiReachable: health.status === 'ok',
    },
    travelApi: {
      baseUrl: '/api/v1/travel',
      reachable: health.status === 'ok',
      status: health.status,
      checkedAt: new Date().toISOString(),
      error: null,
    },
    marketApi: {
      baseUrl: '/api/v1/travel',
      reachable: health.status === 'ok',
      status: health.status,
      checkedAt: new Date().toISOString(),
      error: null,
    },
    capabilities: TRAVEL_CAPABILITIES.map((capability) => ({
      ...capability,
      requiredSkills: capability.requiredSkills.map((skill) => ({
        id: skill,
        name: skill,
        version: 'local',
        status: 'ready',
        health: 'healthy',
        requestedId: skill,
        viaAlias: false,
      })),
      missingSkills: [],
      legacySkillAliases: [],
      readiness: {
        status: 'ready',
        score: 92,
        summary: '本地北京 POI、UGC 特征和路线规划接口可用；实时排队与真实导航为明确边界。',
      },
    })),
    dataProviders: providers,
  };
}
