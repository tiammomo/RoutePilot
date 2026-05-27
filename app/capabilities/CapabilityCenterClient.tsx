"use client";

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  Database,
  Gauge,
  GitBranch,
  Layers3,
  RefreshCcw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
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
import type {
  CapabilityCenterData,
  CapabilityCenterDataProvider,
  CapabilityCenterItem,
} from '@/lib/quant/capability-center';

type ViewMode = 'capabilities' | 'data';

type Props = {
  initialData: CapabilityCenterData;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

function readinessLabel(status: CapabilityCenterItem['readiness']['status']) {
  if (status === 'ready') return '可用';
  if (status === 'warning') return '风险';
  if (status === 'blocked') return '阻断';
  return '规划中';
}

function readinessClass(status: CapabilityCenterItem['readiness']['status']) {
  if (status === 'ready') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'warning') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (status === 'blocked') return 'border-red-200 bg-red-50 text-red-700';
  return 'border-blue-200 bg-blue-50 text-blue-700';
}

function providerClass(status: string) {
  if (status === 'available') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'degraded') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (status === 'planned') return 'border-blue-200 bg-blue-50 text-blue-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function CapabilityListItem({
  capability,
  active,
  onSelect,
}: {
  capability: CapabilityCenterItem;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-md border px-3 py-3 text-left transition-colors ${
        active ? 'border-blue-200 bg-blue-50' : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950">{capability.name}</p>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{capability.description}</p>
        </div>
        <Badge variant="outline" className={`${readinessClass(capability.readiness.status)} shrink-0`}>
          {readinessLabel(capability.readiness.status)}
        </Badge>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500">
        <span>{capability.requiredSkills.length} Skills</span>
        <span>{capability.dataEndpoints.length} 端点</span>
      </div>
    </button>
  );
}

function ProviderCard({ provider }: { provider: CapabilityCenterDataProvider }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-950">{provider.name}</p>
          <p className="mt-1 text-xs text-slate-500">{provider.id} · {provider.category}</p>
        </div>
        <Badge variant="outline" className={providerClass(provider.status)}>{provider.status}</Badge>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-600">{provider.description}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {provider.endpoints.map((endpoint) => (
          <span key={endpoint} className="rounded bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600">{endpoint}</span>
        ))}
      </div>
      {provider.limitations.length > 0 && (
        <div className="mt-3 space-y-1 text-xs leading-5 text-amber-700">
          {provider.limitations.map((item) => <p key={item}>{item}</p>)}
        </div>
      )}
    </div>
  );
}

export default function CapabilityCenterClient({ initialData }: Props) {
  const [data, setData] = useState(initialData);
  const [view, setView] = useState<ViewMode>('capabilities');
  const [keyword, setKeyword] = useState('');
  const [selectedId, setSelectedId] = useState(initialData.defaultCapabilityId);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const filteredCapabilities = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.capabilities.filter((capability) => {
      if (!lower) return true;
      return [
        capability.id,
        capability.name,
        capability.description,
        capability.groupId,
        capability.agentType,
        ...capability.tags,
        ...capability.dataEndpoints,
        ...capability.requiredSkills.map((skill) => skill.id),
      ]
        .join(' ')
        .toLowerCase()
        .includes(lower);
    });
  }, [data.capabilities, keyword]);

  const filteredProviders = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.dataProviders.filter((provider) => {
      if (!lower) return true;
      return [
        provider.id,
        provider.name,
        provider.category,
        provider.description,
        provider.status,
        ...provider.endpoints,
      ]
        .join(' ')
        .toLowerCase()
        .includes(lower);
    });
  }, [data.dataProviders, keyword]);

  const selectedCapability =
    data.capabilities.find((capability) => capability.id === selectedId) ??
    filteredCapabilities[0] ??
    data.capabilities[0] ??
    null;

  const refresh = async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const response = await fetch(`${API_BASE}/api/quant/capability-center`, { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? '刷新能力中心失败');
      }
      setData(payload.data);
      if (!payload.data.capabilities.some((capability: CapabilityCenterItem) => capability.id === selectedId)) {
        setSelectedId(payload.data.defaultCapabilityId);
      }
    } catch (error) {
      setToast(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRefreshing(false);
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
                <h1 className="text-xl font-semibold tracking-normal text-slate-950">能力与数据源中心</h1>
                <Badge variant="outline" className="bg-white text-slate-500">
                  {data.summary.capabilities} 个能力
                </Badge>
              </div>
              <p className="mt-1 truncate text-xs text-slate-500">
                {data.marketApi.baseUrl} · 生成于 {formatDate(data.generatedAt)}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => setView('capabilities')}
                className={`flex h-8 items-center gap-2 rounded px-3 text-sm font-medium ${
                  view === 'capabilities' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Sparkles className="h-4 w-4" />
                能力矩阵
              </button>
              <button
                type="button"
                onClick={() => setView('data')}
                className={`flex h-8 items-center gap-2 rounded px-3 text-sm font-medium ${
                  view === 'data' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Database className="h-4 w-4" />
                数据源
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
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm">
            {toast}
          </div>
        )}

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <StatCard label="可用能力" value={data.summary.readyCapabilities} helper={`${data.summary.plannedCapabilities} 个规划能力`} icon={<Sparkles className="h-4 w-4" />} />
          <StatCard label="阻断能力" value={data.summary.blockedCapabilities} helper="依赖缺失或异常" icon={<XCircle className="h-4 w-4" />} />
          <StatCard label="Skills" value={data.summary.skills} helper={`${data.summary.skillErrors} 个异常`} icon={<Layers3 className="h-4 w-4" />} />
          <StatCard label="数据源" value={data.summary.dataProviders} helper={`${data.summary.availableProviders} 可用`} icon={<Database className="h-4 w-4" />} />
          <StatCard label="降级源" value={data.summary.degradedProviders} helper="需要关注的数据源" icon={<TriangleAlert className="h-4 w-4" />} />
          <StatCard label="市场服务" value={data.summary.marketApiReachable ? '在线' : '离线'} helper={data.marketApi.status} icon={<Server className="h-4 w-4" />} />
        </section>

        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder={view === 'capabilities' ? '搜索能力、Skill、端点...' : '搜索数据源、端点、类别...'}
            className="h-10 border-slate-200 bg-white pl-9"
          />
        </div>

        {view === 'capabilities' ? (
          <section className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
            <Panel
              title="能力矩阵"
              icon={<Boxes className="h-4 w-4 text-blue-700" />}
              action={<Badge variant="outline" className="bg-white text-slate-500">{filteredCapabilities.length}</Badge>}
            >
              <div className="max-h-[760px] space-y-2 overflow-y-auto p-3">
                {filteredCapabilities.map((capability) => (
                  <CapabilityListItem
                    key={capability.id}
                    capability={capability}
                    active={selectedCapability?.id === capability.id}
                    onSelect={() => setSelectedId(capability.id)}
                  />
                ))}
                {!filteredCapabilities.length && (
                  <div className="rounded-md border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500">没有匹配的能力。</div>
                )}
              </div>
            </Panel>

            {selectedCapability ? (
              <div className="min-w-0 space-y-5">
                <Panel
                  title={selectedCapability.name}
                  icon={<Gauge className="h-4 w-4 text-blue-700" />}
                  action={<Badge variant="outline" className={readinessClass(selectedCapability.readiness.status)}>{readinessLabel(selectedCapability.readiness.status)}</Badge>}
                >
                  <div className="space-y-4 p-4">
                    <p className="text-sm leading-6 text-slate-600">{selectedCapability.description}</p>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs text-slate-500">准备度</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">{selectedCapability.readiness.score}</p>
                      </div>
                      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs text-slate-500">Agent</p>
                        <p className="mt-1 truncate text-lg font-semibold text-slate-950">{selectedCapability.agentType}</p>
                      </div>
                      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs text-slate-500">执行能力</p>
                        <p className="mt-1 truncate text-lg font-semibold text-slate-950">{selectedCapability.executionCapabilityId}</p>
                      </div>
                      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs text-slate-500">分组</p>
                        <p className="mt-1 truncate text-lg font-semibold text-slate-950">{selectedCapability.groupId}</p>
                      </div>
                    </div>
                    <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-800">
                      {selectedCapability.readiness.summary}
                    </div>
                  </div>
                </Panel>

                <div className="grid gap-5 xl:grid-cols-2">
                  <Panel title="依赖 Skills" icon={<Layers3 className="h-4 w-4 text-blue-700" />}>
                    <div className="divide-y divide-slate-100">
                      {selectedCapability.requiredSkills.map((skill) => (
                        <div key={skill.id} className="flex items-center justify-between gap-3 px-4 py-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-950">{skill.name}</p>
                            <p className="mt-1 truncate text-xs text-slate-500">
                              {skill.requestedId === skill.id ? skill.id : `${skill.requestedId} -> ${skill.id}`} · v{skill.version}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            {skill.viaAlias && <Badge variant="outline" className="bg-white text-slate-500">alias</Badge>}
                            <Badge variant="outline" className={skill.health === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700'}>{skill.health}</Badge>
                          </div>
                        </div>
                      ))}
                      {selectedCapability.missingSkills.map((skillId) => (
                        <div key={skillId} className="flex items-center justify-between gap-3 px-4 py-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-950">{skillId}</p>
                            <p className="mt-1 text-xs text-slate-500">未在 Skills registry 中找到</p>
                          </div>
                          <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">missing</Badge>
                        </div>
                      ))}
                    </div>
                  </Panel>

                  <Panel title="数据端点" icon={<Database className="h-4 w-4 text-blue-700" />}>
                    <div className="space-y-2 p-4">
                      {selectedCapability.dataEndpoints.map((endpoint) => (
                        <div key={endpoint} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
                          {endpoint}
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>

                <div className="grid gap-5 xl:grid-cols-2">
                  <Panel title="产物契约" icon={<ShieldCheck className="h-4 w-4 text-blue-700" />}>
                    <div className="flex flex-wrap gap-2 p-4">
                      {selectedCapability.expectedArtifacts.map((artifact) => (
                        <Badge key={artifact} variant="outline" className="bg-slate-50 text-slate-600">{artifact}</Badge>
                      ))}
                    </div>
                  </Panel>
                  <Panel title="验证规则" icon={<CheckCircle2 className="h-4 w-4 text-blue-700" />}>
                    <div className="space-y-2 p-4">
                      {selectedCapability.validationRules.map((rule) => (
                        <div key={rule} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
                          {rule}
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>
              </div>
            ) : (
              <Panel title="能力详情" icon={<Gauge className="h-4 w-4 text-blue-700" />}>
                <div className="p-10 text-center text-sm text-slate-500">暂无能力。</div>
              </Panel>
            )}
          </section>
        ) : (
          <section className="space-y-5">
            <Panel
              title="市场数据服务"
              icon={<Server className="h-4 w-4 text-blue-700" />}
              action={<Badge variant="outline" className={data.marketApi.reachable ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700'}>{data.marketApi.status}</Badge>}
            >
              <div className="grid gap-3 p-4 md:grid-cols-3">
                <div className="rounded-md bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Base URL</p>
                  <p className="mt-1 truncate font-mono text-sm font-semibold text-slate-950">{data.marketApi.baseUrl}</p>
                </div>
                <div className="rounded-md bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">检查时间</p>
                  <p className="mt-1 text-sm font-semibold text-slate-950">{formatDate(data.marketApi.checkedAt)}</p>
                </div>
                <div className="rounded-md bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">错误</p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-950">{data.marketApi.error ?? '-'}</p>
                </div>
              </div>
            </Panel>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filteredProviders.map((provider) => (
                <ProviderCard key={provider.id} provider={provider} />
              ))}
            </div>
            {!filteredProviders.length && (
              <div className="rounded-md border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">没有匹配的数据源。</div>
            )}
          </section>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" asChild>
            <Link href="/skills">
              <Wrench className="h-4 w-4" />
              打开 Skills 管理
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/workspaces">
              <GitBranch className="h-4 w-4" />
              打开工作空间运维台
            </Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
