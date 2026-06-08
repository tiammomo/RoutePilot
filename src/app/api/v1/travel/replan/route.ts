import { NextRequest, NextResponse } from 'next/server';
import { replanTravelRoute } from '@/lib/travel/planner';

export async function POST(request: NextRequest) {
  const body = await request.json();
  if (!body?.previous_request) {
    return NextResponse.json({ error: 'previous_request is required' }, { status: 400 });
  }
  return NextResponse.json(await replanTravelRoute(body));
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
