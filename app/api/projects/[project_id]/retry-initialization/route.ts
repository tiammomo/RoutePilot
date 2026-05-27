import { NextRequest, NextResponse } from 'next/server';
import { getDefaultModelForCli, normalizeModelId } from '@/lib/constants/cliModels';
import { serializeProject } from '@/lib/serializers/project';
import { streamManager } from '@/lib/services/stream';
import { getProjectById, updateProject } from '@/lib/services/project';
import { generateProjectId } from '@/lib/utils';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const body = await request.json().catch(() => ({}));
    const project = await getProjectById(project_id);

    if (!project) {
      return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 });
    }

    const instruction =
      typeof body?.instruction === 'string' && body.instruction.trim().length > 0
        ? body.instruction.trim()
        : project.initialPrompt?.trim();

    if (!instruction) {
      return NextResponse.json(
        { success: false, error: 'Project has no initial prompt to retry' },
        { status: 400 },
      );
    }

    const cliPreference = String(body?.cliPreference ?? body?.cli_preference ?? project.preferredCli ?? 'claude').toLowerCase();
    const selectedModel = normalizeModelId(
      cliPreference,
      typeof body?.selectedModel === 'string'
        ? body.selectedModel
        : typeof body?.selected_model === 'string'
        ? body.selected_model
        : project.selectedModel ?? getDefaultModelForCli(cliPreference),
    );
    const requestId =
      typeof body?.requestId === 'string' && body.requestId.trim().length > 0
        ? body.requestId.trim()
        : generateProjectId();

    const updatedProject = await updateProject(project_id, {
      status: 'initializing',
      preferredCli: cliPreference,
      selectedModel,
      previewUrl: null,
      previewPort: null,
    });

    streamManager.publish(project_id, {
      type: 'project_status',
      data: {
        status: 'initializing',
        message: '正在重新提交初始化任务...',
        requestId,
      },
    });

    const actUrl = new URL(`/api/chat/${project_id}/act`, request.url);
    const actResponse = await fetch(actUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instruction,
        displayInstruction: instruction,
        images: [],
        isInitialPrompt: true,
        cliPreference,
        selectedModel,
        requestId,
      }),
    });

    const actPayload = await actResponse.json().catch(() => null);
    if (!actResponse.ok || !actPayload?.success) {
      await updateProject(project_id, { status: 'failed' });
      streamManager.publish(project_id, {
        type: 'project_status',
        data: {
          status: 'failed',
          message: actPayload?.message ?? actPayload?.error ?? '重新初始化提交失败。',
          requestId,
        },
      });
      return NextResponse.json(
        {
          success: false,
          error: actPayload?.error ?? 'Retry initialization failed',
          message: actPayload?.message ?? 'Failed to restart initial generation',
        },
        { status: actResponse.status || 500 },
      );
    }

    return NextResponse.json({
      success: true,
      data: {
        project: serializeProject(updatedProject),
        requestId,
        act: actPayload,
      },
    });
  } catch (error) {
    console.error('[API] Failed to retry project initialization:', error);
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to retry project initialization',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 },
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
