import { NextRequest } from 'next/server';
import { createErrorResponse, createSuccessResponse, handleApiError } from '@/lib/utils/api-response';
import {
  addStrategyUniverseMember,
  buildStrategyPrompt,
  enqueueStrategyParameterScan,
  getStrategyDashboardData,
  getStrategyIngestionJobs,
  getStrategySymbolBars,
  getStrategySymbolDividends,
  getStrategyUniverseMembersPage,
  ingestStrategyUniverseHistoryBatch,
  runStrategyParameterScan,
} from '@/lib/quant/strategies';

export async function GET() {
  try {
    return createSuccessResponse(await getStrategyDashboardData());
  } catch (error) {
    return handleApiError(error, 'StrategyPlatform', 'Failed to fetch strategies');
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    if (body.action === 'run-scan') {
      return createSuccessResponse(
        await enqueueStrategyParameterScan({
          templateId: String(body.templateId ?? ''),
          scanId: String(body.scanId ?? ''),
          symbol: typeof body.symbol === 'string' ? body.symbol : undefined,
        }),
        201
      );
    }
    if (body.action === 'run-scan-now') {
      return createSuccessResponse(
        await runStrategyParameterScan({
          templateId: String(body.templateId ?? ''),
          scanId: String(body.scanId ?? ''),
          symbol: typeof body.symbol === 'string' ? body.symbol : undefined,
        }),
        201
      );
    }
    if (body.action === 'add-universe-member') {
      return createSuccessResponse(
        await addStrategyUniverseMember({
          universeId: typeof body.universeId === 'string' ? body.universeId : undefined,
          query: String(body.query ?? ''),
          syncHistory: body.syncHistory === true,
        }),
        201
      );
    }
    if (body.action === 'universe-members') {
      return createSuccessResponse(
        await getStrategyUniverseMembersPage({
          universeId: typeof body.universeId === 'string' ? body.universeId : undefined,
          page: typeof body.page === 'number' ? body.page : undefined,
          pageSize: typeof body.pageSize === 'number' ? body.pageSize : undefined,
          keyword: typeof body.keyword === 'string' ? body.keyword : undefined,
        })
      );
    }
    if (body.action === 'symbol-bars') {
      return createSuccessResponse(
        await getStrategySymbolBars({
          symbol: String(body.symbol ?? ''),
          timeframe: typeof body.timeframe === 'string' ? body.timeframe : undefined,
          adjustment: typeof body.adjustment === 'string' ? body.adjustment : undefined,
          provider: typeof body.provider === 'string' ? body.provider : undefined,
          limit: typeof body.limit === 'number' ? body.limit : undefined,
        })
      );
    }
    if (body.action === 'symbol-dividends') {
      return createSuccessResponse(
        await getStrategySymbolDividends({
          symbol: String(body.symbol ?? ''),
          limit: typeof body.limit === 'number' ? body.limit : undefined,
        })
      );
    }
    if (body.action === 'ingestion-jobs') {
      return createSuccessResponse(
        await getStrategyIngestionJobs({
          universeId: typeof body.universeId === 'string' ? body.universeId : undefined,
          limit: typeof body.limit === 'number' ? body.limit : undefined,
        })
      );
    }
    if (body.action === 'run-ingestion-batch') {
      return createSuccessResponse(
        await ingestStrategyUniverseHistoryBatch({
          universeId: typeof body.universeId === 'string' ? body.universeId : undefined,
          offset: typeof body.offset === 'number' ? body.offset : undefined,
          batchSize: typeof body.batchSize === 'number' ? body.batchSize : undefined,
          limit: typeof body.limit === 'number' ? body.limit : undefined,
          lookbackYears: typeof body.lookbackYears === 'number' ? body.lookbackYears : undefined,
          period: typeof body.period === 'string' ? body.period : undefined,
          adjustment: typeof body.adjustment === 'string' ? body.adjustment : undefined,
        }),
        201
      );
    }
    if (typeof body.action === 'string') {
      return createErrorResponse(`Unsupported strategy action: ${body.action}`, undefined, 400);
    }
    return createSuccessResponse(buildStrategyPrompt(String(body.templateId ?? ''), body.symbol), 201);
  } catch (error) {
    return handleApiError(error, 'StrategyPlatform', 'Failed to build strategy prompt');
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
