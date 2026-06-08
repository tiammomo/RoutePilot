import { randomUUID } from 'crypto';
import { prisma } from '@/lib/db/client';
import type { TravelQueryIntent } from '@/lib/travel/semantic-intent';

export type TravelSqlTemplateName =
  | 'candidate_culture_pois'
  | 'candidate_food_pois'
  | 'low_queue_pois'
  | 'family_friendly_pois'
  | 'indoor_pois'
  | 'poi_evidence'
  | 'area_summary';

export interface TravelQueryPlanStep {
  template: TravelSqlTemplateName;
  params: {
    area?: string | null;
    limit?: number;
    poiIds?: string[];
    maxBudget?: number | null;
  };
}

export interface TravelQueryPlan {
  raw_text: string;
  intent: TravelQueryIntent;
  steps: TravelQueryPlanStep[];
}

export interface TravelSqlTemplateResult {
  template: TravelSqlTemplateName;
  params: TravelQueryPlanStep['params'];
  elapsed_ms: number;
  result_count: number;
  cache_hit: boolean;
  cache_layer: 'sql_result' | null;
  rows: Array<Record<string, unknown>>;
}

const MAX_LIMIT = 50;
const DEFAULT_LIMIT = 12;
const SQL_RESULT_CACHE_TTL_MS = Number(process.env.TRAVELPILOT_SQL_CACHE_TTL_MS || 2 * 60 * 1000);
const sqlResultCache = new Map<string, { expiresAt: number; rows: Array<Record<string, unknown>> }>();

function clampLimit(value?: number): number {
  if (!Number.isFinite(Number(value))) return DEFAULT_LIMIT;
  return Math.max(1, Math.min(MAX_LIMIT, Math.trunc(Number(value))));
}

function normalizeArea(value?: string | null): string | null {
  const trimmed = String(value || '').trim();
  return trimmed.length > 0 ? trimmed : null;
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function sqlCacheKey(step: TravelQueryPlanStep): string {
  return `${step.template}:${stableJson({
    area: normalizeArea(step.params.area),
    limit: clampLimit(step.params.limit),
    maxBudget: step.params.maxBudget ?? null,
    poiIds: Array.isArray(step.params.poiIds) ? [...step.params.poiIds].sort() : [],
  })}`;
}

function getCachedSqlResult(key: string): Array<Record<string, unknown>> | null {
  const cached = sqlResultCache.get(key);
  if (!cached) return null;
  if (cached.expiresAt < Date.now()) {
    sqlResultCache.delete(key);
    return null;
  }
  return cached.rows;
}

function setCachedSqlResult(key: string, rows: Array<Record<string, unknown>>) {
  sqlResultCache.set(key, { expiresAt: Date.now() + SQL_RESULT_CACHE_TTL_MS, rows });
}

function makePlanStep(template: TravelSqlTemplateName, intent: TravelQueryIntent, extra: TravelQueryPlanStep['params'] = {}): TravelQueryPlanStep {
  return {
    template,
    params: {
      area: intent.area,
      maxBudget: intent.budget_cny,
      limit: DEFAULT_LIMIT,
      ...extra,
    },
  };
}

export function buildTravelQueryPlan(intent: TravelQueryIntent): TravelQueryPlan {
  const steps: TravelQueryPlanStep[] = [];
  steps.push(makePlanStep(intent.route_mode === 'culture' ? 'candidate_culture_pois' : 'candidate_culture_pois', intent));
  if (intent.needs_meal || intent.route_mode === 'mixed') steps.push(makePlanStep('candidate_food_pois', intent));
  if (intent.avoid_queue) steps.push(makePlanStep('low_queue_pois', intent, { limit: 10 }));
  if (intent.persona === 'family' || intent.persona === 'senior') steps.push(makePlanStep('family_friendly_pois', intent, { limit: 10 }));
  if (intent.indoor_preferred) steps.push(makePlanStep('indoor_pois', intent, { limit: 10 }));
  steps.push(makePlanStep('area_summary', intent, { limit: 5 }));
  return { raw_text: intent.raw_text, intent, steps };
}

async function logQuery(params: {
  rawText: string;
  intent: TravelQueryIntent;
  queryPlan: TravelQueryPlan;
  templateName: TravelSqlTemplateName;
  elapsedMs: number;
  resultCount: number;
  status?: string;
  errorMessage?: string | null;
}) {
  await prisma.$executeRaw`
    INSERT INTO travel_query_logs (
      id, raw_text, intent, query_plan, template_name, elapsed_ms,
      result_count, llm_used, status, error_message
    )
    VALUES (
      ${randomUUID()}, ${params.rawText}, CAST(${JSON.stringify(params.intent)} AS jsonb),
      CAST(${JSON.stringify(params.queryPlan)} AS jsonb), ${params.templateName},
      ${params.elapsedMs}, ${params.resultCount}, ${params.intent.llm_used},
      ${params.status || 'ok'}, ${params.errorMessage || null}
    )
  `;
}

async function runTemplate(template: TravelSqlTemplateName, params: TravelQueryPlanStep['params']): Promise<Array<Record<string, unknown>>> {
  const area = normalizeArea(params.area);
  const limit = clampLimit(params.limit);
  const maxBudget = params.maxBudget ?? null;

  switch (template) {
    case 'candidate_culture_pois':
      return prisma.$queryRaw`
        SELECT p.*, COALESCE(jsonb_object_agg(f.feature_key, f.feature_value) FILTER (WHERE f.feature_key IS NOT NULL), '{}'::jsonb) AS features
        FROM travel_pois p
        LEFT JOIN travel_poi_features f ON f.poi_id = p.poi_id
        WHERE (${area}::text IS NULL OR p.area = ${area} OR p.district = ${area})
          AND p.poi_type <> 'food'
          AND (${maxBudget}::double precision IS NULL OR p.avg_cost IS NULL OR p.avg_cost <= ${maxBudget})
        GROUP BY p.poi_id
        ORDER BY COALESCE(p.rating, 0) DESC, COALESCE(p.review_count, 0) DESC
        LIMIT ${limit}
      `;
    case 'candidate_food_pois':
      return prisma.$queryRaw`
        SELECT p.*, COALESCE(jsonb_object_agg(f.feature_key, f.feature_value) FILTER (WHERE f.feature_key IS NOT NULL), '{}'::jsonb) AS features
        FROM travel_pois p
        LEFT JOIN travel_poi_features f ON f.poi_id = p.poi_id
        WHERE (${area}::text IS NULL OR p.area = ${area} OR p.district = ${area})
          AND (p.poi_type = 'food' OR p.poi_kind = 'restaurant' OR p.is_meal_stop = TRUE)
          AND (${maxBudget}::double precision IS NULL OR p.avg_cost IS NULL OR p.avg_cost <= ${maxBudget})
        GROUP BY p.poi_id
        ORDER BY p.is_lunch_suitable DESC NULLS LAST, COALESCE(p.rating, 0) DESC, COALESCE(p.review_count, 0) DESC
        LIMIT ${limit}
      `;
    case 'low_queue_pois':
      return prisma.$queryRaw`
        SELECT p.*, f.feature_value AS queue_risk
        FROM travel_pois p
        JOIN travel_poi_features f ON f.poi_id = p.poi_id AND f.feature_key = 'queue_risk'
        WHERE (${area}::text IS NULL OR p.area = ${area} OR p.district = ${area})
          AND f.feature_value = 'low'
        ORDER BY COALESCE(p.rating, 0) DESC, COALESCE(p.review_count, 0) DESC
        LIMIT ${limit}
      `;
    case 'family_friendly_pois':
      return prisma.$queryRaw`
        SELECT p.*, f.feature_value AS family_friendliness
        FROM travel_pois p
        JOIN travel_poi_features f ON f.poi_id = p.poi_id AND f.feature_key = 'family_friendliness'
        WHERE (${area}::text IS NULL OR p.area = ${area} OR p.district = ${area})
          AND f.feature_value IN ('high', 'medium')
        ORDER BY CASE f.feature_value WHEN 'high' THEN 0 ELSE 1 END, COALESCE(p.rating, 0) DESC
        LIMIT ${limit}
      `;
    case 'indoor_pois':
      return prisma.$queryRaw`
        SELECT p.*, COALESCE(jsonb_object_agg(f.feature_key, f.feature_value) FILTER (WHERE f.feature_key IS NOT NULL), '{}'::jsonb) AS features
        FROM travel_pois p
        LEFT JOIN travel_poi_features f ON f.poi_id = p.poi_id
        WHERE (${area}::text IS NULL OR p.area = ${area} OR p.district = ${area})
          AND (
            p.poi_subtype IN ('museum', 'gallery', 'theater')
            OR p.category IN ('museum', 'art_gallery', 'theater')
            OR p.name ~ '博物馆|美术馆|艺术中心|展览馆|剧场'
          )
        GROUP BY p.poi_id
        ORDER BY COALESCE(p.rating, 0) DESC, COALESCE(p.review_count, 0) DESC
        LIMIT ${limit}
      `;
    case 'poi_evidence': {
      const poiIds = Array.isArray(params.poiIds) ? params.poiIds.slice(0, MAX_LIMIT).map(String) : [];
      return prisma.$queryRaw`
        SELECT
          p.poi_id,
          p.name,
          COALESCE(jsonb_agg(DISTINCT jsonb_build_object('feature_key', f.feature_key, 'feature_value', f.feature_value, 'confidence', f.confidence)) FILTER (WHERE f.feature_key IS NOT NULL), '[]'::jsonb) AS features,
          COALESCE(jsonb_agg(DISTINCT jsonb_build_object('review_id', r.review_id, 'review_text', r.review_text, 'rating', r.rating)) FILTER (WHERE r.review_id IS NOT NULL), '[]'::jsonb) AS reviews
        FROM travel_pois p
        LEFT JOIN travel_poi_features f ON f.poi_id = p.poi_id
        LEFT JOIN travel_reviews r ON r.poi_id = p.poi_id
        WHERE p.poi_id = ANY(${poiIds})
        GROUP BY p.poi_id, p.name
        LIMIT ${limit}
      `;
    }
    case 'area_summary':
      return prisma.$queryRaw`
        SELECT *
        FROM travel_areas
        WHERE (${area}::text IS NULL OR area_name = ${area} OR district = ${area})
        ORDER BY poi_count DESC
        LIMIT ${limit}
      `;
    default: {
      const neverTemplate: never = template;
      throw new Error(`Unsupported travel SQL template: ${neverTemplate}`);
    }
  }
}

export async function executeTravelQueryPlan(plan: TravelQueryPlan): Promise<TravelSqlTemplateResult[]> {
  const results: TravelSqlTemplateResult[] = [];
  for (const step of plan.steps) {
    const started = performance.now();
    const cacheKey = sqlCacheKey(step);
    try {
      const cachedRows = getCachedSqlResult(cacheKey);
      const rows = cachedRows ?? await runTemplate(step.template, step.params);
      if (!cachedRows) setCachedSqlResult(cacheKey, rows);
      const elapsedMs = Number((performance.now() - started).toFixed(2));
      if (!cachedRows) {
        await logQuery({
          rawText: plan.raw_text,
          intent: plan.intent,
          queryPlan: plan,
          templateName: step.template,
          elapsedMs,
          resultCount: rows.length,
        });
      }
      results.push({
        template: step.template,
        params: { ...step.params, limit: clampLimit(step.params.limit) },
        elapsed_ms: elapsedMs,
        result_count: rows.length,
        cache_hit: Boolean(cachedRows),
        cache_layer: cachedRows ? 'sql_result' : null,
        rows,
      });
    } catch (error) {
      const elapsedMs = Number((performance.now() - started).toFixed(2));
      await logQuery({
        rawText: plan.raw_text,
        intent: plan.intent,
        queryPlan: plan,
        templateName: step.template,
        elapsedMs,
        resultCount: 0,
        status: 'error',
        errorMessage: error instanceof Error ? error.message : String(error),
      }).catch(() => undefined);
      throw error;
    }
  }
  return results;
}
