"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  Boxes,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cpu,
  Database,
  FileText,
  Gauge,
  GitBranch,
  Hammer,
  HardDrive,
  Layers3,
  ListChecks,
  Loader2,
  Network,
  Play,
  RefreshCcw,
  ScrollText,
  Search,
  ServerCog,
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
import type { OpsCheck, OpsCheckStatus, OpsLogEntry, OpsPlatformDashboard } from "@/lib/ops/ops-platform";

type OpsView = "health" | "trace" | "system" | "logs";
type Props = {
  initialData: WorkspaceHealthDashboard;
  initialTraceData: GenerationObservabilityDashboard;
  initialOpsData: OpsPlatformDashboard;
  initialView?: OpsView;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const PAGE_SIZE = 10;

const SUB_NAV_ITEMS: SubNavItem[] = [
  { id: "health", label: "健康", icon: <ShieldCheck className="h-4 w-4" /> },
  { id: "trace", label: "链路", icon: <GitBranch className="h-4 w-4" /> },
  { id: "system", label: "巡检", icon: <ServerCog className="h-4 w-4" /> },
  { id: "logs", label: "日志", icon: <ScrollText className="h-4 w-4" /> },
];

type LogTimeRange = "all" | "5m" | "30m" | "1h" | "6h" | "24h" | "custom";

const LOG_TIME_RANGES: Array<{ id: LogTimeRange; label: string; minutes: number | null }> = [
  { id: "all", label: "全部", minutes: null },
  { id: "5m", label: "5 分钟", minutes: 5 },
  { id: "30m", label: "30 分钟", minutes: 30 },
  { id: "1h", label: "1 小时", minutes: 60 },
  { id: "6h", label: "6 小时", minutes: 360 },
  { id: "24h", label: "24 小时", minutes: 1440 },
  { id: "custom", label: "自定义", minutes: null },
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

const OPS_STATUS_LABEL: Record<OpsCheckStatus, string> = {
  ok: "正常",
  warning: "风险",
  failed: "异常",
  unknown: "未知",
};

function opsStatusClass(status: OpsCheckStatus) {
  if (status === "ok") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "failed") return "border-red-200 bg-red-50 text-red-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function OpsStatusBadge({ status }: { status: OpsCheckStatus }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold", opsStatusClass(status))}>
      {OPS_STATUS_LABEL[status]}
    </span>
  );
}

function OpsStatusBar({ data }: { data: OpsPlatformDashboard }) {
  const items = [
    { label: "运维评分", value: data.summary.score, sub: OPS_STATUS_LABEL[data.summary.status], icon: <Activity className="h-3.5 w-3.5" />, status: data.summary.status },
    { label: "正常", value: data.summary.ok, sub: "检查项", icon: <CheckCircle2 className="h-3.5 w-3.5" />, status: "ok" as OpsCheckStatus },
    { label: "风险", value: data.summary.warning, sub: "需关注", icon: <TriangleAlert className="h-3.5 w-3.5" />, status: "warning" as OpsCheckStatus },
    { label: "异常", value: data.summary.failed, sub: "需修复", icon: <XCircle className="h-3.5 w-3.5" />, status: "failed" as OpsCheckStatus },
    { label: "日志源", value: data.summary.logSources, sub: "可直接查看", icon: <ScrollText className="h-3.5 w-3.5" />, status: "unknown" as OpsCheckStatus },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-[128px] flex-1 items-center gap-3 rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2.5">
          <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white", opsStatusClass(item.status).split(" ").at(-1))}>
            {item.icon}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold tabular-nums text-slate-900">{item.value}</p>
            <p className="truncate text-[11px] text-slate-500">{item.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function HealthProfilesPanel({ data }: { data: OpsPlatformDashboard }) {
  return (
    <div className="grid gap-3 xl:grid-cols-3">
      {data.healthProfiles.map((profile) => (
        <section key={profile.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-900">{profile.label}</h3>
                <OpsStatusBadge status={profile.status} />
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">{profile.summary}</p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-2xl font-semibold tabular-nums text-slate-900">{profile.score}</p>
              <p className="text-[11px] text-slate-400">score</p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {profile.factors.map((factor) => (
              <div key={factor.id}>
                <div className="mb-1 flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", factor.status === "ok" ? "bg-emerald-500" : factor.status === "warning" ? "bg-amber-500" : "bg-red-500")} />
                    <span className="truncate text-xs font-medium text-slate-700">{factor.label}</span>
                    <span className="text-[11px] text-slate-400">{factor.weight}%</span>
                  </div>
                  <span className="font-mono text-xs font-semibold text-slate-700">{factor.score}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={cn("h-full rounded-full", factor.status === "ok" ? "bg-emerald-500" : factor.status === "warning" ? "bg-amber-500" : "bg-red-500")}
                    style={{ width: `${factor.score}%` }}
                  />
                </div>
                <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500">{factor.summary}</p>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function OpsCheckPanel({ title, description, checks }: { title: string; description: string; checks: OpsCheck[] }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <p className="mt-1 text-xs text-slate-500">{description}</p>
      </div>
      <div className="divide-y divide-slate-100">
        {checks.map((check) => (
          <div key={check.id} className="grid gap-3 px-4 py-3 lg:grid-cols-[220px_minmax(0,1fr)_auto] lg:items-start">
            <div className="flex items-center gap-2">
              <OpsStatusBadge status={check.status} />
              <span className="text-sm font-semibold text-slate-900">{check.label}</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm text-slate-700">{check.summary}</p>
              {check.detail && <p className="mt-1 break-words text-xs leading-5 text-slate-500">{check.detail}</p>}
              {check.actions?.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {check.actions.map((action) => (
                    <span key={action} className="rounded-md border border-blue-100 bg-blue-50 px-2 py-1 text-xs text-blue-700">
                      {action}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
            <span className="hidden font-mono text-xs text-slate-400 lg:block">{check.id}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SystemView({ data }: { data: OpsPlatformDashboard }) {
  const infrastructure = data.infrastructure;
  const infraItems = [
    { label: "数据库", value: infrastructure.connected ? "已连接" : "未连接", detail: infrastructure.databaseUrl || "DATABASE_URL 未配置", icon: <Database className="h-4 w-4" /> },
    { label: "TimescaleDB", value: infrastructure.timescale.enabled ? "已启用" : "未启用", detail: infrastructure.timescale.version ? `版本 ${infrastructure.timescale.version}` : "股票 K 线和因子时序扩展", icon: <HardDrive className="h-4 w-4" /> },
    { label: "Docker", value: infrastructure.docker.running ? "运行中" : "未运行", detail: infrastructure.docker.service?.status ?? infrastructure.docker.error ?? "timescaledb compose 服务", icon: <ServerCog className="h-4 w-4" /> },
    { label: "quant 表", value: infrastructure.quantSchema.tables.length, detail: infrastructure.quantSchema.tables.slice(0, 4).map((t) => `quant.${t}`).join("、") || "尚未初始化", icon: <Cpu className="h-4 w-4" /> },
  ];

  return (
    <div className="space-y-5">
      <OpsStatusBar data={data} />
      <HealthProfilesPanel data={data} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {infraItems.map((item) => (
          <div key={item.label} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-slate-50 text-slate-500">{item.icon}</span>
              {item.label}
            </div>
            <p className="mt-3 text-lg font-semibold tabular-nums text-slate-900">{item.value}</p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{item.detail}</p>
          </div>
        ))}
      </div>

      {data.infrastructureError && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {data.infrastructureError}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <OpsCheckPanel title="基础环境检查" description="确认本地运行时、数据库、工作空间目录和量化数据后端是否可用。" checks={data.systemChecks} />
        <OpsCheckPanel title="系统能力检查" description="确认 Skills、能力中心、数据源、量化表和日志入口是否具备可运维状态。" checks={data.capabilityChecks} />
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <Network className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-900">常用运维命令</h3>
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {Object.entries(infrastructure.commands).map(([key, command]) => (
            <div key={key} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
              <p className="text-[11px] uppercase text-slate-400">{key}</p>
              <code className="mt-1 block break-all text-xs text-slate-700">{command}</code>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function normalizeLogEntries(activeLog: OpsPlatformDashboard["logSources"][number] | null): OpsLogEntry[] {
  if (!activeLog) return [];
  if (activeLog.entries?.length) return activeLog.entries;
  return activeLog.lines.map((line, index) => ({
    id: `${activeLog.id}-${index}`,
    lineNumber: index + 1,
    timestamp: activeLog.modifiedAt,
    timestampSource: activeLog.modifiedAt ? "source-modified" : null,
    level: null,
    message: line,
    raw: line,
  }));
}

function formatLogTimestamp(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function logLevelClass(level: string | null) {
  const normalized = level?.toUpperCase();
  if (normalized === "ERROR" || normalized === "FATAL") return "text-red-300";
  if (normalized === "WARN" || normalized === "WARNING") return "text-amber-300";
  if (normalized === "INFO" || normalized === "LOG") return "text-blue-200";
  if (normalized === "DEBUG" || normalized === "TRACE") return "text-slate-400";
  return "text-slate-500";
}

function LogsView({
  data,
  activeLogId,
  onSelectLog,
}: {
  data: OpsPlatformDashboard;
  activeLogId: string | null;
  onSelectLog: (id: string) => void;
}) {
  const activeLog =
    data.logSources.find((source) => source.id === activeLogId) ??
    data.logSources.find((source) => source.exists) ??
    data.logSources[0] ??
    null;
  const [logKeyword, setLogKeyword] = useState("");
  const [logTimeRange, setLogTimeRange] = useState<LogTimeRange>("all");
  const [customLogStart, setCustomLogStart] = useState("");
  const [customLogEnd, setCustomLogEnd] = useState("");
  const logEntries = useMemo(() => normalizeLogEntries(activeLog), [activeLog]);
  const filteredEntries = useMemo(() => {
    const keyword = logKeyword.trim().toLowerCase();
    const range = LOG_TIME_RANGES.find((item) => item.id === logTimeRange);
    const threshold = range?.minutes ? Date.now() - range.minutes * 60_000 : null;
    const customStart = logTimeRange === "custom" && customLogStart ? Date.parse(customLogStart) : null;
    const customEnd = logTimeRange === "custom" && customLogEnd ? Date.parse(customLogEnd) : null;
    return logEntries.filter((entry) => {
      if (threshold || customStart || customEnd) {
        const timestamp = entry.timestamp ? Date.parse(entry.timestamp) : Number.NaN;
        if (!Number.isFinite(timestamp)) return false;
        if (threshold && timestamp < threshold) return false;
        if (customStart && timestamp < customStart) return false;
        if (customEnd && timestamp > customEnd) return false;
      }
      if (!keyword) return true;
      return [
        entry.raw,
        entry.message,
        entry.level,
        String(entry.lineNumber),
        entry.timestamp,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [customLogEnd, customLogStart, logEntries, logKeyword, logTimeRange]);
  const approximateTimestampCount = filteredEntries.filter((entry) => entry.timestampSource === "source-modified").length;

  return (
    <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3">
          <h3 className="text-sm font-semibold text-slate-900">日志源</h3>
          <p className="mt-1 text-xs text-slate-500">直接读取本地运行日志尾部，刷新页面即可更新。</p>
        </div>
        <div className="divide-y divide-slate-100">
          {data.logSources.map((source) => (
            <button
              key={source.id}
              type="button"
              onClick={() => onSelectLog(source.id)}
              className={cn("w-full px-4 py-3 text-left transition-colors hover:bg-slate-50", activeLog?.id === source.id && "bg-blue-50/70")}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-slate-900">{source.label}</span>
                <OpsStatusBadge status={source.exists ? "ok" : "warning"} />
              </div>
              <p className="mt-1 truncate font-mono text-xs text-slate-500">{source.path}</p>
              <p className="mt-1 text-xs text-slate-400">
                {source.exists ? `${formatBytes(source.sizeBytes)} · ${formatDate(source.modifiedAt)}` : source.error ?? "未生成"}
              </p>
            </button>
          ))}
        </div>
      </section>

      <section className="min-w-0 rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-slate-900">{activeLog?.label ?? "暂无日志"}</h3>
            <p className="mt-1 truncate font-mono text-xs text-slate-500">{activeLog?.path ?? "-"}</p>
          </div>
          {activeLog && (
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>{activeLog.lineCount} 行</span>
              <span>{formatBytes(activeLog.sizeBytes)}</span>
              <OpsStatusBadge status={activeLog.exists ? "ok" : "warning"} />
            </div>
          )}
        </div>
        <div className="space-y-3 border-b border-slate-100 px-4 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={logKeyword}
                onChange={(event) => setLogKeyword(event.target.value)}
                placeholder="搜索日志内容、级别、行号..."
                className="h-9 border-slate-200 bg-white pl-9"
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {LOG_TIME_RANGES.map((range) => (
                <button
                  key={range.id}
                  type="button"
                  onClick={() => setLogTimeRange(range.id)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                    logTimeRange === range.id
                      ? "border-blue-200 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  )}
                >
                  <Clock3 className="h-3 w-3" />
                  {range.label}
                </button>
              ))}
            </div>
          </div>
          {logTimeRange === "custom" && (
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="text-xs text-slate-500">
                起始时间
                <Input
                  type="datetime-local"
                  value={customLogStart}
                  onChange={(event) => setCustomLogStart(event.target.value)}
                  className="mt-1 h-9 border-slate-200 bg-white"
                />
              </label>
              <label className="text-xs text-slate-500">
                结束时间
                <Input
                  type="datetime-local"
                  value={customLogEnd}
                  onChange={(event) => setCustomLogEnd(event.target.value)}
                  className="mt-1 h-9 border-slate-200 bg-white"
                />
              </label>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>匹配 {filteredEntries.length}/{logEntries.length} 行</span>
            {approximateTimestampCount > 0 && logTimeRange !== "all" && (
              <span className="rounded-md border border-amber-100 bg-amber-50 px-2 py-1 text-amber-700">
                {approximateTimestampCount} 行按日志文件更新时间近似筛选
              </span>
            )}
          </div>
        </div>
        {activeLog?.exists && logEntries.length ? (
          filteredEntries.length ? (
            <div className="max-h-[68vh] overflow-auto bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100">
              <div className="min-w-[720px] space-y-0.5">
                {filteredEntries.map((entry) => (
                  <div key={entry.id} className="grid grid-cols-[42px_72px_52px_minmax(0,1fr)] gap-2 rounded px-2 py-0.5 hover:bg-white/5">
                    <span className="text-right text-slate-500">{entry.lineNumber}</span>
                    <span className={cn("whitespace-nowrap", entry.timestampSource === "line" ? "text-slate-300" : "text-slate-500")}>
                      {formatLogTimestamp(entry.timestamp)}
                    </span>
                    <span className={cn("whitespace-nowrap", logLevelClass(entry.level))}>{entry.level ?? "-"}</span>
                    <span className="whitespace-pre-wrap break-words text-slate-100">{entry.raw}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState
              title="没有匹配的日志"
              description="调整关键词或时间范围后再试。"
              className="border-0 py-16"
            />
          )
        ) : (
          <EmptyState
            title="暂无可读日志"
            description={activeLog?.error ?? "启动前端、后端或评测任务后这里会展示最新日志。"}
            className="border-0 py-16"
          />
        )}
      </section>
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
export default function WorkspacesHealthClient({ initialData, initialTraceData, initialOpsData, initialView = "health" }: Props) {
  const [view, setView] = useState<OpsView>(initialView);
  const [healthData, setHealthData] = useState(initialData);
  const [traceData, setTraceData] = useState(initialTraceData);
  const [opsData, setOpsData] = useState(initialOpsData);
  const [activeLogId, setActiveLogId] = useState<string | null>(initialOpsData.logSources.find((source) => source.exists)?.id ?? initialOpsData.logSources[0]?.id ?? null);
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
      const [hr, tr, or] = await Promise.all([
        fetch(`${API_BASE}/api/workspaces/health`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/workspaces/trace`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/ops/platform`, { cache: "no-store" }),
      ]);
      const [hp, tp, op] = await Promise.all([hr.json(), tr.json(), or.json()]);
      if (!hr.ok || !hp.success) throw new Error(hp.error ?? "刷新健康状态失败");
      if (!tr.ok || !tp.success) throw new Error(tp.error ?? "刷新链路数据失败");
      if (!or.ok || !op.success) throw new Error(op.error ?? "刷新运维状态失败");
      setHealthData(hp.data);
      setTraceData(tp.data);
      setOpsData(op.data);
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
        badge={<Badge variant="outline" className="bg-white text-slate-500">运维评分 {opsData.summary.score}</Badge>}
        subtitle={`${healthData.projectsDir} · 生成于 ${formatDate(view === "trace" ? traceData.generatedAt : view === "health" ? healthData.generatedAt : opsData.generatedAt)}`}
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

        {view === "system" && <SystemView data={opsData} />}

        {view === "logs" && (
          <LogsView
            data={opsData}
            activeLogId={activeLogId}
            onSelectLog={setActiveLogId}
          />
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
                      <EmptyState title="当前阶段没有事件" description="选择阶段标签筛选时间线" className="border-0 py-8" />
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
