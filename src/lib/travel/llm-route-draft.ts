import { z } from 'zod';
import type { TravelQueryIntent } from '@/lib/travel/semantic-intent';
import type { TravelWikiRetrievalResult } from '@/lib/travel/wiki-retrieval';
import type { Poi, TravelCandidateBuckets, TravelPlanningRequest } from '@/lib/travel/planner';

export interface TravelRouteDraft {
  draft_id: string;
  draft_source: 'minimax' | 'rule_fallback';
  selected_poi_ids: string[];
  ordered_poi_ids: string[];
  meal_stop_id: string | null;
  estimated_fit: number;
  preference_reasoning: string;
  known_risks: string[];
  used_wiki_citation_ids: string[];
  model: string | null;
  elapsed_ms: number;
  llm_used: boolean;
  llm_attempted: boolean;
  llm_error: string | null;
  fallback_reason: string | null;
}

export interface TravelRouteDraftValidation {
  status: 'valid' | 'repaired' | 'rejected';
  valid_ordered_poi_ids: string[];
  repair_actions: string[];
  rejection_reasons: string[];
  candidate_pool_size: number;
}

const routeDraftSchema = z.object({
  selected_poi_ids: z.array(z.string().min(1)).min(3).max(6),
  ordered_poi_ids: z.array(z.string().min(1)).min(3).max(6),
  meal_stop_id: z.string().min(1).nullable().catch(null),
  estimated_fit: z.coerce.number().min(0).max(1).catch(0.7),
  preference_reasoning: z.string().trim().min(1).catch('MiniMax selected POIs from the candidate pool.'),
  known_risks: z.array(z.string().trim().min(1)).catch([]),
  used_wiki_citation_ids: z.array(z.string().trim().min(1)).catch([]),
});

function getMiniMaxConfig() {
  const baseUrl = process.env.ANTHROPIC_BASE_URL?.trim() || 'https://api.minimaxi.com/anthropic';
  const token = process.env.ANTHROPIC_AUTH_TOKEN?.trim();
  const model = process.env.ANTHROPIC_MODEL?.trim() || 'mimo-v2.5-pro';
  const timeoutMs = Number(process.env.TRAVELPILOT_DRAFT_TIMEOUT_MS || 1800);
  if (!token) return null;
  return {
    baseUrl: baseUrl.replace(/\/+$/, ''),
    token,
    model,
    timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 1800,
  };
}

function isFoodCandidate(poi: Poi) {
  return poi.poi_type === 'food' || poi.poi_kind === 'restaurant' || poi.is_meal_stop || ['meal', 'snack', 'coffee', 'dessert'].includes(String(poi.meal_type || ''));
}

function uniqueCandidates(buckets: TravelCandidateBuckets) {
  const seen = new Set<string>();
  const all = [
    ...buckets.cultureCandidates.slice(0, 8),
    ...buckets.mealCandidates.slice(0, 5),
    ...buckets.snackCandidates.slice(0, 3),
    ...buckets.indoorCandidates.slice(0, 5),
  ];
  return all.filter((poi) => {
    if (!poi.poi_id || seen.has(poi.poi_id)) return false;
    seen.add(poi.poi_id);
    return true;
  }).slice(0, 12);
}

function compactPoi(poi: Poi) {
  return {
    id: poi.poi_id,
    name: poi.name,
    type: poi.poi_type || poi.category || null,
    meal: poi.meal_type || null,
    cost: Number(poi.avg_cost || 0),
    stay: Number(poi.suggested_duration_min || 90),
    tags: [...(Array.isArray(poi.planning_tags) ? poi.planning_tags : []), ...(Array.isArray(poi.evidence_tags) ? poi.evidence_tags : [])].slice(0, 4),
  };
}

function extractTextFromAnthropicResponse(payload: unknown): string {
  const content = (payload as { content?: unknown })?.content;
  if (Array.isArray(content)) {
    const textBlocks = content
      .map((item) => {
        if (item && typeof item === 'object' && (item as { type?: unknown }).type === 'text') {
          return String((item as { text?: unknown }).text || '');
        }
        return '';
      })
      .join('\n')
      .trim();
    if (textBlocks) return textBlocks;
    return content
      .map((item) => {
        if (item && typeof item === 'object' && (item as { type?: unknown }).type === 'thinking') {
          return String((item as { thinking?: unknown }).thinking || '');
        }
        return '';
      })
      .join('\n')
      .trim();
  }
  const choiceText =
    (payload as { choices?: Array<{ message?: { content?: unknown }; text?: unknown }> })?.choices?.[0]?.message?.content
    ?? (payload as { choices?: Array<{ text?: unknown }> })?.choices?.[0]?.text
    ?? (payload as { output_text?: unknown })?.output_text;
  return typeof choiceText === 'string' ? choiceText.trim() : '';
}

function findJsonObjectCandidates(text: string): string[] {
  const source = String(text || '');
  const candidates: string[] = [];
  for (let start = 0; start < source.length; start += 1) {
    if (source[start] !== '{') continue;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < source.length; index += 1) {
      const char = source[index];
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (char === '\\') {
          escaped = true;
        } else if (char === '"') {
          inString = false;
        }
        continue;
      }
      if (char === '"') {
        inString = true;
      } else if (char === '{') {
        depth += 1;
      } else if (char === '}') {
        depth -= 1;
        if (depth === 0) {
          candidates.push(source.slice(start, index + 1));
          break;
        }
      }
    }
  }
  return candidates;
}

function extractJsonObject(text: string): unknown {
  const raw = String(text || '').trim();
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1]?.trim();
  let candidate = fenced || raw;
  if (!candidate.startsWith('{') && /^"\w+"\s*:/.test(candidate)) {
    candidate = `{${candidate}`;
  }
  const jsonCandidates = findJsonObjectCandidates(candidate);
  for (const jsonCandidate of jsonCandidates) {
    try {
      const parsed = JSON.parse(jsonCandidate);
      if (routeDraftSchema.safeParse(parsed).success) return parsed;
    } catch {
      // Continue scanning other JSON fragments from MiniMax thinking/text blocks.
    }
  }
  throw new Error(`RouteDraft response did not contain valid schema JSON. preview=${candidate.replace(/\s+/g, ' ').slice(0, 160) || '<empty>'}`);
}

function buildPrompt(params: {
  intent: TravelQueryIntent;
  request: TravelPlanningRequest;
  candidates: Poi[];
  wikiRetrieval?: TravelWikiRetrievalResult | null;
}) {
  const wiki = {
    hits: (params.wikiRetrieval?.hits || []).slice(0, 3).map((hit) => ({
      id: hit.path || hit.title,
      title: hit.title,
      type: hit.type,
      snippet: String(hit.snippet || '').slice(0, 90),
    })),
  };
  const minimalIntent = {
    area: params.intent.area,
    duration_minutes: params.intent.duration_minutes,
    budget_cny: params.intent.budget_cny,
    route_mode: params.intent.route_mode,
    needs_meal: params.intent.needs_meal,
    meal_type: params.intent.meal_type,
    avoid_queue: params.intent.avoid_queue,
    walk_preference: params.intent.walk_preference,
    persona: params.intent.persona,
    indoor_preferred: params.intent.indoor_preferred,
  };
  const minimalRequest = {
    area: params.request.area,
    route_mode: params.request.route_mode,
    max_budget: params.request.max_budget,
    max_total_pois: params.request.max_total_pois,
    max_duration_min: params.request.max_duration_min,
    pace: params.request.pace,
    walk_preference: params.request.walk_preference,
    persona_id: params.request.persona_id,
    preference_signals: params.request.preference_signals,
  };
  return [
    'Task: choose/order Beijing route POIs from candidate_pois only.',
    'Output one minified JSON object, no markdown, no explanation outside JSON, no SQL.',
    'Schema: {"selected_poi_ids":["id"],"ordered_poi_ids":["id"],"meal_stop_id":"id|null","estimated_fit":0.8,"preference_reasoning":"中文短句","known_risks":[],"used_wiki_citation_ids":[]}',
    'Rules: 3 POIs if <=240min; include food if needs_meal=true; senior/family/low walk prefer short low-stress; indoor prefer museum/gallery; avoid_queue prefer low queue tags.',
    `intent=${JSON.stringify(minimalIntent)}`,
    `request=${JSON.stringify(minimalRequest)}`,
    `wiki=${JSON.stringify(wiki)}`,
    `candidate_pois=${JSON.stringify(params.candidates.map(compactPoi))}`,
  ].join('\n');
}

function fallbackDraft(params: {
  intent: TravelQueryIntent;
  request: TravelPlanningRequest;
  candidates: Poi[];
  reason: string;
  elapsedMs?: number;
  llmAttempted?: boolean;
}): TravelRouteDraft {
  const targetCount = Math.max(3, Math.min(Number(params.request.max_total_pois || 3), 4));
  const food = params.candidates.find(isFoodCandidate);
  const culture = params.candidates.filter((poi) => !isFoodCandidate(poi));
  const ordered = params.intent.needs_meal && food
    ? [culture[0], food, ...culture.slice(1)].filter(Boolean).slice(0, targetCount)
    : culture.slice(0, targetCount);
  const ids = ordered.map((poi) => poi.poi_id);
  return {
    draft_id: `draft-${Math.random().toString(16).slice(2, 10)}`,
    draft_source: 'rule_fallback',
    selected_poi_ids: ids,
    ordered_poi_ids: ids,
    meal_stop_id: food && ids.includes(food.poi_id) ? food.poi_id : null,
    estimated_fit: 0.62,
    preference_reasoning: 'MiniMax RouteDraft unavailable; selected top validated candidates from local recall.',
    known_risks: [`fallback:${params.reason}`],
    used_wiki_citation_ids: [],
    model: null,
    elapsed_ms: params.elapsedMs || 0,
    llm_used: false,
    llm_attempted: Boolean(params.llmAttempted),
    llm_error: params.llmAttempted ? params.reason : null,
    fallback_reason: params.reason,
  };
}

function normalizeDraft(raw: unknown, model: string, elapsedMs: number): TravelRouteDraft {
  const parsed = routeDraftSchema.parse(raw);
  return {
    draft_id: `draft-${Math.random().toString(16).slice(2, 10)}`,
    draft_source: 'minimax',
    selected_poi_ids: Array.from(new Set(parsed.selected_poi_ids)),
    ordered_poi_ids: parsed.ordered_poi_ids,
    meal_stop_id: parsed.meal_stop_id,
    estimated_fit: parsed.estimated_fit,
    preference_reasoning: parsed.preference_reasoning,
    known_risks: parsed.known_risks.slice(0, 5),
    used_wiki_citation_ids: parsed.used_wiki_citation_ids.slice(0, 8),
    model,
    elapsed_ms: elapsedMs,
    llm_used: true,
    llm_attempted: true,
    llm_error: null,
    fallback_reason: null,
  };
}

export function validateTravelRouteDraft(draft: TravelRouteDraft, candidates: Poi[], request: TravelPlanningRequest): TravelRouteDraftValidation {
  const candidateById = new Map(candidates.map((poi) => [poi.poi_id, poi]));
  const repairActions: string[] = [];
  const rejectionReasons: string[] = [];
  const deduped = Array.from(new Set(draft.ordered_poi_ids));
  if (deduped.length !== draft.ordered_poi_ids.length) repairActions.push('Removed duplicate POI ids from RouteDraft.');
  let validIds = deduped.filter((id) => candidateById.has(id));
  const dropped = deduped.filter((id) => !candidateById.has(id));
  if (dropped.length) repairActions.push(`Dropped POIs outside candidate pool: ${dropped.join(', ')}`);

  const targetCount = Math.max(3, Math.min(Number(request.max_total_pois || 3), 4));
  if (validIds.length < targetCount) {
    for (const poi of candidates) {
      if (validIds.length >= targetCount) break;
      if (!validIds.includes(poi.poi_id)) {
        validIds.push(poi.poi_id);
        repairActions.push(`Added recalled candidate ${poi.name} to satisfy minimum route size.`);
      }
    }
  }

  if (request.preference_signals?.lunch && !validIds.some((id) => isFoodCandidate(candidateById.get(id) as Poi))) {
    const food = candidates.find(isFoodCandidate);
    if (food) {
      validIds = [validIds[0], food.poi_id, ...validIds.slice(1).filter((id) => id !== food.poi_id)].filter(Boolean);
      repairActions.push(`Inserted meal candidate ${food.name}.`);
    } else {
      rejectionReasons.push('No meal candidate available for requested meal stop.');
    }
  }

  validIds = validIds.slice(0, targetCount);
  if (validIds.length < 3) rejectionReasons.push('RouteDraft has fewer than 3 valid POIs after repair.');
  return {
    status: rejectionReasons.length ? 'rejected' : repairActions.length ? 'repaired' : 'valid',
    valid_ordered_poi_ids: validIds,
    repair_actions: repairActions,
    rejection_reasons: rejectionReasons,
    candidate_pool_size: candidates.length,
  };
}

export async function generateTravelRouteDraft(params: {
  intent: TravelQueryIntent;
  request: TravelPlanningRequest;
  buckets: TravelCandidateBuckets;
  wikiRetrieval?: TravelWikiRetrievalResult | null;
  mockResponse?: string | null;
}): Promise<{ draft: TravelRouteDraft; validation: TravelRouteDraftValidation; candidates: Poi[] }> {
  const candidates = uniqueCandidates(params.buckets);
  const mock = params.mockResponse?.trim() || process.env.TRAVELPILOT_DRAFT_MOCK_RESPONSE?.trim();
  if (mock) {
    try {
      const draft = normalizeDraft(JSON.parse(mock), process.env.ANTHROPIC_MODEL?.trim() || 'mimo-v2.5-pro', 0);
      return { draft, validation: validateTravelRouteDraft(draft, candidates, params.request), candidates };
    } catch (error) {
      const draft = fallbackDraft({
        intent: params.intent,
        request: params.request,
        candidates,
        reason: `mock_invalid:${error instanceof Error ? error.message : String(error)}`,
        llmAttempted: false,
      });
      return { draft, validation: validateTravelRouteDraft(draft, candidates, params.request), candidates };
    }
  }
  const config = getMiniMaxConfig();
  if (!config || candidates.length < 3) {
    const draft = fallbackDraft({ intent: params.intent, request: params.request, candidates, reason: !config ? 'missing_anthropic_auth_token' : 'insufficient_candidates' });
    return { draft, validation: validateTravelRouteDraft(draft, candidates, params.request), candidates };
  }

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
        max_tokens: Number(process.env.TRAVELPILOT_DRAFT_MAX_TOKENS || 900),
        temperature: 0,
        messages: [
          { role: 'user', content: buildPrompt({ ...params, candidates }) },
          { role: 'assistant', content: '{' },
        ],
      }),
      signal: controller.signal,
    });
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    const payload = await response.json().catch(async () => ({ error: await response.text().catch(() => '') }));
    if (!response.ok) {
      const draft = fallbackDraft({ intent: params.intent, request: params.request, candidates, reason: `http_${response.status}`, elapsedMs, llmAttempted: true });
      return { draft, validation: validateTravelRouteDraft(draft, candidates, params.request), candidates };
    }
    const text = extractTextFromAnthropicResponse(payload);
    if (!text) throw new Error(`empty_text stop_reason=${String((payload as { stop_reason?: unknown })?.stop_reason || 'unknown')}`);
    const draft = normalizeDraft(extractJsonObject(text), config.model, elapsedMs);
    return { draft, validation: validateTravelRouteDraft(draft, candidates, params.request), candidates };
  } catch (error) {
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    const reason = (error as { name?: string })?.name === 'AbortError' ? 'timeout' : error instanceof Error ? error.message : String(error);
    const draft = fallbackDraft({ intent: params.intent, request: params.request, candidates, reason, elapsedMs, llmAttempted: true });
    return { draft, validation: validateTravelRouteDraft(draft, candidates, params.request), candidates };
  } finally {
    clearTimeout(timeout);
  }
}
