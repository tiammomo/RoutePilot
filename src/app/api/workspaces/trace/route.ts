import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    success: true,
    data: {
      product: 'beijing-travel-agent',
      stages: ['received', 'parsing', 'retrieving_poi', 'planning', 'writing_artifacts', 'rendering', 'completed'],
      note: 'Travel progress is streamed as travel_progress events in the chat channel.',
    },
  });
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
