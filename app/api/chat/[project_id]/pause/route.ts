import { NextRequest, NextResponse } from 'next/server';
import { cancelAgentRuns } from '@/lib/services/agent-runtime';
import { markActiveUserRequestsAsCancelled, markUserRequestAsCancelled } from '@/lib/services/user-requests';
import { streamManager } from '@/lib/services/stream';
import { getProjectById } from '@/lib/services/project';
import { markQuantGenerationQueueCancelled } from '@/lib/quant/generation-queue';
import path from 'path';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const body = await request.json().catch(() => ({}));
    const requestId =
      typeof body.requestId === 'string' && body.requestId.trim()
        ? body.requestId.trim()
        : undefined;
    const reason =
      typeof body.reason === 'string' && body.reason.trim()
        ? body.reason.trim()
        : '用户暂停了当前任务';

    const result = cancelAgentRuns(project_id, requestId, reason);
    if (requestId) {
      await markUserRequestAsCancelled(requestId, reason);
      const project = await getProjectById(project_id);
      if (project) {
        const projectsDir = process.env.PROJECTS_DIR || './data/projects';
        const projectPath = project.repoPath
          ? path.isAbsolute(project.repoPath)
            ? project.repoPath
            : path.resolve(process.cwd(), project.repoPath)
          : path.resolve(process.cwd(), projectsDir, project_id);
        await markQuantGenerationQueueCancelled({
          projectPath,
          projectId: project_id,
          requestId,
          reason,
        }).catch((error) => {
          console.warn('[API] Failed to mark generation queue item cancelled:', error);
        });
      }
    } else {
      await markActiveUserRequestsAsCancelled(project_id, reason);
    }

    streamManager.publish(project_id, {
      type: 'status',
      data: {
        status: 'agent_paused',
        message: reason,
        ...(requestId ? { requestId } : {}),
        metadata: result,
      },
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error('[API] Failed to pause agent:', error);
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to pause agent',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
