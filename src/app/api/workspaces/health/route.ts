import { NextResponse } from 'next/server';
import { getTravelHealthResponse } from '@/lib/travel/api-health';

export async function GET() {
  return NextResponse.json({
    success: true,
    data: await getTravelHealthResponse(),
  });
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
