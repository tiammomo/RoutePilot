/**
 * POST /api/projects/[id]/preview/start
 * Launches the development server for a project and returns the preview URL.
 */

import { NextResponse } from 'next/server';
import { previewManager } from '@/lib/services/preview';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

export async function POST(
  _request: Request,
  { params }: RouteContext
) {
  const { project_id } = await params;
  try {
    const preview = await previewManager.start(project_id);

    return NextResponse.json({
      success: true,
      data: preview,
    });
  } catch (error) {
    console.warn(
      '[API] Preview start failed; retrying after cleanup:',
      error instanceof Error ? error.message : error
    );

    try {
      await previewManager.cleanup(project_id);
      const preview = await previewManager.start(project_id);

      return NextResponse.json({
        success: true,
        recovered: true,
        data: preview,
      });
    } catch (retryError) {
      console.error('[API] Failed to start preview after retry:', retryError);
      return NextResponse.json(
        {
          success: false,
          error:
            retryError instanceof Error
              ? retryError.message
              : 'Failed to start preview',
          firstError: error instanceof Error ? error.message : String(error),
        },
        { status: 500 }
      );
    }
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
