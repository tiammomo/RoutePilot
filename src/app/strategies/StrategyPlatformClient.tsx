"use client";

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  FileClock,
  FlaskConical,
  GitBranch,
  History,
  Loader2,
  Play,
  RefreshCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  SquareStack,
  TrendingUp,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { EmptyState } from '@/components/ui/empty-state';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  ConsoleDetailRow as DetailRow,
  ConsolePanel as Panel,
  ConsoleStatCard as StatCard,
  formatCompactDate as formatDate,
} from '@/components/quant/console-primitives';
import type { StrategyCatalogItem, StrategyDashboardData } from '@/lib/quant/strategies';

type Props = {
  initialData: StrategyDashboardData;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

type StrategyView = 'catalog' | 'scans' | 'compare' | 'queue' | 'versions' | 'archives';

function statusLabel(status: StrategyCatalogItem['status']) {
  if (status === 'ready') return '可回测';
  if (status === 'research') return '研究中';
  return '规划中';
}

function statusClass(status: StrategyCatalogItem['status']) {
  if (status === 'ready') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'research') return 'border-blue-200 bg-blue-50 text-blue-700';
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function riskClass(level: StrategyCatalogItem['readiness']['riskLevel']) {
  if (level === 'low') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (level === 'medium') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-red-200 bg-red-50 text-red-700';
}

function scanStatusClass(status: StrategyCatalogItem['parameterScans'][number]['status']) {
  if (status === 'available') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'planned') return 'border-blue-200 bg-blue-50 text-blue-700';
  return 'border-red-200 bg-red-50 text-red-700';
}

function scanStatusLabel(status: StrategyCatalogItem['parameterScans'][number]['status']) {
  if (status === 'available') return '可执行';
  if (status === 'planned') return '规划中';
  return '阻断';
}

function versionStatusClass(status: StrategyCatalogItem['versions'][number]['status']) {
  if (status === 'active') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'draft') return 'border-blue-200 bg-blue-50 text-blue-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function archiveStatusClass(status: StrategyCatalogItem['backtestArchives'][number]['status']) {
  if (status === 'available') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'pending') return 'border-blue-200 bg-blue-50 text-blue-700';
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function archiveStatusLabel(status: StrategyCatalogItem['backtestArchives'][number]['status']) {
  if (status === 'available') return '已归档';
  if (status === 'pending') return '待归档';
  return '缺失';
}

function jobStatusClass(status: StrategyDashboardData['scanJobs'][number]['status']) {
  if (status === 'completed') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'running') return 'border-blue-200 bg-blue-50 text-blue-700';
  if (status === 'queued') return 'border-slate-200 bg-slate-50 text-slate-600';
  return 'border-red-200 bg-red-50 text-red-700';
}

function formatMetric(value?: number | null, suffix = '') {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(2)}${suffix}`;
}

export default function StrategyPlatformClient({ initialData }: Props) {
  const router = useRouter();
  const [data, setData] = useState(initialData);
  const [selectedId, setSelectedId] = useState(initialData.templates[0]?.id ?? '');
  const [view, setView] = useState<StrategyView>('catalog');
  const [keyword, setKeyword] = useState('');
  const [symbol, setSymbol] = useState(initialData.templates[0]?.defaultSymbols[0] ?? '');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [runningScanId, setRunningScanId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const filteredTemplates = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.templates.filter((template) => {
      if (!lower) return true;
      return [
        template.id,
        template.name,
        template.family,
        template.description,
        template.capabilityId,
        ...template.defaultSymbols,
        ...template.dataDependencies,
        ...template.riskControls,
      ]
        .join(' ')
        .toLowerCase()
        .includes(lower);
    });
  }, [data.templates, keyword]);

  const selectedTemplate =
    data.templates.find(template => template.id === selectedId) ??
    filteredTemplates[0] ??
    data.templates[0] ??
    null;
  const selectedTemplateJobs = selectedTemplate
    ? data.scanJobs.filter(job => job.templateId === selectedTemplate.id)
    : [];
  const selectedTemplateRuns = selectedTemplate
    ? data.scanRuns.filter(run => run.templateId === selectedTemplate.id)
    : [];
  const comparisonResults = (selectedTemplate?.latestScanRun?.results ?? [])
    .filter(result => result.status === 'success')
    .slice()
    .sort((a, b) => (b.metrics.totalReturnPct ?? Number.NEGATIVE_INFINITY) - (a.metrics.totalReturnPct ?? Number.NEGATIVE_INFINITY));

  const refresh = async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? '刷新策略平台失败');
      }
      setData(payload.data);
      if (!payload.data.templates.some((template: StrategyCatalogItem) => template.id === selectedId)) {
        setSelectedId(payload.data.templates[0]?.id ?? '');
      }
    } catch (error) {
      setToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsRefreshing(false);
    }
  };

  const createStrategyWorkspace = async () => {
    if (!selectedTemplate || isCreating) return;
    setIsCreating(true);
    setToast(null);
    try {
      const promptResponse = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ templateId: selectedTemplate.id, symbol }),
      });
      const promptPayload = await promptResponse.json();
      if (!promptResponse.ok || !promptPayload.success) {
        throw new Error(promptPayload.error ?? '生成策略提示失败');
      }

      const projectId = `project-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
      const { name, prompt, capabilityId } = promptPayload.data as { name: string; prompt: string; capabilityId: string };
      const projectResponse = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          name,
          initialPrompt: prompt,
          quantCapabilityId: capabilityId,
        }),
      });
      const projectPayload = await projectResponse.json();
      if (!projectResponse.ok || !projectPayload.success) {
        throw new Error(projectPayload.error ?? '创建策略工作空间失败');
      }

      const createdProjectId = projectPayload.data?.id ?? projectId;
      await fetch(`${API_BASE}/api/chat/${createdProjectId}/act`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction: prompt,
          isInitialPrompt: true,
          quantCapabilityId: capabilityId,
        }),
      }).catch(() => null);

      router.push(`/${createdProjectId}/chat`);
    } catch (error) {
      setToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
      setIsCreating(false);
    }
  };

  const runScan = async (scanId: string) => {
    if (!selectedTemplate || runningScanId) return;
    setRunningScanId(scanId);
    setToast(null);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'run-scan',
          templateId: selectedTemplate.id,
          scanId,
          symbol,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? '参数扫描失败');
      }
      setToast({ type: 'success', message: `扫描任务已加入队列：${payload.data.id}` });
      await refresh();
      setView('scans');
    } catch (error) {
      setToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setRunningScanId(null);
    }
  };

  return (
    <div className="min-h-screen bg-surface text-slate-900">
      <PageHeader
        title="策略平台"
        badge={<Badge variant="outline" className="bg-white text-slate-500">{data.summary.templates} 个策略模板</Badge>}
        subtitle={`策略目录、参数口径、数据依赖、风控限制和策略工作空间 · 生成于 ${formatDate(data.generatedAt)}`}
      >
        <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
          {[
            { id: 'catalog' as const, label: '策略目录', icon: <TrendingUp className="h-4 w-4" /> },
            { id: 'scans' as const, label: '参数扫描', icon: <SlidersHorizontal className="h-4 w-4" /> },
            { id: 'compare' as const, label: '结果对比', icon: <SquareStack className="h-4 w-4" /> },
            { id: 'queue' as const, label: '执行队列', icon: <Clock3 className="h-4 w-4" /> },
            { id: 'versions' as const, label: '版本口径', icon: <History className="h-4 w-4" /> },
            { id: 'archives' as const, label: '回测归档', icon: <FileClock className="h-4 w-4" /> },
          ].map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setView(item.id)}
              className={`flex h-8 items-center gap-2 rounded px-3 text-sm font-medium ${
                view === item.id ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {item.icon}
              <span className="hidden sm:inline">{item.label}</span>
            </button>
          ))}
        </div>
        <Button variant="outline" onClick={refresh} disabled={isRefreshing}>
          <RefreshCcw className={isRefreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          刷新
        </Button>
        <Button onClick={createStrategyWorkspace} disabled={!selectedTemplate || isCreating} className="bg-blue-600 text-white hover:bg-blue-700">
          {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          生成策略工作空间
        </Button>
      </PageHeader>

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

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <StatCard label="策略模板" value={data.summary.templates} helper={`${data.summary.readyTemplates} 个可回测`} icon={<FlaskConical className="h-4 w-4" />} />
          <StatCard label="参数扫描" value={data.summary.parameterScans} helper="扫描网格与约束" icon={<SlidersHorizontal className="h-4 w-4" />} />
          <StatCard label="执行队列" value={data.scanJobs.length} helper={`${data.scanJobs.filter(job => job.status === 'running' || job.status === 'queued').length} 个待完成`} icon={<Clock3 className="h-4 w-4" />} />
          <StatCard label="策略工作空间" value={data.summary.strategyWorkspaces} helper={`${data.summary.backtestWorkspaces} 个回测项目`} icon={<GitBranch className="h-4 w-4" />} />
          <StatCard label="版本口径" value={data.summary.activeVersions} helper={`${data.templates.reduce((sum, template) => sum + template.versions.length, 0)} 条记录`} icon={<History className="h-4 w-4" />} />
          <StatCard label="回测归档" value={data.summary.archivedReports} helper="报告与限制说明" icon={<FileClock className="h-4 w-4" />} />
        </section>

        <section className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <div className="space-y-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索策略、参数、端点..."
                className="pl-9"
              />
            </div>

            <Panel title="策略目录" icon={<TrendingUp className="h-4 w-4 text-blue-700" />}>
              <div className="max-h-[640px] space-y-2 overflow-y-auto p-3">
                {filteredTemplates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => {
                      setSelectedId(template.id);
                      setSymbol(template.defaultSymbols[0] ?? '');
                    }}
                    className={`w-full rounded-md border px-3 py-3 text-left transition-colors ${
                      selectedTemplate?.id === template.id
                        ? 'border-blue-200 bg-blue-50'
                        : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-950">{template.name}</p>
                        <p className="mt-1 text-xs text-slate-500">{template.family} · {template.timeframe}</p>
                      </div>
                      <Badge variant="outline" className={`${statusClass(template.status)} shrink-0`}>
                        {statusLabel(template.status)}
                      </Badge>
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">{template.description}</p>
                    <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500">
                      <span>{template.parameterSchema.length} 参数</span>
                      <span>{template.linkedWorkspaces.length} 工作空间</span>
                    </div>
                  </button>
                ))}
                {!filteredTemplates.length && (
                  <EmptyState title="没有匹配的策略模板" description="尝试其他关键词搜索" className="m-3 border-0" />
                )}
              </div>
            </Panel>
          </div>

          {selectedTemplate ? (
            <div className="space-y-5">
              <Panel
                title={selectedTemplate.name}
                icon={<FlaskConical className="h-4 w-4 text-blue-700" />}
                action={<Badge variant="outline" className={riskClass(selectedTemplate.readiness.riskLevel)}>{selectedTemplate.readiness.label}</Badge>}
              >
                <div className="space-y-5 p-4">
                  <p className="text-sm leading-6 text-slate-600">{selectedTemplate.description}</p>
                  <div className="grid gap-3 md:grid-cols-4">
                    <div className="rounded-md bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">成熟度</p>
                      <p className="mt-1 text-lg font-semibold text-slate-950">{selectedTemplate.readiness.score}</p>
                    </div>
                    <div className="rounded-md bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">能力模块</p>
                      <p className="mt-1 truncate text-lg font-semibold text-slate-950">{selectedTemplate.capabilityId}</p>
                    </div>
                    <div className="rounded-md bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">默认标的</p>
                      <p className="mt-1 truncate text-lg font-semibold text-slate-950">{selectedTemplate.defaultSymbols.join('、')}</p>
                    </div>
                    <div className="rounded-md bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">样本周期</p>
                      <p className="mt-1 truncate text-lg font-semibold text-slate-950">{selectedTemplate.timeframe}</p>
                    </div>
                  </div>
                  <div className="rounded-md border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-800">
                    {selectedTemplate.readiness.summary}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      value={symbol}
                      onChange={(event) => setSymbol(event.target.value)}
                      placeholder="输入标的，例如 510300"
                      className="max-w-xs bg-white"
                    />
                    <Button onClick={createStrategyWorkspace} disabled={isCreating} className="bg-blue-600 text-white hover:bg-blue-700">
                      {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                      用此模板生成
                    </Button>
                  </div>
                </div>
              </Panel>

              {view === 'catalog' && (
                <>
                  <div className="grid gap-5 xl:grid-cols-2">
                    <Panel title="参数口径" icon={<SlidersHorizontal className="h-4 w-4 text-blue-700" />}>
                      <div className="divide-y divide-slate-100 px-4">
                        {selectedTemplate.parameterSchema.map((param) => (
                          <DetailRow
                            key={param.key}
                            label={param.label}
                            value={
                              <span>
                                {param.value}{param.unit ?? ''}
                                <span className="ml-2 text-xs font-normal text-slate-500">{param.description}</span>
                              </span>
                            }
                          />
                        ))}
                      </div>
                    </Panel>

                    <Panel title="评估指标" icon={<BarChart3 className="h-4 w-4 text-blue-700" />}>
                      <div className="flex flex-wrap gap-2 p-4">
                        {selectedTemplate.evaluationMetrics.map((metric) => (
                          <span key={metric} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-sm text-slate-700">
                            {metric}
                          </span>
                        ))}
                      </div>
                    </Panel>
                  </div>

                  <div className="grid gap-5 xl:grid-cols-2">
                    <Panel title="数据依赖" icon={<Database className="h-4 w-4 text-blue-700" />}>
                      <div className="space-y-2 p-4">
                        {selectedTemplate.dataDependencies.map((endpoint) => (
                          <div key={endpoint} className="rounded-md bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600">
                            {endpoint}
                          </div>
                        ))}
                      </div>
                    </Panel>

                    <Panel title="风险与限制" icon={<ShieldCheck className="h-4 w-4 text-blue-700" />}>
                      <div className="space-y-3 p-4 text-sm leading-6">
                        {selectedTemplate.riskControls.map((item) => (
                          <div key={item} className="flex gap-2 text-slate-700">
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                            <span>{item}</span>
                          </div>
                        ))}
                        {selectedTemplate.limitations.map((item) => (
                          <div key={item} className="rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">
                            {item}
                          </div>
                        ))}
                      </div>
                    </Panel>
                  </div>
                </>
              )}

              {view === 'scans' && (
                <Panel title="参数扫描矩阵" icon={<SlidersHorizontal className="h-4 w-4 text-blue-700" />}>
                  <div className="space-y-4 p-4">
                    {selectedTemplate.parameterScans.map((scan) => (
                      <div key={scan.id} className="rounded-md border border-slate-200 bg-white p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-950">{scan.name}</p>
                            <p className="mt-1 text-sm leading-6 text-slate-600">{scan.objective}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className={scanStatusClass(scan.status)}>{scanStatusLabel(scan.status)}</Badge>
                            <Button
                              size="sm"
                              variant={scan.status === 'available' ? 'default' : 'outline'}
                              onClick={() => runScan(scan.id)}
                              disabled={scan.status !== 'available' || Boolean(runningScanId)}
                              className={scan.status === 'available' ? 'bg-blue-600 text-white hover:bg-blue-700' : ''}
                            >
                              {runningScanId === scan.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                              加入队列
                            </Button>
                          </div>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-3">
                          {scan.grid.map((item) => (
                            <div key={item.key} className="rounded-md bg-slate-50 p-3">
                              <p className="text-xs font-medium text-slate-500">{item.key}</p>
                              <p className="mt-2 text-sm font-semibold text-slate-950">
                                {item.values.map(value => `${value}${item.unit ?? ''}`).join(' / ')}
                              </p>
                            </div>
                          ))}
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          <div>
                            <p className="text-xs font-medium text-slate-500">观测指标</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {scan.metrics.map(metric => (
                                <span key={metric} className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{metric}</span>
                              ))}
                            </div>
                          </div>
                          <div>
                            <p className="text-xs font-medium text-slate-500">执行护栏 · {scan.sampleSize} 组</p>
                            <div className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
                              {scan.guardrails.map(item => <p key={item}>{item}</p>)}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                    {selectedTemplate.latestScanRun && (
                      <div className="rounded-md border border-slate-200 bg-white p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-950">最新扫描报告</p>
                            <p className="mt-1 text-xs text-slate-500">
                              {selectedTemplate.latestScanRun.symbol} · {formatDate(selectedTemplate.latestScanRun.completedAt)} · {selectedTemplate.latestScanRun.source}
                            </p>
                          </div>
                          <Badge variant="outline" className={selectedTemplate.latestScanRun.status === 'completed' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : selectedTemplate.latestScanRun.status === 'partial' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-red-200 bg-red-50 text-red-700'}>
                            {selectedTemplate.latestScanRun.status}
                          </Badge>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-4">
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">总组合</p>
                            <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.total}</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">成功</p>
                            <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.succeeded}</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">失败</p>
                            <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.failed}</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">最优结果</p>
                            <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.bestResultId ?? '-'}</p>
                          </div>
                        </div>
                        <div className="mt-4 overflow-x-auto">
                          <table className="w-full min-w-[760px] text-left text-sm">
                            <thead className="text-xs text-slate-500">
                              <tr className="border-b border-slate-100">
                                <th className="py-2 pr-3 font-medium">参数</th>
                                <th className="py-2 pr-3 font-medium">收益</th>
                                <th className="py-2 pr-3 font-medium">回撤</th>
                                <th className="py-2 pr-3 font-medium">胜率</th>
                                <th className="py-2 pr-3 font-medium">交易</th>
                                <th className="py-2 pr-3 font-medium">状态</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedTemplate.latestScanRun.results.slice(0, 12).map((result) => (
                                <tr key={result.id} className="border-b border-slate-50">
                                  <td className="py-2 pr-3 font-mono text-xs text-slate-600">
                                    {Object.entries(result.parameters).map(([key, value]) => `${key}=${value}`).join(', ')}
                                  </td>
                                  <td className="py-2 pr-3 text-slate-900">{result.metrics.totalReturnPct ?? '-'}</td>
                                  <td className="py-2 pr-3 text-slate-900">{result.metrics.maxDrawdownPct ?? '-'}</td>
                                  <td className="py-2 pr-3 text-slate-900">{result.metrics.winRatePct ?? '-'}</td>
                                  <td className="py-2 pr-3 text-slate-900">{result.metrics.tradeCount ?? '-'}</td>
                                  <td className="py-2 pr-3">
                                    <span className={result.status === 'success' ? 'text-emerald-700' : result.status === 'skipped' ? 'text-amber-700' : 'text-red-700'}>
                                      {result.status}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                </Panel>
              )}

              {view === 'versions' && (
                <Panel title="版本口径" icon={<History className="h-4 w-4 text-blue-700" />}>
                  <div className="divide-y divide-slate-100">
                    {selectedTemplate.versions.map((version) => (
                      <div key={version.version} className="grid gap-4 px-4 py-4 md:grid-cols-[180px_minmax(0,1fr)]">
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="font-semibold text-slate-950">{version.version}</p>
                            <Badge variant="outline" className={versionStatusClass(version.status)}>{version.status}</Badge>
                          </div>
                          <p className="mt-2 text-xs text-slate-500">{formatDate(version.updatedAt)}</p>
                        </div>
                        <div className="space-y-3">
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(version.parameterSnapshot).map(([key, value]) => (
                              <span key={key} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600">
                                {key}={value}
                              </span>
                            ))}
                          </div>
                          <div className="space-y-1 text-sm leading-6 text-slate-600">
                            {version.changes.map(change => <p key={change}>{change}</p>)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
              )}

              {view === 'compare' && (
                <Panel title="扫描结果对比" icon={<SquareStack className="h-4 w-4 text-blue-700" />}>
                  {selectedTemplate.latestScanRun ? (
                    <div className="space-y-4 p-4">
                      <div className="grid gap-3 md:grid-cols-4">
                        <div className="rounded-md bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">报告</p>
                          <p className="mt-1 truncate font-semibold text-slate-950">{selectedTemplate.latestScanRun.id}</p>
                        </div>
                        <div className="rounded-md bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">标的</p>
                          <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.symbol}</p>
                        </div>
                        <div className="rounded-md bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">成功组合</p>
                          <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.succeeded}/{selectedTemplate.latestScanRun.total}</p>
                        </div>
                        <div className="rounded-md bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">最优参数</p>
                          <p className="mt-1 font-semibold text-slate-950">{selectedTemplate.latestScanRun.bestResultId ?? '-'}</p>
                        </div>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[860px] text-left text-sm">
                          <thead className="text-xs text-slate-500">
                            <tr className="border-b border-slate-100">
                              <th className="py-2 pr-3 font-medium">排名</th>
                              <th className="py-2 pr-3 font-medium">参数</th>
                              <th className="py-2 pr-3 font-medium">总收益</th>
                              <th className="py-2 pr-3 font-medium">最大回撤</th>
                              <th className="py-2 pr-3 font-medium">胜率</th>
                              <th className="py-2 pr-3 font-medium">交易次数</th>
                              <th className="py-2 pr-3 font-medium">Sharpe</th>
                            </tr>
                          </thead>
                          <tbody>
                            {comparisonResults.map((result, index) => (
                              <tr key={result.id} className={result.id === selectedTemplate.latestScanRun?.bestResultId ? 'border-b border-blue-100 bg-blue-50/70' : 'border-b border-slate-50'}>
                                <td className="py-2 pr-3 font-medium text-slate-900">{index + 1}</td>
                                <td className="py-2 pr-3 font-mono text-xs text-slate-600">
                                  {Object.entries(result.parameters).map(([key, value]) => `${key}=${value}`).join(', ')}
                                </td>
                                <td className="py-2 pr-3 text-slate-900">{formatMetric(result.metrics.totalReturnPct, '%')}</td>
                                <td className="py-2 pr-3 text-slate-900">{formatMetric(result.metrics.maxDrawdownPct, '%')}</td>
                                <td className="py-2 pr-3 text-slate-900">{formatMetric(result.metrics.winRatePct, '%')}</td>
                                <td className="py-2 pr-3 text-slate-900">{result.metrics.tradeCount ?? '-'}</td>
                                <td className="py-2 pr-3 text-slate-900">{formatMetric(result.metrics.sharpe)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <div className="p-8 text-center text-sm text-slate-500">
                      暂无扫描结果，先在参数扫描页加入扫描队列。
                    </div>
                  )}
                </Panel>
              )}

              {view === 'queue' && (
                <Panel title="扫描执行队列" icon={<Clock3 className="h-4 w-4 text-blue-700" />}>
                  <div className="divide-y divide-slate-100">
                    {selectedTemplateJobs.map((job) => {
                      const run = job.runId ? selectedTemplateRuns.find(item => item.id === job.runId) : null;
                      return (
                        <div key={job.id} className="grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1fr)_160px_160px] md:items-center">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="truncate font-medium text-slate-950">{job.id}</p>
                              <Badge variant="outline" className={jobStatusClass(job.status)}>{job.status}</Badge>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">
                              {job.symbol} · {job.scanId} · 创建 {formatDate(job.createdAt)}
                            </p>
                            {job.error && <p className="mt-1 text-xs text-red-600">{job.error}</p>}
                          </div>
                          <div className="text-sm text-slate-600">
                            {run ? `成功 ${run.succeeded}/${run.total}` : job.startedAt ? `开始 ${formatDate(job.startedAt)}` : '等待执行'}
                          </div>
                          <div className="text-sm text-slate-600">
                            {run?.bestResultId ? `最优 ${run.bestResultId}` : job.completedAt ? `完成 ${formatDate(job.completedAt)}` : '-'}
                          </div>
                        </div>
                      );
                    })}
                    {!selectedTemplateJobs.length && (
                      <div className="p-8 text-center text-sm text-slate-500">
                        当前策略暂无扫描队列记录。
                      </div>
                    )}
                  </div>
                </Panel>
              )}

              {view === 'archives' && (
                <Panel title="回测报告归档" icon={<FileClock className="h-4 w-4 text-blue-700" />}>
                  <div className="grid gap-4 p-4 xl:grid-cols-2">
                    {selectedTemplate.backtestArchives.map((archive) => (
                      <div key={archive.id} className="rounded-md border border-slate-200 bg-white p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-950">{archive.title}</p>
                            <p className="mt-1 text-xs text-slate-500">{archive.symbol} · {archive.period}</p>
                          </div>
                          <Badge variant="outline" className={archiveStatusClass(archive.status)}>{archiveStatusLabel(archive.status)}</Badge>
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">总收益</p>
                            <p className="mt-1 font-semibold text-slate-950">{archive.metrics.totalReturnPct ?? '-'}%</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">最大回撤</p>
                            <p className="mt-1 font-semibold text-slate-950">{archive.metrics.maxDrawdownPct ?? '-'}%</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">胜率</p>
                            <p className="mt-1 font-semibold text-slate-950">{archive.metrics.winRatePct ?? '-'}%</p>
                          </div>
                          <div className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">交易次数</p>
                            <p className="mt-1 font-semibold text-slate-950">{archive.metrics.tradeCount ?? '-'}</p>
                          </div>
                        </div>
                        <p className="mt-3 break-all font-mono text-xs text-slate-500">{archive.source}</p>
                        <div className="mt-3 space-y-1 text-xs leading-5 text-amber-700">
                          {archive.limitations.map(item => <p key={item}>{item}</p>)}
                        </div>
                        {archive.linkedWorkspaceId && (
                          <Button variant="outline" size="sm" className="mt-3" asChild>
                            <Link href={`/${archive.linkedWorkspaceId}/chat`}>打开报告工作空间</Link>
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </Panel>
              )}

              <Panel title="关联工作空间" icon={<GitBranch className="h-4 w-4 text-blue-700" />}>
                <div className="divide-y divide-slate-100">
                  {selectedTemplate.linkedWorkspaces.map((workspace) => (
                    <Link
                      key={workspace.id}
                      href={`/${workspace.id}/chat`}
                      className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-slate-50"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-950">{workspace.name}</p>
                        <p className="mt-1 text-xs text-slate-500">{workspace.capabilityId} · {formatDate(workspace.updatedAt ?? workspace.createdAt)}</p>
                      </div>
                      <Badge variant="outline" className="bg-white text-slate-500">{workspace.status ?? '-'}</Badge>
                    </Link>
                  ))}
                  {!selectedTemplate.linkedWorkspaces.length && (
                    <div className="p-8 text-center text-sm text-slate-500">
                      暂无关联工作空间，可用上方按钮按此模板生成。
                    </div>
                  )}
                </div>
              </Panel>
            </div>
          ) : (
            <EmptyState title="暂无策略模板" description="请运行策略扫描生成模板数据" className="border-0" />
          )}
        </section>
      </main>
    </div>
  );
}
