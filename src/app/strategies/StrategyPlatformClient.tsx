"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
  ArrowRight,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/PageHeader";
import { SubNav, type SubNavItem } from "@/components/layout/SubNav";
import { formatCompactDate as formatDate } from "@/components/quant/console-primitives";
import { cn } from "@/lib/utils";
import type { StrategyCatalogItem, StrategyDashboardData } from "@/lib/quant/strategies";

type Props = { initialData: StrategyDashboardData };
type StrategyView = "catalog" | "scans" | "compare" | "queue" | "versions" | "archives";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

// ─── Status helpers ────────────────────────────────────────────
function statusLabel(s: StrategyCatalogItem["status"]) {
  return s === "ready" ? "可回测" : s === "research" ? "研究中" : "规划中";
}
function statusClass(s: StrategyCatalogItem["status"]) {
  if (s === "ready") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (s === "research") return "border-blue-200 bg-blue-50 text-blue-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}
function scanStatusClass(s: StrategyCatalogItem["parameterScans"][number]["status"]) {
  if (s === "available") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (s === "planned") return "border-blue-200 bg-blue-50 text-blue-700";
  return "border-red-200 bg-red-50 text-red-700";
}
function scanStatusLabel(s: StrategyCatalogItem["parameterScans"][number]["status"]) {
  if (s === "available") return "可执行";
  if (s === "planned") return "规划中";
  return "阻断";
}
function versionStatusClass(s: StrategyCatalogItem["versions"][number]["status"]) {
  if (s === "active") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (s === "draft") return "border-blue-200 bg-blue-50 text-blue-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}
function archiveStatusClass(s: StrategyCatalogItem["backtestArchives"][number]["status"]) {
  if (s === "available") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (s === "pending") return "border-blue-200 bg-blue-50 text-blue-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}
function archiveStatusLabel(s: StrategyCatalogItem["backtestArchives"][number]["status"]) {
  if (s === "available") return "已归档";
  if (s === "pending") return "待归档";
  return "缺失";
}
function jobStatusClass(s: StrategyDashboardData["scanJobs"][number]["status"]) {
  if (s === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (s === "running") return "border-blue-200 bg-blue-50 text-blue-700";
  if (s === "queued") return "border-slate-200 bg-slate-50 text-slate-600";
  return "border-red-200 bg-red-50 text-red-700";
}
function riskClass(level: StrategyCatalogItem["readiness"]["riskLevel"]) {
  if (level === "low") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (level === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
}
function formatMetric(value?: number | null, suffix = "") {
  if (value === null || value === undefined) return "-";
  return `${Number(value).toFixed(2)}${suffix}`;
}

// ─── Sub-nav items ─────────────────────────────────────────────
const SUB_NAV_ITEMS: SubNavItem[] = [
  { id: "catalog", label: "策略目录", icon: <TrendingUp className="h-4 w-4" /> },
  { id: "scans", label: "参数扫描", icon: <SlidersHorizontal className="h-4 w-4" /> },
  { id: "compare", label: "结果对比", icon: <SquareStack className="h-4 w-4" /> },
  { id: "queue", label: "执行队列", icon: <Clock3 className="h-4 w-4" /> },
  { id: "versions", label: "版本口径", icon: <History className="h-4 w-4" /> },
  { id: "archives", label: "回测归档", icon: <FileClock className="h-4 w-4" /> },
];

// ─── Status Bar ────────────────────────────────────────────────
function StatusBar({ data }: { data: StrategyDashboardData }) {
  const items = [
    { label: "策略模板", value: data.summary.templates, sub: `${data.summary.readyTemplates} 可回测`, icon: <FlaskConical className="h-3.5 w-3.5" /> },
    { label: "参数扫描", value: data.summary.parameterScans, sub: "扫描网格与约束", icon: <SlidersHorizontal className="h-3.5 w-3.5" /> },
    { label: "执行队列", value: data.scanJobs.length, sub: `${data.scanJobs.filter((j) => j.status === "running" || j.status === "queued").length} 待完成`, icon: <Clock3 className="h-3.5 w-3.5" /> },
    { label: "工作空间", value: data.summary.strategyWorkspaces, sub: `${data.summary.backtestWorkspaces} 回测项目`, icon: <GitBranch className="h-3.5 w-3.5" /> },
    { label: "版本口径", value: data.summary.activeVersions, sub: `${data.templates.reduce((s, t) => s + t.versions.length, 0)} 条记录`, icon: <History className="h-3.5 w-3.5" /> },
    { label: "回测归档", value: data.summary.archivedReports, sub: "报告与限制说明", icon: <FileClock className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-[130px] flex-1 items-center gap-3 rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white text-slate-500">{item.icon}</div>
          <div className="min-w-0">
            <p className="text-sm font-semibold tabular-nums text-slate-900">{item.value}</p>
            <p className="truncate text-[11px] text-slate-500">{item.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Strategy Selector Bar ─────────────────────────────────────
function StrategySelector({
  templates,
  selectedId,
  keyword,
  onKeywordChange,
  onSelect,
}: {
  templates: StrategyCatalogItem[];
  selectedId: string;
  keyword: string;
  onKeywordChange: (v: string) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={keyword}
            onChange={(e) => onKeywordChange(e.target.value)}
            placeholder="搜索策略、参数、端点..."
            className="h-9 border-slate-200 bg-white pl-9"
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {templates.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelect(t.id)}
            className={cn(
              "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors",
              selectedId === t.id
                ? "border-blue-200 bg-blue-50 text-blue-700"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
            )}
          >
            <span className={cn("text-sm font-medium", selectedId === t.id ? "text-blue-700" : "text-slate-700")}>
              {t.name}
            </span>
            <span className={cn("rounded-full border px-1.5 py-0 text-[10px] font-medium", statusClass(t.status))}>
              {statusLabel(t.status)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────
export default function StrategyPlatformClient({ initialData }: Props) {
  const router = useRouter();
  const [data, setData] = useState(initialData);
  const [selectedId, setSelectedId] = useState(initialData.templates[0]?.id ?? "");
  const [view, setView] = useState<StrategyView>("catalog");
  const [keyword, setKeyword] = useState("");
  const [symbol, setSymbol] = useState(initialData.templates[0]?.defaultSymbols[0] ?? "");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [runningScanId, setRunningScanId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const filteredTemplates = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.templates.filter((t) => {
      if (!lower) return true;
      return [t.id, t.name, t.family, t.description, t.capabilityId, ...t.defaultSymbols, ...t.dataDependencies, ...t.riskControls]
        .join(" ").toLowerCase().includes(lower);
    });
  }, [data.templates, keyword]);

  const selectedTemplate =
    data.templates.find((t) => t.id === selectedId) ?? filteredTemplates[0] ?? data.templates[0] ?? null;

  const selectedTemplateJobs = selectedTemplate
    ? data.scanJobs.filter((j) => j.templateId === selectedTemplate.id)
    : [];
  const selectedTemplateRuns = selectedTemplate
    ? data.scanRuns.filter((r) => r.templateId === selectedTemplate.id)
    : [];
  const comparisonResults = (selectedTemplate?.latestScanRun?.results ?? [])
    .filter((r) => r.status === "success")
    .slice()
    .sort((a, b) => (b.metrics.totalReturnPct ?? -Infinity) - (a.metrics.totalReturnPct ?? -Infinity));

  const refresh = async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const r = await fetch(`${API_BASE}/api/quant/strategies`, { cache: "no-store" });
      const payload = await r.json();
      if (!r.ok || !payload.success) throw new Error(payload.error ?? "刷新失败");
      setData(payload.data);
      if (!payload.data.templates.some((t: StrategyCatalogItem) => t.id === selectedId)) {
        setSelectedId(payload.data.templates[0]?.id ?? "");
      }
    } catch (error) {
      setToast({ type: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsRefreshing(false);
    }
  };

  const createStrategyWorkspace = async () => {
    if (!selectedTemplate || isCreating) return;
    setIsCreating(true);
    setToast(null);
    try {
      const pr = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ templateId: selectedTemplate.id, symbol }),
      });
      const pp = await pr.json();
      if (!pr.ok || !pp.success) throw new Error(pp.error ?? "生成策略提示失败");
      const projectId = `project-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
      const { name, prompt, capabilityId } = pp.data as { name: string; prompt: string; capabilityId: string };
      const cr = await fetch(`${API_BASE}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, name, initialPrompt: prompt, quantCapabilityId: capabilityId }),
      });
      const cp = await cr.json();
      if (!cr.ok || !cp.success) throw new Error(cp.error ?? "创建策略工作空间失败");
      const createdId = cp.data?.id ?? projectId;
      await fetch(`${API_BASE}/api/chat/${createdId}/act`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: prompt, isInitialPrompt: true, quantCapabilityId: capabilityId }),
      }).catch(() => null);
      router.push(`/${createdId}/chat`);
    } catch (error) {
      setToast({ type: "error", message: error instanceof Error ? error.message : String(error) });
      setIsCreating(false);
    }
  };

  const runScan = async (scanId: string) => {
    if (!selectedTemplate || runningScanId) return;
    setRunningScanId(scanId);
    setToast(null);
    try {
      const r = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "run-scan", templateId: selectedTemplate.id, scanId, symbol }),
      });
      const payload = await r.json();
      if (!r.ok || !payload.success) throw new Error(payload.error ?? "参数扫描失败");
      setToast({ type: "success", message: `扫描任务已加入队列：${payload.data.id}` });
      await refresh();
      setView("scans");
    } catch (error) {
      setToast({ type: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setRunningScanId(null);
    }
  };

  const switchView = (v: string) => setView(v as StrategyView);
  const selectTemplate = (id: string) => {
    setSelectedId(id);
    const t = data.templates.find((tmpl) => tmpl.id === id);
    if (t) setSymbol(t.defaultSymbols[0] ?? "");
  };

  return (
    <div className="min-h-screen bg-surface text-slate-900">
      <PageHeader
        title="策略平台"
        badge={<Badge variant="outline" className="bg-white text-slate-500">{data.summary.templates} 个策略模板</Badge>}
        subtitle={`策略目录、参数口径、数据依赖、风控限制和策略工作空间 · 生成于 ${formatDate(data.generatedAt)}`}
      />

      <SubNav
        items={SUB_NAV_ITEMS}
        activeId={view}
        onChange={switchView}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={refresh} disabled={isRefreshing}>
              <RefreshCcw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
              刷新
            </Button>
            {selectedTemplate && (view === "catalog" || view === "scans") && (
              <Button size="sm" onClick={createStrategyWorkspace} disabled={isCreating} className="bg-blue-600 text-white hover:bg-blue-700">
                {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                生成工作空间
              </Button>
            )}
          </div>
        }
      />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 lg:px-6">
        {toast && (
          <div className={cn("rounded-md border px-4 py-3 text-sm shadow-sm",
            toast.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"
          )}>{toast.message}</div>
        )}

        <StatusBar data={data} />

        {/* Strategy selector — visible on all tabs */}
        <StrategySelector
          templates={filteredTemplates}
          selectedId={selectedId}
          keyword={keyword}
          onKeywordChange={setKeyword}
          onSelect={selectTemplate}
        />

        {!selectedTemplate && !filteredTemplates.length ? (
          <EmptyState title="暂无策略模板" description="请运行策略扫描生成模板数据" className="border-0" />
        ) : selectedTemplate ? (
          <>
            {/* Template overview header */}
            <div className="rounded-lg border border-slate-200 bg-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-bold text-slate-950">{selectedTemplate.name}</h2>
                    <Badge variant="outline" className={riskClass(selectedTemplate.readiness.riskLevel)}>
                      {selectedTemplate.readiness.label}
                    </Badge>
                    <Badge variant="outline" className={statusClass(selectedTemplate.status)}>
                      {statusLabel(selectedTemplate.status)}
                    </Badge>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{selectedTemplate.description}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <div className="rounded-md bg-slate-50 px-3 py-2 text-center">
                    <p className="text-xs text-slate-500">成熟度</p>
                    <p className="text-lg font-bold tabular-nums text-slate-900">{selectedTemplate.readiness.score}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2 text-center">
                    <p className="text-xs text-slate-500">工作空间</p>
                    <p className="text-lg font-bold tabular-nums text-slate-900">{selectedTemplate.linkedWorkspaces.length}</p>
                  </div>
                </div>
              </div>
              <div className="mt-3 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-800">
                {selectedTemplate.readiness.summary}
              </div>
            </div>

            {/* ── Tab: Catalog ─────────────────────────── */}
            {view === "catalog" && (
              <div className="space-y-5">
                <div className="grid gap-5 lg:grid-cols-2">
                  {/* Parameters */}
                  <section className="rounded-lg border border-slate-200 bg-white">
                    <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                      <SlidersHorizontal className="h-4 w-4 text-blue-600" />参数口径
                    </h3>
                    <div className="divide-y divide-slate-100">
                      {selectedTemplate.parameterSchema.map((p) => (
                        <div key={p.key} className="flex items-start justify-between gap-4 px-4 py-2.5 text-sm">
                          <span className="shrink-0 text-slate-500">{p.label}</span>
                          <span className="min-w-0 break-words text-right font-medium text-slate-900">
                            {p.value}{p.unit ?? ""}
                            <span className="ml-2 text-xs font-normal text-slate-500">{p.description}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>

                  {/* Metrics */}
                  <section className="rounded-lg border border-slate-200 bg-white">
                    <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                      <BarChart3 className="h-4 w-4 text-blue-600" />评估指标
                    </h3>
                    <div className="flex flex-wrap gap-2 p-4">
                      {selectedTemplate.evaluationMetrics.map((m) => (
                        <span key={m} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-sm text-slate-700">{m}</span>
                      ))}
                    </div>
                  </section>

                  {/* Dependencies */}
                  <section className="rounded-lg border border-slate-200 bg-white">
                    <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                      <Database className="h-4 w-4 text-blue-600" />数据依赖
                    </h3>
                    <div className="space-y-2 p-4">
                      {selectedTemplate.dataDependencies.map((ep) => (
                        <code key={ep} className="block rounded-md bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600">{ep}</code>
                      ))}
                    </div>
                  </section>

                  {/* Risk & Limitations */}
                  <section className="rounded-lg border border-slate-200 bg-white">
                    <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                      <ShieldCheck className="h-4 w-4 text-blue-600" />风险与限制
                    </h3>
                    <div className="space-y-3 p-4 text-sm">
                      {selectedTemplate.riskControls.map((item) => (
                        <div key={item} className="flex gap-2 text-slate-700">
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                          <span>{item}</span>
                        </div>
                      ))}
                      {selectedTemplate.limitations.map((item) => (
                        <div key={item} className="rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">{item}</div>
                      ))}
                    </div>
                  </section>
                </div>

                {/* Symbol input + generate CTA */}
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-4">
                  <Input
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="输入标的，例如 510300"
                    className="max-w-xs bg-white"
                  />
                  <Button onClick={createStrategyWorkspace} disabled={isCreating} className="bg-blue-600 text-white hover:bg-blue-700">
                    {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    用此模板生成工作空间
                  </Button>
                </div>
              </div>
            )}

            {/* ── Tab: Scans ──────────────────────────── */}
            {view === "scans" && (
              <div className="space-y-4">
                {selectedTemplate.parameterScans.length === 0 ? (
                  <EmptyState title="暂无参数扫描" description="当前策略未配置参数扫描矩阵" className="border-0" />
                ) : (
                  selectedTemplate.parameterScans.map((scan) => (
                    <div key={scan.id} className="rounded-lg border border-slate-200 bg-white p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h3 className="font-semibold text-slate-950">{scan.name}</h3>
                          <p className="mt-1 text-sm text-slate-600">{scan.objective}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className={scanStatusClass(scan.status)}>{scanStatusLabel(scan.status)}</Badge>
                          <Button
                            size="sm"
                            variant={scan.status === "available" ? "default" : "outline"}
                            onClick={() => runScan(scan.id)}
                            disabled={scan.status !== "available" || Boolean(runningScanId)}
                            className={scan.status === "available" ? "bg-blue-600 text-white hover:bg-blue-700" : ""}
                          >
                            {runningScanId === scan.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                            加入队列
                          </Button>
                        </div>
                      </div>
                      <div className="mt-4 grid gap-3 sm:grid-cols-3">
                        {scan.grid.map((item) => (
                          <div key={item.key} className="rounded-md bg-slate-50 p-3">
                            <p className="text-xs font-medium text-slate-500">{item.key}</p>
                            <p className="mt-2 text-sm font-semibold text-slate-950">
                              {item.values.map((v) => `${v}${item.unit ?? ""}`).join(" / ")}
                            </p>
                          </div>
                        ))}
                      </div>
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-slate-500">观测指标</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {scan.metrics.map((m) => (
                              <span key={m} className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{m}</span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">执行护栏 · {scan.sampleSize} 组</p>
                          <div className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
                            {scan.guardrails.map((g) => <p key={g}>{g}</p>)}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}

                {selectedTemplate.latestScanRun && (
                  <div className="rounded-lg border border-slate-200 bg-white p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-semibold text-slate-950">最新扫描报告</h3>
                        <p className="mt-1 text-xs text-slate-500">
                          {selectedTemplate.latestScanRun.symbol} · {formatDate(selectedTemplate.latestScanRun.completedAt)} · {selectedTemplate.latestScanRun.source}
                        </p>
                      </div>
                      <Badge variant="outline" className={
                        selectedTemplate.latestScanRun.status === "completed" ? "border-emerald-200 bg-emerald-50 text-emerald-700" :
                        selectedTemplate.latestScanRun.status === "partial" ? "border-amber-200 bg-amber-50 text-amber-700" :
                        "border-red-200 bg-red-50 text-red-700"
                      }>{selectedTemplate.latestScanRun.status}</Badge>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-4">
                      {[
                        { label: "总组合", value: selectedTemplate.latestScanRun.total },
                        { label: "成功", value: selectedTemplate.latestScanRun.succeeded },
                        { label: "失败", value: selectedTemplate.latestScanRun.failed },
                        { label: "最优结果", value: selectedTemplate.latestScanRun.bestResultId ?? "-" },
                      ].map((item) => (
                        <div key={item.label} className="rounded-md bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">{item.label}</p>
                          <p className="mt-1 font-semibold text-slate-950">{item.value}</p>
                        </div>
                      ))}
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
                          {selectedTemplate.latestScanRun.results.slice(0, 12).map((r) => (
                            <tr key={r.id} className="border-b border-slate-50">
                              <td className="py-2 pr-3 font-mono text-xs text-slate-600">
                                {Object.entries(r.parameters).map(([k, v]) => `${k}=${v}`).join(", ")}
                              </td>
                              <td className="py-2 pr-3 text-slate-900">{r.metrics.totalReturnPct ?? "-"}</td>
                              <td className="py-2 pr-3 text-slate-900">{r.metrics.maxDrawdownPct ?? "-"}</td>
                              <td className="py-2 pr-3 text-slate-900">{r.metrics.winRatePct ?? "-"}</td>
                              <td className="py-2 pr-3 text-slate-900">{r.metrics.tradeCount ?? "-"}</td>
                              <td className="py-2 pr-3">
                                <span className={r.status === "success" ? "text-emerald-700" : r.status === "skipped" ? "text-amber-700" : "text-red-700"}>{r.status}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Compare ────────────────────────── */}
            {view === "compare" && (
              <div className="rounded-lg border border-slate-200 bg-white">
                <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                  <SquareStack className="h-4 w-4 text-blue-600" />扫描结果对比
                </h3>
                {selectedTemplate.latestScanRun ? (
                  <div className="space-y-4 p-5">
                    <div className="grid gap-3 sm:grid-cols-4">
                      {[
                        { label: "报告", value: selectedTemplate.latestScanRun.id },
                        { label: "标的", value: selectedTemplate.latestScanRun.symbol },
                        { label: "成功组合", value: `${selectedTemplate.latestScanRun.succeeded}/${selectedTemplate.latestScanRun.total}` },
                        { label: "最优参数", value: selectedTemplate.latestScanRun.bestResultId ?? "-" },
                      ].map((item) => (
                        <div key={item.label} className="rounded-md bg-slate-50 p-3">
                          <p className="text-xs text-slate-500">{item.label}</p>
                          <p className="mt-1 truncate font-semibold text-slate-950">{item.value}</p>
                        </div>
                      ))}
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[860px] text-left text-sm">
                        <thead className="text-xs text-slate-500">
                          <tr className="border-b border-slate-100">
                            <th className="py-2 pr-3 font-medium">#</th>
                            <th className="py-2 pr-3 font-medium">参数</th>
                            <th className="py-2 pr-3 font-medium">收益</th>
                            <th className="py-2 pr-3 font-medium">回撤</th>
                            <th className="py-2 pr-3 font-medium">胜率</th>
                            <th className="py-2 pr-3 font-medium">交易</th>
                            <th className="py-2 pr-3 font-medium">Sharpe</th>
                          </tr>
                        </thead>
                        <tbody>
                          {comparisonResults.map((r, i) => (
                            <tr key={r.id} className={r.id === selectedTemplate.latestScanRun?.bestResultId ? "border-b border-blue-100 bg-blue-50/70" : "border-b border-slate-50"}>
                              <td className="py-2 pr-3 font-medium text-slate-900">{i + 1}</td>
                              <td className="py-2 pr-3 font-mono text-xs text-slate-600">{Object.entries(r.parameters).map(([k, v]) => `${k}=${v}`).join(", ")}</td>
                              <td className="py-2 pr-3 tabular-nums text-slate-900">{formatMetric(r.metrics.totalReturnPct, "%")}</td>
                              <td className="py-2 pr-3 tabular-nums text-slate-900">{formatMetric(r.metrics.maxDrawdownPct, "%")}</td>
                              <td className="py-2 pr-3 tabular-nums text-slate-900">{formatMetric(r.metrics.winRatePct, "%")}</td>
                              <td className="py-2 pr-3 tabular-nums text-slate-900">{r.metrics.tradeCount ?? "-"}</td>
                              <td className="py-2 pr-3 tabular-nums text-slate-900">{formatMetric(r.metrics.sharpe)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <EmptyState title="暂无扫描结果" description="先在参数扫描页加入扫描队列" className="border-0 m-5" />
                )}
              </div>
            )}

            {/* ── Tab: Queue ──────────────────────────── */}
            {view === "queue" && (
              <div className="rounded-lg border border-slate-200 bg-white">
                <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                  <Clock3 className="h-4 w-4 text-blue-600" />扫描执行队列
                </h3>
                {selectedTemplateJobs.length === 0 ? (
                  <EmptyState title="暂无队列记录" description="当前策略没有扫描执行记录" className="border-0 m-5" />
                ) : (
                  <div className="divide-y divide-slate-100">
                    {selectedTemplateJobs.map((job) => {
                      const run = job.runId ? selectedTemplateRuns.find((r) => r.id === job.runId) : null;
                      return (
                        <div key={job.id} className="grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_160px_160px] md:items-center">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="truncate font-medium text-slate-950">{job.id}</p>
                              <Badge variant="outline" className={jobStatusClass(job.status)}>{job.status}</Badge>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">{job.symbol} · {job.scanId} · 创建 {formatDate(job.createdAt)}</p>
                            {job.error && <p className="mt-1 text-xs text-red-600">{job.error}</p>}
                          </div>
                          <div className="text-sm text-slate-600">{run ? `成功 ${run.succeeded}/${run.total}` : job.startedAt ? `开始 ${formatDate(job.startedAt)}` : "等待执行"}</div>
                          <div className="text-sm text-slate-600">{run?.bestResultId ? `最优 ${run.bestResultId}` : job.completedAt ? `完成 ${formatDate(job.completedAt)}` : "-"}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Versions ───────────────────────── */}
            {view === "versions" && (
              <div className="rounded-lg border border-slate-200 bg-white">
                <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                  <History className="h-4 w-4 text-blue-600" />版本口径
                </h3>
                {selectedTemplate.versions.length === 0 ? (
                  <EmptyState title="暂无版本记录" description="当前策略没有版本变更历史" className="border-0 m-5" />
                ) : (
                  <div className="divide-y divide-slate-100">
                    {selectedTemplate.versions.map((v) => (
                      <div key={v.version} className="grid gap-4 px-4 py-4 md:grid-cols-[180px_minmax(0,1fr)]">
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="font-semibold text-slate-950">{v.version}</p>
                            <Badge variant="outline" className={versionStatusClass(v.status)}>{v.status}</Badge>
                          </div>
                          <p className="mt-2 text-xs text-slate-500">{formatDate(v.updatedAt)}</p>
                        </div>
                        <div className="space-y-3">
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(v.parameterSnapshot).map(([k, val]) => (
                              <span key={k} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600">{k}={val}</span>
                            ))}
                          </div>
                          <div className="space-y-1 text-sm text-slate-600">{v.changes.map((c) => <p key={c}>{c}</p>)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Archives ───────────────────────── */}
            {view === "archives" && (
              <div className="space-y-4">
                <div className="rounded-lg border border-slate-200 bg-white">
                  <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                    <FileClock className="h-4 w-4 text-blue-600" />回测报告归档
                  </h3>
                  {selectedTemplate.backtestArchives.length === 0 ? (
                    <EmptyState title="暂无归档报告" description="运行回测后这里会出现归档报告" className="border-0 m-5" />
                  ) : (
                    <div className="grid gap-4 p-5 lg:grid-cols-2">
                      {selectedTemplate.backtestArchives.map((arch) => (
                        <div key={arch.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="font-semibold text-slate-950">{arch.title}</p>
                              <p className="mt-1 text-xs text-slate-500">{arch.symbol} · {arch.period}</p>
                            </div>
                            <Badge variant="outline" className={archiveStatusClass(arch.status)}>{archiveStatusLabel(arch.status)}</Badge>
                          </div>
                          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                            {[
                              { label: "总收益", value: `${arch.metrics.totalReturnPct ?? "-"}%` },
                              { label: "最大回撤", value: `${arch.metrics.maxDrawdownPct ?? "-"}%` },
                              { label: "胜率", value: `${arch.metrics.winRatePct ?? "-"}%` },
                              { label: "交易次数", value: arch.metrics.tradeCount ?? "-" },
                            ].map((item) => (
                              <div key={item.label} className="rounded-md bg-slate-50 p-3">
                                <p className="text-xs text-slate-500">{item.label}</p>
                                <p className="mt-1 font-semibold text-slate-950">{item.value}</p>
                              </div>
                            ))}
                          </div>
                          <p className="mt-3 break-all font-mono text-xs text-slate-500">{arch.source}</p>
                          {arch.limitations.length > 0 && (
                            <div className="mt-3 space-y-1 text-xs leading-5 text-amber-700">
                              {arch.limitations.map((l) => <p key={l}>{l}</p>)}
                            </div>
                          )}
                          {arch.linkedWorkspaceId && (
                            <Button variant="outline" size="sm" className="mt-3" asChild>
                              <Link href={`/${arch.linkedWorkspaceId}/chat`}>打开报告工作空间</Link>
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Linked workspaces — always visible */}
            {selectedTemplate.linkedWorkspaces.length > 0 && (
              <section className="rounded-lg border border-slate-200 bg-white">
                <h3 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">
                  <GitBranch className="h-4 w-4 text-blue-600" />关联工作空间
                  <Badge variant="outline" className="bg-white text-slate-500">{selectedTemplate.linkedWorkspaces.length}</Badge>
                </h3>
                <div className="divide-y divide-slate-100">
                  {selectedTemplate.linkedWorkspaces.map((ws) => (
                    <Link
                      key={ws.id}
                      href={`/${ws.id}/chat`}
                      className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-slate-50"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-950">{ws.name}</p>
                        <p className="mt-1 text-xs text-slate-500">{ws.capabilityId} · {formatDate(ws.updatedAt ?? ws.createdAt)}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge variant="outline" className="bg-white text-slate-500">{ws.status ?? "-"}</Badge>
                        <ArrowRight className="h-4 w-4 text-slate-300" />
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </>
        ) : null}
      </main>
    </div>
  );
}
