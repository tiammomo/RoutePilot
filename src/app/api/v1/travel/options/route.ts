import { NextResponse } from 'next/server';
import { travelOptions } from '@/lib/travel/planner';

export async function GET() {
  return NextResponse.json(await travelOptions());
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
