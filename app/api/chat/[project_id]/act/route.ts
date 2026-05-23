/**
 * AI Action API Route
 * POST /api/chat/[project_id]/act - Execute AI command
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getProjectById,
  updateProject,
  updateProjectActivity,
} from '@/lib/services/project';
import { createMessage } from '@/lib/services/message';
import { getDefaultModelForCli, normalizeModelId } from '@/lib/constants/cliModels';
import { streamManager } from '@/lib/services/stream';
import type { ChatActRequest } from '@/types/backend';
import { generateProjectId } from '@/lib/utils';
import { previewManager } from '@/lib/services/preview';
import path from 'path';
import fs from 'fs/promises';
import { randomUUID } from 'crypto';
import { serializeMessage } from '@/lib/serializers/chat';
import {
  upsertUserRequest,
  markUserRequestAsProcessing,
} from '@/lib/services/user-requests';
import { writeInitialRunPlan } from '@/lib/quant/workspace';
import { prefetchQuantDataForRunPlan } from '@/lib/quant/data-prefetch';
import {
  buildQuantValidationRepairInstruction,
  validateQuantProject,
} from '@/lib/quant/validation';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

type CliRuntime = {
  initializeNextJsProject: (
    projectId: string,
    projectPath: string,
    instruction: string,
    model?: string,
    requestId?: string
  ) => Promise<void>;
  applyChanges: (
    projectId: string,
    projectPath: string,
    instruction: string,
    model?: string,
    sessionId?: string,
    requestId?: string
  ) => Promise<void>;
};

async function loadCliRuntime(cliPreference: string): Promise<CliRuntime> {
  switch (cliPreference) {
    case 'codex':
      return import('@/lib/services/cli/codex');
    case 'cursor':
      return import('@/lib/services/cli/cursor');
    case 'qwen':
      return import('@/lib/services/cli/qwen');
    case 'glm':
      return import('@/lib/services/cli/glm');
    case 'claude':
    default:
      return import('@/lib/services/cli/claude');
  }
}

function coerceString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(/*turbopackIgnore: true*/ process.cwd(), PROJECTS_DIR);

function resolveAssetsPath(projectId: string): string {
  return path.join(PROJECTS_DIR_ABSOLUTE, projectId, 'assets');
}

function ensureAbsoluteAssetPath(projectId: string, inputPath: string): string {
  const normalized = path.normalize(inputPath);
  if (path.isAbsolute(normalized)) {
    return normalized;
  }
  const resolvedFromCwd = path.resolve(/*turbopackIgnore: true*/ process.cwd(), normalized);
  if (resolvedFromCwd.startsWith(PROJECTS_DIR_ABSOLUTE)) {
    return resolvedFromCwd;
  }
  const projectBase = path.join(PROJECTS_DIR_ABSOLUTE, projectId);
  return path.resolve(projectBase, normalized);
}

function resolveProjectRoot(projectId: string, repoPath?: string | null): string {
  if (repoPath) {
    return path.isAbsolute(repoPath) ? repoPath : path.resolve(/*turbopackIgnore: true*/ process.cwd(), repoPath);
  }
  return path.join(PROJECTS_DIR_ABSOLUTE, projectId);
}

function runValidationAfterExecution(params: {
  execution: Promise<void>;
  repairExecutor: (
    projectId: string,
    projectPath: string,
    instruction: string,
    model: string,
    sessionId?: string,
    requestId?: string
  ) => Promise<void>;
  projectId: string;
  projectPath: string;
  instruction: string;
  selectedModel: string;
  sessionId?: string;
  requestId: string;
  conversationId?: string | null;
  cliSource?: string | null;
}) {
  const validateAndRepair = async (executionError?: unknown) => {
    const firstReport = await validateQuantProject({
      projectId: params.projectId,
      projectPath: params.projectPath,
      requestId: params.requestId,
      conversationId: params.conversationId,
      cliSource: params.cliSource,
    });

    if (firstReport.passed) {
      if (executionError) {
        streamManager.publish(params.projectId, {
          type: 'status',
          data: {
            status: 'validation_passed_after_agent_error',
            message: 'Agent 执行异常结束，但产物自动验证已通过。',
            requestId: params.requestId,
          },
        });
      }
      return;
    }

    const repairRequestId = `${params.requestId}-validation-repair`;
    const repairInstruction = buildQuantValidationRepairInstruction(firstReport, {
      originalInstruction: params.instruction,
    });
    streamManager.publish(params.projectId, {
      type: 'status',
      data: {
        status: 'validation_repairing',
        message: executionError
          ? 'Agent 执行异常结束，正在基于自动验证失败项触发修复。'
          : '自动验证未通过，正在让 Agent 根据失败项修复产物。',
        requestId: params.requestId,
        metadata: {
          repairRequestId,
          failedChecks: firstReport.checks
            .filter((check) => check.status === 'failed')
            .map((check) => ({ id: check.id, summary: check.summary })),
        },
      },
    });

    try {
      await upsertUserRequest({
        id: repairRequestId,
        projectId: params.projectId,
        instruction: repairInstruction,
        cliPreference: params.cliSource,
      });
      await markUserRequestAsProcessing(repairRequestId);
    } catch (error) {
      console.error('[API] Failed to record validation repair request:', error);
    }

    try {
      await params.repairExecutor(
        params.projectId,
        params.projectPath,
        repairInstruction,
        params.selectedModel,
        params.sessionId,
        repairRequestId
      );
    } catch (error) {
      console.error('[API] Validation repair execution failed:', error);
      streamManager.publish(params.projectId, {
        type: 'status',
        data: {
          status: 'validation_repair_failed',
          message: '自动修复执行失败，正在保留最终验证报告用于排查。',
          requestId: repairRequestId,
        },
      });
    }

    await validateQuantProject({
      projectId: params.projectId,
      projectPath: params.projectPath,
      requestId: repairRequestId,
      conversationId: params.conversationId,
      cliSource: params.cliSource,
    });
  };

  void (async () => {
    let executionError: unknown;
    try {
      await params.execution;
    } catch (error) {
      executionError = error;
      console.error('[API] Agent execution or automatic validation failed:', error);
    }

    try {
      await validateAndRepair(executionError);
    } catch (validationError) {
      console.error('[API] Automatic validation after agent execution failed:', validationError);
    }
  })();
}

async function mirrorAssetToPublic(
  projectRoot: string,
  filename: string,
  sourcePath: string,
): Promise<{ publicPath: string | null; publicUrl: string | null }> {
  const resolvedSourcePath = path.isAbsolute(sourcePath) ? sourcePath : path.resolve(/*turbopackIgnore: true*/ process.cwd(), sourcePath);
  const hostUploadsDir = path.join(/*turbopackIgnore: true*/ process.cwd(), 'public', 'uploads');
  let hostPublicPath: string | null = null;

  try {
    await fs.mkdir(hostUploadsDir, { recursive: true });
    const destinationPath = path.join(hostUploadsDir, filename);
    try {
      await fs.access(destinationPath);
    } catch {
      await fs.copyFile(resolvedSourcePath, destinationPath);
    }
    hostPublicPath = destinationPath;
  } catch (error) {
    console.warn('[API] Failed to mirror asset into application public/uploads:', error);
  }

  try {
    const uploadsDir = path.join(projectRoot, 'public', 'uploads');
    await fs.mkdir(uploadsDir, { recursive: true });
    const destinationPath = path.join(uploadsDir, filename);
    try {
      await fs.access(destinationPath);
    } catch {
      await fs.copyFile(resolvedSourcePath, destinationPath);
    }
    return {
      publicPath: hostPublicPath ?? destinationPath,
      publicUrl: hostPublicPath ? `/uploads/${filename}` : null,
    };
  } catch (error) {
    console.warn('[API] Failed to mirror asset into project public/uploads:', error);
    if (hostPublicPath) {
      return { publicPath: hostPublicPath, publicUrl: `/uploads/${filename}` };
    }
    return { publicPath: null, publicUrl: null };
  }
}

function inferExtensionFromMime(mime?: string): string {
  if (!mime) return '.png';
  const normalized = mime.toLowerCase();
  if (normalized.includes('png')) return '.png';
  if (normalized.includes('jpeg') || normalized.includes('jpg')) return '.jpg';
  if (normalized.includes('gif')) return '.gif';
  if (normalized.includes('webp')) return '.webp';
  if (normalized.includes('svg')) return '.svg';
  return '.png';
}

async function materializeBase64Image(
  projectId: string,
  projectRoot: string,
  base64: string,
  nameHint?: string,
  mimeType?: string,
): Promise<{ absolutePath: string; filename: string; publicUrl: string | null }> {
  const buffer = Buffer.from(base64, 'base64');
  const extension = inferExtensionFromMime(mimeType);
  const safeName = nameHint && nameHint.trim() ? nameHint.trim() : `image-${randomUUID()}`;
  const filename = `${safeName.replace(/[^a-zA-Z0-9-_]/g, '-') || 'image'}-${randomUUID()}${extension}`;
  const assetsDir = resolveAssetsPath(projectId);
  await fs.mkdir(assetsDir, { recursive: true });
  const absolutePath = path.join(assetsDir, filename);
  await fs.writeFile(absolutePath, buffer);
  const mirror = await mirrorAssetToPublic(projectRoot, filename, absolutePath);
  return {
    absolutePath,
    filename,
    publicUrl: mirror.publicUrl,
  };
}

type RawImageAttachment = Record<string, unknown>;

async function normalizeImageAttachment(
  projectId: string,
  projectRoot: string,
  raw: RawImageAttachment,
  index: number,
): Promise<{ name: string; path: string; url: string; publicUrl?: string } | null> {
  const name = typeof raw.name === 'string' && raw.name.trim().length > 0 ? raw.name.trim() : `Image ${index + 1}`;
  const providedUrl = typeof raw.url === 'string' && raw.url.trim().length > 0 ? raw.url.trim() : undefined;
  const providedPublicUrl =
    typeof raw.public_url === 'string' && raw.public_url.trim().length > 0
      ? raw.public_url.trim()
      : typeof raw.publicUrl === 'string' && raw.publicUrl.trim().length > 0
      ? raw.publicUrl.trim()
      : undefined;

  const pathValue =
    typeof raw.path === 'string' && raw.path.trim().length > 0 ? ensureAbsoluteAssetPath(projectId, raw.path.trim()) : null;

  const base64DataCandidate =
    typeof raw.base64_data === 'string'
      ? raw.base64_data
      : typeof raw.base64Data === 'string'
      ? raw.base64Data
      : null;

  const mimeTypeCandidate =
    typeof raw.mime_type === 'string'
      ? raw.mime_type
      : typeof raw.mimeType === 'string'
      ? raw.mimeType
      : undefined;

  if (pathValue) {
    try {
      await fs.stat(pathValue);
      const filename = path.basename(pathValue);
      let effectivePublicUrl = providedPublicUrl;
      if (!effectivePublicUrl) {
        const mirror = await mirrorAssetToPublic(projectRoot, filename, pathValue);
        effectivePublicUrl = mirror.publicUrl ?? undefined;
      }
      return {
        name,
        path: pathValue,
        url: providedUrl ?? `/api/assets/${projectId}/${filename}`,
        publicUrl: effectivePublicUrl,
      };
    } catch {
      // fall through and try to materialize if base64 present
    }
  }

  if (base64DataCandidate) {
    try {
      const materialized = await materializeBase64Image(
        projectId,
        projectRoot,
        base64DataCandidate,
        name,
        mimeTypeCandidate,
      );
      return {
        name,
        path: materialized.absolutePath,
        url: providedUrl ?? `/api/assets/${projectId}/${materialized.filename}`,
        publicUrl: providedPublicUrl ?? materialized.publicUrl ?? undefined,
      };
    } catch (error) {
      console.error('[API] Failed to materialize base64 image:', error);
      return null;
    }
  }

  return null;
}

/**
 * POST /api/chat/[project_id]/act
 * Execute AI command
 */
export async function POST(request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const rawBody = await request.json().catch(() => ({}));
    const body = (rawBody && typeof rawBody === 'object' ? rawBody : {}) as ChatActRequest &
      Record<string, unknown>;

    const project = await getProjectById(project_id);
    if (!project) {
      return NextResponse.json(
        { success: false, error: 'Project not found' },
        { status: 404 },
      );
    }

    const legacyBody = body as Record<string, unknown>;
    const projectRoot = resolveProjectRoot(project_id, project.repoPath);
    const rawInstruction = typeof body.instruction === 'string' ? body.instruction : '';
    const instructionWithoutLegacyPaths = rawInstruction.replace(/\n*Image #\d+ path: [^\n]+/g, '').trim();

    const rawImages: RawImageAttachment[] = Array.isArray((body as Record<string, unknown>).images)
      ? ((body as Record<string, unknown>).images as RawImageAttachment[])
      : Array.isArray(legacyBody['images'])
      ? (legacyBody['images'] as RawImageAttachment[])
      : [];

    const processedImages: { name: string; path: string; url: string; publicUrl?: string }[] = [];
    for (let index = 0; index < rawImages.length; index += 1) {
      const normalized = await normalizeImageAttachment(project_id, projectRoot, rawImages[index], index);
      if (normalized) {
        processedImages.push(normalized);
      }
    }

    const imageLines = processedImages.map((image, idx) => `Image #${idx + 1} path: ${image.path}`);
    const finalInstruction = [instructionWithoutLegacyPaths, imageLines.join('\n')]
      .filter((segment) => segment && segment.trim().length > 0)
      .join('\n\n')
      .trim();

    if (!finalInstruction) {
      return NextResponse.json(
        { success: false, error: 'instruction or images are required' },
        { status: 400 },
      );
    }

    const cliPreferenceRaw =
      coerceString((body as Record<string, unknown>).cliPreference) ??
      coerceString(legacyBody['cli_preference']) ??
      project.preferredCli ??
      'claude';
    const cliPreference = cliPreferenceRaw.toLowerCase();

    const selectedModelRaw =
      coerceString(body.selectedModel) ??
      coerceString(legacyBody['selected_model']) ??
      project.selectedModel ??
      getDefaultModelForCli(cliPreference);
    const selectedModel = normalizeModelId(cliPreference, selectedModelRaw);

    const conversationId =
      coerceString(body.conversationId) ?? coerceString(legacyBody['conversation_id']);

    const requestId =
      coerceString(body.requestId) ??
      coerceString(legacyBody['request_id']) ??
      generateProjectId();

    const isInitialPrompt =
      body.isInitialPrompt === true ||
      legacyBody['is_initial_prompt'] === true ||
      legacyBody['is_initial_prompt'] === 'true';

    const metadata =
      processedImages.length > 0
        ? {
            attachments: processedImages.map((image) => ({
              name: image.name,
              url: image.url,
              publicUrl: image.publicUrl,
              path: image.path,
            })),
          }
        : undefined;

    console.log('📸 Creating message with attachments:', {
      projectId: project_id,
      hasAttachments: processedImages.length > 0,
      attachmentsCount: processedImages.length,
      metadataKeys: metadata ? Object.keys(metadata) : [],
      metadataString: JSON.stringify(metadata, null, 2)
    });

    const userMessage = await createMessage({
      projectId: project_id,
      role: 'user',
      messageType: 'chat',
      content: finalInstruction,
      conversationId: conversationId ?? undefined,
      cliSource: cliPreference,
      metadata,
      requestId: requestId,
    });

    console.log('📸 Message created successfully:', {
      messageId: userMessage.id,
      hasMetadata: Boolean(metadata),
      metadataType: metadata ? typeof metadata : 'undefined',
      metadataKeys: metadata ? Object.keys(metadata) : [],
      metadataString: metadata ? JSON.stringify(metadata, null, 2) : undefined,
      metadataJsonLength: userMessage.metadataJson ? userMessage.metadataJson.length : 0,
    });

    if (requestId) {
      try {
        const storedInstruction =
          rawInstruction && rawInstruction.trim().length > 0
            ? rawInstruction.trim()
            : instructionWithoutLegacyPaths || finalInstruction;

        await upsertUserRequest({
          id: requestId,
          projectId: project_id,
          instruction: storedInstruction || finalInstruction,
          cliPreference,
        });
        await markUserRequestAsProcessing(requestId);
      } catch (error) {
        console.error('[API] Failed to record user request metadata:', error);
      }
    }

    streamManager.publish(project_id, {
      type: 'message',
      data: serializeMessage(userMessage, { requestId }),
    });

    await updateProjectActivity(project_id);

    const projectPath = project.repoPath || path.join(/*turbopackIgnore: true*/ process.cwd(), 'projects', project_id);

    const existingSelected = normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined);

    try {
      const runPlan = await writeInitialRunPlan({
        projectPath,
        instruction: finalInstruction,
        requestId,
        capabilityId:
          coerceString((body as Record<string, unknown>).quantCapabilityId) ??
          coerceString(legacyBody['quant_capability_id']) ??
          coerceString((body as Record<string, unknown>).capabilityId) ??
          coerceString(legacyBody['capability_id']),
      });
      const prefetch = await prefetchQuantDataForRunPlan({
        projectPath,
        plan: runPlan,
      });
      if (!prefetch.skipped) {
        streamManager.publish(project_id, {
          type: 'status',
          data: {
            status: 'quant_data_prefetched',
            message: prefetch.summary,
            requestId,
            metadata: {
              symbol: prefetch.symbol,
              finalDataPath: prefetch.finalDataPath,
              rawFiles: prefetch.rawFiles,
            },
          },
        });
      }
    } catch (error) {
      console.error('[API] Failed to prepare QuantPilot run plan or data prefetch:', error);
    }

    if (
      project.preferredCli !== cliPreference ||
      existingSelected !== selectedModel
    ) {
      try {
        await updateProject(project_id, {
          preferredCli: cliPreference,
          selectedModel,
        });
      } catch (error) {
        console.error('[API] Failed to persist project CLI/model settings:', error);
      }
    }

    try {
      const status = previewManager.getStatus(project_id);
      if (!status.url) {
        previewManager.start(project_id).catch((error) => {
          console.warn('[API] Failed to auto-start preview (will continue):', error);
        });
      }
    } catch (error) {
      console.warn('[API] Preview auto-start check failed (will continue):', error);
    }

    const cliRuntime = await loadCliRuntime(cliPreference);

    if (isInitialPrompt) {
      const execution = cliRuntime.initializeNextJsProject(
        project_id,
        projectPath,
        finalInstruction,
        selectedModel,
        requestId
      );
      runValidationAfterExecution({
        execution,
        repairExecutor: cliRuntime.applyChanges,
        projectId: project_id,
        projectPath,
        instruction: finalInstruction,
        selectedModel,
        requestId,
        conversationId,
        cliSource: cliPreference,
      });
    } else {
      const sessionId =
        cliPreference === 'claude'
          ? project.activeClaudeSessionId || undefined
          : cliPreference === 'cursor'
          ? project.activeCursorSessionId || undefined
          : undefined;

      const execution = cliRuntime.applyChanges(
        project_id,
        projectPath,
        finalInstruction,
        selectedModel,
        sessionId,
        requestId
      );
      runValidationAfterExecution({
        execution,
        repairExecutor: cliRuntime.applyChanges,
        projectId: project_id,
        projectPath,
        instruction: finalInstruction,
        selectedModel,
        sessionId,
        requestId,
        conversationId,
        cliSource: cliPreference,
      });
    }

    return NextResponse.json({
      success: true,
      message: 'AI execution started',
      requestId,
      userMessageId: userMessage.id,
      conversationId: conversationId ?? null,
    });
  } catch (error) {
    console.error('[API] Failed to execute AI:', error);
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to execute AI',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 },
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
