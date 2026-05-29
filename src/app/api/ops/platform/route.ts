import { NextResponse } from 'next/server';
import { getOpsPlatformDashboard } from '@/lib/ops/ops-platform';

export async function GET() {
  try {
    return NextResponse.json({
      success: true,
      data: await getOpsPlatformDashboard(),
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
