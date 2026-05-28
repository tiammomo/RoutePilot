"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Boxes,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileText,
  Gauge,
  GitBranch,
  Hammer,
  Image as ImageIcon,
  Layers3,
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
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/PageHeader";
import { SubNav, type SubNavItem } from "@/components/layout/SubNav";
import { formatCompactDate as formatDate } from "@/components/quant/console-primitives";
import {
  healthStatusClass,
  healthStatusIcon,
  healthStatusLabel,
  TimelineItem,
  TraceDetailSheet,
  TraceProjectListItem,
  traceDotClass,
  traceStageIcon,
  traceStageLabel,
  traceStatusClass,
  traceStatusIcon,
  traceStatusLabel,
  type TraceDetailKind,
} from "@/components/quant/workspace-console-primitives";
import { cn } from "@/lib/utils";
import type { WorkspaceHealthDashboard, WorkspaceHealthItem, WorkspaceHealthStatus } from "@/lib/quant/workspace-health";
import type {
  GenerationObservabilityDashboard,
  GenerationStageId,
  GenerationTraceProject,
  GenerationTraceStatus,
} from "@/lib/quant/generation-observability";

type OpsView = "health" | "trace";
type Props = {
  initialData: WorkspaceHealthDashboard;
  initialTraceData: GenerationObservabilityDashboard;
  initialView?: OpsView;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const PAGE_SIZE = 10;

const SUB_NAV_ITEMS: SubNavItem[] = [
  { id: "health", label: "健康总览", icon: <ShieldCheck className="h-4 w-4" /> },
  { id: "trace", label: "链路观测", icon: <GitBranch className="h-4 w-4" /> },
];

// ─── Health StatusBar ──────────────────────────────────────────
function HealthStatusBar({ data }: { data: WorkspaceHealthDashboard }) {
  const items = [
    { label: "平均健康分", value: data.summary.averageScore, sub: "综合评分", icon: <ShieldCheck className="h-3.5 w-3.5" />, accent: data.summary.averageScore < 70 },
    { label: "健康", value: data.summary.healthy, sub: "验证与产物正常", icon: <CheckCircle2 className="h-3.5 w-3.5" />, ok: true },
    { label: "风险", value: data.summary.warning, sub: "数据质量或过期", icon: <TriangleAlert className="h-3.5 w-3.5" />, warn: true },
    { label: "失败", value: data.summary.failed, sub: "缺产物或验证失败", icon: <XCircle className="h-3.5 w-3.5" />, err: true },
    { label: "待验证", value: data.summary.unknown, sub: "缺少验证报告", icon: <Gauge className="h-3.5 w-3.5" />, muted: true },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-[120px] flex-1 items-center gap-3 rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2.5">
          <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white",
            item.ok ? "text-emerald-600" : item.warn ? "text-amber-600" : item.err ? "text-red-500" : item.accent ? "text-amber-500" : "text-slate-500"
          )}>{item.icon}</div>
          <div className="min-w-0">
            <p className={cn("text-sm font-semibold tabular-nums", item.accent ? "text-amber-600" : "text-slate-900")}>{item.value}</p>
            <p className="truncate text-[11px] text-slate-500">{item.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Trace StatusBar ───────────────────────────────────────────
function TraceStatusBar({ data }: { data: GenerationObservabilityDashboard }) {
  const items = [
    { label: "项目", value: data.summary.total, sub: "纳入观测", icon: <Boxes className="h-3.5 w-3.5" /> },
    { label: "阻断", value: data.summary.failed, sub: "错误或验证失败", icon: <XCircle className="h-3.5 w-3.5" />, err: true },
    { label: "风险", value: data.summary.warning, sub: "警告或待修复", icon: <TriangleAlert className="h-3.5 w-3.5" />, warn: true },
    { label: "运行中", value: data.summary.running, sub: "pending 阶段", icon: <Play className="h-3.5 w-3.5" />, ok: true },
    { label: "24h 事件", value: data.summary.eventsLast24h, sub: "最近链路动作", icon: <Clock3 className="h-3.5 w-3.5" /> },
    { label: "工具调用", value: data.summary.toolCalls, sub: `${data.summary.requests} 请求`, icon: <TerminalSquare className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-[120px] flex-1 items-center gap-3 rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2.5">
          <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white",
            item.err ? "text-red-500" : item.warn ? "text-amber-600" : item.ok ? "text-blue-600" : "text-slate-500"
          )}>{item.icon}</div>
          <div className="min-w-0">
            <p className="text-sm font-semibold tabular-nums text-slate-900">{item.value}</p>
            <p className="truncate text-[11px] text-slate-500">{item.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Health Row ────────────────────────────────────────────────
function HealthRow({ project, onClick }: { project: WorkspaceHealthItem; onClick: () => void }) {
  const status = project.health.status;
  const score = project.health.score;

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-4 border-b border-slate-100 px-4 py-3 text-left transition-colors hover:bg-slate-50 last:border-b-0"
    >
      {/* Score donut-like bar */}
      <div className="flex shrink-0 items-center gap-2">
        <div className="h-10 w-10 rounded-full border-2 border-slate-200 flex items-center justify-center relative">
          <span className={cn("text-sm font-bold tabular-nums",
            score >= 80 ? "text-emerald-600" : score >= 60 ? "text-amber-600" : "text-red-600"
          )}>{score}</span>
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-semibold text-slate-900">{project.name}</p>
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", healthStatusClass(status))}>
            {healthStatusLabel[status]}
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-slate-500">{project.id} · {project.repoPath}</p>
        <p className="mt-1 line-clamp-1 text-xs text-slate-500">{project.health.summary}</p>
      </div>

      <div className="hidden shrink-0 gap-4 text-right text-xs sm:flex">
        <div>
          <p className="text-slate-500">验证</p>
          <p className={cn("font-medium", project.validation.passed === true ? "text-emerald-600" : project.validation.passed === false ? "text-red-600" : "text-slate-500")}>
            {project.validation.passed === null ? "-" : project.validation.passed ? "通过" : "失败"}
          </p>
        </div>
        <div>
          <p className="text-slate-500">产物</p>
          <p className="font-medium text-slate-700">{project.artifacts.filter((a) => a.exists).length}/{project.artifacts.length}</p>
        </div>
        <ChevronRight className="h-4 w-4 self-center text-slate-300 group-hover:text-slate-500" />
      </div>
    </button>
  );
}

// ─── Health Detail Sheet ───────────────────────────────────────
function HealthSheet({
  project,
  open,
  onOpenChange,
  isValidating,
  onValidate,
}: {
  project: WorkspaceHealthItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isValidating: boolean;
  onValidate: () => void;
}) {
  if (!project) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-[520px] max-w-[94vw] flex-col gap-0 p-0 sm:max-w-[600px]">
        <SheetHeader className="border-b px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <SheetTitle className="text-base">{project.name}</SheetTitle>
              <SheetDescription className="mt-1 truncate font-mono text-xs">{project.repoPath}</SheetDescription>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className={cn("rounded-full border px-2.5 py-1 text-xs font-semibold", healthStatusClass(project.health.status))}>
                {healthStatusLabel[project.health.status]} · {project.health.score}
              </span>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* Quick summary */}
          <p className="text-sm leading-6 text-slate-600">{project.health.summary}</p>

          {/* Status triad */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: "验证", info: healthStatusLabel[project.validation.status], ok: project.validation.passed === true, bad: project.validation.passed === false },
              { label: "契约", info: healthStatusLabel[project.artifactContracts.status], ok: project.artifactContracts.status === "healthy", bad: project.artifactContracts.status === "failed" },
              { label: "视觉验收", info: healthStatusLabel[project.visualValidation.status], ok: project.visualValidation.status === "healthy", bad: project.visualValidation.status === "failed" },
            ].map((item) => (
              <div key={item.label} className={cn("rounded-md border p-2.5 text-center",
                item.ok ? "border-emerald-200 bg-emerald-50" : item.bad ? "border-red-200 bg-red-50" : "border-slate-200 bg-slate-50"
              )}>
                <p className="text-[11px] text-slate-500">{item.label}</p>
                <p className={cn("mt-1 text-sm font-semibold", item.ok ? "text-emerald-700" : item.bad ? "text-red-700" : "text-slate-700")}>{item.info}</p>
              </div>
            ))}
          </div>

          {/* Next actions */}
          {project.nextActions.length > 0 && (
            <section>
              <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900"><Sparkles className="h-4 w-4 text-blue-500" />建议操作</h4>
              <div className="space-y-1.5">
                {project.nextActions.map((action) => (
                  <div key={action} className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm leading-6 text-blue-800">{action}</div>
                ))}
              </div>
            </section>
          )}

          {/* Artifacts */}
          <section>
            <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900"><FileText className="h-4 w-4 text-slate-500" />关键产物</h4>
            <div className="divide-y divide-slate-100 rounded-md border border-slate-200">
              {project.artifacts.map((artifact) => (
                <div key={artifact.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{artifact.label}</p>
                    <p className="truncate font-mono text-xs text-slate-500">{artifact.path}</p>
                  </div>
                  <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", healthStatusClass(artifact.status))}>
                    {artifact.exists ? healthStatusLabel[artifact.status] : "缺失"}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Events */}
          {project.events.length > 0 && (
            <section>
              <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900"><Clock3 className="h-4 w-4 text-slate-500" />最近事件</h4>
              <div className="max-h-60 space-y-2 overflow-y-auto">
                {project.events.slice(-8).reverse().map((event, i) => (
                  <div key={`${event.created_at}-${i}`} className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-slate-900">{event.stage}</p>
                      <span className="text-xs text-slate-500">{formatDate(event.created_at ?? null)}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-600">{event.summary}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Repair plan */}
          {project.repairPlan.needed && (
            <section>
              <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900"><Wrench className="h-4 w-4 text-amber-500" />修复计划</h4>
              <div className="rounded-md border border-amber-100 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
                {project.repairPlan.stepCount} 个修复步骤：{project.repairPlan.path}
              </div>
            </section>
          )}

          {/* Actions */}
          <div className="grid gap-2 sm:grid-cols-2">
            <Button onClick={onValidate} disabled={isValidating} className="bg-blue-600 text-white hover:bg-blue-700">
              {isValidating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              重新验证
            </Button>
            <Button variant="outline" asChild>
              <Link href={`/${project.id}/chat`}><ChevronRight className="h-4 w-4" />进入项目</Link>
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ─── Main Page ─────────────────────────────────────────────────
export default function WorkspacesHealthClient({ initialData, initialTraceData, initialView = "health" }: Props) {
  const [view, setView] = useState<OpsView>(initialView);
  const [healthData, setHealthData] = useState(initialData);
  const [traceData, setTraceData] = useState(initialTraceData);
  const [keyword, setKeyword] = useState("");
  const [healthFilter, setHealthFilter] = useState<WorkspaceHealthStatus | "all">("all");
  const [traceFilter, setTraceFilter] = useState<GenerationTraceStatus | "all">("all");
  const [traceStageFilter, setTraceStageFilter] = useState<GenerationStageId | "all">("all");
  const [healthPage, setHealthPage] = useState(1);
  const [tracePage, setTracePage] = useState(1);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [validatingId, setValidatingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Sheet state
  const [healthSheetProject, setHealthSheetProject] = useState<WorkspaceHealthItem | null>(null);
  const [healthSheetOpen, setHealthSheetOpen] = useState(false);
  const [traceSheetProject, setTraceSheetProject] = useState<GenerationTraceProject | null>(null);
  const [traceSheetOpen, setTraceSheetOpen] = useState(false);
  const [traceDetailKind, setTraceDetailKind] = useState<TraceDetailKind>("queue");
  const [traceDetailOpen, setTraceDetailOpen] = useState(false);

  // ── Health filtering ─────────────────────────────────────────
  const filteredHealthProjects = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return healthData.projects.filter((p) => {
      if (healthFilter !== "all" && p.health.status !== healthFilter) return false;
      if (!lower) return true;
      return [p.id, p.name, p.description, p.repoPath, p.quantCapabilityId, p.selectedModel, ...p.runPlan.symbols]
        .filter(Boolean).join(" ").toLowerCase().includes(lower);
    });
  }, [healthData.projects, keyword, healthFilter]);

  const healthPageCount = Math.max(1, Math.ceil(filteredHealthProjects.length / PAGE_SIZE));
  const safeHealthPage = Math.min(healthPage, healthPageCount);
  const pagedHealth = filteredHealthProjects.slice((safeHealthPage - 1) * PAGE_SIZE, safeHealthPage * PAGE_SIZE);

  // ── Trace filtering ──────────────────────────────────────────
  const filteredTraceProjects = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return traceData.projects.filter((p) => {
      if (traceFilter !== "all" && p.trace.status !== traceFilter) return false;
      if (!lower) return true;
      return [p.id, p.name, p.description, p.repoPath, p.preferredCli, p.selectedModel, p.runPlan.capabilityId, ...p.runPlan.symbols, p.latestRequest?.instruction]
        .filter(Boolean).join(" ").toLowerCase().includes(lower);
    });
  }, [traceData.projects, keyword, traceFilter]);

  const tracePageCount = Math.max(1, Math.ceil(filteredTraceProjects.length / PAGE_SIZE));
  const safeTracePage = Math.min(tracePage, tracePageCount);
  const pagedTrace = filteredTraceProjects.slice((safeTracePage - 1) * PAGE_SIZE, safeTracePage * PAGE_SIZE);

  const selectedTraceTimeline = useMemo(() => {
    if (!traceSheetProject) return [];
    return traceSheetProject.timeline.filter((e) => traceStageFilter === "all" || e.stage === traceStageFilter);
  }, [traceSheetProject, traceStageFilter]);

  // ── Actions ──────────────────────────────────────────────────
  const refresh = async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const [hr, tr] = await Promise.all([
        fetch(`${API_BASE}/api/workspaces/health`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/workspaces/trace`, { cache: "no-store" }),
      ]);
      const [hp, tp] = await Promise.all([hr.json(), tr.json()]);
      if (!hr.ok || !hp.success) throw new Error(hp.error ?? "刷新健康状态失败");
      if (!tr.ok || !tp.success) throw new Error(tp.error ?? "刷新链路数据失败");
      setHealthData(hp.data);
      setTraceData(tp.data);
    } catch (error) {
      setToast({ type: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsRefreshing(false);
    }
  };

  const validateProject = async (projectId: string) => {
    setValidatingId(projectId);
    try {
      const r = await fetch(`${API_BASE}/api/projects/${projectId}/quant/validation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requestId: `ops-console-${Date.now()}` }),
      });
      const payload = await r.json();
      if (!r.ok || !payload.success) throw new Error(payload.message ?? "验证失败");
      setToast({ type: payload.data?.passed ? "success" : "error", message: payload.data?.passed ? "验证通过" : "验证未通过，已更新修复计划" });
      await refresh();
    } catch (error) {
      setToast({ type: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setValidatingId(null);
    }
  };

  const openHealthSheet = (project: WorkspaceHealthItem) => {
    setHealthSheetProject(project);
    setHealthSheetOpen(true);
  };

  const openTraceSheet = (project: GenerationTraceProject) => {
    setTraceSheetProject(project);
    setTraceSheetOpen(true);
    setTraceStageFilter("all");
  };

  const switchView = (id: string) => {
    setView(id as OpsView);
    setKeyword("");
  };

  const FILTER_CHIPS_HEALTH: { id: WorkspaceHealthStatus | "all"; label: string; icon?: React.ReactNode }[] = [
    { id: "all", label: "全部" },
    { id: "failed", label: "失败", icon: <XCircle className="h-3 w-3" /> },
    { id: "warning", label: "风险", icon: <TriangleAlert className="h-3 w-3" /> },
    { id: "unknown", label: "待验证", icon: <Gauge className="h-3 w-3" /> },
    { id: "healthy", label: "健康", icon: <CheckCircle2 className="h-3 w-3" /> },
  ];

  const FILTER_CHIPS_TRACE: { id: GenerationTraceStatus | "all"; label: string }[] = [
    { id: "all", label: "全部" },
    { id: "error", label: "阻断" },
    { id: "warning", label: "风险" },
    { id: "pending", label: "运行中" },
    { id: "success", label: "正常" },
    { id: "unknown", label: "未知" },
  ];

  return (
    <div className="min-h-screen bg-surface text-slate-900">
      <PageHeader
        title="运维平台"
        badge={<Badge variant="outline" className="bg-white text-slate-500">{healthData.summary.total} 个工作空间</Badge>}
        subtitle={`${healthData.projectsDir} · 生成于 ${formatDate(view === "health" ? healthData.generatedAt : traceData.generatedAt)}`}
      />

      <SubNav
        items={SUB_NAV_ITEMS}
        activeId={view}
        onChange={switchView}
        actions={
          <Button variant="outline" size="sm" onClick={refresh} disabled={isRefreshing}>
            <RefreshCcw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
            刷新
          </Button>
        }
      />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 lg:px-6">
        {toast && (
          <div className={cn("rounded-md border px-4 py-3 text-sm shadow-sm",
            toast.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"
          )}>{toast.message}</div>
        )}

        {/* ── Health View ─────────────────────────────────── */}
        {view === "health" && (
          <>
            <HealthStatusBar data={healthData} />

            {/* Search + filters */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={keyword}
                  onChange={(e) => { setKeyword(e.target.value); setHealthPage(1); }}
                  placeholder="搜索项目、标的、路径..."
                  className="h-9 border-slate-200 bg-white pl-9"
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {FILTER_CHIPS_HEALTH.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  onClick={() => { setHealthFilter(chip.id); setHealthPage(1); }}
                  className={cn("inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                    healthFilter === chip.id ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  )}
                >
                  {chip.icon}{chip.label}
                </button>
              ))}
            </div>

            {/* Project list */}
            {filteredHealthProjects.length === 0 ? (
              <EmptyState
                title={keyword || healthFilter !== "all" ? "没有匹配的工作空间" : "暂无工作空间"}
                description={keyword ? "尝试其他关键词" : "从首页创建量化任务后这里会出现工作空间"}
                className="border-0"
              />
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                {pagedHealth.map((project) => (
                  <HealthRow key={project.id} project={project} onClick={() => openHealthSheet(project)} />
                ))}
                {healthPageCount > 1 && (
                  <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2.5 text-sm text-slate-500">
                    <span>第 {safeHealthPage}/{healthPageCount} 页 · 每页 {PAGE_SIZE} 个</span>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => setHealthPage((p) => Math.max(1, p - 1))} disabled={safeHealthPage <= 1}>上一页</Button>
                      <Button variant="outline" size="sm" onClick={() => setHealthPage((p) => Math.min(healthPageCount, p + 1))} disabled={safeHealthPage >= healthPageCount}>下一页</Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* ── Trace View ─────────────────────────────────── */}
        {view === "trace" && (
          <>
            <TraceStatusBar data={traceData} />

            {/* Search + filters */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={keyword}
                  onChange={(e) => { setKeyword(e.target.value); setTracePage(1); }}
                  placeholder="搜索项目、标的、模型、请求..."
                  className="h-9 border-slate-200 bg-white pl-9"
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {FILTER_CHIPS_TRACE.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  onClick={() => { setTraceFilter(chip.id); setTracePage(1); }}
                  className={cn("inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                    traceFilter === chip.id ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  )}
                >
                  {chip.label}
                </button>
              ))}
            </div>

            {/* Project list */}
            {filteredTraceProjects.length === 0 ? (
              <EmptyState
                title={keyword || traceFilter !== "all" ? "没有匹配的项目" : "暂无项目"}
                description={keyword ? "尝试其他关键词" : "从首页创建任务后这里会出现项目链路"}
                className="border-0"
              />
            ) : (
              <div className="space-y-3">
                {pagedTrace.map((project) => (
                  <TraceProjectListItem
                    key={project.id}
                    project={project}
                    active={traceSheetProject?.id === project.id}
                    onSelect={() => openTraceSheet(project)}
                  />
                ))}
                {tracePageCount > 1 && (
                  <div className="flex items-center justify-between text-sm text-slate-500">
                    <span>第 {safeTracePage}/{tracePageCount} 页 · 每页 {PAGE_SIZE} 个</span>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => setTracePage((p) => Math.max(1, p - 1))} disabled={safeTracePage <= 1}>上一页</Button>
                      <Button variant="outline" size="sm" onClick={() => setTracePage((p) => Math.min(tracePageCount, p + 1))} disabled={safeTracePage >= tracePageCount}>下一页</Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* ── Health Detail Sheet ────────────────────────── */}
        <HealthSheet
          project={healthSheetProject}
          open={healthSheetOpen}
          onOpenChange={setHealthSheetOpen}
          isValidating={validatingId === healthSheetProject?.id}
          onValidate={() => healthSheetProject && validateProject(healthSheetProject.id)}
        />

        {/* ── Trace Detail Sheet ──────────────────────────── */}
        <Sheet open={traceSheetOpen} onOpenChange={setTraceSheetOpen}>
          <SheetContent side="right" className="flex w-[720px] max-w-[96vw] flex-col gap-0 p-0 sm:max-w-[800px]">
            {traceSheetProject && (
              <>
                <SheetHeader className="border-b px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <SheetTitle className="text-base">{traceSheetProject.name}</SheetTitle>
                      <SheetDescription className="mt-1 text-xs">{traceSheetProject.trace.summary}</SheetDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", traceStatusClass(traceSheetProject.trace.status))}>
                        {traceStatusLabel[traceSheetProject.trace.status]}
                      </span>
                      <span className="text-xs text-slate-500">{formatDate(traceSheetProject.trace.lastEventAt)}</span>
                    </div>
                  </div>
                </SheetHeader>

                <div className="flex-1 space-y-5 overflow-y-auto p-5">
                  {/* Key metrics */}
                  <div className="grid grid-cols-4 gap-2 text-sm">
                    {[
                      { label: "事件", value: traceSheetProject.trace.eventCount },
                      { label: "请求", value: traceSheetProject.trace.requestCount },
                      { label: "工具调用", value: traceSheetProject.trace.toolCallCount },
                      { label: "验证", value: traceSheetProject.validation.passed === null ? "待验证" : traceSheetProject.validation.passed ? "通过" : "失败", ok: traceSheetProject.validation.passed === true, bad: traceSheetProject.validation.passed === false },
                    ].map((item) => (
                      <div key={item.label} className="rounded-md border border-slate-200 bg-slate-50 p-2.5 text-center">
                        <p className="text-xs text-slate-500">{item.label}</p>
                        <p className={cn("mt-1 text-lg font-semibold", item.ok ? "text-emerald-600" : item.bad ? "text-red-600" : "text-slate-900")}>{item.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Next actions */}
                  {traceSheetProject.nextActions.length > 0 && (
                    <section>
                      <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Hammer className="h-4 w-4 text-blue-500" />下一步操作</h4>
                      <div className="space-y-1.5">
                        {traceSheetProject.nextActions.map((a) => (
                          <div key={a} className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-800">{a}</div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Stages */}
                  <section>
                    <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Layers3 className="h-4 w-4 text-slate-500" />生成阶段</h4>
                    <div className="grid grid-cols-4 gap-1.5">
                      {traceSheetProject.stages.map((stage) => (
                        <button
                          key={stage.id}
                          type="button"
                          onClick={() => setTraceStageFilter(traceStageFilter === stage.id ? "all" : stage.id)}
                          className={cn("rounded-md border p-2.5 text-left transition-colors",
                            traceStageFilter === stage.id ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white hover:border-slate-300"
                          )}
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span className="flex items-center gap-1 truncate text-xs font-medium text-slate-700">
                              {traceStageIcon(stage.id)}{stage.label}
                            </span>
                            <span className={cn("h-2 w-2 shrink-0 rounded-full", traceDotClass(stage.status))} />
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500">{stage.eventCount} 事件</p>
                        </button>
                      ))}
                    </div>
                  </section>

                  {/* Timeline */}
                  <section>
                    <div className="mb-2 flex items-center justify-between">
                      <h4 className="flex items-center gap-2 text-sm font-semibold"><GitBranch className="h-4 w-4 text-slate-500" />链路时间线</h4>
                      {traceStageFilter !== "all" && (
                        <Button variant="ghost" size="sm" onClick={() => setTraceStageFilter("all")}>清除筛选</Button>
                      )}
                    </div>
                    {selectedTraceTimeline.length ? (
                      <div className="space-y-3 rounded-md bg-slate-50/70 p-3">
                        {selectedTraceTimeline.map((event) => <TimelineItem key={event.id} event={event} />)}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500">当前阶段没有事件</div>
                    )}
                  </section>

                  {/* Detail panels: Queue, State, Contracts, Visual, Plan, Tools */}
                  <section>
                    <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold"><ListChecks className="h-4 w-4 text-slate-500" />运行详情</h4>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {/* Queue */}
                      <div className="rounded-md border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h5 className="text-xs font-semibold text-slate-700">生成队列</h5>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => { setTraceDetailKind("queue"); setTraceDetailOpen(true); }}>详情</Button>
                        </div>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-slate-500">运行中</span><span className="font-medium">{traceSheetProject.generationQueue.running}</span></div>
                          <div className="flex justify-between"><span className="text-slate-500">排队</span><span className="font-medium">{traceSheetProject.generationQueue.queued}</span></div>
                          <div className="flex justify-between"><span className="text-slate-500">失败</span><span className="font-medium text-red-600">{traceSheetProject.generationQueue.failed}</span></div>
                        </div>
                      </div>

                      {/* State */}
                      <div className="rounded-md border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h5 className="text-xs font-semibold text-slate-700">状态机</h5>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => { setTraceDetailKind("state"); setTraceDetailOpen(true); }}>详情</Button>
                        </div>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-slate-500">状态</span><span className="font-medium">{traceSheetProject.generationState?.status ?? "-"}</span></div>
                          <div className="flex justify-between"><span className="text-slate-500">步骤</span><span className="font-medium">{traceSheetProject.generationState?.activeStep ?? "-"}</span></div>
                        </div>
                      </div>

                      {/* Contracts */}
                      <div className="rounded-md border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h5 className="text-xs font-semibold text-slate-700">产物契约</h5>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => { setTraceDetailKind("contracts"); setTraceDetailOpen(true); }}>详情</Button>
                        </div>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-slate-500">状态</span><span className="font-medium">{traceStatusLabel[traceSheetProject.artifactContracts.status]}</span></div>
                          <div className="flex justify-between"><span className="text-slate-500">失败/警告</span><span className="font-medium">{traceSheetProject.artifactContracts.failedChecks}/{traceSheetProject.artifactContracts.warningChecks}</span></div>
                        </div>
                      </div>

                      {/* Visual */}
                      <div className="rounded-md border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h5 className="text-xs font-semibold text-slate-700">视觉验收</h5>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => { setTraceDetailKind("visual"); setTraceDetailOpen(true); }}>详情</Button>
                        </div>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-slate-500">状态</span><span className="font-medium">{traceStatusLabel[traceSheetProject.visualValidation.status]}</span></div>
                          <div className="flex justify-between"><span className="text-slate-500">截图</span><span className="font-medium">{traceSheetProject.visualValidation.screenshots.length}</span></div>
                        </div>
                      </div>

                      {/* Plan */}
                      <div className="rounded-md border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h5 className="text-xs font-semibold text-slate-700">运行计划</h5>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => { setTraceDetailKind("plan"); setTraceDetailOpen(true); }}>详情</Button>
                        </div>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-slate-500">能力</span><span className="font-medium">{traceSheetProject.runPlan.executionCapabilityId ?? "-"}</span></div>
                          <div className="flex justify-between"><span className="text-slate-500">标的</span><span className="max-w-[120px] truncate font-medium">{traceSheetProject.runPlan.symbols.join("、") || "-"}</span></div>
                        </div>
                      </div>

                      {/* Tools */}
                      <div className="rounded-md border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h5 className="text-xs font-semibold text-slate-700">工具画像</h5>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => { setTraceDetailKind("tools"); setTraceDetailOpen(true); }}>详情</Button>
                        </div>
                        {traceSheetProject.topTools.slice(0, 3).map((tool) => (
                          <div key={tool.name} className="flex justify-between text-xs">
                            <span className="truncate text-slate-500">{tool.name}</span>
                            <span className="font-medium">×{tool.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </section>

                  <div className="pt-2">
                    <Button asChild>
                      <Link href={`/${traceSheetProject.id}/chat`}><ChevronRight className="h-4 w-4" />打开项目会话</Link>
                    </Button>
                  </div>
                </div>
              </>
            )}
          </SheetContent>
        </Sheet>

        {/* Legacy detail sheet for drill-down */}
        <TraceDetailSheet
          project={traceSheetProject}
          kind={traceDetailKind}
          open={traceDetailOpen}
          onOpenChange={setTraceDetailOpen}
        />
      </main>
    </div>
  );
}
