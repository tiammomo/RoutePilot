import { NextResponse } from 'next/server';
import { travelHealth } from '@/lib/travel/planner';

export async function GET() {
  const health = await travelHealth();
  return NextResponse.json({
    success: true,
    data: {
      product: 'beijing-travel-agent',
      status: health.status,
      dataLoaded: health.data_loaded,
      poiCount: health.poi_count,
      cache: health.cache,
      dataLoadElapsedMs: health.data_load_elapsed_ms,
    },
  });
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
