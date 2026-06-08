import { NextRequest, NextResponse } from 'next/server';
import { planTravelRoute } from '@/lib/travel/planner';

export async function POST(request: NextRequest) {
  const body = await request.json();
  return NextResponse.json(await planTravelRoute(body || {}));
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
