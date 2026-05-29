import { NextResponse } from 'next/server';
import { getInfrastructureHealth } from '@/lib/ops/infrastructure-health';

export async function GET() {
  const result = await getInfrastructureHealth();
  return NextResponse.json(
    {
      success: result.success,
      data: result.data,
      error: result.error,
    },
    { status: result.status }
  );
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
