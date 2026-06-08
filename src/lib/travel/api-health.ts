import { travelHealth } from '@/lib/travel/planner';

export const TRAVEL_AGENT_PRODUCT = 'beijing-travel-agent';

export const TRAVEL_AGENT_CORE_CAPABILITIES = [
  'local_poi_ugc_data',
  'intent_parse',
  'route_plan',
  'dynamic_replan',
  'constraint_validation',
  'artifact_rendering',
] as const;

export async function getTravelHealthResponse() {
  return travelHealth();
}

export async function getTravelPlatformHealthResponse() {
  return {
    product: TRAVEL_AGENT_PRODUCT,
    travel: await travelHealth(),
    coreCapabilities: TRAVEL_AGENT_CORE_CAPABILITIES,
  };
}
