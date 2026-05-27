import fs from 'fs/promises';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { getProjectById } from '@/lib/services/project';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(process.cwd(), PROJECTS_DIR);

function contentType(filePath: string) {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === '.png') return 'image/png';
  if (extension === '.jpg' || extension === '.jpeg') return 'image/jpeg';
  if (extension === '.webp') return 'image/webp';
  if (extension === '.gif') return 'image/gif';
  if (extension === '.json') return 'application/json; charset=utf-8';
  return 'text/plain; charset=utf-8';
}

function resolveProjectPath(projectId: string, repoPath?: string | null) {
  if (repoPath) {
    return path.isAbsolute(repoPath) ? repoPath : path.resolve(process.cwd(), repoPath);
  }
  return path.join(PROJECTS_DIR_ABSOLUTE, projectId);
}

function resolveSafeArtifactPath(projectPath: string, relativePath: string) {
  const root = path.resolve(projectPath);
  const normalizedRelativePath = relativePath.replace(/\\/g, '/').replace(/^\/+/, '');
  const resolved = path.resolve(root, normalizedRelativePath);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    throw new Error('Path traversal is not allowed');
  }
  return resolved;
}

export async function GET(request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const project = await getProjectById(project_id);
    if (!project) {
      return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 });
    }

    const artifactPath = new URL(request.url).searchParams.get('path');
    if (!artifactPath) {
      return NextResponse.json({ success: false, error: 'path query parameter is required' }, { status: 400 });
    }

    const projectPath = resolveProjectPath(project_id, project.repoPath);
    const absolutePath = resolveSafeArtifactPath(projectPath, artifactPath);
    const stat = await fs.stat(absolutePath).catch(() => null);
    if (!stat?.isFile()) {
      return NextResponse.json({ success: false, error: 'Artifact not found' }, { status: 404 });
    }

    const body = await fs.readFile(absolutePath);
    const response = new NextResponse(body as unknown as BodyInit);
    response.headers.set('Content-Type', contentType(absolutePath));
    response.headers.set('Cache-Control', 'no-store');
    return response;
  } catch (error) {
    console.error('[API] Failed to read project artifact:', error);
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to read project artifact',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 },
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
