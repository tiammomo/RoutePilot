import { NextResponse } from 'next/server';
import { warmTravelData } from '@/lib/travel/planner';

export async function POST() {
  return NextResponse.json(await warmTravelData());
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
