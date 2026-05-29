import { getWorkspaceHealthDashboard } from '@/lib/quant/workspace-health';
import { getGenerationObservabilityDashboard } from '@/lib/quant/generation-observability';
import { getOpsPlatformDashboard } from '@/lib/ops/ops-platform';
import WorkspacesHealthClient from './WorkspacesHealthClient';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '运维平台 · QuantPilot',
};

type Props = {
  searchParams?: Promise<{ view?: string }>;
};

export default async function OpsPlatformPage({ searchParams }: Props) {
  const params = await searchParams;
  const workspaceHealthPromise = getWorkspaceHealthDashboard();
  const [data, traceData, opsData] = await Promise.all([
    workspaceHealthPromise,
    getGenerationObservabilityDashboard(),
    getOpsPlatformDashboard({ workspaceHealth: workspaceHealthPromise }),
  ]);
  const view = params?.view;
  return (
    <WorkspacesHealthClient
      initialData={data}
      initialTraceData={traceData}
      initialOpsData={opsData}
      initialView={view === 'trace' || view === 'system' || view === 'logs' ? view : 'health'}
    />
  );
}

export const dynamic = 'force-dynamic';
