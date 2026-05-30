"use client";

import { Fragment, type FormEvent, type PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  CheckCircle2,
  CircleStop,
  GitBranch,
  Loader2,
  Pause,
  Play,
  RefreshCcw,
  Search,
  ShieldCheck,
  SkipForward,
  SquareStack,
  TrendingUp,
  ArrowRight,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ListPlus,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import * as Dialog from "@radix-ui/react-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/PageHeader";
import { SubNav, type SubNavItem } from "@/components/layout/SubNav";
import { formatCompactDate as formatDate } from "@/components/quant/console-primitives";
import { cn } from "@/lib/utils";
import type {
  StrategyAutoFillIngestionStartResult,
  StrategyCatalogItem,
  StrategyDashboardData,
  StrategyDividendEvent,
  StrategyHistoryIngestionResult,
  StrategyIngestionJob,
  StrategyLocalKlineBar,
  StrategyLocalKlineResponse,
  StrategySectorCapitalFlowItem,
  StrategyUniverse,
  StrategyUniverseMember,
  StrategyUniverseMembersPage,
} from "@/lib/quant/strategies";

type Props = { initialData: StrategyDashboardData };
type StrategyView =
  | "universe"
  | "catalog"
  | "sectorFlow"
  | "knowledge"
  | "scans"
  | "compare";
type IngestionRangeMode = "incremental" | "lookback" | "custom";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const INGESTION_BATCH_SIZE = 25;
const INGESTION_LOG_LIMIT = 20;

// ─── Status helpers ────────────────────────────────────────────
function statusLabel(s: StrategyCatalogItem["status"]) {
  return s === "ready" ? "可执行" : s === "research" ? "需补数据" : "规划中";
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
function riskClass(level: StrategyCatalogItem["readiness"]["riskLevel"]) {
  if (level === "low") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (level === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
}
function strategyKindLabel(kind?: StrategyCatalogItem["kind"]) {
  if (kind === "stock_selection") return "选股";
  if (kind === "trade_price") return "买卖价格";
  return "策略";
}
function strategyKindClass(kind?: StrategyCatalogItem["kind"]) {
  if (kind === "stock_selection") return "border-blue-200 bg-blue-50 text-blue-700";
  if (kind === "trade_price") return "border-violet-200 bg-violet-50 text-violet-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}
function ruleStatusClass(status?: "ready" | "needs_data" | "manual") {
  if (status === "needs_data") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "manual") return "border-slate-200 bg-slate-50 text-slate-600";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}
function ruleStatusLabel(status?: "ready" | "needs_data" | "manual") {
  if (status === "needs_data") return "缺数据";
  if (status === "manual") return "人工确认";
  return "已具备";
}
function previewRules(strategy: StrategyCatalogItem) {
  const rules = strategy.kind === "trade_price"
    ? [...(strategy.entryRules ?? []), ...(strategy.exitRules ?? [])]
    : strategy.selectionRules ?? [];
  return rules.slice(0, 3);
}
function dataStatusText(strategy: StrategyCatalogItem) {
  const missing = strategy.dataReadiness?.missing.length ?? 0;
  if (missing > 0) return `缺 ${missing} 项`;
  return "数据可用";
}
function formatMetric(value?: number | null, suffix = "") {
  if (value === null || value === undefined) return "-";
  return `${Number(value).toFixed(2)}${suffix}`;
}

function formatDataDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const partMap = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${partMap.year}-${partMap.month}-${partMap.day}`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const partMap = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${partMap.year}-${partMap.month}-${partMap.day} ${partMap.hour}:${partMap.minute}:${partMap.second}`;
}

function todayInputValue() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function addDaysInputValue(value: string, days: number) {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00+08:00`);
  if (Number.isNaN(date.getTime())) return "";
  date.setDate(date.getDate() + days);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatDuration(seconds?: number | null) {
  const total = finiteNumber(seconds);
  if (total === null || total < 0) return "-";
  const rounded = Math.round(total);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hours > 0) return `${hours}时${minutes}分`;
  if (minutes > 0) return `${minutes}分${secs}秒`;
  return `${secs}秒`;
}

function timestampMs(value?: string | null) {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function finiteNumber(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatNumberValue(value?: number | null, digits = 2) {
  const number = finiteNumber(value);
  if (number === null) return "-";
  return number.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatLargeValue(value?: number | null, digits = 2) {
  const number = finiteNumber(value);
  if (number === null) return "-";
  const abs = Math.abs(number);
  if (abs >= 100000000) return `${formatNumberValue(number / 100000000, digits)} 亿`;
  if (abs >= 10000) return `${formatNumberValue(number / 10000, digits)} 万`;
  return formatNumberValue(number, digits);
}

function formatSignedPercent(value?: number | null) {
  const number = finiteNumber(value);
  if (number === null) return "-";
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function formatPercentValue(value?: number | null) {
  const number = finiteNumber(value);
  if (number === null) return "-";
  return `${number.toFixed(2)}%`;
}

function signedToneClass(value?: number | null) {
  const number = finiteNumber(value);
  if (number === null) return "text-slate-900";
  return number >= 0 ? "text-red-600" : "text-emerald-600";
}

function trendLabel(status: StrategyUniverseMember["trendStatus"]) {
  if (status === "bullish") return "多头";
  if (status === "bearish") return "空头";
  if (status === "sideways") return "震荡";
  return "不足";
}

function trendClass(status: StrategyUniverseMember["trendStatus"]) {
  if (status === "bullish") return "border-red-200 bg-red-50 text-red-700";
  if (status === "bearish") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "sideways") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

function liquidityLabel(member: StrategyUniverseMember) {
  if (finiteNumber(member.avgAmount20d) !== null) return formatLargeValue(member.avgAmount20d, 1);
  if (finiteNumber(member.avgVolume20d) !== null) return formatLargeValue(member.avgVolume20d, 1);
  return "-";
}

function liquiditySubLabel(member: StrategyUniverseMember) {
  if (finiteNumber(member.avgAmount20d) !== null && finiteNumber(member.avgTurnover20d) !== null) {
    return `20日均额 · 换手 ${formatPercentValue(member.avgTurnover20d)}`;
  }
  if (finiteNumber(member.avgAmount20d) !== null) return "20日均额";
  if (finiteNumber(member.avgTurnover20d) !== null) return `20日换手 ${formatPercentValue(member.avgTurnover20d)}`;
  if (finiteNumber(member.avgVolume20d) !== null) return "20日均量";
  return "暂无";
}

function valuationSummary(member: StrategyUniverseMember) {
  const pe = finiteNumber(member.peTtm);
  const pb = finiteNumber(member.pbMrq);
  if (pe === null && pb === null) return "-";
  return [
    pe !== null ? `PE ${formatNumberValue(pe, 1)}` : null,
    pb !== null ? `PB ${formatNumberValue(pb, 1)}` : null,
  ].filter(Boolean).join(" / ");
}

function tradeStatusLabel(member: StrategyUniverseMember) {
  if (member.limitUp) return "涨停";
  if (member.limitDown) return "跌停";
  if (member.tradeStatus && member.tradeStatus !== "1") return "停牌";
  if (member.isSt) return "ST";
  return "正常";
}

function tradeStatusClass(member: StrategyUniverseMember) {
  if (member.limitUp) return "border-red-200 bg-red-50 text-red-700";
  if (member.limitDown) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (member.tradeStatus && member.tradeStatus !== "1") return "border-amber-200 bg-amber-50 text-amber-700";
  if (member.isSt) return "border-orange-200 bg-orange-50 text-orange-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

function isEtfUniverse(universe?: StrategyUniverse | null) {
  if (!universe) return false;
  return universe.id === "etf-index-pool" || universe.etfCount + universe.indexCount > universe.stockCount;
}

function jobStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "partial") return "部分完成";
  if (status === "failed") return "失败";
  if (status === "running") return "运行中";
  if (status === "queued") return "排队中";
  return status || "-";
}

function jobStatusClass(status: string) {
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "partial") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "failed") return "border-red-200 bg-red-50 text-red-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function ingestionControlLabel(control?: string | null) {
  if (control === "pause") return "暂停中";
  if (control === "stop") return "停止中";
  if (control === "resume" || control === "run") return "运行";
  if (control === "idle") return "空闲";
  return "-";
}

function ingestionRangeLabel(job?: StrategyIngestionJob | null) {
  if (!job) return "-";
  const start = stringFromUnknown(job.metadata.effective_start) ?? stringFromUnknown(job.metadata.start);
  const end = stringFromUnknown(job.metadata.end);
  if (!start && (!end || end === "20500101")) return "近 5 年";
  return `${start ?? "默认"} 至 ${end && end !== "20500101" ? end : "最新交易日"}`;
}

function findLatestUniverseBatchJob(jobs: StrategyIngestionJob[]) {
  return jobs.find((job) => job.provider !== "baostock-autofill" && (job.universeTotalSymbols ?? 0) > 1) ?? null;
}

function findLatestAutoFillJob(jobs: StrategyIngestionJob[]) {
  return jobs.find((job) => job.provider === "baostock-autofill") ?? null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type IngestionSymbolLog = {
  symbol: string;
  name?: string | null;
  status?: string | null;
  barsReceived?: number | null;
  rowsUpserted?: number | null;
  firstDate?: string | null;
  lastDate?: string | null;
  error?: string | null;
  skipReason?: string | null;
  coverageRowCount?: number | null;
  coverageFirstDate?: string | null;
  coverageLastDate?: string | null;
  missingFields?: string[];
};

function numberFromUnknown(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringFromUnknown(value: unknown) {
  return typeof value === "string" && value ? value : null;
}

function ingestionProgress(job: StrategyIngestionJob | null | undefined) {
  if (!job) {
    return {
      completedBatches: 0,
      totalBatches: 0,
      completedSymbols: 0,
      totalSymbols: 0,
      percent: 0,
      elapsedSeconds: null as number | null,
      etaSeconds: null as number | null,
      currentSymbol: null as string | null,
      lastHeartbeatAt: null as string | null,
      control: null as string | null,
      preflightSkippedSymbols: 0,
    };
  }
  const completedBatches = numberFromUnknown(job.metadata.completed_batches) ?? 0;
  const totalBatches =
    numberFromUnknown(job.metadata.total_batches) ??
    numberFromUnknown(job.metadata.max_batches) ??
    Math.max(1, Math.ceil((job.universeTotalSymbols ?? job.totalSymbols) / Math.max(job.batchSize ?? 25, 1)));
  const completedSymbols = job.completedSymbols;
  const totalSymbols = job.universeTotalSymbols ?? job.totalSymbols;
  const percent = totalSymbols > 0 ? Math.min(100, Math.max(0, (completedSymbols / totalSymbols) * 100)) : 0;
  const startedAt = timestampMs(job.startedAt ?? job.createdAt);
  const endedAt = job.status === "running" ? Date.now() : timestampMs(job.completedAt ?? job.updatedAt);
  const elapsedSeconds = startedAt && endedAt ? Math.max(0, (endedAt - startedAt) / 1000) : null;
  const etaSeconds =
    elapsedSeconds !== null && completedSymbols > 0 && totalSymbols > completedSymbols
      ? (elapsedSeconds / completedSymbols) * (totalSymbols - completedSymbols)
      : null;
  return {
    completedBatches,
    totalBatches,
    completedSymbols,
    totalSymbols,
    percent,
    elapsedSeconds,
    etaSeconds,
    currentSymbol: stringFromUnknown(job.metadata.current_symbol),
    lastHeartbeatAt: stringFromUnknown(job.metadata.last_heartbeat_at) ?? job.updatedAt,
    control: stringFromUnknown(job.metadata.control),
    preflightSkippedSymbols: numberFromUnknown(job.metadata.preflight_skipped_symbols) ?? 0,
  };
}

function getIngestionSymbolLogs(job: StrategyIngestionJob): IngestionSymbolLog[] {
  const rawResults = job.metadata.symbol_results;
  const rawSymbols = Array.isArray(rawResults) && rawResults.length ? rawResults : job.metadata.symbols;
  if (!Array.isArray(rawSymbols)) return [];

  return rawSymbols
    .map((item): IngestionSymbolLog | null => {
      if (typeof item === "string") return { symbol: item };
      if (!isRecord(item)) return null;
      const symbol = stringFromUnknown(item.symbol) ?? stringFromUnknown(item.query);
      if (!symbol) return null;
      return {
        symbol,
        name: stringFromUnknown(item.name),
        status: stringFromUnknown(item.status),
        barsReceived: numberFromUnknown(item.bars_received),
        rowsUpserted: numberFromUnknown(item.rows_upserted),
        firstDate: stringFromUnknown(item.first_date),
        lastDate: stringFromUnknown(item.last_date),
        error: stringFromUnknown(item.error),
        skipReason: stringFromUnknown(item.skip_reason),
        coverageRowCount: numberFromUnknown(item.coverage_row_count),
        coverageFirstDate: stringFromUnknown(item.coverage_first_date),
        coverageLastDate: stringFromUnknown(item.coverage_last_date),
        missingFields: Array.isArray(item.missing_fields)
          ? item.missing_fields.map((value) => String(value)).filter(Boolean)
          : [],
      };
    })
    .filter((item): item is IngestionSymbolLog => Boolean(item));
}

function ingestionBatchRangeLabel(job: StrategyIngestionJob) {
  if (job.provider === "baostock-autofill") {
    const progress = ingestionProgress(job);
    return `${progress.completedBatches}/${progress.totalBatches} 批`;
  }
  const offset = job.batchOffset;
  if (offset === null || offset === undefined) return "单次任务";
  const size = job.batchSize ?? job.totalSymbols;
  const total = job.universeTotalSymbols;
  const start = offset + 1;
  const end = offset + Math.max(size, job.totalSymbols, 0);
  if (total !== null && total !== undefined) return `${start}-${Math.min(end, total)} / ${total}`;
  return `${start}-${end}`;
}

function ingestionSymbolPreview(job: StrategyIngestionJob) {
  const symbols = getIngestionSymbolLogs(job);
  if (!symbols.length) return "-";
  const skipped = symbols.filter((item) => item.skipReason === "local_coverage_ready").length;
  const preview = symbols.slice(0, 6).map((item) =>
    item.name ? `${item.symbol} ${item.name}` : item.symbol
  );
  const suffix = symbols.length > preview.length ? ` 等 ${symbols.length} 个` : "";
  const skipText = skipped ? `；本地跳过 ${skipped} 个` : "";
  return `${preview.join("、")}${suffix}${skipText}`;
}

function ingestionErrorPreview(job: StrategyIngestionJob) {
  if (job.error) return job.error;
  const failed = getIngestionSymbolLogs(job).filter((item) => item.error);
  if (!failed.length) return null;
  return failed
    .slice(0, 3)
    .map((item) => `${item.symbol}: ${item.error}`)
    .join("；");
}

// ─── Sub-nav items ─────────────────────────────────────────────
const SUB_NAV_ITEMS: SubNavItem[] = [
  { id: "universe", label: "股票池", icon: <SquareStack className="h-4 w-4" /> },
  { id: "catalog", label: "策略目录", icon: <TrendingUp className="h-4 w-4" /> },
  { id: "sectorFlow", label: "板块资金", icon: <BarChart3 className="h-4 w-4" /> },
  { id: "knowledge", label: "金融知识", icon: <BookOpen className="h-4 w-4" /> },
];

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

// ─── Strategy Row (Table List) ──────────────────────────────────
function StrategyRow({ strategy, onClick }: { strategy: StrategyCatalogItem; onClick: () => void }) {
  const paramPreview = strategy.parameterSchema
    .slice(0, 3)
    .map((p) => `${p.label}=${p.value}${p.unit ?? ""}`)
    .join("  ");
  const rules = previewRules(strategy);
  const missingCount = strategy.dataReadiness?.missing.length ?? 0;

  return (
    <tr
      onClick={onClick}
      className="group cursor-pointer bg-white shadow-sm transition-colors hover:bg-blue-50/40"
    >
      <td className="w-1 rounded-l-lg border-y border-l border-slate-100 py-3.5 pl-4 pr-0">
        <div
          className={cn(
            "h-9 w-1 rounded-full",
            strategy.status === "ready"
              ? "bg-emerald-400"
              : strategy.status === "research"
                ? "bg-blue-400"
                : "bg-amber-400"
          )}
        />
      </td>
      <td className="border-y border-slate-100 px-4 py-3.5 min-w-[240px]">
        <div className="flex items-center gap-2">
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-semibold", strategyKindClass(strategy.kind))}>
            {strategyKindLabel(strategy.kind)}
          </span>
          <p className="text-sm font-semibold text-slate-900 transition-colors group-hover:text-blue-700">
            {strategy.name}
          </p>
        </div>
        <p className="mt-1 text-[11px] text-slate-400">{strategy.family} · {strategy.timeframe}</p>
      </td>
      <td className="min-w-[360px] border-y border-slate-100 px-3 py-3.5">
        <div className="flex flex-wrap gap-1.5">
          {rules.map((rule) => (
            <span key={rule.label} className={cn("rounded-md border px-2 py-1 text-[11px] font-medium", ruleStatusClass(rule.dataStatus))}>
              {rule.label}
            </span>
          ))}
        </div>
        <p className="mt-1 line-clamp-1 text-xs text-slate-500">{strategy.description}</p>
      </td>
      <td className="border-y border-slate-100 px-3 py-3.5">
        <span
          className={cn(
            "inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium",
            missingCount > 0 ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
          )}
        >
          {dataStatusText(strategy)}
        </span>
        <p className="mt-1 text-[11px] text-slate-400">{strategy.readiness.label}</p>
      </td>
      <td className="hidden border-y border-slate-100 px-3 py-3.5 lg:table-cell">
        <span className="block max-w-[280px] truncate font-mono text-xs text-slate-500">
          {paramPreview || "-"}
        </span>
        {strategy.rankingRules?.length ? (
          <span className="mt-1 block truncate text-[11px] text-slate-400">{strategy.rankingRules[0]}</span>
        ) : null}
      </td>
      <td className="rounded-r-lg border-y border-r border-slate-100 px-4 py-3.5">
        <ChevronDown className="h-4 w-4 -rotate-90 text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-blue-400" />
      </td>
    </tr>
  );
}

const UNIVERSE_PAGE_SIZE = 10;
const DETAIL_ANIMATION_MS = 260;
const KLINE_TIMEFRAMES = [
  { id: "daily", label: "日线" },
  { id: "weekly", label: "周线" },
  { id: "monthly", label: "月线" },
] as const;
type KlineTimeframe = (typeof KLINE_TIMEFRAMES)[number]["id"];
const MOVING_AVERAGE_CONFIGS = [
  { period: 5, label: "MA5", color: "#2563eb", textClass: "text-blue-600" },
  { period: 10, label: "MA10", color: "#16a34a", textClass: "text-emerald-600" },
  { period: 20, label: "MA20", color: "#d97706", textClass: "text-amber-600" },
  { period: 30, label: "MA30", color: "#db2777", textClass: "text-pink-600" },
  { period: 60, label: "MA60", color: "#7c3aed", textClass: "text-violet-600" },
] as const;

function buildUniverseMembersPage(
  universe: StrategyUniverse | null,
  page = 1,
  keyword = ""
): StrategyUniverseMembersPage {
  const total = universe?.memberCount ?? universe?.members.length ?? 0;
  return {
    universeId: universe?.id ?? "",
    page,
    pageSize: UNIVERSE_PAGE_SIZE,
    total,
    totalPages: Math.max(1, Math.ceil(total / UNIVERSE_PAGE_SIZE)),
    keyword: keyword || null,
    members: universe?.members ?? [],
    fetchedAt: new Date().toISOString(),
  };
}

function UniverseView({
  data,
  isAdding,
  onAdd,
}: {
  data: StrategyDashboardData;
  isAdding: boolean;
  onAdd: (universeId: string, query: string) => Promise<void>;
}) {
  const initialUniverse =
    data.research.universes.find((universe) => universe.id === data.research.primaryUniverseId) ??
    data.research.universes[0] ??
    null;
  const [memberQuery, setMemberQuery] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedMemberSymbol, setSelectedMemberSymbol] = useState<string | null>(null);
  const [selectedUniverseId, setSelectedUniverseId] = useState(
    initialUniverse?.id ?? data.research.primaryUniverseId
  );
  const [membersPage, setMembersPage] = useState<StrategyUniverseMembersPage>(() =>
    buildUniverseMembersPage(initialUniverse)
  );
  const [memberReloadToken, setMemberReloadToken] = useState(0);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<StrategyIngestionJob[]>([]);
  const [isLoadingJobs, setIsLoadingJobs] = useState(false);
  const [isRunningBatch, setIsRunningBatch] = useState(false);
  const [isAutoFilling, setIsAutoFilling] = useState(false);
  const [isControllingIngestion, setIsControllingIngestion] = useState(false);
  const [autoFillMessage, setAutoFillMessage] = useState<string | null>(null);
  const [isIngestionDialogOpen, setIsIngestionDialogOpen] = useState(false);
  const [ingestionRangeMode, setIngestionRangeMode] = useState<IngestionRangeMode>("incremental");
  const [ingestionStartDate, setIngestionStartDate] = useState("");
  const [ingestionEndDate, setIngestionEndDate] = useState(() => todayInputValue());
  const [batchOffset, setBatchOffset] = useState(0);
  const [openingMemberSymbol, setOpeningMemberSymbol] = useState<string | null>(null);
  const [closingMemberSymbol, setClosingMemberSymbol] = useState<string | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openFrameRef = useRef<number | null>(null);
  const autoFillPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedUniverse =
    data.research.universes.find((universe) => universe.id === selectedUniverseId) ??
    data.research.universes.find((universe) => universe.id === data.research.primaryUniverseId) ??
    data.research.universes[0] ??
    null;
  const selectedIsEtfUniverse = isEtfUniverse(selectedUniverse);
  const selectedUniverseNoun = selectedIsEtfUniverse ? "ETF/指数" : "股票";

  useEffect(() => {
    if (data.research.universes.some((universe) => universe.id === selectedUniverseId)) return;
    setSelectedUniverseId(data.research.primaryUniverseId);
  }, [data.research.primaryUniverseId, data.research.universes, selectedUniverseId]);

  useEffect(() => {
    setMembersPage(buildUniverseMembersPage(selectedUniverse));
  }, [data.generatedAt, selectedUniverse]);

  const loadIngestionJobs = useCallback(async (): Promise<StrategyIngestionJob[]> => {
    if (!selectedUniverse) return [];
    setIsLoadingJobs(true);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "ingestion-jobs",
          universeId: selectedUniverse.id,
          limit: INGESTION_LOG_LIMIT,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? "读取补数任务失败");
      }
      const jobs = (payload.data?.jobs ?? []) as StrategyIngestionJob[];
      setIngestionJobs(jobs);
      const latestJob = findLatestUniverseBatchJob(jobs);
      if (latestJob?.nextOffset !== undefined && latestJob.nextOffset !== null) {
        setBatchOffset(latestJob.nextOffset);
      }
      return jobs;
    } catch {
      setIngestionJobs([]);
      return [];
    } finally {
      setIsLoadingJobs(false);
    }
  }, [selectedUniverse]);

  useEffect(() => {
    void loadIngestionJobs();
  }, [loadIngestionJobs]);

  useEffect(() => {
    if (!selectedUniverse) return;
    const controller = new AbortController();
    const keyword = memberSearch.trim();
    const requestedPage = page;
    setIsLoadingMembers(true);
    setMemberError(null);
    void fetch(`${API_BASE}/api/quant/strategies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "universe-members",
        universeId: selectedUniverse.id,
        page: requestedPage,
        pageSize: UNIVERSE_PAGE_SIZE,
        keyword,
      }),
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.success) {
          throw new Error(payload.error ?? "读取股票池分页失败");
        }
        const nextPage = payload.data as StrategyUniverseMembersPage;
        setMembersPage(nextPage);
        if (nextPage.page !== requestedPage) setPage(nextPage.page);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMemberError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingMembers(false);
      });
    return () => controller.abort();
  }, [memberReloadToken, memberSearch, page, selectedUniverse]);

  const members = membersPage.universeId === selectedUniverse?.id ? membersPage.members : [];
  const hasMemberSearch = Boolean(memberSearch.trim());
  const selectedUniverseTotal = selectedUniverse?.memberCount ?? membersPage.total;
  const memberTotal = membersPage.total;
  const totalPages = Math.max(1, membersPage.totalPages);
  const currentPage = Math.min(page, totalPages);
  const pagedMembers = members;
  const latestUniverseBatchJob = findLatestUniverseBatchJob(ingestionJobs);
  const latestAutoFillJob = findLatestAutoFillJob(ingestionJobs);
  const hasRunningBatchJob = latestUniverseBatchJob?.status === "running";
  const hasRunningAutoFillJob = latestAutoFillJob?.status === "running";
  const recentRowsUpserted = ingestionJobs.reduce((sum, job) => sum + job.rowsUpserted, 0);
  const activeJob = latestAutoFillJob ?? latestUniverseBatchJob;
  const activeProgress = ingestionProgress(activeJob);
  const activeControl = activeProgress.control;
  const isIngestionBusy = isRunningBatch || isAutoFilling || hasRunningBatchJob || hasRunningAutoFillJob;
  const latestDataDate = selectedUniverse?.latestTs?.slice(0, 10) ?? members.find((member) => member.lastTs)?.lastTs?.slice(0, 10) ?? "";
  const incrementalStartDate = latestDataDate ? addDaysInputValue(latestDataDate, 1) : "";
  const canRunIncrementalIngestion = ingestionRangeMode !== "incremental" || !incrementalStartDate || !ingestionEndDate || incrementalStartDate <= ingestionEndDate;
  const selectedIngestionStart = ingestionRangeMode === "custom"
    ? ingestionStartDate
    : ingestionRangeMode === "incremental"
      ? incrementalStartDate
      : "";
  const selectedIngestionEnd = ingestionRangeMode === "custom" || ingestionRangeMode === "incremental"
    ? ingestionEndDate
    : "";
  const effectiveIngestionEndLabel = selectedIngestionEnd || "最新交易日";
  const selectedRangeLabel = ingestionRangeMode === "lookback"
    ? "近 5 年"
    : `${selectedIngestionStart || "默认起点"} 至 ${effectiveIngestionEndLabel}`;
  const activeRangeLabel = ingestionRangeLabel(activeJob);

  const addMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedUniverse || !memberQuery.trim()) return;
    await onAdd(selectedUniverse.id, memberQuery.trim());
    setMemberQuery("");
    setMemberSearch("");
    setPage(1);
    setMemberReloadToken((value) => value + 1);
  };

  const ingestionRequestRange = useCallback(() => {
    const start = selectedIngestionStart.trim();
    const end = selectedIngestionEnd.trim();
    return {
      start: start || undefined,
      end: end || undefined,
    };
  }, [selectedIngestionEnd, selectedIngestionStart]);

  const runIngestionBatchAt = useCallback(async (offset: number) => {
    if (!selectedUniverse) throw new Error("未选择补数池");
    const range = ingestionRequestRange();
    const response = await fetch(`${API_BASE}/api/quant/strategies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "run-ingestion-batch",
        universeId: selectedUniverse.id,
        offset,
        batchSize: INGESTION_BATCH_SIZE,
        limit: 1260,
        lookbackYears: 5,
        start: range.start,
        end: range.end,
        period: selectedUniverse.defaultTimeframe || "daily",
        adjustment: selectedUniverse.defaultAdjustment || "qfq",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.success) {
      throw new Error(payload.error ?? "运行补数批次失败");
    }
    const result = payload.data as StrategyHistoryIngestionResult;
    setBatchOffset(result.next_offset ?? 0);
    await loadIngestionJobs();
    setMemberReloadToken((value) => value + 1);
    return result;
  }, [ingestionRequestRange, loadIngestionJobs, selectedUniverse]);

  const runIngestionBatch = async () => {
    if (!selectedUniverse || isRunningBatch || isAutoFilling) return;
    if (!canRunIncrementalIngestion) {
      setMemberError("当前数据已覆盖到所选结束日期，无需增量补数。");
      return;
    }
    if (hasRunningBatchJob || hasRunningAutoFillJob) {
      setMemberError("已有补数任务正在运行，完成后再补下一批。");
      return;
    }
    setIsRunningBatch(true);
    setMemberError(null);
    try {
      await runIngestionBatchAt(batchOffset);
    } catch (error) {
      setMemberError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRunningBatch(false);
    }
  };

  const stopAutoFillPolling = () => {
    if (autoFillPollRef.current) {
      clearInterval(autoFillPollRef.current);
      autoFillPollRef.current = null;
    }
  };

  const runIngestionAutoFill = async () => {
    if (!selectedUniverse || isAutoFilling || isRunningBatch) return;
    if (!canRunIncrementalIngestion) {
      setMemberError("当前数据已覆盖到所选结束日期，无需增量补数。");
      return;
    }
    const range = ingestionRequestRange();
    setIsAutoFilling(true);
    setMemberError(null);
    setAutoFillMessage("正在提交后端自动补齐任务...");
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "start-ingestion-autofill",
          universeId: selectedUniverse.id,
          offset: batchOffset,
          batchSize: INGESTION_BATCH_SIZE,
          limit: 1260,
          lookbackYears: 5,
          start: range.start,
          end: range.end,
          period: selectedUniverse.defaultTimeframe || "daily",
          adjustment: selectedUniverse.defaultAdjustment || "qfq",
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? "启动后端自动补齐失败");
      }
      const result = payload.data as StrategyAutoFillIngestionStartResult;
      setBatchOffset(result.next_offset ?? batchOffset);
      setAutoFillMessage(`后端自动补齐已启动 · ${result.job_id}`);
      await loadIngestionJobs();
    } catch (error) {
      setMemberError(error instanceof Error ? error.message : String(error));
      setAutoFillMessage(null);
    }
  };

  const controlIngestion = async (control: "pause" | "resume" | "stop") => {
    const job = latestAutoFillJob;
    if (!job || job.status !== "running" || isControllingIngestion) return;
    setIsControllingIngestion(true);
    setMemberError(null);
    const label = control === "pause" ? "暂停" : control === "resume" ? "继续" : "停止";
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "control-ingestion-job",
          jobId: job.id,
          control,
          reason: `${label}策略平台自动补数`,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? `${label}补数任务失败`);
      }
      setAutoFillMessage(
        control === "pause"
          ? "已请求暂停，当前标的处理完后会挂起。"
          : control === "resume"
            ? "已请求继续，后端将从当前 offset 恢复。"
            : "已请求停止，当前标的处理完后会安全收尾。"
      );
      await loadIngestionJobs();
    } catch (error) {
      setMemberError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsControllingIngestion(false);
    }
  };

  useEffect(() => {
    const running = hasRunningAutoFillJob || (isAutoFilling && autoFillMessage);
    if (!running) {
      stopAutoFillPolling();
      if (latestAutoFillJob && isAutoFilling) {
        setIsAutoFilling(false);
      }
      return;
    }
    stopAutoFillPolling();
    void loadIngestionJobs();
    autoFillPollRef.current = setInterval(() => {
      void loadIngestionJobs().then((jobs) => {
        const autoFillJob = findLatestAutoFillJob(jobs);
        if (!autoFillJob) return;
        const completedBatches = numberFromUnknown(autoFillJob.metadata.completed_batches) ?? 0;
        const maxBatches = numberFromUnknown(autoFillJob.metadata.max_batches);
        const nextOffset = autoFillJob.nextOffset ?? batchOffset;
        setAutoFillMessage(
          autoFillJob.status === "running"
            ? `后端自动补齐中 · ${completedBatches}${maxBatches ? `/${maxBatches}` : ""} 批 · 下批 ${nextOffset}`
            : `后端自动补齐${jobStatusLabel(autoFillJob.status)} · 下批 ${nextOffset}`
        );
        if (autoFillJob.status !== "running") {
          setIsAutoFilling(false);
          setMemberReloadToken((value) => value + 1);
          stopAutoFillPolling();
        }
      });
    }, 2000);
    return stopAutoFillPolling;
  }, [autoFillMessage, batchOffset, hasRunningAutoFillJob, isAutoFilling, latestAutoFillJob, loadIngestionJobs]);

  const clearCloseTimer = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const clearOpenFrame = () => {
    if (openFrameRef.current !== null) {
      cancelAnimationFrame(openFrameRef.current);
      openFrameRef.current = null;
    }
  };

  const finishOpeningOnNextFrame = (symbol: string) => {
    openFrameRef.current = requestAnimationFrame(() => {
      openFrameRef.current = requestAnimationFrame(() => {
        setOpeningMemberSymbol((current) => (current === symbol ? null : current));
        openFrameRef.current = null;
      });
    });
  };

  const scheduleCloseRemoval = (symbol: string) => {
    setClosingMemberSymbol(symbol);
    closeTimerRef.current = setTimeout(() => {
      setClosingMemberSymbol((current) => (current === symbol ? null : current));
      closeTimerRef.current = null;
    }, DETAIL_ANIMATION_MS);
  };

  const closeMemberDetail = (symbol: string) => {
    clearCloseTimer();
    clearOpenFrame();
    setOpeningMemberSymbol(null);
    setSelectedMemberSymbol(null);
    scheduleCloseRemoval(symbol);
  };

  const toggleMemberDetail = (symbol: string) => {
    if (selectedMemberSymbol === symbol) {
      closeMemberDetail(symbol);
      return;
    }
    const previousSymbol = selectedMemberSymbol;
    clearCloseTimer();
    clearOpenFrame();
    setOpeningMemberSymbol(symbol);
    setSelectedMemberSymbol(symbol);
    setClosingMemberSymbol(null);
    if (previousSymbol && previousSymbol !== symbol) {
      scheduleCloseRemoval(previousSymbol);
    }
    finishOpeningOnNextFrame(symbol);
  };

  useEffect(
    () => () => {
      clearCloseTimer();
      clearOpenFrame();
    },
    []
  );

  return (
    <div className="space-y-5">
      {data.research.error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          市场数据服务暂不可用，当前展示本地兜底配置：{data.research.error}
        </div>
      )}

      {selectedUniverse && (
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-950">{selectedUniverse.name}</h2>
                <Badge variant="outline" className="bg-white text-slate-500">
                  {hasMemberSearch ? `${memberTotal} / ${selectedUniverseTotal} 只` : `${selectedUniverseTotal} 只`}
                </Badge>
                {isLoadingMembers && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                一张可检索、可分页的{selectedUniverseNoun}列表；点击任意标的查看 K 线、覆盖统计和主数据。
              </p>
            </div>
            <form onSubmit={addMember} className="flex min-w-[280px] flex-1 flex-wrap justify-end gap-2">
              <Input
                value={memberQuery}
                onChange={(event) => setMemberQuery(event.target.value)}
                placeholder="输入代码或名称，例如 比亚迪 / 000001"
                className="h-9 max-w-sm border-slate-200 bg-white"
              />
              <Button type="submit" size="sm" disabled={isAdding || !memberQuery.trim()} className="bg-blue-600 text-white hover:bg-blue-700">
                {isAdding ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListPlus className="h-4 w-4" />}
                加入{selectedUniverseNoun}池
              </Button>
            </form>
          </div>
          <Dialog.Root
            open={isIngestionDialogOpen}
            onOpenChange={(open) => {
              setIsIngestionDialogOpen(open);
              if (open) void loadIngestionJobs();
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
              {data.research.universes.length > 1 ? (
                <div className="flex flex-wrap gap-2">
                  {data.research.universes.map((universe) => (
                    <button
                      key={universe.id}
                      type="button"
                      onClick={() => {
                        setSelectedUniverseId(universe.id);
                        setMemberSearch("");
                        setPage(1);
                        setSelectedMemberSymbol(null);
                        setOpeningMemberSymbol(null);
                        setClosingMemberSymbol(null);
                        setMemberError(null);
                        setMembersPage(buildUniverseMembersPage(universe));
                      }}
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
                        selectedUniverse.id === universe.id
                          ? "border-blue-200 bg-blue-50 text-blue-700"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                      )}
                    >
                      {universe.name}
                      <span className="ml-1.5 text-xs text-slate-400">{universe.memberCount}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div />
              )}
              <Dialog.Trigger asChild>
                <Button type="button" variant="outline" size="sm" className="border-slate-200 bg-white">
                    {isRunningBatch || isAutoFilling || hasRunningBatchJob || hasRunningAutoFillJob ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCcw className="h-4 w-4" />
                    )}
                    补数
                    {activeJob && (
                      <span className={cn("ml-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium", jobStatusClass(activeJob.status))}>
                        {jobStatusLabel(activeJob.status)}
                      </span>
                    )}
                </Button>
              </Dialog.Trigger>
            </div>
                <Dialog.Portal>
                  <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
                  <Dialog.Content className="fixed left-[50%] top-[50%] z-50 max-h-[86vh] w-[min(1120px,calc(100vw-32px))] translate-x-[-50%] translate-y-[-50%] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
                    <div className="flex max-h-[86vh] flex-col">
                      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
                        <div>
                          <Dialog.Title className="text-lg font-semibold text-slate-950">低频补数</Dialog.Title>
                          <Dialog.Description className="mt-1 text-sm text-slate-500">
                            选择补数范围后分批补充成交额、换手率、停牌/ST、涨跌停和估值字段；本地已有覆盖会跳过。
                          </Dialog.Description>
                        </div>
                        <div className="flex items-center gap-2">
                          {isLoadingJobs && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
                          {activeJob && (
                            <Badge variant="outline" className={jobStatusClass(activeJob.status)}>
                              {jobStatusLabel(activeJob.status)}
                            </Badge>
                          )}
                          <Dialog.Close className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600">
                            <X className="h-5 w-5" />
                          </Dialog.Close>
                        </div>
                      </div>
                      <div className="flex-1 overflow-y-auto p-5">
                        <div className="space-y-4">
                          <div className="rounded-md border border-slate-200 bg-white">
                            <div className="flex flex-wrap items-start justify-between gap-4 px-4 py-4">
                              <div>
                                <p className="text-sm font-semibold text-slate-900">更新进度</p>
                                <p className="mt-1 text-xs text-slate-500">
                                  范围：{activeJob?.status === "running" ? activeRangeLabel : selectedRangeLabel}
                                </p>
                              </div>
                              <div className="grid grid-cols-2 gap-4 text-right text-xs text-slate-500 md:grid-cols-4">
                                <div>
                                  <p>完成标的</p>
                                  <p className="mt-1 font-mono text-base font-semibold text-slate-950">
                                    {activeProgress.completedSymbols}/{activeProgress.totalSymbols || selectedUniverseTotal}
                                  </p>
                                </div>
                                <div>
                                  <p>入库行数</p>
                                  <p className="mt-1 font-mono text-base font-semibold text-slate-950">
                                    {activeJob?.rowsUpserted.toLocaleString("zh-CN") ?? recentRowsUpserted.toLocaleString("zh-CN")}
                                  </p>
                                </div>
                                <div>
                                  <p>预计剩余</p>
                                  <p className="mt-1 font-mono text-base font-semibold text-slate-950">{formatDuration(activeProgress.etaSeconds)}</p>
                                </div>
                                <div>
                                  <p>预计完成</p>
                                  <p className="mt-1 font-mono text-base font-semibold text-slate-950">
                                    {activeProgress.etaSeconds !== null
                                      ? formatDateTime(new Date(Date.now() + activeProgress.etaSeconds * 1000).toISOString())
                                      : "-"}
                                  </p>
                                </div>
                              </div>
                            </div>
                            <div className="px-4 pb-4">
                              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                                <div
                                  className="h-full rounded-full bg-blue-600 transition-all"
                                  style={{ width: `${activeProgress.percent}%` }}
                                />
                              </div>
                              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                                <span>
                                  当前标的 {activeProgress.currentSymbol ?? "-"} · {ingestionControlLabel(activeControl)}
                                  {activeProgress.preflightSkippedSymbols ? ` · 本地跳过 ${activeProgress.preflightSkippedSymbols}` : ""}
                                </span>
                                <span>心跳 {formatDateTime(activeProgress.lastHeartbeatAt)}</span>
                              </div>
                            </div>
                          </div>
                          <div className="rounded-md border border-slate-200 bg-slate-50/60 px-4 py-4">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-slate-900">补数范围</p>
                                <p className="mt-1 text-xs text-slate-500">默认按本地最新交易日向后补；也可以手动指定完整日期范围。</p>
                              </div>
                              <div className="flex rounded-md border border-slate-200 bg-white p-1">
                                {[
                                  ["incremental", "增量"] as const,
                                  ["lookback", "近5年"] as const,
                                  ["custom", "自定义"] as const,
                                ].map(([mode, label]) => (
                                  <button
                                    key={mode}
                                    type="button"
                                    onClick={() => setIngestionRangeMode(mode)}
                                    className={cn(
                                      "rounded px-3 py-1.5 text-xs font-medium transition-colors",
                                      ingestionRangeMode === mode ? "bg-blue-50 text-blue-700" : "text-slate-500 hover:bg-slate-50"
                                    )}
                                  >
                                    {label}
                                  </button>
                                ))}
                              </div>
                            </div>
                            <div className="mt-4 grid gap-3 md:grid-cols-3">
                              <label className="text-xs text-slate-500">
                                开始日期
                                <Input
                                  type="date"
                                  value={selectedIngestionStart}
                                  onChange={(event) => {
                                    setIngestionRangeMode("custom");
                                    setIngestionStartDate(event.target.value);
                                  }}
                                  disabled={ingestionRangeMode !== "custom"}
                                  className="mt-1 h-9 border-slate-200 bg-white"
                                />
                              </label>
                              <label className="text-xs text-slate-500">
                                结束日期
                                <Input
                                  type="date"
                                  value={selectedIngestionEnd}
                                  onChange={(event) => setIngestionEndDate(event.target.value)}
                                  disabled={ingestionRangeMode === "lookback"}
                                  className="mt-1 h-9 border-slate-200 bg-white"
                                />
                              </label>
                              <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
                                <p>当前范围</p>
                                <p className="mt-1 font-mono text-sm font-semibold text-slate-900">{selectedRangeLabel}</p>
                              </div>
                            </div>
                            {!canRunIncrementalIngestion && (
                              <p className="mt-2 text-xs text-emerald-600">当前本地数据已覆盖到所选结束日期，无需增量补数。</p>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-4 py-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-900">执行控制</p>
                              {(autoFillMessage || isIngestionBusy) && (
                                <p className="mt-1 text-xs text-blue-600">
                                  {autoFillMessage ?? "已有补数任务运行中，等待完成后可继续。"}
                                </p>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <Button variant="outline" size="sm" onClick={() => void loadIngestionJobs()} disabled={isLoadingJobs}>
                                <RefreshCcw className={cn("h-4 w-4", isLoadingJobs && "animate-spin")} />
                                刷新进度
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={runIngestionBatch}
                                disabled={isIngestionBusy || !canRunIncrementalIngestion}
                              >
                                {isRunningBatch ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                                补下一批
                              </Button>
                              {isAutoFilling || hasRunningAutoFillJob ? (
                                <>
                                  {activeControl === "pause" ? (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => void controlIngestion("resume")}
                                      disabled={isControllingIngestion}
                                    >
                                      {isControllingIngestion ? <Loader2 className="h-4 w-4 animate-spin" /> : <SkipForward className="h-4 w-4" />}
                                      继续
                                    </Button>
                                  ) : (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => void controlIngestion("pause")}
                                      disabled={isControllingIngestion || activeControl === "stop"}
                                    >
                                      {isControllingIngestion ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
                                      暂停
                                    </Button>
                                  )}
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void controlIngestion("stop")}
                                    disabled={isControllingIngestion || activeControl === "stop"}
                                    className="border-red-200 text-red-700 hover:bg-red-50"
                                  >
                                    <CircleStop className="h-4 w-4" />
                                    停止
                                  </Button>
                                </>
                              ) : (
                                <Button
                                  size="sm"
                                  onClick={runIngestionAutoFill}
                                  disabled={isIngestionBusy || !canRunIncrementalIngestion}
                                  className="bg-blue-600 text-white hover:bg-blue-700"
                                >
                                  <Play className="h-4 w-4" />
                                  一键补齐
                                </Button>
                              )}
                            </div>
                          </div>
                <div className="border-t border-slate-200 bg-white px-4 py-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-900">最近批次</p>
                    <span className="text-xs text-slate-500">近 {INGESTION_LOG_LIMIT} 批 · 入库 {recentRowsUpserted.toLocaleString("zh-CN")} 行</span>
                  </div>
                  {ingestionJobs.length ? (
                    <div className="overflow-x-auto rounded-md border border-slate-200">
                      <table className="w-full min-w-[980px] text-left text-xs">
                        <thead className="bg-slate-50 text-slate-500">
                          <tr>
	                            <th className="px-3 py-2 font-medium">状态</th>
	                            <th className="px-3 py-2 font-medium">批次</th>
	                            <th className="px-3 py-2 font-medium">范围</th>
	                            <th className="px-3 py-2 font-medium">标的</th>
	                            <th className="px-3 py-2 font-medium">入库</th>
                            <th className="px-3 py-2 font-medium">时间</th>
                            <th className="px-3 py-2 font-medium">样本 / 错误</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {ingestionJobs.map((job) => {
                            const errorPreview = ingestionErrorPreview(job);
                            return (
                              <tr key={job.id} className="align-top">
                                <td className="px-3 py-3">
                                  <Badge variant="outline" className={jobStatusClass(job.status)}>
                                    {jobStatusLabel(job.status)}
                                  </Badge>
                                </td>
	                                <td className="px-3 py-3">
	                                  <p className="font-mono font-semibold text-slate-900">{ingestionBatchRangeLabel(job)}</p>
	                                </td>
	                                <td className="px-3 py-3 font-mono text-slate-600">
	                                  {ingestionRangeLabel(job)}
	                                </td>
                                  <td className="px-3 py-3">
                                    <p className="font-mono font-semibold text-slate-900">
                                      {job.completedSymbols}/{job.totalSymbols}
                                    </p>
                                    <p className={cn("mt-1", job.failedSymbols ? "text-red-600" : "text-slate-400")}>
                                      {job.failedSymbols ? `${job.failedSymbols} 失败` : "无失败"}
                                    </p>
                                    {job.provider === "baostock-autofill" && (
                                      <p className="mt-1 text-slate-400">
                                        {ingestionControlLabel(stringFromUnknown(job.metadata.control))}
                                      </p>
                                    )}
                                  </td>
                                  <td className="px-3 py-3">
                                    <p className="font-mono font-semibold text-slate-900">
                                      {job.rowsUpserted.toLocaleString("zh-CN")} 行
                                    </p>
                                    <p className="mt-1 text-slate-400">
                                      收到 {job.rowsReceived.toLocaleString("zh-CN")}
                                    </p>
                                    {numberFromUnknown(job.metadata.preflight_skipped_symbols) ? (
                                      <p className="mt-1 text-emerald-600">
                                        本地跳过 {numberFromUnknown(job.metadata.preflight_skipped_symbols)}
                                      </p>
                                    ) : null}
                                  </td>
                                <td className="px-3 py-3">
                                  <p className="font-mono text-slate-700">{formatDateTime(job.startedAt ?? job.createdAt)}</p>
                                  <p className="mt-1 font-mono text-slate-400">{formatDateTime(job.completedAt ?? job.updatedAt)}</p>
                                </td>
                                <td className="px-3 py-3">
                                  <p className="line-clamp-2 text-slate-600">{ingestionSymbolPreview(job)}</p>
                                  {errorPreview && (
                                    <p className="mt-1 line-clamp-2 text-red-600">{errorPreview}</p>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                      暂无补数日志
                    </div>
                  )}
                </div>
                        </div>
                      </div>
                    </div>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
            <div className="relative min-w-[240px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={memberSearch}
                onChange={(event) => {
                  setMemberSearch(event.target.value);
                  setPage(1);
                  setSelectedMemberSymbol(null);
                }}
                placeholder="筛选名称、代码、板块、交易所..."
                className="h-9 border-slate-200 bg-white pl-9"
              />
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span>第 {currentPage} / {totalPages} 页</span>
              <Button variant="outline" size="sm" onClick={() => setPage(Math.max(1, currentPage - 1))} disabled={currentPage <= 1 || isLoadingMembers}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage >= totalPages || isLoadingMembers}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {memberError && (
            <div className="border-b border-amber-100 bg-amber-50 px-5 py-2 text-sm text-amber-700">
              {memberError}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1500px] text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="w-[9%] px-5 py-3 font-medium">标的名称</th>
                  <th className="w-[8%] px-3 py-3 font-medium">代码</th>
                  <th className="w-[29%] px-3 py-3 font-medium">所属板块</th>
                  <th className="w-[9%] px-3 py-3 font-medium">行情</th>
                  <th className="w-[10%] px-3 py-3 font-medium">强弱</th>
                  <th className="w-[9%] px-3 py-3 font-medium">趋势</th>
                  <th className="w-[10%] px-3 py-3 font-medium">流动性</th>
                  <th className="w-[8%] px-3 py-3 font-medium">估值</th>
                  <th className="w-[6%] px-3 py-3 font-medium">状态</th>
                  <th className="w-[12%] px-3 py-3 font-medium">数据覆盖</th>
                </tr>
              </thead>
              <tbody>
                {pagedMembers.map((member) => {
                  const isDetailSelected = selectedMemberSymbol === member.symbol;
                  const isDetailOpen = isDetailSelected && openingMemberSymbol !== member.symbol;
                  const isDetailClosing = closingMemberSymbol === member.symbol;
                  const shouldRenderDetail = isDetailSelected || isDetailClosing;
                  const displaySectorTags = member.sectorTags.length
                    ? member.sectorTags
                    : selectedIsEtfUniverse
                      ? [member.assetType.toUpperCase()]
                      : [];

                  return (
                    <Fragment key={member.symbol}>
                      <tr
                        aria-expanded={isDetailSelected}
                        onClick={() => toggleMemberDetail(member.symbol)}
                        className={cn(
                          "cursor-pointer border-t border-slate-100 transition-colors hover:bg-slate-50",
                          shouldRenderDetail && "bg-blue-50/60"
                        )}
                      >
                        <td className="px-5 py-3 font-medium text-slate-950">{member.name ?? member.symbol}</td>
                        <td className="px-3 py-3">
                          <span className="font-mono text-xs text-slate-700">{member.symbol}</span>
                        </td>
                        <td className="px-3 py-3">
                          {displaySectorTags.length ? (
                            <div className="flex flex-wrap gap-1.5">
                              {displaySectorTags.map((tag, tagIndex) => (
                                <Badge key={`${tag}-${tagIndex}`} variant="outline" className="border-blue-100 bg-blue-50 text-blue-700">
                                  {tag}
                                </Badge>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-400">-</span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <div className="space-y-0.5">
                            <p className="font-semibold tabular-nums text-slate-950">{formatNumberValue(member.latestClose)}</p>
                            <p className={cn("text-xs font-medium tabular-nums", signedToneClass(member.latestChangePct))}>
                              {formatSignedPercent(member.latestChangePct)}
                            </p>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <div className="space-y-1 text-xs tabular-nums">
                            <p>
                              <span className="text-slate-400">20日 </span>
                              <span className={cn("font-semibold", signedToneClass(member.strength20dPct))}>
                                {formatSignedPercent(member.strength20dPct)}
                              </span>
                            </p>
                            <p>
                              <span className="text-slate-400">60日 </span>
                              <span className={cn("font-semibold", signedToneClass(member.strength60dPct))}>
                                {formatSignedPercent(member.strength60dPct)}
                              </span>
                            </p>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <div className="space-y-1">
                            <Badge variant="outline" className={trendClass(member.trendStatus)}>
                              {trendLabel(member.trendStatus)}
                            </Badge>
                            <p className="text-xs tabular-nums text-slate-400">
                              MA20 {formatNumberValue(member.ma20)} / MA60 {formatNumberValue(member.ma60)}
                            </p>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <div className="space-y-0.5">
                            <p className="font-semibold tabular-nums text-slate-950">{liquidityLabel(member)}</p>
                            <p className="text-xs text-slate-400">{liquiditySubLabel(member)}</p>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <p className="text-xs font-semibold tabular-nums text-slate-700">{valuationSummary(member)}</p>
                        </td>
                        <td className="px-3 py-3">
                          <Badge variant="outline" className={tradeStatusClass(member)}>
                            {tradeStatusLabel(member)}
                          </Badge>
                        </td>
                        <td className="px-3 py-3">
                          <p className="text-slate-700">
                            {formatDataDate(member.firstTs)} 至 {formatDataDate(member.lastTs)}
                          </p>
                        </td>
                      </tr>
                      {shouldRenderDetail && (
                        <tr key={`${member.symbol}-detail`} className="border-t border-slate-100">
                          <td colSpan={10} className="p-0">
                            <div
                              className={cn(
                                "grid transition-[grid-template-rows,opacity] duration-300 ease-out",
                                isDetailOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
                              )}
                            >
                              <div
                                className={cn(
                                  "overflow-hidden transition-transform duration-300 ease-out",
                                  isDetailOpen ? "translate-y-0 scale-100" : "-translate-y-2 scale-[0.985]"
                                )}
                              >
                                <StockKlineDetail
                                  member={member}
                                  universe={selectedUniverse}
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {!pagedMembers.length && (
                  <tr className="border-t border-slate-100">
                    <td colSpan={10} className="px-5 py-12 text-center text-sm text-slate-500">
                      {isLoadingMembers ? "正在读取股票池..." : "没有匹配的股票"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function klineTimeframeLabel(value: string) {
  return KLINE_TIMEFRAMES.find((option) => option.id === value)?.label ?? value;
}

function klineFetchLimit(timeframe: KlineTimeframe) {
  if (timeframe === "daily") return 1260;
  if (timeframe === "weekly") return 260;
  return 120;
}

const KLINE_DETAIL_CACHE_TTL_MS = 60 * 1000;
const KLINE_DETAIL_CACHE_MAX = 96;
const klineDetailCache = new Map<string, { data: StrategyLocalKlineResponse; expiresAt: number }>();
const klineDetailPromises = new Map<string, Promise<StrategyLocalKlineResponse>>();
const dividendEventsCache = new Map<string, { data: StrategyDividendEvent[]; expiresAt: number }>();
const dividendEventsPromises = new Map<string, Promise<StrategyDividendEvent[]>>();

function setBoundedCacheValue<T>(cache: Map<string, { data: T; expiresAt: number }>, key: string, data: T) {
  cache.set(key, { data, expiresAt: Date.now() + KLINE_DETAIL_CACHE_TTL_MS });
  while (cache.size > KLINE_DETAIL_CACHE_MAX) {
    const oldestKey = cache.keys().next().value as string | undefined;
    if (!oldestKey) break;
    cache.delete(oldestKey);
  }
}

function getFreshCacheValue<T>(cache: Map<string, { data: T; expiresAt: number }>, key: string) {
  const cached = cache.get(key);
  if (!cached) return null;
  if (cached.expiresAt < Date.now()) {
    cache.delete(key);
    return null;
  }
  return cached.data;
}

function klineDetailCacheKey(symbol: string, timeframe: KlineTimeframe, adjustment: string) {
  return `${symbol}::${timeframe}::${adjustment}`;
}

function dividendEventsCacheKey(symbol: string) {
  return `${symbol}::dividends`;
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function movingAverageSeries(bars: StrategyLocalKlineBar[], period: number) {
  let sum = 0;
  return bars.map((bar, index) => {
    sum += bar.close;
    if (index >= period) {
      sum -= bars[index - period].close;
    }
    return index >= period - 1 ? sum / period : null;
  });
}

function movingAverageAtIndex(bars: StrategyLocalKlineBar[], period: number, index: number) {
  if (index < period - 1) return null;
  const window = bars.slice(index - period + 1, index + 1);
  if (window.length < period || window.some((bar) => finiteNumber(bar.close) === null)) return null;
  return window.reduce((sum, bar) => sum + bar.close, 0) / period;
}

function returnPctForBar(bars: StrategyLocalKlineBar[], index: number) {
  const directValue = finiteNumber(bars[index]?.changePercent);
  if (directValue !== null) return directValue;
  const current = finiteNumber(bars[index]?.close);
  const previous = finiteNumber(bars[index]?.previousClose) ?? finiteNumber(bars[index - 1]?.close);
  if (current === null || previous === null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

function normalizedTradeDate(value?: string | null) {
  const formatted = formatDataDate(value);
  return formatted === "-" ? null : formatted;
}

function dateKeyToTime(dateKey?: string | null) {
  if (!dateKey) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey);
  if (!match) return null;
  const [, year, month, day] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day));
}

function dateKeyToWeekKey(dateKey: string) {
  const time = dateKeyToTime(dateKey);
  if (time === null) return dateKey;
  const date = new Date(time);
  const day = date.getUTCDay();
  const mondayOffset = (day + 6) % 7;
  const monday = new Date(time - mondayOffset * 24 * 60 * 60 * 1000);
  return monday.toISOString().slice(0, 10);
}

function klineAggregationKey(bar: StrategyLocalKlineBar, timeframe: KlineTimeframe) {
  const dateKey = normalizedTradeDate(bar.ts);
  if (!dateKey) return bar.ts;
  if (timeframe === "monthly") return dateKey.slice(0, 7);
  if (timeframe === "weekly") return dateKeyToWeekKey(dateKey);
  return dateKey;
}

function aggregateKlineBars(bars: StrategyLocalKlineBar[], timeframe: KlineTimeframe) {
  if (timeframe === "daily") return bars;
  const grouped = new Map<string, StrategyLocalKlineBar[]>();
  for (const bar of bars) {
    const key = klineAggregationKey(bar, timeframe);
    const group = grouped.get(key) ?? [];
    group.push(bar);
    grouped.set(key, group);
  }

  return Array.from(grouped.values()).map((group) => {
    const sorted = group.slice().sort((left, right) => {
      const leftTime = new Date(left.ts).getTime();
      const rightTime = new Date(right.ts).getTime();
      return leftTime - rightTime;
    });
    const first = sorted[0];
    const last = sorted.at(-1) ?? first;
    const high = Math.max(...sorted.map((bar) => bar.high));
    const low = Math.min(...sorted.map((bar) => bar.low));
    const volume = sorted.reduce((sum, bar) => sum + bar.volume, 0);
    const amountValues = sorted.map((bar) => finiteNumber(bar.amount)).filter((value): value is number => value !== null);
    const amount = amountValues.length ? amountValues.reduce((sum, value) => sum + value, 0) : null;
    const previousClose = finiteNumber(first.previousClose);
    const changeAmount = previousClose !== null ? last.close - previousClose : null;
    const changePercent = previousClose !== null && previousClose !== 0 ? (changeAmount! / previousClose) * 100 : null;
    const amplitude = previousClose !== null && previousClose !== 0 ? ((high - low) / previousClose) * 100 : null;
    return {
      ...last,
      ts: last.ts,
      open: first.open,
      high,
      low,
      close: last.close,
      previousClose,
      volume,
      amount,
      amplitude,
      changeAmount,
      changePercent,
      turnover: null,
      limitUp: null,
      limitDown: null,
      metadata: {},
    };
  });
}

function buildKlineSummary(bars: StrategyLocalKlineBar[], rowCount = bars.length): StrategyLocalKlineResponse["summary"] {
  const latest = bars.at(-1);
  const previous = bars.at(-2);
  const previousClose = finiteNumber(previous?.close) ?? finiteNumber(latest?.previousClose);
  const totalAmountValues = bars.map((bar) => finiteNumber(bar.amount)).filter((value): value is number => value !== null);
  return {
    rowCount,
    firstTs: bars[0]?.ts ?? null,
    lastTs: latest?.ts ?? null,
    latestClose: latest?.close ?? null,
    previousClose,
    returnPct:
      latest && previousClose !== null && previousClose !== 0
        ? ((latest.close - previousClose) / previousClose) * 100
        : null,
    high: bars.length ? Math.max(...bars.map((bar) => bar.high)) : null,
    low: bars.length ? Math.min(...bars.map((bar) => bar.low)) : null,
    totalVolume: bars.reduce((sum, bar) => sum + bar.volume, 0),
    totalAmount: totalAmountValues.length ? totalAmountValues.reduce((sum, value) => sum + value, 0) : null,
  };
}

function deriveKlineResponse(
  dailyDetail: StrategyLocalKlineResponse,
  timeframe: KlineTimeframe,
  limit: number
): StrategyLocalKlineResponse {
  if (timeframe === "daily") {
    const bars = dailyDetail.bars.slice(-limit).map((bar) => ({ ...bar, metadata: {} }));
    const windowSummary = buildKlineSummary(bars);
    return {
      ...dailyDetail,
      timeframe,
      bars,
      summary: {
        ...dailyDetail.summary,
        high: windowSummary.high,
        low: windowSummary.low,
        totalVolume: windowSummary.totalVolume,
        totalAmount: windowSummary.totalAmount,
      },
    };
  }
  const allBars = aggregateKlineBars(dailyDetail.bars, timeframe);
  const bars = allBars.slice(-limit);
  return {
    ...dailyDetail,
    timeframe,
    bars,
    summary: buildKlineSummary(bars, allBars.length),
  };
}

function readCachedKlineDetail(symbol: string, timeframe: KlineTimeframe, adjustment: string) {
  return getFreshCacheValue(klineDetailCache, klineDetailCacheKey(symbol, timeframe, adjustment));
}

async function fetchDailyKlineDetail(symbol: string, adjustment: string): Promise<StrategyLocalKlineResponse> {
  const response = await fetch(`${API_BASE}/api/quant/strategies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "symbol-bars",
      symbol,
      timeframe: "daily",
      adjustment,
      limit: klineFetchLimit("daily"),
      includeMetadata: false,
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.success) throw new Error(payload.error ?? "读取 K 线失败");
  return deriveKlineResponse(payload.data as StrategyLocalKlineResponse, "daily", klineFetchLimit("daily"));
}

async function loadCachedKlineDetail(
  symbol: string,
  timeframe: KlineTimeframe,
  adjustment: string
): Promise<StrategyLocalKlineResponse> {
  const key = klineDetailCacheKey(symbol, timeframe, adjustment);
  const cached = getFreshCacheValue(klineDetailCache, key);
  if (cached) return cached;
  const inFlight = klineDetailPromises.get(key);
  if (inFlight) return inFlight;

  const promise: Promise<StrategyLocalKlineResponse> = (async (): Promise<StrategyLocalKlineResponse> => {
    const data: StrategyLocalKlineResponse = timeframe === "daily"
      ? await fetchDailyKlineDetail(symbol, adjustment)
      : deriveKlineResponse(
          await loadCachedKlineDetail(symbol, "daily", adjustment),
          timeframe,
          klineFetchLimit(timeframe)
        );
    setBoundedCacheValue(klineDetailCache, key, data);
    return data;
  })();

  klineDetailPromises.set(key, promise);
  try {
    return await promise;
  } finally {
    klineDetailPromises.delete(key);
  }
}

async function loadCachedDividendEvents(symbol: string) {
  const key = dividendEventsCacheKey(symbol);
  const cached = getFreshCacheValue(dividendEventsCache, key);
  if (cached) return cached;
  const inFlight = dividendEventsPromises.get(key);
  if (inFlight) return inFlight;

  const promise = (async () => {
    const response = await fetch(`${API_BASE}/api/quant/strategies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "symbol-dividends",
        symbol,
        limit: 40,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.error ?? "读取分红事件失败");
    const events = (payload.data?.events ?? []) as StrategyDividendEvent[];
    setBoundedCacheValue(dividendEventsCache, key, events);
    return events;
  })();

  dividendEventsPromises.set(key, promise);
  try {
    return await promise;
  } finally {
    dividendEventsPromises.delete(key);
  }
}

function resolveDividendMarkerIndex(
  visibleBars: StrategyLocalKlineBar[],
  eventDateKey: string,
  timeframe: KlineTimeframe
) {
  const barDateKeys = visibleBars.map((bar) => normalizedTradeDate(bar.ts));
  const exactIndex = barDateKeys.findIndex((dateKey) => dateKey === eventDateKey);
  if (exactIndex >= 0) return exactIndex;

  const eventTime = dateKeyToTime(eventDateKey);
  if (eventTime === null) return -1;

  const barTimes = barDateKeys.map(dateKeyToTime);
  const oneDay = 24 * 60 * 60 * 1000;

  if (timeframe === "daily") {
    return barTimes.findIndex((barTime) =>
      barTime !== null && barTime >= eventTime && barTime - eventTime <= oneDay * 4
    );
  }

  const maxWindow = timeframe === "weekly" ? oneDay * 10 : oneDay * 35;
  for (let index = 0; index < barTimes.length; index += 1) {
    const current = barTimes[index];
    if (current === null || current < eventTime) continue;
    const previous = index > 0 ? barTimes[index - 1] : null;
    const isInBucket = previous === null
      ? current - eventTime <= maxWindow
      : eventTime > previous && eventTime <= current;
    if (isInBucket) return index;
  }

  return -1;
}

function limitThresholdForSymbol(symbol: string, name?: string | null, exchange?: string | null) {
  const code = symbol.split(".", 1)[0];
  if ((name ?? "").toUpperCase().includes("ST")) return 5;
  if (exchange === "BJ" || code.startsWith("4") || code.startsWith("8")) return 30;
  if (code.startsWith("300") || code.startsWith("301") || code.startsWith("688")) return 20;
  return 10;
}

function limitMarkerForBar(
  bar: StrategyLocalKlineBar,
  threshold: number,
  timeframe: KlineTimeframe
): "up" | "down" | null {
  if (timeframe !== "daily") return null;
  if (bar.limitUp) return "up";
  if (bar.limitDown) return "down";
  const changePercent = finiteNumber(bar.changePercent);
  if (changePercent === null) return null;
  const tolerance = threshold >= 20 ? 0.12 : 0.06;
  if (changePercent >= threshold - tolerance) return "up";
  if (changePercent <= -threshold + tolerance) return "down";
  return null;
}

function KlineMiniChart({
  bars,
  dividendEvents,
  symbol,
  name,
  exchange,
  timeframe,
  selectedBarTs,
  onSelectBar,
  onResetSelection,
}: {
  bars: StrategyLocalKlineBar[];
  dividendEvents: StrategyDividendEvent[];
  symbol: string;
  name?: string | null;
  exchange?: string | null;
  timeframe: KlineTimeframe;
  selectedBarTs?: string | null;
  onSelectBar?: (bar: StrategyLocalKlineBar) => void;
  onResetSelection?: () => void;
}) {
  const cleanBars = useMemo(
    () => bars.filter((bar) =>
      [bar.open, bar.high, bar.low, bar.close, bar.volume].every(
        (value) => typeof value === "number" && Number.isFinite(value)
      )
    ),
    [bars]
  );
  const visibleCount = Math.min(90, cleanBars.length);
  const maxStartIndex = Math.max(0, cleanBars.length - visibleCount);
  const [startIndex, setStartIndex] = useState(maxStartIndex);
  const dragRef = useRef<{ x: number; startIndex: number; hasMoved: boolean } | null>(null);
  const resolvedStartIndex = clampNumber(startIndex, 0, maxStartIndex);
  const visibleBars = cleanBars.slice(resolvedStartIndex, resolvedStartIndex + visibleCount);
  const selectedVisibleIndex = visibleBars.findIndex((bar) => bar.ts === selectedBarTs);
  const averages = useMemo(
    () => MOVING_AVERAGE_CONFIGS.map((config) => ({
      ...config,
      values: movingAverageSeries(cleanBars, config.period),
    })),
    [cleanBars]
  );
  const visibleAverages = averages.map((average) => ({
    ...average,
    values: average.values.slice(resolvedStartIndex, resolvedStartIndex + visibleCount),
  }));
  const activeVisibleAverages = visibleAverages.filter((average) =>
    average.values.some((value) => finiteNumber(value) !== null)
  );
  const dividendMarkersByIndex = useMemo(() => {
    const map = new Map<number, StrategyDividendEvent[]>();
    for (const event of dividendEvents) {
      const date = normalizedTradeDate(event.exDividendDate);
      if (!date) continue;
      const index = resolveDividendMarkerIndex(visibleBars, date, timeframe);
      if (index < 0) continue;
      const events = map.get(index) ?? [];
      events.push(event);
      map.set(index, events);
    }
    return map;
  }, [dividendEvents, timeframe, visibleBars]);

  useEffect(() => {
    setStartIndex(maxStartIndex);
  }, [maxStartIndex, bars]);

  if (!visibleBars.length) {
    return (
      <div className="flex h-[340px] items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
        暂无可展示的 K 线样本
      </div>
    );
  }

  const width = 1320;
  const height = 360;
  const left = 66;
  const right = 24;
  const chartTop = 24;
  const chartHeight = 220;
  const volumeTop = 278;
  const volumeHeight = 42;
  const dateLabelY = height - 10;
  const chartWidth = width - left - right;
  const priceValues = [
    ...visibleBars.flatMap((bar) => [bar.high, bar.low]),
    ...visibleAverages.flatMap((average) => average.values).filter((value): value is number => value !== null),
  ];
  const highest = Math.max(...priceValues);
  const lowest = Math.min(...priceValues);
  const priceRange = Math.max(highest - lowest, 0.01);
  const maxVolume = Math.max(...visibleBars.map((bar) => bar.volume), 1);
  const step = chartWidth / visibleBars.length;
  const candleWidth = Math.max(3, Math.min(10, step * 0.55));
  const priceY = (price: number) => chartTop + ((highest - price) / priceRange) * chartHeight;
  const limitThreshold = limitThresholdForSymbol(symbol, name, exchange);
  const buildAveragePath = (values: Array<number | null>) =>
    values.reduce((path, value, index) => {
      if (value === null) return path;
      const x = left + index * step + step / 2;
      const y = priceY(value);
      return `${path}${path ? " L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
    }, "");
  const rangeLeftPct = cleanBars.length ? (resolvedStartIndex / cleanBars.length) * 100 : 0;
  const rangeWidthPct = cleanBars.length ? (visibleBars.length / cleanBars.length) * 100 : 100;
  const visibleIndexFromPointer = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !visibleBars.length) return -1;
    const localX = ((event.clientX - rect.left) / rect.width) * width;
    const localY = ((event.clientY - rect.top) / rect.height) * height;
    if (localX < left || localX > width - right || localY < chartTop || localY > volumeTop + volumeHeight) {
      return -1;
    }
    const rawIndex = Math.round((localX - left - step / 2) / step);
    return clampNumber(rawIndex, 0, visibleBars.length - 1);
  };
  const selectBarFromPointer = (event: PointerEvent<SVGSVGElement>) => {
    const index = visibleIndexFromPointer(event);
    const bar = index >= 0 ? visibleBars[index] : null;
    if (bar) {
      onSelectBar?.(bar);
    } else {
      onResetSelection?.();
    }
  };
  const moveByDelta = (clientX: number) => {
    if (!dragRef.current || !maxStartIndex) return;
    const pixelsPerBar = Math.max(8, step);
    const deltaBars = Math.round((clientX - dragRef.current.x) / pixelsPerBar);
    setStartIndex(clampNumber(dragRef.current.startIndex - deltaBars, 0, maxStartIndex));
  };
  const handlePointerDown = (event: PointerEvent<SVGSVGElement>) => {
    selectBarFromPointer(event);
    if (!maxStartIndex) return;
    dragRef.current = { x: event.clientX, startIndex: resolvedStartIndex, hasMoved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    if (dragRef.current && event.buttons === 1) {
      dragRef.current.hasMoved = dragRef.current.hasMoved || Math.abs(event.clientX - dragRef.current.x) > 3;
      moveByDelta(event.clientX);
      return;
    }
    selectBarFromPointer(event);
  };
  const handlePointerUp = (event: PointerEvent<SVGSVGElement>) => {
    if (dragRef.current && !dragRef.current.hasMoved) {
      selectBarFromPointer(event);
    }
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };
  const handlePointerLeave = () => {
    if (!dragRef.current) onResetSelection?.();
  };

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm text-slate-500">
        <span>{formatDataDate(visibleBars[0]?.ts)} 至 {formatDataDate(visibleBars.at(-1)?.ts)}</span>
        <div className="flex flex-wrap items-center gap-3">
          {activeVisibleAverages.map((average) => (
            <span key={average.label} className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: average.color }} />
              {average.label}
            </span>
          ))}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={cn("h-[360px] w-full touch-pan-y select-none", maxStartIndex ? "cursor-grab active:cursor-grabbing" : "cursor-default")}
        role="img"
        aria-label="本地 K 线图"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerLeave}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = chartTop + ratio * chartHeight;
          const price = highest - ratio * priceRange;
          return (
            <g key={ratio}>
              <line x1={left} x2={width - right} y1={y} y2={y} stroke="#e2e8f0" strokeDasharray="3 4" />
              <text x={12} y={y + 5} className="fill-slate-400 text-[14px]">
                {price.toFixed(2)}
              </text>
            </g>
          );
        })}
        <line x1={left} x2={width - right} y1={volumeTop - 10} y2={volumeTop - 10} stroke="#e2e8f0" />
        {visibleBars.map((bar, index) => {
          const x = left + index * step + step / 2;
          const isUp = bar.close >= bar.open;
          const color = isUp ? "#dc2626" : "#059669";
          const yHigh = priceY(bar.high);
          const yLow = priceY(bar.low);
          const yOpen = priceY(bar.open);
          const yClose = priceY(bar.close);
          const bodyTop = Math.min(yOpen, yClose);
          const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1);
          const volumeHeightPx = (bar.volume / maxVolume) * volumeHeight;
          return (
            <g key={`${bar.ts}-${index}`}>
              <line x1={x} x2={x} y1={yHigh} y2={yLow} stroke={color} strokeWidth={1.2} />
              <rect
                x={x - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                fill={isUp ? "#fff1f2" : color}
                stroke={color}
                strokeWidth={1}
              />
              <rect
                x={x - candleWidth / 2}
                y={volumeTop + volumeHeight - volumeHeightPx}
                width={candleWidth}
                height={volumeHeightPx}
                fill={isUp ? "#fecdd3" : "#a7f3d0"}
              />
            </g>
          );
        })}
        {activeVisibleAverages.map((average) => {
          const path = buildAveragePath(average.values);
          return path ? (
            <path
              key={average.label}
              d={path}
              fill="none"
              stroke={average.color}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.4}
            />
          ) : null;
        })}
        {selectedVisibleIndex >= 0 && (
          <g pointerEvents="none">
            {(() => {
              const selectedBar = visibleBars[selectedVisibleIndex];
              const selectedX = left + selectedVisibleIndex * step + step / 2;
              return (
                <>
                  <rect
                    x={selectedX - step / 2}
                    y={chartTop}
                    width={step}
                    height={volumeTop + volumeHeight - chartTop}
                    fill="#dbeafe"
                    opacity={0.3}
                  />
                  <line
                    x1={selectedX}
                    x2={selectedX}
                    y1={chartTop}
                    y2={volumeTop + volumeHeight}
                    stroke="#2563eb"
                    strokeDasharray="4 4"
                    strokeWidth={1.2}
                  />
                  <circle
                    cx={selectedX}
                    cy={priceY(selectedBar.close)}
                    r={4.5}
                    fill="#2563eb"
                    stroke="#ffffff"
                    strokeWidth={2}
                  />
                </>
              );
            })()}
          </g>
        )}
        {visibleBars.map((bar, index) => {
          const x = left + index * step + step / 2;
          const dividendEventsForBar = dividendMarkersByIndex.get(index) ?? [];
          const limitMarker = limitMarkerForBar(bar, limitThreshold, timeframe);
          const yHigh = priceY(bar.high);
          const yLow = priceY(bar.low);
          const dividendBadgeY = Math.max(chartTop + 2, yHigh - 36);
          return (
            <g key={`${bar.ts}-${index}-markers`}>
              {dividendEventsForBar.length > 0 && (
                <g>
                  <title>
                    {dividendEventsForBar.map((event) =>
                      `除权除息日 ${formatDataDate(event.exDividendDate)}：${event.planProfile ?? "分红送配"}`
                    ).join("；")}
                  </title>
                  <line
                    x1={x}
                    x2={x}
                    y1={chartTop}
                    y2={volumeTop + volumeHeight}
                    stroke="#f59e0b"
                    strokeDasharray="4 4"
                    strokeWidth={1}
                    opacity={0.85}
                  />
                  <circle
                    cx={x}
                    cy={Math.max(chartTop + 24, yHigh)}
                    r={4.8}
                    fill="#f59e0b"
                    stroke="#fff7ed"
                    strokeWidth={2}
                  />
                  <g transform={`translate(${x - 13}, ${dividendBadgeY})`}>
                    <rect
                      width={26}
                      height={18}
                      rx={4}
                      fill="#fffbeb"
                      stroke="#f59e0b"
                      strokeWidth={1}
                    />
                    <text
                      x={13}
                      y={13}
                      textAnchor="middle"
                      className="fill-amber-700 text-[11px] font-bold"
                    >
                      除
                    </text>
                  </g>
                </g>
              )}
              {limitMarker && (
                <g transform={`translate(${x - 11}, ${limitMarker === "up" ? Math.max(chartTop + 2, yHigh - 22) : Math.min(chartTop + chartHeight - 14, yLow + 8)})`}>
                  <rect
                    width={22}
                    height={16}
                    rx={3}
                    fill={limitMarker === "up" ? "#fee2e2" : "#dcfce7"}
                    stroke={limitMarker === "up" ? "#ef4444" : "#22c55e"}
                    strokeWidth={0.8}
                  />
                  <text
                    x={11}
                    y={11.5}
                    textAnchor="middle"
                    className={cn(
                      "text-[10px] font-semibold",
                      limitMarker === "up" ? "fill-red-600" : "fill-emerald-600"
                    )}
                  >
                    <title>
                      {limitMarker === "up" ? "涨停" : "跌停"}：{formatSignedPercent(bar.changePercent)}
                    </title>
                    {limitMarker === "up" ? "涨" : "跌"}
                  </text>
                </g>
              )}
            </g>
          );
        })}
        <text x={left} y={dateLabelY} className="fill-slate-500 text-[14px]">
          {formatDataDate(visibleBars[0]?.ts)}
        </text>
        <text x={width - right} y={dateLabelY} textAnchor="end" className="fill-slate-500 text-[14px]">
          {formatDataDate(visibleBars.at(-1)?.ts)}
        </text>
      </svg>
      <div className="mt-2 h-1.5 rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-blue-500"
          style={{
            marginLeft: `${rangeLeftPct}%`,
            width: `${Math.max(4, rangeWidthPct)}%`,
          }}
        />
      </div>
    </div>
  );
}

function StockKlineDetail({
  member,
  universe,
}: {
  member: StrategyUniverseMember;
  universe: StrategyUniverse;
}) {
  const initialTimeframe = KLINE_TIMEFRAMES.some((option) => option.id === universe.defaultTimeframe)
    ? (universe.defaultTimeframe as KlineTimeframe)
    : "daily";
  const adjustment = universe.defaultAdjustment || "qfq";
  const [detailTimeframe, setDetailTimeframe] = useState<KlineTimeframe>("daily");
  const [detail, setDetail] = useState<StrategyLocalKlineResponse | null>(null);
  const [selectedBarTs, setSelectedBarTs] = useState<string | null>(null);
  const [dividendEvents, setDividendEvents] = useState<StrategyDividendEvent[]>([]);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRequestIdRef = useRef(0);

  const loadDetail = useCallback(async (timeframe: KlineTimeframe) => {
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    setDetailTimeframe(timeframe);
    setSelectedBarTs(null);
    setDetailError(null);

    const cached = readCachedKlineDetail(member.symbol, timeframe, adjustment);
    if (cached) {
      setDetail(cached);
      setSelectedBarTs(cached.bars.at(-1)?.ts ?? null);
      setIsLoadingDetail(false);
      return;
    }

    setDetail(null);
    setIsLoadingDetail(true);
    try {
      const nextDetail = await loadCachedKlineDetail(member.symbol, timeframe, adjustment);
      if (detailRequestIdRef.current !== requestId) return;
      setDetail(nextDetail);
      setSelectedBarTs(nextDetail.bars.at(-1)?.ts ?? null);
    } catch (error) {
      if (detailRequestIdRef.current !== requestId) return;
      setDetailError(error instanceof Error ? error.message : String(error));
    } finally {
      if (detailRequestIdRef.current === requestId) {
        setIsLoadingDetail(false);
      }
    }
  }, [adjustment, member.symbol]);

  const loadDividendEvents = useCallback(async () => {
    try {
      setDividendEvents(await loadCachedDividendEvents(member.symbol));
    } catch {
      setDividendEvents([]);
    }
  }, [member.symbol]);

  useEffect(() => {
    void loadDetail(initialTimeframe);
  }, [initialTimeframe, loadDetail]);

  useEffect(() => {
    void loadDividendEvents();
  }, [loadDividendEvents]);

  const selectedBarIndex = detail
    ? detail.bars.findIndex((bar) => bar.ts === selectedBarTs)
    : -1;
  const resolvedSelectedBarIndex = detail
    ? selectedBarIndex >= 0 ? selectedBarIndex : detail.bars.length - 1
    : -1;
  const selectedBar = detail && resolvedSelectedBarIndex >= 0
    ? detail.bars[resolvedSelectedBarIndex]
    : null;
  const selectedReturnPct = detail && resolvedSelectedBarIndex >= 0
    ? returnPctForBar(detail.bars, resolvedSelectedBarIndex)
    : null;
  const selectedDateLabel = selectedBar ? formatDataDate(selectedBar.ts) : null;
  const metricCards = detail && selectedBar
    ? [
        { label: "收盘", value: formatNumberValue(selectedBar.close) },
        {
          label: "涨跌",
          value: formatSignedPercent(selectedReturnPct),
          className: signedToneClass(selectedReturnPct),
        },
        { label: "开盘", value: formatNumberValue(selectedBar.open) },
        { label: "最高", value: formatNumberValue(selectedBar.high), className: "text-red-600" },
        { label: "最低", value: formatNumberValue(selectedBar.low), className: "text-emerald-600" },
        { label: "振幅", value: formatPercentValue(selectedBar.amplitude) },
        { label: "换手", value: formatPercentValue(selectedBar.turnover) },
        { label: "成交量", value: formatLargeValue(selectedBar.volume, 1) },
        { label: "成交额", value: formatLargeValue(selectedBar.amount, 1) },
        ...MOVING_AVERAGE_CONFIGS.map((config) => ({
          label: config.label,
          value: formatNumberValue(movingAverageAtIndex(detail.bars, config.period, resolvedSelectedBarIndex)),
          className: config.textClass,
        })),
      ]
    : [];

  return (
    <div className="border-t border-slate-100 bg-slate-50/70 p-5">
      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-2">
            <p className="shrink-0 text-sm font-semibold text-slate-950">
              K 线详情
              {selectedDateLabel && (
                <span className="ml-2 align-middle text-xs font-medium text-slate-500">
                  {selectedDateLabel}
                </span>
              )}
            </p>
            {detail && (
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                {metricCards.map((item) => (
                  <div key={item.label} className="inline-flex items-baseline gap-1.5 rounded-md bg-slate-50 px-2.5 py-1.5">
                    <span className="text-[13px] text-slate-500">{item.label}</span>
                    <span className={cn("text-base font-semibold tabular-nums text-slate-950", item.className)}>
                      {item.value}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="inline-flex h-9 rounded-md border border-slate-200 bg-slate-50 p-1">
            {KLINE_TIMEFRAMES.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  if (option.id !== detailTimeframe) {
                    void loadDetail(option.id);
                  }
                }}
                disabled={isLoadingDetail}
                className={cn(
                  "rounded px-3 text-sm font-medium transition-colors",
                  detailTimeframe === option.id
                    ? "bg-white text-blue-700 shadow-sm"
                    : "text-slate-500 hover:text-slate-700",
                  isLoadingDetail && "cursor-wait opacity-70"
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {isLoadingDetail ? (
          <div className="flex h-80 items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在读取本地 TimescaleDB K 线...
          </div>
        ) : detailError ? (
          <div className="m-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {detailError}
          </div>
        ) : detail ? (
          <div className="p-5">
            <KlineMiniChart
              bars={detail.bars}
              dividendEvents={dividendEvents}
              symbol={member.symbol}
              name={member.name}
              exchange={member.exchange}
              timeframe={detailTimeframe}
              selectedBarTs={selectedBar?.ts ?? null}
              onSelectBar={(bar) => setSelectedBarTs(bar.ts)}
              onResetSelection={() => setSelectedBarTs(detail.bars.at(-1)?.ts ?? null)}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function sectorSignalLabel(signal: StrategySectorCapitalFlowItem["signal"]) {
  if (signal === "warming") return "资金升温";
  if (signal === "cooling") return "资金转冷";
  if (signal === "neutral") return "观察";
  return "样本不足";
}

function sectorSignalClass(signal: StrategySectorCapitalFlowItem["signal"]) {
  if (signal === "warming") return "border-red-200 bg-red-50 text-red-700";
  if (signal === "cooling") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (signal === "neutral") return "border-blue-200 bg-blue-50 text-blue-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

function SectorCapitalFlowView({ data }: { data: StrategyDashboardData }) {
  const primaryUniverse =
    data.research.universes.find((universe) => universe.id === data.research.primaryUniverseId) ??
    data.research.universes.find((universe) => universe.stockCount > 0) ??
    data.research.universes[0] ??
    null;
  const [selectedUniverseId, setSelectedUniverseId] = useState(primaryUniverse?.id ?? data.research.primaryUniverseId);
  const [items, setItems] = useState<StrategySectorCapitalFlowItem[]>([]);
  const [proxyNote, setProxyNote] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedUniverse =
    data.research.universes.find((universe) => universe.id === selectedUniverseId) ??
    primaryUniverse;

  const loadSectorFlow = useCallback(async () => {
    if (!selectedUniverse) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "sector-capital-flow",
          universeId: selectedUniverse.id,
          limit: 50,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? "读取板块资金失败");
      }
      setItems((payload.data?.items ?? []) as StrategySectorCapitalFlowItem[]);
      setProxyNote(String(payload.data?.proxyNote ?? ""));
    } catch (loadError) {
      setItems([]);
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setIsLoading(false);
    }
  }, [selectedUniverse]);

  useEffect(() => {
    void loadSectorFlow();
  }, [loadSectorFlow]);

  const leadingItems = items.slice(0, 6);
  const warmingCount = items.filter((item) => item.signal === "warming").length;
  const totalProxyAmount = items.reduce((sum, item) => sum + (finiteNumber(item.proxyNetAmount) ?? 0), 0);

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-950">板块资金与主力动向</h2>
              <Badge variant="outline" className="bg-white text-slate-500">
                {items.length ? `${items.length} 个板块标签` : "等待数据"}
              </Badge>
              {isLoading && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
            </div>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
              用本地 TimescaleDB 中的板块标签、成交额、换手、上涨占比和 20 日强弱，先构建板块资金热度代理；真实 DDE/主力净流入字段接入后再替换为资金流口径。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {data.research.universes.filter((universe) => universe.stockCount > 0).map((universe) => (
              <button
                key={universe.id}
                type="button"
                onClick={() => setSelectedUniverseId(universe.id)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
                  selectedUniverse?.id === universe.id
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                )}
              >
                {universe.name}
              </button>
            ))}
            <Button variant="outline" size="sm" onClick={() => void loadSectorFlow()} disabled={isLoading}>
              <RefreshCcw className={cn("h-4 w-4", isLoading && "animate-spin")} />
              刷新
            </Button>
          </div>
        </div>

        {error && (
          <div className="border-b border-amber-100 bg-amber-50 px-5 py-3 text-sm text-amber-700">
            {error}
          </div>
        )}

        <div className="grid gap-3 border-b border-slate-100 px-5 py-4 md:grid-cols-4">
          <div className="rounded-md bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">升温板块</p>
            <p className="mt-1 text-xl font-bold tabular-nums text-slate-950">{warmingCount}</p>
          </div>
          <div className="rounded-md bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">方向成交额代理</p>
            <p className={cn("mt-1 text-xl font-bold tabular-nums", signedToneClass(totalProxyAmount))}>
              {formatLargeValue(totalProxyAmount, 1)}
            </p>
          </div>
          <div className="rounded-md bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">覆盖股票池</p>
            <p className="mt-1 text-xl font-bold tabular-nums text-slate-950">{selectedUniverse?.memberCount ?? "-"}</p>
          </div>
          <div className="rounded-md bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">真实主力字段</p>
            <p className="mt-1 text-xl font-bold text-amber-600">待接入</p>
          </div>
        </div>

        <div className="grid gap-4 px-5 py-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="w-full min-w-[1120px] text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">板块</th>
                  <th className="px-3 py-3 font-medium">信号</th>
                  <th className="px-3 py-3 font-medium">方向成交额代理</th>
                  <th className="px-3 py-3 font-medium">最新成交额</th>
                  <th className="px-3 py-3 font-medium">量能比</th>
                  <th className="px-3 py-3 font-medium">上涨占比</th>
                  <th className="px-3 py-3 font-medium">20日强弱</th>
                  <th className="px-3 py-3 font-medium">换手</th>
                  <th className="px-3 py-3 font-medium">样本</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr key={item.sector} className="align-top hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-950">{item.sector}</p>
                      <p className="mt-1 text-xs text-slate-400">{item.coveredCount}/{item.memberCount} 已覆盖 · 涨停 {item.limitUpCount}</p>
                    </td>
                    <td className="px-3 py-3">
                      <Badge variant="outline" className={sectorSignalClass(item.signal)}>
                        {sectorSignalLabel(item.signal)}
                      </Badge>
                    </td>
                    <td className="px-3 py-3">
                      <p className={cn("font-semibold tabular-nums", signedToneClass(item.proxyNetAmount))}>
                        {formatLargeValue(item.proxyNetAmount, 1)}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">上涨为正、下跌为负</p>
                    </td>
                    <td className="px-3 py-3 font-semibold tabular-nums text-slate-900">
                      {formatLargeValue(item.latestAmount, 1)}
                    </td>
                    <td className="px-3 py-3 font-semibold tabular-nums text-slate-900">
                      {finiteNumber(item.amountRatio20d) === null ? "-" : `${formatNumberValue(item.amountRatio20d, 2)}x`}
                    </td>
                    <td className="px-3 py-3">
                      <p className="font-semibold tabular-nums text-slate-900">{formatPercentValue(item.risingRatio)}</p>
                      <p className="mt-1 text-xs text-slate-400">{item.risingCount} 只上涨</p>
                    </td>
                    <td className={cn("px-3 py-3 font-semibold tabular-nums", signedToneClass(item.strength20dPct))}>
                      {formatSignedPercent(item.strength20dPct)}
                    </td>
                    <td className="px-3 py-3 font-semibold tabular-nums text-slate-900">
                      {formatPercentValue(item.avgTurnover20d)}
                    </td>
                    <td className="px-3 py-3">
                      <p className="line-clamp-2 max-w-[220px] text-xs leading-5 text-slate-500">
                        {item.topSymbols.join("、") || "-"}
                      </p>
                    </td>
                  </tr>
                ))}
                {!items.length && (
                  <tr>
                    <td colSpan={9} className="px-5 py-12 text-center text-sm text-slate-500">
                      {isLoading ? "正在读取板块资金代理..." : "暂无板块资金数据"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <aside className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-950">如何探查主力资金</p>
              <div className="mt-3 space-y-3 text-sm leading-6 text-slate-600">
                <p><span className="font-semibold text-slate-900">先看板块：</span>板块内多数股票上涨、成交额放大且 20 日强弱转正，说明资金不是孤立拉一只票。</p>
                <p><span className="font-semibold text-slate-900">再看龙头：</span>涨停数、成交额排名和强弱排名同步靠前，才更像主动资金聚集。</p>
                <p><span className="font-semibold text-slate-900">最后看连续性：</span>DDE/主力净流入至少观察 3 日，单日大额流入可能是对倒或出货。</p>
              </div>
            </div>
            <div className="rounded-lg border border-amber-100 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">当前口径说明</p>
              <p className="mt-2 text-sm leading-6 text-amber-800">
                {proxyNote || "当前为成交额、换手、上涨占比和20日强弱聚合出的资金热度代理，不是 DDE/主力净流入真实字段。"}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-950">后续真实字段</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {["主力净流入", "超大单净额", "大单净额", "DDE 大单金额", "DDE 大单净量", "3/5日资金连续性"].map((item) => (
                  <Badge key={item} variant="outline" className="border-blue-100 bg-blue-50 text-blue-700">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          </aside>
        </div>

        {leadingItems.length > 0 && (
          <div className="border-t border-slate-100 px-5 py-4">
            <p className="text-sm font-semibold text-slate-900">当前最值得关注的板块</p>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {leadingItems.map((item) => (
                <div key={item.sector} className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-slate-950">{item.sector}</p>
                    <Badge variant="outline" className={sectorSignalClass(item.signal)}>
                      {sectorSignalLabel(item.signal)}
                    </Badge>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-slate-400">方向额</span>
                      <p className={cn("font-semibold tabular-nums", signedToneClass(item.proxyNetAmount))}>
                        {formatLargeValue(item.proxyNetAmount, 1)}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-400">强弱</span>
                      <p className={cn("font-semibold tabular-nums", signedToneClass(item.strength20dPct))}>
                        {formatSignedPercent(item.strength20dPct)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

const FINANCIAL_KNOWLEDGE_ITEMS = [
  {
    category: "资金流",
    title: "DDE 大单金额",
    formula: "大单买入金额 - 大单卖出金额",
    meaning: "衡量大资金在某只股票上的净流入方向。不同数据源对“大单”的阈值会不同，落库时必须保留 provider 和 raw_payload。",
    decision: "连续为正通常代表资金承接更强，适合和涨停、均线多头、放量一起使用；单日转负可作为接力策略的降权或退出信号。",
    caveats: ["不要只看单日", "必须看成交额覆盖", "需要区分日终数据和盘中快照"],
  },
  {
    category: "资金流",
    title: "大单净量",
    formula: "大单买入量 - 大单卖出量；部分源会再除以流通盘",
    meaning: "更偏成交数量口径，适合做同日股票间排序。若用百分比口径，大小盘之间更可比。",
    decision: "用于候选股排序时，比简单涨幅更能体现资金主动性；但需要和价格是否过热一起约束，避免追高。",
    caveats: ["不同源口径不可直接混排", "小盘股容易被极端成交放大", "缺失时不能回填为 0"],
  },
  {
    category: "趋势",
    title: "移动均线 MA",
    formula: "MA(N) = 最近 N 个交易日收盘价之和 / N",
    meaning: "MA5/10 反映短线成本，MA20/30 反映月度趋势，MA60 更接近中期趋势。",
    decision: "股价在 MA5 上方且 MA5 > MA10 > MA20 > MA30 > MA60，通常说明短中期成本逐级抬升，是趋势选股的重要过滤。",
    caveats: ["均线滞后", "震荡市容易反复假信号", "除权复权口径必须统一"],
  },
  {
    category: "事件",
    title: "涨停/跌停",
    formula: "涨停价约等于前收盘价 * (1 + 涨跌幅限制)",
    meaning: "主板、创业板、科创板、北交所、ST 的涨跌幅规则不同，所以策略里要明确剔除或分层处理。",
    decision: "近 4 日涨停至少 1 次说明短线情绪被激活；当日已经涨停则可能无法合理买入，应从候选中剔除或标记不可成交。",
    caveats: ["涨停不等于可以买到", "一字板需要盘口数据", "不同板块涨跌幅制度不同"],
  },
  {
    category: "波动",
    title: "ATR 真实波幅",
    formula: "TR = max(高-低, |高-昨收|, |低-昨收|)，ATR = TR 的 N 日均值",
    meaning: "ATR 衡量一只股票近期正常波动范围，比简单涨跌幅更适合做止损和买入区间。",
    decision: "买入价、止损价、追高上限可以用 ATR 反推，例如止损距离 1.2 ATR，止盈至少 2R。",
    caveats: ["突发事件会抬高 ATR", "低价股 ATR 百分比更重要", "不能替代流动性检查"],
  },
  {
    category: "流动性",
    title: "换手率",
    formula: "换手率 = 成交量 / 流通股本 * 100%",
    meaning: "反映筹码交换程度。高换手说明交易活跃，也可能说明分歧很大。",
    decision: "接力策略需要最低换手确认活跃度；但极端高换手叠加放量阴线，往往是短线转弱信号。",
    caveats: ["流通股本口径要稳定", "新股和小盘股需单独阈值", "高换手不必然上涨"],
  },
  {
    category: "流动性",
    title: "成交额",
    formula: "成交额 = 成交价格 * 成交量 的日内累计",
    meaning: "比成交量更适合跨价格区间比较流动性，策略筛选时应设置最低成交额门槛。",
    decision: "成交额不足的股票，即使命中 DDE 或均线条件，也可能无法承载实际交易规模。",
    caveats: ["放量也可能是出货", "需要和涨跌幅方向一起看", "低成交额样本回测容易虚高"],
  },
  {
    category: "开盘强弱",
    title: "高开与回踩承接",
    formula: "开盘涨幅 = (今日开盘价 - 昨日收盘价) / 昨日收盘价 * 100%",
    meaning: "高开代表情绪延续，回踩前收或 MA5 不破代表承接较强。",
    decision: "涨停次日策略里，开盘价大于昨收是强势条件；高开过多则成本失控，需要等待回踩或放弃。",
    caveats: ["日线只能粗略判断", "真实承接要分钟线", "集合竞价金额很关键"],
  },
  {
    category: "风控",
    title: "R 倍数与收益风险比",
    formula: "R = 买入价 - 止损价；收益风险比 = (目标价 - 买入价) / R",
    meaning: "把买入、止损、止盈统一成可比较的风险单位，避免只看涨幅不看亏损。",
    decision: "建议买入前先算止损，至少看到 2R 空间再考虑入场；达到 2R 可先减仓，再用均线跟踪。",
    caveats: ["止损不能事后移动放宽", "目标价不应凭感觉设置", "滑点会降低真实收益风险比"],
  },
] as const;

function FinancialKnowledgeView() {
  const categories = Array.from(new Set(FINANCIAL_KNOWLEDGE_ITEMS.map((item) => item.category)));

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <BookOpen className="h-4 w-4 text-blue-600" />
            指标公式
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            统一沉淀 MA、DDE、ATR、换手率、涨停和收益风险比的计算口径。
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <BarChart3 className="h-4 w-4 text-emerald-600" />
            决策影响
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            每个指标都对应选股、买入成本、卖出风控或流动性过滤，不做孤立解释。
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <ShieldCheck className="h-4 w-4 text-amber-600" />
            使用边界
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            明确常见误用和数据口径差异，避免把单个信号误解成交易结论。
          </p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-slate-900">知识分类</p>
          <div className="mt-3 space-y-2">
            {categories.map((category) => {
              const count = FINANCIAL_KNOWLEDGE_ITEMS.filter((item) => item.category === category).length;
              return (
                <div key={category} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
                  <span className="font-medium text-slate-700">{category}</span>
                  <span className="tabular-nums text-slate-400">{count}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
            DDE 和大单净量必须保留数据源口径；不同供应商阈值不同，不能直接混用。
          </div>
        </aside>

        <div className="space-y-3">
          {FINANCIAL_KNOWLEDGE_ITEMS.map((item) => (
            <article key={item.title} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-slate-50 text-slate-500">{item.category}</Badge>
                    <h3 className="text-base font-bold text-slate-950">{item.title}</h3>
                  </div>
                  <code className="mt-2 block rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs leading-5 text-slate-800">
                    {item.formula}
                  </code>
                </div>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1.2fr_1fr]">
                <div className="rounded-md bg-slate-50 p-3">
                  <p className="text-xs font-semibold text-slate-500">含义</p>
                  <p className="mt-1 text-sm leading-6 text-slate-700">{item.meaning}</p>
                </div>
                <div className="rounded-md bg-blue-50 p-3">
                  <p className="text-xs font-semibold text-blue-600">对决策的影响</p>
                  <p className="mt-1 text-sm leading-6 text-blue-900">{item.decision}</p>
                </div>
                <div className="rounded-md bg-amber-50 p-3">
                  <p className="text-xs font-semibold text-amber-700">注意事项</p>
                  <div className="mt-1 space-y-1 text-sm leading-6 text-amber-900">
                    {item.caveats.map((caveat) => <p key={caveat}>{caveat}</p>)}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────
export default function StrategyPlatformClient({ initialData }: Props) {
  const router = useRouter();
  const [data, setData] = useState(initialData);
  const [selectedId, setSelectedId] = useState(initialData.templates[0]?.id ?? "");
  const [view, setView] = useState<StrategyView>("universe");
  const [keyword, setKeyword] = useState("");
  const [symbol, setSymbol] = useState(initialData.templates[0]?.defaultSymbols[0] ?? "");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isAddingMember, setIsAddingMember] = useState(false);
  const [runningScanId, setRunningScanId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [dialogStrategy, setDialogStrategy] = useState<StrategyCatalogItem | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const filteredTemplates = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.templates.filter((t) => {
      if (!lower) return true;
      return [
        t.id,
        t.name,
        t.family,
        strategyKindLabel(t.kind),
        t.description,
        t.capabilityId,
        ...t.defaultSymbols,
        ...t.dataDependencies,
        ...t.riskControls,
        ...(t.selectionRules ?? []).flatMap((rule) => [rule.label, rule.description]),
        ...(t.entryRules ?? []).flatMap((rule) => [rule.label, rule.description]),
        ...(t.exitRules ?? []).flatMap((rule) => [rule.label, rule.description]),
        ...(t.rankingRules ?? []),
      ]
        .join(" ").toLowerCase().includes(lower);
    });
  }, [data.templates, keyword]);

  const families = useMemo(() => Array.from(new Set(data.templates.map((t) => t.family))), [data.templates]);
  const [familyFilter, setFamilyFilter] = useState<string | null>(null);
  const displayTemplates = familyFilter ? filteredTemplates.filter((t) => t.family === familyFilter) : filteredTemplates;

  const selectedTemplate =
    data.templates.find((t) => t.id === selectedId) ?? filteredTemplates[0] ?? data.templates[0] ?? null;

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
    const strategy = dialogStrategy || selectedTemplate;
    if (!strategy || isCreating) return;
    setIsCreating(true);
    setToast(null);
    try {
      const pr = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ templateId: strategy.id, symbol }),
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

  const addUniverseMember = async (universeId: string, query: string) => {
    if (isAddingMember) return;
    setIsAddingMember(true);
    setToast(null);
    try {
      const r = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "add-universe-member",
          universeId,
          query,
          syncHistory: false,
        }),
      });
      const payload = await r.json();
      if (!r.ok || !payload.success) throw new Error(payload.error ?? "加入股票池失败");
      await refresh();
      const member = payload.data?.member;
      setToast({
        type: "success",
        message: `${member?.name ?? member?.symbol ?? query} 已加入股票池`,
      });
    } catch (error) {
      setToast({ type: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsAddingMember(false);
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
        subtitle={`股票池、策略目录、板块资金和金融知识 · 生成于 ${formatDate(data.generatedAt)}`}
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
          </div>
        }
      />

      <main className="mx-auto w-full max-w-[1900px] space-y-5 px-3 py-6 lg:px-4">
        {toast && (
          <div className={cn("rounded-md border px-4 py-3 text-sm shadow-sm",
            toast.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"
          )}>{toast.message}</div>
        )}
        {/* ── Universe Tab ─────────────────────────────── */}
        {view === "universe" && (
          <UniverseView data={data} isAdding={isAddingMember} onAdd={addUniverseMember} />
        )}

        {/* ── Catalog Tab: Strategy Plan Library ────────── */}
        {view === "catalog" && (
          <>
            {/* Search + family filter (merged) */}
            <div className="space-y-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="relative min-w-[260px] flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="搜索选股条件、买入卖出、DDE、均线..." className="h-9 rounded-lg border-slate-200/80 bg-white pl-9 shadow-sm" />
                </div>
                <div className="flex items-center gap-0.5 rounded-lg border border-slate-200/80 bg-slate-50 p-0.5 shadow-sm">
                  <button type="button" onClick={() => setFamilyFilter(null)}
                    className={cn(
                      "relative rounded-md px-2.5 py-1 text-xs font-medium transition-all duration-150",
                      !familyFilter
                        ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/50"
                        : "text-slate-500 hover:text-slate-700"
                    )}>
                    全部<span className="ml-1 text-slate-400 tabular-nums">{data.templates.length}</span>
                  </button>
                  {families.map((fam) => {
                    const count = data.templates.filter((t) => t.family === fam).length;
                    return (
                      <button key={fam} type="button" onClick={() => setFamilyFilter(fam)}
                        className={cn(
                          "relative rounded-md px-2.5 py-1 text-xs font-medium transition-all duration-150",
                          familyFilter === fam
                            ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/50"
                            : "text-slate-500 hover:text-slate-700"
                        )}>
                        {fam}<span className="ml-1 text-slate-400 tabular-nums">{count}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Filter active indicator */}
              {familyFilter && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <div className="h-1 w-1 rounded-full bg-blue-400" />
                  已筛选 <span className="font-semibold text-slate-700">{familyFilter}</span>
                  <button type="button" onClick={() => setFamilyFilter(null)} className="ml-1 text-slate-400 hover:text-slate-600 underline underline-offset-2">清除</button>
                  <span className="text-slate-300">·</span>
                  <span className="tabular-nums">{displayTemplates.length} 个策略方案</span>
                </div>
              )}
            </div>

            {/* Strategy table */}
            {displayTemplates.length === 0 ? (
              <EmptyState title={keyword || familyFilter ? "没有匹配的策略方案" : "暂无策略方案"} description={keyword ? "尝试其他关键词" : "请运行策略扫描生成模板数据"} className="border-0" />
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200/80 bg-slate-50/70 p-2 shadow-sm">
                <table className="w-full min-w-[1120px] border-separate border-spacing-y-1.5 text-left">
                  <thead className="text-[11px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="w-1 rounded-l-lg bg-slate-50 py-2.5 pl-4 pr-0 font-medium" />
                      <th className="bg-slate-50 px-4 py-2.5 font-medium">策略方案</th>
                      <th className="bg-slate-50 px-3 py-2.5 font-medium">核心逻辑</th>
                      <th className="bg-slate-50 px-3 py-2.5 font-medium">数据状态</th>
                      <th className="hidden bg-slate-50 px-3 py-2.5 font-medium lg:table-cell">参数口径</th>
                      <th className="rounded-r-lg bg-slate-50 px-4 py-2.5 font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {displayTemplates.map((t) => (
                      <StrategyRow
                        key={t.id}
                        strategy={t}
                        onClick={() => {
                          setDialogStrategy(t);
                          setSymbol(t.defaultSymbols[0] ?? "");
                          setDialogOpen(true);
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Strategy Detail Dialog */}
            <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
                <Dialog.Content className="fixed left-[50%] top-[50%] z-50 max-h-[85vh] w-[96vw] max-w-[680px] translate-x-[-50%] translate-y-[-50%] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
                  {dialogStrategy && (
                    <div className="flex max-h-[85vh] flex-col">
                      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
                        <div>
                          <Dialog.Title className="text-lg font-bold text-slate-900">{dialogStrategy.name}</Dialog.Title>
                          <Dialog.Description className="mt-1 text-sm text-slate-500">
                            {dialogStrategy.family} · {dialogStrategy.timeframe} · {dialogStrategy.readiness.summary}
                          </Dialog.Description>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", statusClass(dialogStrategy.status))}>{statusLabel(dialogStrategy.status)}</span>
                          <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", riskClass(dialogStrategy.readiness.riskLevel))}>{dialogStrategy.readiness.score}分</span>
                          <Dialog.Close className="ml-2 rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600">
                            <X className="h-5 w-5" />
                          </Dialog.Close>
                        </div>
                      </div>

                      <div className="flex-1 space-y-6 overflow-y-auto p-6">
                        <p className="text-sm leading-6 text-slate-600">{dialogStrategy.description}</p>

                        {dialogStrategy.selectionRules?.length ? (
                          <section>
                            <h4 className="mb-3 text-sm font-semibold text-slate-900">选股条件</h4>
                            <div className="grid gap-2 sm:grid-cols-2">
                              {dialogStrategy.selectionRules.map((rule) => (
                                <div key={rule.label} className="rounded-lg border border-slate-200 bg-white p-3">
                                  <div className="flex items-center justify-between gap-2">
                                    <p className="text-sm font-semibold text-slate-900">{rule.label}</p>
                                    <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium", ruleStatusClass(rule.dataStatus))}>
                                      {ruleStatusLabel(rule.dataStatus)}
                                    </span>
                                  </div>
                                  <p className="mt-1 text-xs leading-5 text-slate-500">{rule.description}</p>
                                </div>
                              ))}
                            </div>
                          </section>
                        ) : null}

                        {dialogStrategy.entryRules?.length || dialogStrategy.exitRules?.length ? (
                          <section>
                            <h4 className="mb-3 text-sm font-semibold text-slate-900">买入与卖出价格计划</h4>
                            <div className="grid gap-3 md:grid-cols-2">
                              {dialogStrategy.entryRules?.length ? (
                                <div className="rounded-lg border border-slate-200">
                                  <div className="border-b border-slate-100 px-4 py-2 text-sm font-semibold text-slate-900">买入/成本控制</div>
                                  <div className="divide-y divide-slate-100">
                                    {dialogStrategy.entryRules.map((rule) => (
                                      <div key={rule.label} className="px-4 py-3">
                                        <div className="flex items-center justify-between gap-2">
                                          <p className="text-sm font-medium text-slate-800">{rule.label}</p>
                                          <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium", ruleStatusClass(rule.dataStatus))}>
                                            {ruleStatusLabel(rule.dataStatus)}
                                          </span>
                                        </div>
                                        <p className="mt-1 text-xs leading-5 text-slate-500">{rule.description}</p>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                              {dialogStrategy.exitRules?.length ? (
                                <div className="rounded-lg border border-slate-200">
                                  <div className="border-b border-slate-100 px-4 py-2 text-sm font-semibold text-slate-900">卖出/风控退出</div>
                                  <div className="divide-y divide-slate-100">
                                    {dialogStrategy.exitRules.map((rule) => (
                                      <div key={rule.label} className="px-4 py-3">
                                        <div className="flex items-center justify-between gap-2">
                                          <p className="text-sm font-medium text-slate-800">{rule.label}</p>
                                          <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium", ruleStatusClass(rule.dataStatus))}>
                                            {ruleStatusLabel(rule.dataStatus)}
                                          </span>
                                        </div>
                                        <p className="mt-1 text-xs leading-5 text-slate-500">{rule.description}</p>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          </section>
                        ) : null}

                        {dialogStrategy.rankingRules?.length ? (
                          <section>
                            <h4 className="mb-2 text-sm font-semibold text-slate-900">排序与输出</h4>
                            <div className="flex flex-wrap gap-2">
                              {dialogStrategy.rankingRules.map((rule) => (
                                <span key={rule} className="rounded-md border border-blue-100 bg-blue-50 px-2.5 py-1.5 text-xs font-medium text-blue-700">
                                  {rule}
                                </span>
                              ))}
                            </div>
                          </section>
                        ) : null}

                        {dialogStrategy.dataReadiness ? (
                          <section>
                            <h4 className="mb-3 text-sm font-semibold text-slate-900">数据可用性</h4>
                            <div className="grid gap-3 md:grid-cols-2">
                              <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 p-4">
                                <p className="mb-2 text-xs font-semibold text-emerald-700">已具备</p>
                                <div className="space-y-1 text-xs leading-5 text-emerald-800">
                                  {dialogStrategy.dataReadiness.ready.map((item) => <p key={item}>{item}</p>)}
                                </div>
                              </div>
                              <div className="rounded-lg border border-amber-100 bg-amber-50/70 p-4">
                                <p className="mb-2 text-xs font-semibold text-amber-700">待补齐</p>
                                <div className="space-y-1 text-xs leading-5 text-amber-800">
                                  {dialogStrategy.dataReadiness.missing.length
                                    ? dialogStrategy.dataReadiness.missing.map((item) => <p key={item}>{item}</p>)
                                    : <p>暂无关键缺口</p>}
                                </div>
                              </div>
                            </div>
                            {dialogStrategy.dataReadiness.notes.length ? (
                              <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
                                {dialogStrategy.dataReadiness.notes.map((item) => <p key={item}>{item}</p>)}
                              </div>
                            ) : null}
                          </section>
                        ) : null}

                        <section>
                          <h4 className="mb-3 text-sm font-semibold text-slate-900">参数配置</h4>
                          <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                            {dialogStrategy.parameterSchema.map((p) => (
                              <div key={p.key} className="flex items-start justify-between gap-4 px-4 py-3 text-sm">
                                <span className="shrink-0 font-medium text-slate-700">{p.label}</span>
                                <div className="text-right">
                                  <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-900">{p.value}{p.unit ?? ""}</span>
                                  <p className="mt-0.5 text-xs text-slate-400">{p.description}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </section>

                        <section>
                          <h4 className="mb-2 text-sm font-semibold text-slate-900">默认标的</h4>
                          <div className="flex flex-wrap gap-2">
                            {dialogStrategy.defaultSymbols.map((sym) => (
                              <span key={sym} className="rounded-md bg-slate-100 px-2.5 py-1.5 font-mono text-xs font-medium text-slate-700">{sym}</span>
                            ))}
                          </div>
                        </section>

                        <div className="grid gap-6 sm:grid-cols-2">
                          <section>
                            <h4 className="mb-2 text-sm font-semibold text-slate-900">评估指标</h4>
                            <div className="flex flex-wrap gap-1.5">
                              {dialogStrategy.evaluationMetrics.map((m) => (
                                <span key={m} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700">{m}</span>
                              ))}
                            </div>
                          </section>
                          <section>
                            <h4 className="mb-2 text-sm font-semibold text-slate-900">数据依赖</h4>
                            <div className="space-y-1">
                              {dialogStrategy.dataDependencies.map((ep) => (
                                <code key={ep} className="block truncate rounded bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600">{ep}</code>
                              ))}
                            </div>
                          </section>
                        </div>

                        <section>
                          <h4 className="mb-2 text-sm font-semibold text-slate-900">护栏与限制</h4>
                          <div className="space-y-2 rounded-lg border border-slate-200 p-4 text-sm">
                            {dialogStrategy.riskControls.map((item) => (
                              <div key={item} className="flex gap-2 text-slate-700">
                                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                                <span>{item}</span>
                              </div>
                            ))}
                            {dialogStrategy.limitations.map((item) => (
                              <div key={item} className="rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">{item}</div>
                            ))}
                          </div>
                        </section>

                        {dialogStrategy.backtestArchives.length > 0 && (
                          <section>
                            <h4 className="mb-3 text-sm font-semibold text-slate-900">回测归档</h4>
                            <div className="grid gap-3 sm:grid-cols-2">
                              {dialogStrategy.backtestArchives.map((a) => (
                                <div key={a.id} className="rounded-lg border border-slate-200 p-4">
                                  <div className="flex items-center justify-between gap-2">
                                    <p className="text-sm font-semibold text-slate-900">{a.title}</p>
                                    <Badge variant="outline" className="text-[10px]">{a.status}</Badge>
                                  </div>
                                  <p className="mt-1 text-xs text-slate-500">{a.symbol} · {a.period}</p>
                                  <div className="mt-3 grid grid-cols-2 gap-3">
                                    <div className="rounded-md bg-slate-50 px-3 py-2">
                                      <p className="text-[11px] text-slate-400">累计收益</p>
                                      <p className={cn("mt-0.5 text-lg font-bold tabular-nums", parseFloat(String(a.metrics.totalReturnPct ?? 0)) >= 0 ? "text-red-600" : "text-emerald-600")}>{a.metrics.totalReturnPct ?? "-"}%</p>
                                    </div>
                                    <div className="rounded-md bg-slate-50 px-3 py-2">
                                      <p className="text-[11px] text-slate-400">最大回撤</p>
                                      <p className="mt-0.5 text-lg font-bold tabular-nums text-emerald-600">{a.metrics.maxDrawdownPct ?? "-"}%</p>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </section>
                        )}

                        {dialogStrategy.linkedWorkspaces.length > 0 && (
                          <section>
                            <h4 className="mb-2 text-sm font-semibold text-slate-900">关联工作空间</h4>
                            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                              {dialogStrategy.linkedWorkspaces.map((ws) => (
                                <Link key={ws.id} href={`/${ws.id}/chat`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-slate-50">
                                  <div className="min-w-0"><p className="font-medium text-slate-900">{ws.name}</p><p className="text-xs text-slate-500">{ws.capabilityId} · {formatDate(ws.updatedAt ?? ws.createdAt)}</p></div>
                                  <ArrowRight className="h-4 w-4 text-slate-300" />
                                </Link>
                              ))}
                            </div>
                          </section>
                        )}
                      </div>

                      <div className="shrink-0 border-t border-slate-100 bg-slate-50/80 px-6 py-4">
                        <div className="flex items-center gap-3">
                          <Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="输入标的代码，例如 510300" className="h-10 max-w-[180px] bg-white" />
                          <Button onClick={createStrategyWorkspace} disabled={isCreating} className="flex-1 bg-blue-600 text-white hover:bg-blue-700">
                            {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                            基于此策略生成工作空间
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </>
        )}

        {view === "sectorFlow" && (
          <SectorCapitalFlowView data={data} />
        )}

        {view === "knowledge" && (
          <FinancialKnowledgeView />
        )}

        {/* ── Scans & Compare: Single-template view ──────── */}
        {(view === "scans" || view === "compare") && (
          <>
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
                        <Badge variant="outline" className={riskClass(selectedTemplate.readiness.riskLevel)}>{selectedTemplate.readiness.label}</Badge>
                        <Badge variant="outline" className={statusClass(selectedTemplate.status)}>{statusLabel(selectedTemplate.status)}</Badge>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{selectedTemplate.description}</p>
                    </div>
                  </div>
                </div>

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
          </>
        )}
      </main>
    </div>
  );
}
