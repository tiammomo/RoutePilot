import { NextResponse } from 'next/server';
import { getTravelEvidence } from '@/lib/travel/planner';

interface RouteContext {
  params: Promise<{ poi_id: string }>;
}

export async function GET(_request: Request, { params }: RouteContext) {
  const { poi_id } = await params;
  const payload = await getTravelEvidence(decodeURIComponent(poi_id));
  if (!payload.poi) {
    return NextResponse.json({ error: 'POI not found', ...payload }, { status: 404 });
  }
  return NextResponse.json(payload);
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
