import type { TravelCapabilityId } from '@/lib/travel/capabilities';

export interface TravelVisualizationTemplate {
  id: string;
  name: string;
  scenario: string;
  painPoints: string[];
  requiredComponents: string[];
  optionalComponents: string[];
  dataSignals: string[];
  finalDataContract: string[];
}

const DEFAULT_TEMPLATE_ID: TravelCapabilityId = 'mixed_food_route';

const TEMPLATE_BY_CAPABILITY: Record<TravelCapabilityId, TravelVisualizationTemplate> = {
  mixed_food_route: {
    id: 'mixed-food-itinerary',
    name: '餐饮文化混排路线模板',
    scenario: '把餐饮、文化和娱乐 POI 串联成可直接执行的北京本地路线。',
    painPoints: ['不能只输出 POI 列表，必须有时间轴、预算、转移和风险。', 'UGC 只能作为静态证据，不得包装成实时排队。'],
    requiredComponents: ['路线摘要', '三方案对比', '时间轴', 'POI 决策卡', '预算与步行估算', 'UGC 证据', '风险提示'],
    optionalComponents: ['地图草图', '备选 POI', '用户追问入口'],
    dataSignals: ['planning_response.proposals', 'pois[].evidence_summary', 'duration_summary', 'budget_summary'],
    finalDataContract: ['parsed_request', 'planning_response', 'evidence', 'risks'],
  },
  culture_route: {
    id: 'culture-itinerary',
    name: '北京文化路线模板',
    scenario: '围绕博物馆、景点、剧场、美术馆等文化点生成半日游或一日游路线。',
    painPoints: ['必须解释为什么这些点适合串联。', '营业时间未知时必须提示，不能静默忽略。'],
    requiredComponents: ['文化路线摘要', '时间轴', '文化类别覆盖', '营业时间检查', '预算估算', '路线理由'],
    optionalComponents: ['备选文化点', '节奏调整按钮'],
    dataSignals: ['ordered_poi_ids', 'opening_hours_check', 'category_coverage_summary'],
    finalDataContract: ['planning_response', 'proposals', 'pois'],
  },
  family_low_queue: {
    id: 'family-low-queue-itinerary',
    name: '亲子低排队路线模板',
    scenario: '面向亲子/轻松出行，降低排队和步行压力。',
    painPoints: ['必须展示亲子友好、排队、环境相关证据或缺失说明。'],
    requiredComponents: ['亲子友好摘要', '低排队说明', '轻松时间轴', 'UGC 证据', '风险提示'],
    optionalComponents: ['雨天友好提示', '老人友好提示'],
    dataSignals: ['family_friendliness', 'queue_risk', 'environment_quality'],
    finalDataContract: ['planning_response', 'evidence'],
  },
  budget_route: {
    id: 'budget-itinerary',
    name: '预算优先路线模板',
    scenario: '在预算上限内生成高性价比路线。',
    painPoints: ['必须展示总预算、单点价格和取舍理由。'],
    requiredComponents: ['预算摘要', '单点花费', '性价比证据', '超预算风险', '备选替换'],
    optionalComponents: ['预算滑块', '免费 POI 推荐'],
    dataSignals: ['budget_summary', 'value_for_money', 'avg_cost'],
    finalDataContract: ['planning_response', 'budget_summary'],
  },
  efficient_route: {
    id: 'efficient-itinerary',
    name: '效率优先路线模板',
    scenario: '以少转移、少走路和短时长为目标生成路线。',
    painPoints: ['必须展示距离和时间估算置信度。'],
    requiredComponents: ['效率摘要', '转移时间', '总时长', '少走路理由', '风险提示'],
    optionalComponents: ['紧凑/轻松节奏切换'],
    dataSignals: ['duration_summary', 'transfer_minutes', 'travel_time_confidence'],
    finalDataContract: ['planning_response', 'duration_summary'],
  },
  replan_compare: {
    id: 'replan-comparison',
    name: '动态重规划模板',
    scenario: '基于上一轮路线追加约束并比较变化。',
    painPoints: ['必须说明哪些约束被应用，哪些点被保留或替换。'],
    requiredComponents: ['重规划摘要', '变更说明', '新旧方案对比', '锁定 POI', '风险变化'],
    optionalComponents: ['回退上版', '继续追问'],
    dataSignals: ['replan_metadata', 'request_snapshot', 'proposals'],
    finalDataContract: ['planning_response', 'replan_metadata'],
  },
};

export function getTravelVisualizationTemplate(id?: string | null): TravelVisualizationTemplate {
  const capabilityId = (id ?? DEFAULT_TEMPLATE_ID) as TravelCapabilityId;
  return TEMPLATE_BY_CAPABILITY[capabilityId] ?? TEMPLATE_BY_CAPABILITY[DEFAULT_TEMPLATE_ID];
}

export function serializeTravelVisualizationTemplate(id?: string | null) {
  const template = getTravelVisualizationTemplate(id);
  return {
    templateId: template.id,
    name: template.name,
    scenario: template.scenario,
    painPoints: template.painPoints,
    requiredComponents: template.requiredComponents,
    optionalComponents: template.optionalComponents,
    dataSignals: template.dataSignals,
    finalDataContract: template.finalDataContract,
  };
}
