import { NextRequest, NextResponse } from 'next/server';
import { parseAndPlanTravel } from '@/lib/travel/planner';

export async function POST(request: NextRequest) {
  const body = await request.json();
  if (!body?.goal) {
    return NextResponse.json({ error: 'goal is required' }, { status: 400 });
  }
  return NextResponse.json(await parseAndPlanTravel(body));
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
