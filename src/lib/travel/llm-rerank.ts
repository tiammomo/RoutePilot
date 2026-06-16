import { z } from 'zod';
import type { TravelQueryIntent } from '@/lib/travel/semantic-intent';
import type { TravelWikiRetrievalResult } from '@/lib/travel/wiki-retrieval';

export interface TravelProposalSummary {
  proposal_id: string;
  title: string;
  strategy: string;
  ordered_poi_names: string[];
  total_budget_estimate: number;
  total_route_duration_min: number;
  total_transfer_minutes: number;
  total_walking_distance_m: number;
  quality_summary?: Record<string, unknown> | null;
  transfer_source_summary?: Record<string, unknown> | null;
  risks?: string[];
  stop_summaries: Array<{
    poi_id: string;
    name: string;
    poi_type: string;
    meal_slot: string | null;
    recommendation_reason: string;
  }>;
}

export interface TravelRerankResult {
  ranked_proposal_ids: string[];
  primary_proposal_id: string;
  preference_match_scores: Record<string, number>;
  explanation_by_proposal: Record<string, string>;
  final_user_explanation: string;
  model: string | null;
  elapsed_ms: number;
  llm_used: boolean;
  rerank_source?: 'minimax' | 'wiki_local' | 'planner_fallback';
  fallback_reason: string | null;
}

const rerankSchema = z.object({
  ranked_proposal_ids: z.array(z.string().min(1)).min(1),
  primary_proposal_id: z.string().min(1),
  preference_match_scores: z.record(z.string(), z.coerce.number().min(0).max(1)).catch({}),
  explanation_by_proposal: z.record(z.string(), z.string().min(1)).catch({}),
  final_user_explanation: z.string().min(1),
});

function getMiniMaxConfig() {
  const baseUrl = process.env.ANTHROPIC_BASE_URL?.trim() || 'https://api.minimaxi.com/anthropic';
  const token = process.env.ANTHROPIC_AUTH_TOKEN?.trim();
  const model = process.env.ANTHROPIC_MODEL?.trim() || 'mimo-v2.5-pro';
  const timeoutMs = Number(process.env.TRAVELPILOT_RERANK_TIMEOUT_MS || 1500);
  if (!token) return null;
  return {
    baseUrl: baseUrl.replace(/\/+$/, ''),
    token,
    model,
    timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 1500,
  };
}

function extractTextFromAnthropicResponse(payload: unknown): string {
  const content = (payload as { content?: unknown })?.content;
  if (Array.isArray(content)) {
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

  // Some Anthropic-compatible gateways return OpenAI-style responses.
  const choiceText =
    (payload as { choices?: Array<{ message?: { content?: unknown }; text?: unknown }> })?.choices?.[0]?.message?.content
    ?? (payload as { choices?: Array<{ text?: unknown }> })?.choices?.[0]?.text
    ?? (payload as { output_text?: unknown })?.output_text;
  return typeof choiceText === 'string' ? choiceText.trim() : '';
}

function describeEmptyTextResponse(payload: unknown): string {
  const stopReason = String((payload as { stop_reason?: unknown })?.stop_reason || 'unknown');
  const content = (payload as { content?: unknown })?.content;
  const contentTypes = Array.isArray(content)
    ? content.map((item) => String((item as { type?: unknown })?.type || 'unknown')).join(',')
    : 'none';
  return `empty_text stop_reason=${stopReason} content_types=${contentTypes}`;
}

function extractJsonObject(text: string): unknown {
  const raw = String(text || '').trim();
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1]?.trim();
  const candidate = fenced || raw;
  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start < 0 || end <= start) {
    const preview = candidate.replace(/\s+/g, ' ').slice(0, 160) || '<empty>';
    throw new Error(`Rerank response did not contain JSON. preview=${preview}`);
  }
  return JSON.parse(candidate.slice(start, end + 1));
}

function compactProposal(proposal: TravelProposalSummary) {
  return {
    proposal_id: proposal.proposal_id,
    title: proposal.title,
    strategy: proposal.strategy,
    route: proposal.ordered_poi_names,
    budget_cny: proposal.total_budget_estimate,
    duration_min: proposal.total_route_duration_min,
    transfer_min: proposal.total_transfer_minutes,
    walking_m: proposal.total_walking_distance_m,
    risks: proposal.risks?.slice(0, 2) || [],
    stops: proposal.stop_summaries.slice(0, 4).map((stop) => ({
      name: stop.name,
      type: stop.poi_type,
      meal_slot: stop.meal_slot,
    })),
  };
}

function buildPrompt(intent: TravelQueryIntent, proposals: TravelProposalSummary[], wikiRetrieval?: TravelWikiRetrievalResult | null) {
  const wikiEvidence = wikiRetrieval
    ? {
        vault_path: wikiRetrieval.vault_path,
        citations: wikiRetrieval.citations.slice(0, 3).map((citation) => ({
          title: citation.title,
          path: citation.path,
        })),
        linked_entities: wikiRetrieval.linked_entities.slice(0, 8),
      }
    : null;

  return [
    'You are a preference reranker for a Beijing travel agent.',
    'Return ONLY one valid JSON object. Do not use Markdown. Do not add prose before or after JSON.',
    'Do not write SQL. Do not create a new route. Do not add, remove, rename, or modify POIs.',
    'You may only reorder the provided proposal_id values and explain the ranking.',
    'The JSON object must have exactly these keys:',
    '{"ranked_proposal_ids":["proposal_id"],"primary_proposal_id":"proposal_id","preference_match_scores":{"proposal_id":0.0},"explanation_by_proposal":{"proposal_id":"short Chinese explanation"},"final_user_explanation":"Chinese explanation for the user"}',
    'Rules:',
    '- ranked_proposal_ids must include every proposal_id exactly once.',
    '- primary_proposal_id must be the first id in ranked_proposal_ids.',
    '- Scores must be numbers from 0 to 1.',
    '- Explanations must be grounded in the provided proposals, user intent, and Wiki evidence.',
    '- If all proposals are similar, still return valid JSON and keep the safest order.',
    `User intent JSON: ${JSON.stringify(intent)}`,
    `Candidate proposals JSON: ${JSON.stringify(proposals.map(compactProposal))}`,
    `Wiki evidence JSON: ${JSON.stringify(wikiEvidence)}`,
  ].join('\n');
}

export function buildProposalSummaries(proposals: Array<Record<string, any>>): TravelProposalSummary[] {
  return proposals.slice(0, 3).map((proposal) => ({
    proposal_id: String(proposal.proposal_id),
    title: String(proposal.display_title || proposal.title || proposal.strategy || '路线方案'),
    strategy: String(proposal.strategy || 'balanced'),
    ordered_poi_names: Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.map(String) : [],
    total_budget_estimate: Number(proposal.total_budget_estimate || 0),
    total_route_duration_min: Number(proposal.total_route_duration_min || 0),
    total_transfer_minutes: Number(proposal.total_transfer_minutes || 0),
    total_walking_distance_m: Number(proposal.total_walking_distance_m || 0),
    quality_summary: proposal.quality_summary || null,
    transfer_source_summary: proposal.transfer_source_summary || null,
    risks: Array.isArray(proposal.risks) ? proposal.risks.map(String).slice(0, 3) : [],
    stop_summaries: Array.isArray(proposal.pois)
      ? proposal.pois.map((poi: Record<string, any>) => ({
          poi_id: String(poi.poi_id || ''),
          name: String(poi.name || ''),
          poi_type: String(poi.poi_type || ''),
          meal_slot: poi.meal_slot ? String(poi.meal_slot) : null,
          recommendation_reason: String(poi.recommendation_reason || ''),
        }))
      : [],
  }));
}

export function fallbackTravelRerank(proposals: TravelProposalSummary[], reason: string): TravelRerankResult {
  const ids = proposals.map((proposal) => proposal.proposal_id);
  const primaryId = ids[0] || '';
  return {
    ranked_proposal_ids: ids,
    primary_proposal_id: primaryId,
    preference_match_scores: Object.fromEntries(ids.map((id, index) => [id, Number((1 - index * 0.1).toFixed(2))])),
    explanation_by_proposal: Object.fromEntries(proposals.map((proposal) => [proposal.proposal_id, `${proposal.title} 保留规则 planner 的原始排序。`])),
    final_user_explanation: '当前主推方案保持规则 planner 的原始排序，原因是 MiniMax 偏好重排不可用或未通过校验。',
    model: null,
    elapsed_ms: 0,
    llm_used: false,
    rerank_source: 'planner_fallback',
    fallback_reason: reason,
  };
}

function scoreProposalWithWiki(proposal: TravelProposalSummary, intent: TravelQueryIntent, wikiRetrieval?: TravelWikiRetrievalResult | null): number {
  const routeText = `${proposal.title} ${proposal.strategy} ${proposal.ordered_poi_names.join(' ')}`.toLowerCase();
  const wikiText = JSON.stringify(wikiRetrieval?.hits || []).toLowerCase();
  let score = 100;
  if (intent.budget_cny !== null && proposal.total_budget_estimate <= intent.budget_cny) score += 16;
  if (intent.duration_minutes !== null && proposal.total_route_duration_min <= intent.duration_minutes) score += 20;
  if (intent.walk_preference === 'low') score -= Math.min(18, proposal.total_walking_distance_m / 300);
  if (intent.avoid_queue && /少排队|低排队|queue_risk|不排队|low queue/i.test(wikiText)) score += 10;
  if (intent.indoor_preferred && /室内优先|museum|gallery|美术馆|博物馆|艺术/i.test(`${wikiText} ${routeText}`)) score += 10;
  if (intent.persona === 'senior' && /老人友好|低步行|少走路|low walk/i.test(wikiText)) score += 12;
  if (intent.persona === 'family' && /亲子友好|family/i.test(wikiText)) score += 12;
  if (intent.persona === 'couple' && /情侣浪漫|咖啡|艺术|美术馆|romantic/i.test(`${wikiText} ${routeText}`)) score += 12;
  for (const hit of wikiRetrieval?.hits || []) {
    const title = String(hit.title || '').toLowerCase();
    if (proposal.ordered_poi_names.some((name) => title.includes(String(name).toLowerCase()) || routeText.includes(String(name).toLowerCase()))) {
      score += Math.min(12, Number(hit.score || 0) / 2);
    }
  }
  return Number(score.toFixed(3));
}

function wikiLocalTravelRerank(
  proposals: TravelProposalSummary[],
  intent: TravelQueryIntent,
  wikiRetrieval: TravelWikiRetrievalResult | null | undefined,
  reason: string,
  elapsedMs = 0,
): TravelRerankResult {
  const scored = proposals
    .map((proposal) => ({ proposal, score: scoreProposalWithWiki(proposal, intent, wikiRetrieval) }))
    .sort((left, right) => right.score - left.score);
  const ids = scored.map((item) => item.proposal.proposal_id);
  return {
    ranked_proposal_ids: ids,
    primary_proposal_id: ids[0] || '',
    preference_match_scores: Object.fromEntries(scored.map((item) => [item.proposal.proposal_id, Math.max(0, Math.min(1, Number((item.score / 140).toFixed(3))))])),
    explanation_by_proposal: Object.fromEntries(scored.map((item) => [
      item.proposal.proposal_id,
      `${item.proposal.title} 已根据 Obsidian Wiki evidence、预算、时长和步行约束进行本地重排。`,
    ])),
    final_user_explanation: 'MiniMax 重排未返回合规 JSON，系统已改用 Obsidian LLM-Wiki 证据和硬约束做本地确定性重排，路线仍由规则 planner 保证可执行。',
    model: null,
    elapsed_ms: elapsedMs,
    llm_used: false,
    rerank_source: 'wiki_local',
    fallback_reason: `llm_fallback:${reason}`,
  };
}

export function validateTravelRerank(raw: unknown, proposals: TravelProposalSummary[], model: string, elapsedMs: number): TravelRerankResult {
  const parsed = rerankSchema.parse(raw);
  const knownIds = new Set(proposals.map((proposal) => proposal.proposal_id));
  const rankedIds = parsed.ranked_proposal_ids.map(String);
  const uniqueIds = new Set(rankedIds);
  if (rankedIds.length !== proposals.length) throw new Error('Rerank did not return all proposal ids.');
  if (uniqueIds.size !== rankedIds.length) throw new Error('Rerank returned duplicate proposal ids.');
  if (!rankedIds.every((id) => knownIds.has(id))) throw new Error('Rerank returned unknown proposal id.');
  if (!knownIds.has(parsed.primary_proposal_id)) throw new Error('Rerank primary_proposal_id is not a known proposal.');
  if (parsed.primary_proposal_id !== rankedIds[0]) throw new Error('Rerank primary_proposal_id must equal ranked_proposal_ids[0].');
  return {
    ranked_proposal_ids: rankedIds,
    primary_proposal_id: parsed.primary_proposal_id,
    preference_match_scores: parsed.preference_match_scores,
    explanation_by_proposal: parsed.explanation_by_proposal,
    final_user_explanation: parsed.final_user_explanation,
    model,
    elapsed_ms: elapsedMs,
    llm_used: true,
    rerank_source: 'minimax',
    fallback_reason: null,
  };
}

export async function rerankTravelProposals(params: {
  intent: TravelQueryIntent;
  proposals: Array<Record<string, any>>;
  wikiRetrieval?: TravelWikiRetrievalResult | null;
}): Promise<TravelRerankResult> {
  const summaries = buildProposalSummaries(params.proposals);
  if (summaries.length === 0) return fallbackTravelRerank([], 'no_proposals');

  const mock = process.env.TRAVELPILOT_RERANK_MOCK_RESPONSE?.trim();
  if (mock) {
    try {
      return validateTravelRerank(JSON.parse(mock), summaries, process.env.ANTHROPIC_MODEL?.trim() || 'mimo-v2.5-pro', 0);
    } catch (error) {
      return wikiLocalTravelRerank(summaries, params.intent, params.wikiRetrieval, `mock_invalid:${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const config = getMiniMaxConfig();
  if (!config) return wikiLocalTravelRerank(summaries, params.intent, params.wikiRetrieval, 'missing_anthropic_auth_token');

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
        max_tokens: Number(process.env.TRAVELPILOT_RERANK_MAX_TOKENS || 2000),
        temperature: 0,
        messages: [{ role: 'user', content: buildPrompt(params.intent, summaries, params.wikiRetrieval) }],
      }),
      signal: controller.signal,
    });
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    const payload = await response.json().catch(async () => ({ error: await response.text().catch(() => '') }));
    if (!response.ok) return wikiLocalTravelRerank(summaries, params.intent, params.wikiRetrieval, `http_${response.status}`, elapsedMs);
    const text = extractTextFromAnthropicResponse(payload);
    if (!text) return wikiLocalTravelRerank(summaries, params.intent, params.wikiRetrieval, describeEmptyTextResponse(payload), elapsedMs);
    const json = extractJsonObject(text);
    return validateTravelRerank(json, summaries, config.model, elapsedMs);
  } catch (error) {
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    return wikiLocalTravelRerank(
      summaries,
      params.intent,
      params.wikiRetrieval,
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
