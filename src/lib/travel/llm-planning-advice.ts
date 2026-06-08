import { z } from 'zod';
import type { TravelQueryIntent } from '@/lib/travel/semantic-intent';
import type { TravelWikiRetrievalResult } from '@/lib/travel/wiki-retrieval';
import type { TravelPlanningRequest } from '@/lib/travel/planner';

export interface TravelPlanningAdvice {
  source: 'minimax' | 'wiki_local';
  llm_used: boolean;
  model: string | null;
  elapsed_ms: number;
  fallback_reason: string | null;
  max_total_pois: number | null;
  pace: 'relaxed' | 'balanced' | 'compact' | null;
  walk_preference: 'low' | 'medium' | 'high' | null;
  route_mode: 'culture' | 'mixed' | null;
  preference_signals_patch: Record<string, boolean>;
  avoid_poi_keywords: string[];
  candidate_strategy_notes: string[];
  user_facing_reason: string;
}

const adviceSchema = z.object({
  max_total_pois: z.coerce.number().int().min(3).max(6).nullable().catch(null),
  pace: z.enum(['relaxed', 'balanced', 'compact']).nullable().catch(null),
  walk_preference: z.enum(['low', 'medium', 'high']).nullable().catch(null),
  route_mode: z.enum(['culture', 'mixed']).nullable().catch(null),
  preference_signals_patch: z.record(z.string(), z.coerce.boolean()).catch({}),
  avoid_poi_keywords: z.array(z.string().trim().min(1)).catch([]),
  candidate_strategy_notes: z.array(z.string().trim().min(1)).catch([]),
  user_facing_reason: z.string().trim().min(1).catch('已根据用户偏好调整候选路线策略。'),
});

function getMiniMaxConfig() {
  const baseUrl = process.env.ANTHROPIC_BASE_URL?.trim() || 'https://api.minimaxi.com/anthropic';
  const token = process.env.ANTHROPIC_AUTH_TOKEN?.trim();
  const model = process.env.ANTHROPIC_MODEL?.trim() || 'MiniMax-M2.7';
  const timeoutMs = Number(process.env.TRAVELPILOT_ADVICE_TIMEOUT_MS || 1200);
  if (!token) return null;
  return {
    baseUrl: baseUrl.replace(/\/+$/, ''),
    token,
    model,
    timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 1200,
  };
}

function extractTextFromAnthropicResponse(payload: unknown): string {
  const content = (payload as { content?: unknown })?.content;
  if (!Array.isArray(content)) return '';
  return content
    .map((item) => {
      if (item && typeof item === 'object' && (item as { type?: unknown }).type === 'text') {
        return String((item as { text?: unknown }).text || '');
      }
      return '';
    })
    .join('\n')
    .trim();
}

function extractJsonObject(text: string): unknown {
  const raw = String(text || '').trim();
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1]?.trim();
  const candidate = fenced || raw;
  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('Planning advice response did not contain JSON.');
  return JSON.parse(candidate.slice(start, end + 1));
}

function buildPrompt(intent: TravelQueryIntent, request: TravelPlanningRequest, wikiRetrieval?: TravelWikiRetrievalResult | null) {
  const wikiEvidence = {
    hits: (wikiRetrieval?.hits || []).slice(0, 5).map((hit) => ({
      title: hit.title,
      type: hit.type,
      score: hit.score,
      snippet: hit.snippet,
      entity_ids: hit.entity_ids,
    })),
    linked_entities: (wikiRetrieval?.linked_entities || []).slice(0, 12),
  };
  return [
    'You are a Beijing travel planning policy advisor.',
    'Return only one JSON object. Do not return Markdown. Do not write SQL. Do not generate a route. Do not invent POIs.',
    'Your job is to convert user preference and Wiki evidence into safe planner knobs for a deterministic route planner.',
    'Allowed JSON fields:',
    '{',
    '  "max_total_pois": 3|4|5|6|null,',
    '  "pace": "relaxed"|"balanced"|"compact"|null,',
    '  "walk_preference": "low"|"medium"|"high"|null,',
    '  "route_mode": "culture"|"mixed"|null,',
    '  "preference_signals_patch": { [signal: string]: boolean },',
    '  "avoid_poi_keywords": string[],',
    '  "candidate_strategy_notes": string[],',
    '  "user_facing_reason": string',
    '}',
    'Useful signals include: lunch, avoid_queue, indoor, senior, family, couple, coffee, snack, value_for_money.',
    'For short trips under 4 hours, prefer 3 POIs. For senior/low-walk requests, prefer relaxed pace and low walk.',
    `intent=${JSON.stringify(intent)}`,
    `current_request=${JSON.stringify(request)}`,
    `wiki_evidence=${JSON.stringify(wikiEvidence)}`,
  ].join('\n');
}

function normalizeAdvice(raw: unknown, meta: Pick<TravelPlanningAdvice, 'source' | 'llm_used' | 'model' | 'elapsed_ms' | 'fallback_reason'>): TravelPlanningAdvice {
  const parsed = adviceSchema.parse(raw);
  const allowedSignals = new Set(['lunch', 'avoid_queue', 'indoor', 'senior', 'family', 'couple', 'coffee', 'snack', 'value_for_money', 'formal_meal']);
  const preferencePatch = Object.fromEntries(
    Object.entries(parsed.preference_signals_patch).filter(([key]) => allowedSignals.has(key)),
  );
  return {
    ...meta,
    max_total_pois: parsed.max_total_pois,
    pace: parsed.pace,
    walk_preference: parsed.walk_preference,
    route_mode: parsed.route_mode,
    preference_signals_patch: preferencePatch,
    avoid_poi_keywords: parsed.avoid_poi_keywords.slice(0, 8),
    candidate_strategy_notes: parsed.candidate_strategy_notes.slice(0, 8),
    user_facing_reason: parsed.user_facing_reason,
  };
}

function buildWikiLocalAdvice(intent: TravelQueryIntent, reason: string, elapsedMs = 0): TravelPlanningAdvice {
  const shortTrip = intent.duration_minutes !== null && intent.duration_minutes <= 240;
  const veryShortTrip = intent.duration_minutes !== null && intent.duration_minutes <= 180;
  const lowWalk = intent.walk_preference === 'low' || intent.persona === 'senior' || intent.persona === 'family';
  const patch: Record<string, boolean> = {
    lunch: intent.needs_meal,
    avoid_queue: intent.avoid_queue,
    indoor: intent.indoor_preferred,
    value_for_money: intent.budget_cny !== null,
  };
  if (intent.persona) patch[intent.persona === 'senior' ? 'senior' : intent.persona === 'family' ? 'family' : intent.persona === 'couple' ? 'couple' : 'friends'] = true;
  if (intent.meal_type === 'coffee') patch.coffee = true;
  if (intent.meal_type === 'snack' || intent.meal_type === 'dessert') patch.snack = true;

  return {
    source: 'wiki_local',
    llm_used: false,
    model: null,
    elapsed_ms: elapsedMs,
    fallback_reason: reason,
    max_total_pois: veryShortTrip ? 3 : shortTrip ? 3 : null,
    pace: lowWalk ? 'relaxed' : shortTrip ? 'compact' : null,
    walk_preference: lowWalk ? 'low' : null,
    route_mode: intent.needs_meal ? 'mixed' : intent.route_mode,
    preference_signals_patch: patch,
    avoid_poi_keywords: lowWalk ? ['高步行强度', '大范围户外绕行'] : [],
    candidate_strategy_notes: [
      shortTrip ? '短时长请求优先减少 POI 数量，避免规则 planner 塞入过多点位。' : '保留用户原始时长弹性。',
      lowWalk ? '低步行/老人/亲子请求优先低步行、低压力、近距离候选。' : '按普通步行压力排序。',
      intent.avoid_queue ? '不想排队时降低高排队风险候选。' : '未明确排队约束。',
    ],
    user_facing_reason: '已在路线生成前根据意图和 Obsidian Wiki 证据调整 planner 参数，避免只靠固定规则表硬排。',
  };
}

export function applyTravelPlanningAdvice(request: TravelPlanningRequest, advice: TravelPlanningAdvice | null): TravelPlanningRequest {
  if (!advice) return request;
  return {
    ...request,
    max_total_pois: advice.max_total_pois ?? request.max_total_pois,
    pace: advice.pace ?? request.pace,
    walk_preference: advice.walk_preference ?? request.walk_preference,
    route_mode: advice.route_mode ?? request.route_mode,
    preference_signals: {
      ...(request.preference_signals || {}),
      ...advice.preference_signals_patch,
    },
  };
}

export async function getTravelPlanningAdvice(params: {
  intent: TravelQueryIntent;
  request: TravelPlanningRequest;
  wikiRetrieval?: TravelWikiRetrievalResult | null;
}): Promise<TravelPlanningAdvice> {
  const config = getMiniMaxConfig();
  if (!config) return buildWikiLocalAdvice(params.intent, 'missing_anthropic_auth_token');

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);
  const started = performance.now();
  try {
    const response = await fetch(`${config.baseUrl}/v1/messages`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': config.token,
        authorization: `Bearer ${config.token}`,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: config.model,
        max_tokens: 800,
        temperature: 0,
        messages: [{ role: 'user', content: buildPrompt(params.intent, params.request, params.wikiRetrieval) }],
      }),
      signal: controller.signal,
    });
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    const payload = await response.json().catch(async () => ({ error: await response.text().catch(() => '') }));
    if (!response.ok) return buildWikiLocalAdvice(params.intent, `http_${response.status}`, elapsedMs);
    const json = extractJsonObject(extractTextFromAnthropicResponse(payload));
    return normalizeAdvice(json, {
      source: 'minimax',
      llm_used: true,
      model: config.model,
      elapsed_ms: elapsedMs,
      fallback_reason: null,
    });
  } catch (error) {
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    return buildWikiLocalAdvice(
      params.intent,
      (error as { name?: string })?.name === 'AbortError'
        ? 'timeout'
        : error instanceof Error
          ? error.message
          : String(error),
      elapsedMs,
    );
  } finally {
    clearTimeout(timeout);
  }
}
