import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { getProjectById } from '@/lib/services/project';
import {
  readQuantValidationRepairPlan,
  readQuantValidationReport,
  validateQuantProject,
} from '@/lib/quant/validation';
import { updateQuantGenerationStep } from '@/lib/quant/generation-state';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(process.cwd(), PROJECTS_DIR);

function resolveProjectPath(projectId: string, repoPath?: string | null): string {
  if (repoPath) {
    return path.isAbsolute(repoPath) ? repoPath : path.resolve(process.cwd(), repoPath);
  }
  return path.join(PROJECTS_DIR_ABSOLUTE, projectId);
}

export async function GET(_request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const project = await getProjectById(project_id);
    if (!project) {
      return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 });
    }

    const projectPath = resolveProjectPath(project_id, project.repoPath);
    const report = await readQuantValidationReport(projectPath);
    const repairPlan = await readQuantValidationRepairPlan(projectPath);
    return NextResponse.json({
      success: true,
      data: report,
      repairPlan,
    });
  } catch (error) {
    console.error('[API] Failed to read quant validation report:', error);
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to read quant validation report',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const project = await getProjectById(project_id);
    if (!project) {
      return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 });
    }

    const body = await request.json().catch(() => ({}));
    const requestId = typeof body.requestId === 'string' ? body.requestId : undefined;
    const conversationId = typeof body.conversationId === 'string' ? body.conversationId : undefined;
    const projectPath = resolveProjectPath(project_id, project.repoPath);
    if (requestId) {
      await updateQuantGenerationStep({
        projectPath,
        projectId: project_id,
        requestId,
        stepId: 'validation',
        status: 'running',
        summary: '手动触发自动验证。',
      });
    }
    const report = await validateQuantProject({
      projectId: project_id,
      projectPath,
      requestId,
      conversationId,
      cliSource: 'validator',
    });
    const repairPlan = await readQuantValidationRepairPlan(projectPath);
    if (requestId) {
      await updateQuantGenerationStep({
        projectPath,
        projectId: project_id,
        requestId,
        stepId: 'validation',
        status: report.passed ? 'success' : 'failed',
        summary: report.passed
          ? '手动验证通过。'
          : `手动验证未通过：${report.checks.filter((check) => check.status === 'failed').length} 项失败。`,
        ...(report.passed
          ? {}
          : {
              errorMessage: '手动验证未通过。',
              metadata: {
                failedChecks: report.checks
                  .filter((check) => check.status === 'failed')
                  .map((check) => ({ id: check.id, summary: check.summary })),
              },
            }),
      });
    }

    return NextResponse.json({
      success: true,
      data: report,
      repairPlan,
    });
  } catch (error) {
    console.error('[API] Failed to run quant validation:', error);
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to run quant validation',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
