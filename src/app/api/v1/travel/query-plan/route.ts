import { NextRequest, NextResponse } from 'next/server';
import { parseTravelQueryIntent, TravelIntentError } from '@/lib/travel/semantic-intent';
import { buildTravelQueryPlan, executeTravelQueryPlan } from '@/lib/travel/sql-query';

export async function POST(request: NextRequest) {
  const started = performance.now();
  try {
    const body = await request.json().catch(() => ({}));
    const rawText = typeof body?.raw_text === 'string' ? body.raw_text : typeof body?.goal === 'string' ? body.goal : '';
    if (!rawText.trim()) {
      return NextResponse.json({ error: 'raw_text or goal is required' }, { status: 400 });
    }

    const intent = await parseTravelQueryIntent(rawText);
    const queryPlan = buildTravelQueryPlan(intent);
    const shouldQuery = !(body?.dry_run || intent.missing_fields.length > 0);
    const results = shouldQuery ? await executeTravelQueryPlan(queryPlan) : [];
    const elapsedMs = Number((performance.now() - started).toFixed(2));
    const sqlElapsedMs = Number(results.reduce((sum, item) => sum + Number(item.elapsed_ms || 0), 0).toFixed(2));
    const queryCacheHit = results.length > 0 && results.every((item) => item.cache_hit);

    return NextResponse.json({
      intent,
      query_plan: queryPlan,
      results,
      clarification:
        intent.missing_fields.length > 0
          ? {
              required: true,
              missing_fields: intent.missing_fields,
              message: `还缺少 ${intent.missing_fields.join('、')}，补充后可以继续查询候选路线。`,
            }
          : null,
      generation_metrics: {
        elapsed_ms: elapsedMs,
        within_10s: elapsedMs < 10000,
        sql_query_count: queryPlan.steps.length,
        llm_used: intent.llm_used,
        parser: intent.parser,
        model: intent.model,
        llm_elapsed_ms: intent.llm_elapsed_ms,
        sql_elapsed_ms: sqlElapsedMs,
        intent_cache_hit: intent.cache_hit,
        query_cache_hit: queryCacheHit,
        cache_hit: intent.cache_hit || queryCacheHit,
        cache_layer: intent.cache_layer || (queryCacheHit ? 'sql_result' : null),
        db_used: shouldQuery,
        llm_attempted: intent.llm_attempted,
        llm_error: intent.llm_error,
      },
    });
  } catch (error) {
    if (error instanceof TravelIntentError) {
      return NextResponse.json(
        {
          error: error.message,
          code: error.code,
          details: error.details ?? null,
        },
        { status: error.status },
      );
    }
    return NextResponse.json(
      { error: 'Failed to build travel query plan', message: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 },
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
