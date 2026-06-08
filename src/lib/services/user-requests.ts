import { prisma } from '@/lib/db/client';
import { Prisma } from '@prisma/client';

export interface ActiveRequestSummary {
  hasActiveRequests: boolean;
  activeCount: number;
}

export type UserRequestStatus =
  | 'pending'
  | 'processing'
  | 'active'
  | 'running'
  | 'cancelled'
  | 'completed'
  | 'failed';

const ACTIVE_REQUEST_STALE_MS =
  Number.parseInt(process.env.QUANTPILOT_ACTIVE_REQUEST_STALE_MS ?? '', 10) || 30 * 60 * 1000;
const ACTIVE_REQUEST_ORPHAN_MS =
  Number.parseInt(process.env.QUANTPILOT_ACTIVE_REQUEST_ORPHAN_MS ?? '', 10) || 8 * 60 * 1000;

const ACTIVE_STATUSES: UserRequestStatus[] = ['pending', 'processing', 'active', 'running'];
const globalForActiveRequests = globalThis as unknown as {
  __quantpilot_active_request_runtime__?: Set<string>;
};
const activeRuntimeRequests =
  globalForActiveRequests.__quantpilot_active_request_runtime__ ??
  (globalForActiveRequests.__quantpilot_active_request_runtime__ = new Set<string>());

function activeRequestWhere(projectId: string): Prisma.UserRequestWhereInput {
  return {
    projectId,
    status: {
      in: ACTIVE_STATUSES,
    },
  };
}

function trackRuntimeRequest(id: string): void {
  activeRuntimeRequests.add(id);
}

function untrackRuntimeRequest(id: string): void {
  activeRuntimeRequests.delete(id);
}

async function expireStaleActiveRequests(projectId: string): Promise<void> {
  const now = Date.now();
  const hardStaleBefore = new Date(now - ACTIVE_REQUEST_STALE_MS);
  const orphanBefore = new Date(now - ACTIVE_REQUEST_ORPHAN_MS);

  const hardStaleRequests = await prisma.userRequest.findMany({
    where: {
      ...activeRequestWhere(projectId),
      createdAt: {
        lt: hardStaleBefore,
      },
    },
    select: {
      id: true,
    },
  });

  await prisma.userRequest.updateMany({
    where: {
      ...activeRequestWhere(projectId),
      createdAt: {
        lt: hardStaleBefore,
      },
    },
    data: {
      status: 'failed',
      completedAt: new Date(),
      errorMessage: '请求超过平台活动窗口未结束，已自动标记为失败。请重新发起任务。',
    },
  });

  hardStaleRequests.forEach((request) => untrackRuntimeRequest(request.id));

  const activeRequests = await prisma.userRequest.findMany({
    where: activeRequestWhere(projectId),
    select: {
      id: true,
      createdAt: true,
    },
  });

  if (activeRequests.length === 0) {
    return;
  }

  const orphanedRequestIds: string[] = [];
  await Promise.all(
    activeRequests.map(async (request) => {
      if (activeRuntimeRequests.has(request.id)) {
        return;
      }

      const latestMessage = await prisma.message.findFirst({
        where: {
          projectId,
          requestId: request.id,
        },
        select: {
          createdAt: true,
        },
        orderBy: {
          createdAt: 'desc',
        },
      });

      const lastActivityAt = latestMessage?.createdAt ?? request.createdAt;
      if (lastActivityAt < orphanBefore) {
        orphanedRequestIds.push(request.id);
      }
    })
  );

  if (orphanedRequestIds.length === 0) {
    return;
  }

  await prisma.userRequest.updateMany({
    where: {
      projectId,
      id: {
        in: orphanedRequestIds,
      },
      status: {
        in: ACTIVE_STATUSES,
      },
    },
    data: {
      status: 'failed',
      completedAt: new Date(),
      errorMessage: '请求执行中长时间没有新事件，已自动标记为失败。请重新发起任务。',
    },
  });

  orphanedRequestIds.forEach(untrackRuntimeRequest);
}

export async function getActiveRequests(projectId: string): Promise<ActiveRequestSummary> {
  await expireStaleActiveRequests(projectId);

  const count = await prisma.userRequest.count({
    where: activeRequestWhere(projectId),
  });

  return {
    hasActiveRequests: count > 0,
    activeCount: count,
  };
}

interface UpsertUserRequestOptions {
  id: string;
  projectId: string;
  instruction: string;
  cliPreference?: string | null;
}

async function handleNotFound(error: unknown, context: string): Promise<void> {
  if (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    error.code === 'P2025'
  ) {
    if (process.env.NODE_ENV !== 'production') {
      console.warn(`[UserRequests] ${context}: record not found`);
    }
    return;
  }

  throw error;
}

/**
 * Create or update a user request record.
 * Uses the client-provided requestId as the primary key.
 */
export async function upsertUserRequest({
  id,
  projectId,
  instruction,
  cliPreference,
}: UpsertUserRequestOptions) {
  return prisma.userRequest.upsert({
    where: { id },
    create: {
      id,
      projectId,
      instruction,
      status: 'pending',
      ...(cliPreference !== undefined ? { cliPreference } : {}),
    },
    update: {
      instruction,
      ...(cliPreference !== undefined ? { cliPreference } : {}),
    },
  });
}

async function updateStatus(
  id: string,
  status: UserRequestStatus,
  options: { errorMessage?: string | null; setCompletionTimestamp?: boolean } = {}
) {
  try {
    const data: Prisma.UserRequestUpdateInput = {
      status,
    };

    if (options.setCompletionTimestamp ?? (status === 'completed' || status === 'failed' || status === 'cancelled')) {
      data.completedAt = new Date();
    } else if (status === 'pending' || status === 'processing' || status === 'running' || status === 'active') {
      data.completedAt = null;
    }

    if ('errorMessage' in options) {
      data.errorMessage = options.errorMessage ?? null;
    } else if (status !== 'failed') {
      data.errorMessage = null;
    }

    await prisma.userRequest.updateMany({
      where: { id },
      data,
    });
  } catch (error) {
    await handleNotFound(error, `update status to ${status}`);
  }
}

export async function markUserRequestAsRunning(id: string): Promise<void> {
  await updateStatus(id, 'running');
  trackRuntimeRequest(id);
}

export async function markUserRequestAsProcessing(id: string): Promise<void> {
  await updateStatus(id, 'processing');
  trackRuntimeRequest(id);
}

export async function isUserRequestCancelled(id: string): Promise<boolean> {
  const request = await prisma.userRequest.findUnique({
    where: { id },
    select: { status: true },
  });
  return request?.status === 'cancelled';
}

export async function markUserRequestAsCompleted(id: string): Promise<void> {
  await updateStatus(id, 'completed', {
    errorMessage: null,
    setCompletionTimestamp: true,
  });
  untrackRuntimeRequest(id);
}

export async function markUserRequestAsCancelled(
  id: string,
  errorMessage = '用户暂停了当前任务',
): Promise<void> {
  await updateStatus(id, 'cancelled', {
    errorMessage,
    setCompletionTimestamp: true,
  });
  untrackRuntimeRequest(id);
}

export async function markActiveUserRequestsAsCancelled(
  projectId: string,
  errorMessage = '用户暂停了当前任务',
): Promise<void> {
  const activeRequests = await prisma.userRequest.findMany({
    where: activeRequestWhere(projectId),
    select: {
      id: true,
    },
  });

  await prisma.userRequest.updateMany({
    where: activeRequestWhere(projectId),
    data: {
      status: 'cancelled',
      completedAt: new Date(),
      errorMessage,
    },
  });

  activeRequests.forEach((request) => untrackRuntimeRequest(request.id));
}

export async function markActiveUserRequestsAsCompleted(projectId: string): Promise<void> {
  const activeRequests = await prisma.userRequest.findMany({
    where: activeRequestWhere(projectId),
    select: {
      id: true,
    },
  });

  await prisma.userRequest.updateMany({
    where: activeRequestWhere(projectId),
    data: {
      status: 'completed',
      completedAt: new Date(),
      errorMessage: null,
    },
  });

  activeRequests.forEach((request) => untrackRuntimeRequest(request.id));
}

export async function markUserRequestAsFailed(
  id: string,
  errorMessage?: string,
): Promise<void> {
  await updateStatus(id, 'failed', {
    errorMessage: errorMessage ?? 'Request failed',
    setCompletionTimestamp: true,
  });
  untrackRuntimeRequest(id);
}
