import { NextResponse } from 'next/server';
import { getTravelPlatformHealthResponse } from '@/lib/travel/api-health';

export async function GET() {
  return NextResponse.json({
    success: true,
    data: await getTravelPlatformHealthResponse(),
  });
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
