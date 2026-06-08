import { NextRequest, NextResponse } from 'next/server';
import { listTravelPois } from '@/lib/travel/planner';

export async function GET(request: NextRequest) {
  const search = request.nextUrl.searchParams;
  const routeMode = search.get('route_mode') === 'culture' ? 'culture' : 'mixed';
  const payload = await listTravelPois({
    route_mode: routeMode,
    area: search.get('area'),
    limit: Number(search.get('limit') || 100),
  });
  return NextResponse.json(payload);
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
