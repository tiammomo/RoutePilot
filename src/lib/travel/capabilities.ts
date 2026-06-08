export type TravelCapabilityId =
  | 'culture_route'
  | 'mixed_food_route'
  | 'family_low_queue'
  | 'budget_route'
  | 'efficient_route'
  | 'replan_compare';

export type TravelCapabilityStatus = 'ready' | 'planned';
export type TravelCapabilityGroupId = 'route_planning' | 'personalization' | 'quality_validation';

export interface TravelCapabilityGroup {
  id: TravelCapabilityGroupId;
  name: string;
  description: string;
}

export interface TravelCapability {
  id: TravelCapabilityId;
  name: string;
  shortName: string;
  description: string;
  inputHint: string;
  tags: string[];
  status: TravelCapabilityStatus;
  groupId: TravelCapabilityGroupId;
  agentType: 'travel_planner' | 'travel_validator' | 'travel_dashboard';
  subAgentKey: TravelCapabilityId;
  executionCapabilityId: TravelCapabilityId;
  requiredSkills: string[];
  dataEndpoints: string[];
  expectedArtifacts: string[];
  validationRules: string[];
  promptGuidance: string[];
}

export interface TravelProjectSettings {
  capabilityId: TravelCapabilityId;
  agentType: TravelCapability['agentType'];
  subAgentKey: TravelCapabilityId;
  executionCapabilityId: TravelCapabilityId;
  status: TravelCapabilityStatus;
  requiredSkills: string[];
  dataEndpoints: string[];
  expectedArtifacts: string[];
  validationRules: string[];
}

export const DEFAULT_TRAVEL_CAPABILITY_ID: TravelCapabilityId = 'mixed_food_route';

export const TRAVEL_CAPABILITY_GROUPS: TravelCapabilityGroup[] = [
  {
    id: 'route_planning',
    name: '路线生成',
    description: '围绕北京 POI 自动串联文化、餐饮和娱乐点位，生成可执行路线。',
  },
  {
    id: 'personalization',
    name: '偏好个性化',
    description: '把预算、少走路、少排队、亲子友好和餐饮偏好转成排序权重。',
  },
  {
    id: 'quality_validation',
    name: '约束验证',
    description: '检查时间、预算、类别覆盖、营业时间、UGC 证据和生成耗时。',
  },
];

const BASE_EXPECTED_ARTIFACTS = [
  '.travelpilot/run_plan.json',
  '.travelpilot/events.jsonl',
  '.travelpilot/validation.json',
  'evidence/sources.json',
  'evidence/data_quality.json',
  'data_file/final/itinerary-data.json',
  'app/page.tsx',
];

function baseExpectedArtifacts() {
  return [...BASE_EXPECTED_ARTIFACTS];
}

export const TRAVEL_CAPABILITIES: TravelCapability[] = [
  {
    id: 'mixed_food_route',
    name: '餐饮 + 文化混排',
    shortName: '吃逛混排',
    description: '在北京区域内组合餐饮、文化或娱乐 POI，兼顾排队风险、预算和步行距离。',
    inputHint: '例如：前门附近玩 4 小时，中午吃饭，想吃好但不想排队，预算 200，少走路。',
    tags: ['餐饮', '文化', 'UGC', '少排队'],
    status: 'ready',
    groupId: 'route_planning',
    agentType: 'travel_planner',
    subAgentKey: 'mixed_food_route',
    executionCapabilityId: 'mixed_food_route',
    requiredSkills: ['travel-run-planner', 'travel-poi-retrieval', 'travel-ugc-evidence', 'travel-route-optimizer', 'travel-constraint-validator', 'travel-visualization-html'],
    dataEndpoints: ['POST /api/v1/travel/parse-and-plan', 'POST /api/v1/travel/plan', 'GET /api/v1/travel/evidence/{poi_id}'],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '混合路线至少包含 1 个餐饮 POI 和 2 个文化/娱乐 POI。',
      '必须展示预算、时长、步行/转移估算和 UGC 排队/性价比证据。',
      '距离和时间必须标注为本地估算，不包装成实时导航。',
    ],
    promptGuidance: ['优先解析区域、时长、预算、少排队和少走路偏好。', '餐饮点优先选择 queue_risk 低、value_for_money 高的 POI。'],
  },
  {
    id: 'culture_route',
    name: '北京文化路线',
    shortName: '文化游',
    description: '围绕博物馆、景点、剧场、美术馆等文化 POI 生成半日或一日路线。',
    inputHint: '例如：故宫附近安排 4 个文化点，预算 200 以内，少走路。',
    tags: ['文化', '博物馆', '景点', '半日游'],
    status: 'ready',
    groupId: 'route_planning',
    agentType: 'travel_planner',
    subAgentKey: 'culture_route',
    executionCapabilityId: 'culture_route',
    requiredSkills: ['travel-run-planner', 'travel-poi-retrieval', 'travel-route-optimizer', 'travel-constraint-validator', 'travel-visualization-html'],
    dataEndpoints: ['POST /api/v1/travel/parse-and-plan', 'POST /api/v1/travel/plan'],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: ['文化路线至少包含 3 个文化/娱乐 POI。', '必须检查营业时间覆盖并提示未知字段。'],
    promptGuidance: ['优先选择同一区域内高评分、低成本、停留时长适配的文化 POI。'],
  },
  {
    id: 'family_low_queue',
    name: '亲子低排队路线',
    shortName: '亲子低排',
    description: '提高亲子友好、环境质量和低排队 UGC 信号权重。',
    inputHint: '例如：带孩子在什刹海附近轻松玩，不想排队，安排吃饭。',
    tags: ['亲子', '少排队', '轻松'],
    status: 'ready',
    groupId: 'personalization',
    agentType: 'travel_planner',
    subAgentKey: 'family_low_queue',
    executionCapabilityId: 'mixed_food_route',
    requiredSkills: ['travel-run-planner', 'travel-ugc-evidence', 'travel-route-optimizer'],
    dataEndpoints: ['POST /api/v1/travel/parse-and-plan', 'POST /api/v1/travel/replan'],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: ['必须展示亲子、排队和环境相关 UGC 证据或说明缺失。'],
    promptGuidance: ['降低 queue_risk 高、walk_intensity 高的点位权重。'],
  },
  {
    id: 'budget_route',
    name: '预算优先路线',
    shortName: '预算优先',
    description: '在预算上限内优先保留高性价比、低成本 POI。',
    inputHint: '例如：预算 100 以内，前门附近吃逛路线，尽量不排队。',
    tags: ['预算', '性价比', '低成本'],
    status: 'ready',
    groupId: 'personalization',
    agentType: 'travel_planner',
    subAgentKey: 'budget_route',
    executionCapabilityId: 'mixed_food_route',
    requiredSkills: ['travel-run-planner', 'travel-ugc-evidence', 'travel-constraint-validator'],
    dataEndpoints: ['POST /api/v1/travel/plan', 'POST /api/v1/travel/replan'],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: ['必须给出总预算估算和超预算风险。'],
    promptGuidance: ['优先选择 avg_cost 低且 value_for_money 高的点位。'],
  },
  {
    id: 'efficient_route',
    name: '效率优先路线',
    shortName: '效率优先',
    description: '优先缩短转移距离和总时长，降低回头路。',
    inputHint: '例如：天坛附近 3 小时高效串联 3 个点。',
    tags: ['少走路', '效率', '短时长'],
    status: 'ready',
    groupId: 'route_planning',
    agentType: 'travel_planner',
    subAgentKey: 'efficient_route',
    executionCapabilityId: 'culture_route',
    requiredSkills: ['travel-run-planner', 'travel-route-optimizer', 'travel-constraint-validator'],
    dataEndpoints: ['POST /api/v1/travel/plan'],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: ['必须展示转移时间估算和总时长是否满足约束。'],
    promptGuidance: ['按区域内最近邻排序，优先减少步行和转移时间。'],
  },
  {
    id: 'replan_compare',
    name: '动态重规划',
    shortName: '重规划',
    description: '基于上一轮路线继续追加预算、步行、保留或排除 POI 约束。',
    inputHint: '例如：预算降到 100，保留第一个点，少走路一点。',
    tags: ['追问', '重规划', '方案对比'],
    status: 'ready',
    groupId: 'quality_validation',
    agentType: 'travel_validator',
    subAgentKey: 'replan_compare',
    executionCapabilityId: 'replan_compare',
    requiredSkills: ['travel-run-planner', 'travel-route-optimizer', 'travel-constraint-validator'],
    dataEndpoints: ['POST /api/v1/travel/replan'],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: ['必须保留锁定 POI，并输出 replan_metadata。'],
    promptGuidance: ['把用户追问转换为 request_snapshot 的增量约束。'],
  },
];

export function getTravelCapability(id?: string | null): TravelCapability {
  return TRAVEL_CAPABILITIES.find((item) => item.id === id) ?? TRAVEL_CAPABILITIES.find((item) => item.id === DEFAULT_TRAVEL_CAPABILITY_ID)!;
}

export function getExecutionTravelCapability(id?: string | null): TravelCapability {
  const capability = getTravelCapability(id);
  if (capability.executionCapabilityId === capability.id) return capability;
  return getTravelCapability(capability.executionCapabilityId);
}

export function buildTravelProjectSettings(id?: string | null): TravelProjectSettings {
  const capability = getTravelCapability(id);
  return {
    capabilityId: capability.id,
    agentType: capability.agentType,
    subAgentKey: capability.subAgentKey,
    executionCapabilityId: capability.executionCapabilityId,
    status: capability.status,
    requiredSkills: [...capability.requiredSkills],
    dataEndpoints: [...capability.dataEndpoints],
    expectedArtifacts: [...capability.expectedArtifacts],
    validationRules: [...capability.validationRules],
  };
}

export function serializeTravelCapabilities() {
  return TRAVEL_CAPABILITIES.map((capability) => ({
    ...capability,
    requiredSkills: [...capability.requiredSkills],
    dataEndpoints: [...capability.dataEndpoints],
    expectedArtifacts: [...capability.expectedArtifacts],
    validationRules: [...capability.validationRules],
    promptGuidance: [...capability.promptGuidance],
  }));
}
