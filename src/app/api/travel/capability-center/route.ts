import { NextResponse } from 'next/server';
import { getTravelCapabilityCenterData } from '@/lib/travel/capability-center';

export async function GET() {
  try {
    return NextResponse.json({
      success: true,
      data: await getTravelCapabilityCenterData(),
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      },
      { status: 500 },
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
