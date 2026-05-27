"use client";

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  FileText,
  Gauge,
  GitBranch,
  Hammer,
  Image as ImageIcon,
  ListChecks,
  Loader2,
  Play,
  RefreshCcw,
  Search,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  TriangleAlert,
  Wrench,
  XCircle,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  ConsolePanel as Panel,
  ConsoleStatCard as StatCard,
  formatCompactDate as formatDate,
} from '@/components/quant/console-primitives';
import {
  DetailButton,
  TimelineItem,
  TraceDetailSheet,
  TraceProjectListItem,
  healthStatusClass,
  healthStatusIcon,
  healthStatusLabel,
  traceDotClass,
  traceStageIcon,
  traceStageLabel,
  traceStatusClass,
  traceStatusIcon,
  traceStatusLabel,
  type TraceDetailKind,
} from '@/components/quant/workspace-console-primitives';
import type { WorkspaceHealthDashboard, WorkspaceHealthItem, WorkspaceHealthStatus } from '@/lib/quant/workspace-health';
import type {
  GenerationObservabilityDashboard,
  GenerationStageId,
  GenerationTraceProject,
  GenerationTraceStatus,
} from '@/lib/quant/generation-observability';

type WorkspaceConsoleView = 'health' | 'trace';

type Props = {
  initialData: WorkspaceHealthDashboard;
  initialTraceData: GenerationObservabilityDashboard;
  initialView?: WorkspaceConsoleView;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

export default function WorkspacesHealthClient({ initialData, initialTraceData, initialView = 'health' }: Props) {
  const [view, setView] = useState<WorkspaceConsoleView>(initialView);
  const [healthDashboard, setHealthDashboard] = useState(initialData);
  const [traceDashboard, setTraceDashboard] = useState(initialTraceData);
  const [selectedId, setSelectedId] = useState(initialData.projects[0]?.id ?? initialTraceData.projects[0]?.id ?? '');
  const [keyword, setKeyword] = useState('');
  const [healthStatusFilter, setHealthStatusFilter] = useState<WorkspaceHealthStatus | 'all'>('all');
  const [traceStatusFilter, setTraceStatusFilter] = useState<GenerationTraceStatus | 'all'>('all');
  const [traceStageFilter, setTraceStageFilter] = useState<GenerationStageId | 'all'>('all');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [validatingId, setValidatingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [traceDetailKind, setTraceDetailKind] = useState<TraceDetailKind>('queue');
  const [traceDetailOpen, setTraceDetailOpen] = useState(false);

  const filteredHealthProjects = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return healthDashboard.projects.filter((project) => {
      const statusMatched = healthStatusFilter === 'all' || project.health.status === healthStatusFilter;
      const keywordMatched =
        !lower ||
        [
          project.id,
          project.name,
          project.description,
          project.repoPath,
          project.quantCapabilityId,
          project.selectedModel,
          ...project.runPlan.symbols,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
          .includes(lower);
      return statusMatched && keywordMatched;
    });
  }, [healthDashboard.projects, keyword, healthStatusFilter]);

  const filteredTraceProjects = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return traceDashboard.projects.filter((project) => {
      const statusMatched = traceStatusFilter === 'all' || project.trace.status === traceStatusFilter;
      const keywordMatched =
        !lower ||
        [
          project.id,
          project.name,
          project.description,
          project.repoPath,
          project.preferredCli,
          project.selectedModel,
          project.runPlan.capabilityId,
          ...project.runPlan.symbols,
          project.latestRequest?.instruction,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
          .includes(lower);
      return statusMatched && keywordMatched;
    });
  }, [traceDashboard.projects, keyword, traceStatusFilter]);

  const selectedHealthProject =
    healthDashboard.projects.find((project) => project.id === selectedId) ??
    filteredHealthProjects[0] ??
    healthDashboard.projects[0] ??
    null;
  const selectedTraceProject =
    traceDashboard.projects.find((project) => project.id === selectedId) ??
    filteredTraceProjects[0] ??
    traceDashboard.projects[0] ??
    null;

  const selectedTraceTimeline = useMemo(() => {
    if (!selectedTraceProject) return [];
    return selectedTraceProject.timeline.filter((event) => traceStageFilter === 'all' || event.stage === traceStageFilter);
  }, [selectedTraceProject, traceStageFilter]);

  const openTraceDetail = (kind: TraceDetailKind) => {
    setTraceDetailKind(kind);
    setTraceDetailOpen(true);
  };

  const refresh = async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const [healthResponse, traceResponse] = await Promise.all([
        fetch(`${API_BASE}/api/workspaces/health`, { cache: 'no-store' }),
        fetch(`${API_BASE}/api/workspaces/trace`, { cache: 'no-store' }),
      ]);
      const [healthPayload, tracePayload] = await Promise.all([healthResponse.json(), traceResponse.json()]);
      if (!healthResponse.ok || !healthPayload.success) {
        throw new Error(healthPayload.error ?? '刷新工作空间健康状态失败');
      }
      if (!traceResponse.ok || !tracePayload.success) {
        throw new Error(tracePayload.error ?? '刷新生成链路失败');
      }
      setHealthDashboard(healthPayload.data);
      setTraceDashboard(tracePayload.data);
      const nextProjects = view === 'health' ? healthPayload.data.projects : tracePayload.data.projects;
      if (!nextProjects.some((project: WorkspaceHealthItem | GenerationTraceProject) => project.id === selectedId)) {
        setSelectedId(nextProjects[0]?.id ?? '');
      }
    } catch (error) {
      setToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsRefreshing(false);
    }
  };

  const validateProject = async (projectId: string) => {
    setValidatingId(projectId);
    setToast(null);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/quant/validation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requestId: `workspace-console-${Date.now()}` }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.message ?? payload.error ?? '重新验证失败');
      }
      setToast({ type: payload.data?.passed ? 'success' : 'error', message: payload.data?.passed ? '验证通过。' : '验证未通过，已更新修复计划。' });
      await refresh();
    } catch (error) {
      setToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setValidatingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#f6f7fb] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex min-h-16 flex-col items-stretch justify-between gap-3 px-4 py-3 lg:flex-row lg:items-center lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Button variant="ghost" size="icon" asChild>
              <Link href="/" aria-label="返回首页">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold tracking-normal text-slate-950">工作空间运维台</h1>
                <Badge variant="outline" className="bg-white text-slate-500">
                  {healthDashboard.summary.total} 个
                </Badge>
              </div>
              <p className="mt-1 truncate text-xs text-slate-500">
                {healthDashboard.projectsDir} · 生成于 {formatDate(view === 'health' ? healthDashboard.generatedAt : traceDashboard.generatedAt)}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => setView('health')}
                className={`flex h-8 items-center gap-2 rounded px-3 text-sm font-medium ${
                  view === 'health' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <ShieldCheck className="h-4 w-4" />
                健康总览
              </button>
              <button
                type="button"
                onClick={() => setView('trace')}
                className={`flex h-8 items-center gap-2 rounded px-3 text-sm font-medium ${
                  view === 'trace' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <GitBranch className="h-4 w-4" />
                链路观测
              </button>
            </div>
            <Button variant="outline" onClick={refresh} disabled={isRefreshing}>
              <RefreshCcw className={isRefreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
              刷新
            </Button>
          </div>
        </div>
      </header>

      <main className="space-y-5 px-4 py-5 lg:px-6">
        {toast && (
          <div
            className={`rounded-md border px-4 py-3 text-sm shadow-sm ${
              toast.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-red-200 bg-red-50 text-red-700'
            }`}
          >
            {toast.message}
          </div>
        )}

        {view === 'health' ? (
          <>
            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <StatCard label="平均健康分" value={healthDashboard.summary.averageScore} helper="按阻断和风险扣分" icon={<ShieldCheck className="h-4 w-4" />} />
              <StatCard label="健康" value={healthDashboard.summary.healthy} helper="验证和关键产物正常" icon={<CheckCircle2 className="h-4 w-4" />} />
              <StatCard label="风险" value={healthDashboard.summary.warning} helper="有数据质量或过期风险" icon={<TriangleAlert className="h-4 w-4" />} />
              <StatCard label="失败" value={healthDashboard.summary.failed} helper="缺产物或验证失败" icon={<XCircle className="h-4 w-4" />} />
              <StatCard label="待验证" value={healthDashboard.summary.unknown} helper="缺少验证报告" icon={<Gauge className="h-4 w-4" />} />
            </section>

            <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
              <Panel
                title="工作空间"
                icon={<Database className="h-4 w-4 text-blue-600" />}
                action={
                  <Badge variant="outline" className="bg-white text-slate-500">
                    {filteredHealthProjects.length}/{healthDashboard.projects.length}
                  </Badge>
                }
              >
                <div className="border-b border-slate-100 p-3">
                  <div className="grid gap-2 md:grid-cols-[minmax(220px,1fr)_160px]">
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <Input
                        value={keyword}
                        onChange={(event) => setKeyword(event.target.value)}
                        placeholder="搜索项目、标的、路径..."
                        className="h-9 border-slate-200 bg-white pl-9"
                      />
                    </div>
                    <select
                      className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      value={healthStatusFilter}
                      onChange={(event) => setHealthStatusFilter(event.target.value as WorkspaceHealthStatus | 'all')}
                    >
                      <option value="all">全部状态</option>
                      <option value="failed">失败</option>
                      <option value="warning">风险</option>
                      <option value="unknown">待验证</option>
                      <option value="healthy">健康</option>
                    </select>
                  </div>
                </div>

                <div className="divide-y divide-slate-100">
                  {filteredHealthProjects.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      className={`w-full px-4 py-3 text-left transition hover:bg-slate-50 ${
                        selectedHealthProject?.id === project.id ? 'bg-blue-50/60' : 'bg-white'
                      }`}
                      onClick={() => setSelectedId(project.id)}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <p className="truncate font-medium text-slate-950">{project.name}</p>
                            <Badge variant="outline" className={healthStatusClass(project.health.status)}>
                              {healthStatusIcon(project.health.status)}
                              <span className="ml-1">{healthStatusLabel[project.health.status]}</span>
                            </Badge>
                          </div>
                          <p className="mt-1 truncate text-xs text-slate-500">
                            {project.id} · {project.repoPath}
                          </p>
                          <p className="mt-2 text-sm text-slate-600">{project.health.summary}</p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="text-lg font-semibold text-slate-950">{project.health.score}</p>
                          <p className="text-xs text-slate-500">健康分</p>
                        </div>
                      </div>
                    </button>
                  ))}
                  {!filteredHealthProjects.length && <div className="p-10 text-center text-sm text-slate-500">没有匹配的工作空间。</div>}
                </div>
              </Panel>

              <div className="space-y-5">
                {selectedHealthProject ? (
                  <>
                    <Panel
                      title="当前诊断"
                      icon={<ShieldCheck className="h-4 w-4 text-emerald-600" />}
                      action={
                        <Badge variant="outline" className={healthStatusClass(selectedHealthProject.health.status)}>
                          {healthStatusLabel[selectedHealthProject.health.status]}
                        </Badge>
                      }
                    >
                      <div className="space-y-4 p-4">
                        <div>
                          <p className="text-base font-semibold text-slate-950">{selectedHealthProject.name}</p>
                          <p className="mt-1 truncate text-xs text-slate-500">{selectedHealthProject.repoPath}</p>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-slate-500">验证</p>
                            <p className="mt-1 font-semibold text-slate-900">{healthStatusLabel[selectedHealthProject.validation.status]}</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-slate-500">契约</p>
                            <p className="mt-1 font-semibold text-slate-900">{healthStatusLabel[selectedHealthProject.artifactContracts.status]}</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-slate-500">视觉</p>
                            <p className="mt-1 font-semibold text-slate-900">{healthStatusLabel[selectedHealthProject.visualValidation.status]}</p>
                          </div>
                        </div>
                        <div className="space-y-2">
                          {selectedHealthProject.nextActions.map((action) => (
                            <div key={action} className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-800">
                              {action}
                            </div>
                          ))}
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          <Button onClick={() => validateProject(selectedHealthProject.id)} disabled={validatingId === selectedHealthProject.id} className="bg-blue-600 text-white hover:bg-blue-700">
                            {validatingId === selectedHealthProject.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                            重新验证
                          </Button>
                          <Button variant="outline" asChild>
                            <Link href={`/${selectedHealthProject.id}/chat`}>
                              <ChevronRight className="h-4 w-4" />
                              进入项目
                            </Link>
                          </Button>
                        </div>
                      </div>
                    </Panel>

                    <Panel title="关键产物" icon={<FileText className="h-4 w-4 text-blue-600" />}>
                      <div className="divide-y divide-slate-100">
                        {selectedHealthProject.artifacts.map((artifact) => (
                          <div key={artifact.id} className="flex items-start justify-between gap-3 px-4 py-3 text-sm">
                            <div className="min-w-0">
                              <p className="font-medium text-slate-900">{artifact.label}</p>
                              <p className="mt-1 truncate font-mono text-xs text-slate-500">{artifact.path}</p>
                            </div>
                            <Badge variant="outline" className={healthStatusClass(artifact.status)}>
                              {artifact.exists ? healthStatusLabel[artifact.status] : '缺失'}
                            </Badge>
                          </div>
                        ))}
                      </div>
                    </Panel>

                    <Panel title="最近事件" icon={<Gauge className="h-4 w-4 text-slate-600" />}>
                      <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
                        {selectedHealthProject.events.slice(-8).reverse().map((event, index) => (
                          <div key={`${event.created_at}-${index}`} className="px-4 py-3 text-sm">
                            <div className="flex items-center justify-between gap-3">
                              <p className="font-medium text-slate-900">{event.stage}</p>
                              <span className="text-xs text-slate-500">{formatDate(event.created_at ?? null)}</span>
                            </div>
                            <p className="mt-1 text-slate-600">{event.summary}</p>
                          </div>
                        ))}
                        {!selectedHealthProject.events.length && <div className="p-8 text-center text-sm text-slate-500">暂无事件日志。</div>}
                      </div>
                    </Panel>
                  </>
                ) : (
                  <Panel title="当前诊断" icon={<ShieldCheck className="h-4 w-4 text-emerald-600" />}>
                    <div className="p-10 text-center text-sm text-slate-500">暂无工作空间。</div>
                  </Panel>
                )}
              </div>
            </section>

            {selectedHealthProject?.repairPlan.needed && (
              <Panel title="修复计划" icon={<Wrench className="h-4 w-4 text-amber-600" />}>
                <div className="p-4 text-sm text-slate-600">
                  已生成 {selectedHealthProject.repairPlan.stepCount} 个修复步骤：{selectedHealthProject.repairPlan.path}
                </div>
              </Panel>
            )}
          </>
        ) : (
          <>
            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
              <StatCard label="项目" value={traceDashboard.summary.total} helper="纳入观测的 workspace" icon={<Boxes className="h-4 w-4" />} />
              <StatCard label="阻断" value={traceDashboard.summary.failed} helper="错误或验证失败" icon={<XCircle className="h-4 w-4" />} />
              <StatCard label="风险" value={traceDashboard.summary.warning} helper="警告或待修复" icon={<TriangleAlert className="h-4 w-4" />} />
              <StatCard label="运行中" value={traceDashboard.summary.running} helper="pending 阶段" icon={<Play className="h-4 w-4" />} />
              <StatCard label="24h 事件" value={traceDashboard.summary.eventsLast24h} helper="最近链路动作" icon={<Clock3 className="h-4 w-4" />} />
              <StatCard label="工具调用" value={traceDashboard.summary.toolCalls} helper={`${traceDashboard.summary.requests} 个请求`} icon={<TerminalSquare className="h-4 w-4" />} />
            </section>

            <section className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
              <Panel
                title="项目链路"
                icon={<GitBranch className="h-4 w-4 text-blue-700" />}
                action={
                  <Badge variant="outline" className="bg-white text-slate-500">
                    {filteredTraceProjects.length}
                  </Badge>
                }
              >
                <div className="space-y-3 p-4">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      value={keyword}
                      onChange={(event) => setKeyword(event.target.value)}
                      placeholder="搜索项目、标的、模型、请求..."
                      className="pl-9"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(['all', 'error', 'warning', 'pending', 'success', 'unknown'] as Array<GenerationTraceStatus | 'all'>).map((status) => (
                      <button
                        key={status}
                        type="button"
                        onClick={() => setTraceStatusFilter(status)}
                        className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                          traceStatusFilter === status ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'
                        }`}
                      >
                        {status === 'all' ? '全部' : traceStatusLabel[status]}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="max-h-[720px] space-y-2 overflow-y-auto border-t border-slate-100 p-3">
                  {filteredTraceProjects.length ? (
                    filteredTraceProjects.map((project) => (
                      <TraceProjectListItem
                        key={project.id}
                        project={project}
                        active={selectedTraceProject?.id === project.id}
                        onSelect={() => setSelectedId(project.id)}
                      />
                    ))
                  ) : (
                    <div className="rounded-md border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">没有匹配的项目。</div>
                  )}
                </div>
              </Panel>

              {selectedTraceProject ? (
                <div className="min-w-0 space-y-5">
                  <Panel
                    title={selectedTraceProject.name}
                    icon={traceStatusIcon(selectedTraceProject.trace.status)}
                    action={
                      <Button variant="outline" size="sm" asChild>
                        <Link href={`/${selectedTraceProject.id}/chat`}>打开会话</Link>
                      </Button>
                    }
                  >
                    <div className="space-y-4 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className={traceStatusClass(selectedTraceProject.trace.status)}>
                          {traceStatusLabel[selectedTraceProject.trace.status]}
                        </Badge>
                        <Badge variant="outline" className="bg-white text-slate-500">
                          {selectedTraceProject.preferredCli ?? 'cli'} / {selectedTraceProject.selectedModel ?? 'model'}
                        </Badge>
                        <Badge variant="outline" className="bg-white text-slate-500">
                          {selectedTraceProject.runPlan.capabilityId ?? '未规划'}
                        </Badge>
                        <span className="text-xs text-slate-500">最近事件 {formatDate(selectedTraceProject.trace.lastEventAt)}</span>
                      </div>
                      <p className="text-sm leading-6 text-slate-600">{selectedTraceProject.trace.summary}</p>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">事件</p>
                          <p className="mt-1 text-lg font-semibold text-slate-950">{selectedTraceProject.trace.eventCount}</p>
                        </div>
                        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">请求</p>
                          <p className="mt-1 text-lg font-semibold text-slate-950">{selectedTraceProject.trace.requestCount}</p>
                        </div>
                        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">工具调用</p>
                          <p className="mt-1 text-lg font-semibold text-slate-950">{selectedTraceProject.trace.toolCallCount}</p>
                        </div>
                        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">验证</p>
                          <p className="mt-1 text-lg font-semibold text-slate-950">
                            {selectedTraceProject.validation.passed === null ? '待验证' : selectedTraceProject.validation.passed ? '通过' : '失败'}
                          </p>
                        </div>
                      </div>
                      <div className="grid gap-2 md:grid-cols-4 xl:grid-cols-8">
                        {selectedTraceProject.stages.map((stage) => (
                          <button
                            key={stage.id}
                            type="button"
                            onClick={() => setTraceStageFilter(traceStageFilter === stage.id ? 'all' : stage.id)}
                            className={`min-w-0 rounded-md border p-3 text-left ${
                              traceStageFilter === stage.id ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-white'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="flex min-w-0 items-center gap-1 truncate text-xs font-semibold text-slate-700">
                                {traceStageIcon(stage.id)}
                                {stage.label}
                              </span>
                              <span className={`h-2 w-2 shrink-0 rounded-full ${traceDotClass(stage.status)}`} />
                            </div>
                            <p className="mt-2 text-xs text-slate-500">{stage.eventCount} 事件</p>
                          </button>
                        ))}
                      </div>
                    </div>
                  </Panel>

                  <Panel
                    title="链路时间线"
                    icon={<GitBranch className="h-4 w-4 text-blue-700" />}
                    action={
                      traceStageFilter !== 'all' ? (
                        <Button variant="ghost" size="sm" onClick={() => setTraceStageFilter('all')}>
                          清除筛选
                        </Button>
                      ) : null
                    }
                  >
                    <div className="space-y-4 bg-slate-50/70 p-4">
                      {selectedTraceTimeline.length ? (
                        selectedTraceTimeline.map((event) => <TimelineItem key={event.id} event={event} />)
                      ) : (
                        <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
                          当前阶段没有事件。
                        </div>
                      )}
                    </div>
                  </Panel>

                  <div className="grid gap-5 xl:grid-cols-3">
                    <Panel title="下一步" icon={<Hammer className="h-4 w-4 text-blue-700" />}>
                      <div className="space-y-2 p-4">
                        {selectedTraceProject.nextActions.map((action) => (
                          <div key={action} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
                            {action}
                          </div>
                        ))}
                      </div>
                    </Panel>

                    <Panel
                      title="生成队列"
                      icon={<Clock3 className="h-4 w-4 text-blue-700" />}
                      action={<DetailButton onClick={() => openTraceDetail('queue')} />}
                    >
                      <div className="space-y-3 p-4 text-sm text-slate-600">
                        <div className="flex justify-between gap-3">
                          <span>运行中</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.generationQueue.running}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>排队</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.generationQueue.queued}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>失败记录</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.generationQueue.failed}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>活跃请求</span>
                          <span className="max-w-[180px] truncate font-medium text-slate-950">{selectedTraceProject.generationQueue.activeRequestId ?? '-'}</span>
                        </div>
                      </div>
                    </Panel>

                    <Panel
                      title="状态机"
                      icon={<GitBranch className="h-4 w-4 text-blue-700" />}
                      action={<DetailButton onClick={() => openTraceDetail('state')} />}
                    >
                      <div className="space-y-3 p-4 text-sm text-slate-600">
                        <div className="flex justify-between gap-3">
                          <span>运行状态</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.generationState?.status ?? '-'}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>当前步骤</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.generationState?.activeStep ?? '-'}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>修复次数</span>
                          <span className="font-medium text-slate-950">
                            {selectedTraceProject.generationState
                              ? `${selectedTraceProject.generationState.repairAttemptCount}/${selectedTraceProject.generationState.maxRepairAttempts}`
                              : '-'}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>更新时间</span>
                          <span className="font-medium text-slate-950">{formatDate(selectedTraceProject.generationState?.updatedAt ?? null)}</span>
                        </div>
                      </div>
                    </Panel>

                    <Panel
                      title="产物契约"
                      icon={<FileText className="h-4 w-4 text-blue-700" />}
                      action={<DetailButton onClick={() => openTraceDetail('contracts')} />}
                    >
                      <div className="space-y-3 p-4 text-sm text-slate-600">
                        <div className="flex justify-between gap-3">
                          <span>状态</span>
                          <span className="font-medium text-slate-950">{traceStatusLabel[selectedTraceProject.artifactContracts.status]}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>失败</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.artifactContracts.failedChecks}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>警告</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.artifactContracts.warningChecks}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>更新时间</span>
                          <span className="font-medium text-slate-950">{formatDate(selectedTraceProject.artifactContracts.updatedAt)}</span>
                        </div>
                      </div>
                    </Panel>

                    <Panel
                      title="视觉验收"
                      icon={<ImageIcon className="h-4 w-4 text-blue-700" />}
                      action={<DetailButton onClick={() => openTraceDetail('visual')} />}
                    >
                      <div className="space-y-3 p-4 text-sm text-slate-600">
                        <div className="flex justify-between gap-3">
                          <span>状态</span>
                          <span className="font-medium text-slate-950">{traceStatusLabel[selectedTraceProject.visualValidation.status]}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>失败</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.visualValidation.failedChecks}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>警告</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.visualValidation.warningChecks}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>截图</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.visualValidation.screenshots.length}</span>
                        </div>
                      </div>
                    </Panel>

                    <Panel
                      title="运行计划"
                      icon={<ListChecks className="h-4 w-4 text-blue-700" />}
                      action={<DetailButton onClick={() => openTraceDetail('plan')} />}
                    >
                      <div className="space-y-3 p-4 text-sm text-slate-600">
                        <div className="flex justify-between gap-3">
                          <span>状态</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.runPlan.status ?? '-'}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>执行能力</span>
                          <span className="font-medium text-slate-950">{selectedTraceProject.runPlan.executionCapabilityId ?? '-'}</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>标的</span>
                          <span className="max-w-[220px] truncate font-medium text-slate-950">
                            {selectedTraceProject.runPlan.symbols.length ? selectedTraceProject.runPlan.symbols.join('、') : '-'}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span>更新时间</span>
                          <span className="font-medium text-slate-950">{formatDate(selectedTraceProject.runPlan.updatedAt)}</span>
                        </div>
                      </div>
                    </Panel>

                    <Panel
                      title="工具画像"
                      icon={<TerminalSquare className="h-4 w-4 text-blue-700" />}
                      action={<DetailButton onClick={() => openTraceDetail('tools')} />}
                    >
                      <div className="space-y-2 p-4">
                        {selectedTraceProject.topTools.length ? (
                          selectedTraceProject.topTools.map((tool) => (
                            <div key={tool.name} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium text-slate-900">{tool.name}</p>
                                <p className="text-xs text-slate-500">
                                  {tool.errorCount} 错误 · 平均 {tool.averageDurationMs ?? '-'}ms
                                </p>
                              </div>
                              <span className="text-sm font-semibold text-slate-950">{tool.count}</span>
                            </div>
                          ))
                        ) : (
                          <div className="rounded-md border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">暂无工具调用记录。</div>
                        )}
                      </div>
                    </Panel>
                  </div>
                </div>
              ) : (
                <Panel title="链路时间线" icon={<GitBranch className="h-4 w-4 text-blue-700" />}>
                  <div className="p-8 text-center text-sm text-slate-500">暂无项目。</div>
                </Panel>
              )}
            </section>
          </>
        )}
      </main>
      <TraceDetailSheet
        project={selectedTraceProject}
        kind={traceDetailKind}
        open={traceDetailOpen}
        onOpenChange={setTraceDetailOpen}
      />
    </div>
  );
}
