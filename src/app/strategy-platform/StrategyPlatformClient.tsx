"use client";

import { Fragment, type FormEvent, type PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  CheckCircle2,
  Database,
  GitBranch,
  Loader2,
  Play,
  RefreshCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  SquareStack,
  TrendingUp,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  ListPlus,
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
import { cn } from "@/lib/utils";
import type {
  StrategyCatalogItem,
  StrategyDashboardData,
  StrategyDividendEvent,
  StrategyHistoryIngestionResult,
  StrategyIngestionJob,
  StrategyLocalKlineBar,
  StrategyLocalKlineResponse,
  StrategyUniverse,
  StrategyUniverseMember,
  StrategyUniverseMembersPage,
} from "@/lib/quant/strategies";

type Props = { initialData: StrategyDashboardData };
type StrategyView =
  | "universe"
  | "catalog"
  | "scans"
  | "compare";

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
function riskClass(level: StrategyCatalogItem["readiness"]["riskLevel"]) {
  if (level === "low") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (level === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
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
  return status || "-";
}

function jobStatusClass(status: string) {
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "partial") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "failed") return "border-red-200 bg-red-50 text-red-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

// ─── Sub-nav items ─────────────────────────────────────────────
const SUB_NAV_ITEMS: SubNavItem[] = [
  { id: "universe", label: "股票池", icon: <SquareStack className="h-4 w-4" /> },
  { id: "catalog", label: "策略目录", icon: <TrendingUp className="h-4 w-4" /> },
  { id: "scans", label: "参数扫描", icon: <SlidersHorizontal className="h-4 w-4" /> },
  { id: "compare", label: "结果对比", icon: <SquareStack className="h-4 w-4" /> },
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

// ─── Strategy Card (Catalog) ────────────────────────────────────
function StrategyCard({ strategy, onClick }: { strategy: StrategyCatalogItem; onClick: () => void }) {
  const paramSummary = strategy.parameterSchema.slice(0, 3).map((p) => `${p.label}=${p.value}${p.unit ?? ""}`).join(", ");
  const hasMoreParams = strategy.parameterSchema.length > 3;
  const bestArchive = strategy.backtestArchives.find((a) => a.status === "available");

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col rounded-lg border border-slate-200 bg-white p-5 text-left shadow-sm transition-all hover:border-blue-200 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-base font-bold text-slate-900 group-hover:text-blue-700 transition-colors">{strategy.name}</p>
          <p className="mt-0.5 text-xs text-slate-500">{strategy.family} · {strategy.timeframe}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", statusClass(strategy.status))}>{statusLabel(strategy.status)}</span>
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", riskClass(strategy.readiness.riskLevel))}>
            {strategy.readiness.riskLevel === "low" ? "低风险" : strategy.readiness.riskLevel === "medium" ? "中风险" : "高风险"}
          </span>
        </div>
      </div>
      <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-600">{strategy.description}</p>
      <div className="mt-3 flex items-center gap-1.5 text-xs text-slate-500">
        <SlidersHorizontal className="h-3 w-3 shrink-0" />
        <span className="truncate">{paramSummary}</span>
        {hasMoreParams && <span className="shrink-0 text-slate-400">+{strategy.parameterSchema.length - 3}</span>}
      </div>
      <div className="mt-auto flex items-center justify-between gap-3 pt-4">
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1"><Database className="h-3 w-3" />{strategy.dataDependencies.length} 数据源</span>
          <span className="flex items-center gap-1"><GitBranch className="h-3 w-3" />{strategy.linkedWorkspaces.length} 空间</span>
          {bestArchive && (
            <span className="flex items-center gap-1 text-emerald-600"><BarChart3 className="h-3 w-3" />{bestArchive.metrics.totalReturnPct != null ? `${bestArchive.metrics.totalReturnPct}%` : "已归档"}</span>
          )}
        </div>
        <ArrowRight className="h-4 w-4 text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-blue-500" />
      </div>
    </button>
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
  const [batchOffset, setBatchOffset] = useState(0);
  const [openingMemberSymbol, setOpeningMemberSymbol] = useState<string | null>(null);
  const [closingMemberSymbol, setClosingMemberSymbol] = useState<string | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openFrameRef = useRef<number | null>(null);

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

  const loadIngestionJobs = useCallback(async () => {
    if (!selectedUniverse) return;
    setIsLoadingJobs(true);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "ingestion-jobs",
          universeId: selectedUniverse.id,
          limit: 8,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error ?? "读取补数任务失败");
      }
      const jobs = (payload.data?.jobs ?? []) as StrategyIngestionJob[];
      setIngestionJobs(jobs);
      const latestJob = jobs.find((job) => (job.universeTotalSymbols ?? 0) > 1);
      if (latestJob?.nextOffset !== undefined && latestJob.nextOffset !== null) {
        setBatchOffset(latestJob.nextOffset);
      }
    } catch {
      setIngestionJobs([]);
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
  const latestUniverseBatchJob = ingestionJobs.find(
    (job) => (job.universeTotalSymbols ?? 0) > 1
  );

  const addMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedUniverse || !memberQuery.trim()) return;
    await onAdd(selectedUniverse.id, memberQuery.trim());
    setMemberQuery("");
    setMemberSearch("");
    setPage(1);
    setMemberReloadToken((value) => value + 1);
  };

  const runIngestionBatch = async () => {
    if (!selectedUniverse || isRunningBatch) return;
    setIsRunningBatch(true);
    setMemberError(null);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "run-ingestion-batch",
          universeId: selectedUniverse.id,
          offset: batchOffset,
          batchSize: 25,
          limit: 1260,
          lookbackYears: 5,
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
    } catch (error) {
      setMemberError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRunningBatch(false);
    }
  };

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
              {data.research.universes.length > 1 && (
                <div className="mt-3 flex flex-wrap gap-2">
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
              )}
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
          <div className="border-b border-slate-100 px-5 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-slate-50/60 px-4 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-slate-900">低频补数进度</p>
                  {isLoadingJobs && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
                  {latestUniverseBatchJob && (
                    <Badge variant="outline" className={jobStatusClass(latestUniverseBatchJob.status)}>
                      {jobStatusLabel(latestUniverseBatchJob.status)}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {selectedIsEtfUniverse
                    ? "Baostock 分批补充 ETF/指数成交额和换手率；估值字段仅 A 股股票有效，历史 K 线不会因为补数窗口而删除。"
                    : "Baostock 分批补充成交额、换手率、停牌/ST、涨跌停和估值字段；历史 K 线不会因为补数窗口而删除。"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {latestUniverseBatchJob ? (
                  <span className="text-xs text-slate-500">
                    {latestUniverseBatchJob.completedSymbols}/{latestUniverseBatchJob.totalSymbols} 标的 · {latestUniverseBatchJob.rowsUpserted.toLocaleString("zh-CN")} 行 · 下批 {batchOffset}
                  </span>
                ) : (
                  <span className="text-xs text-slate-500">尚未运行全池批次 · 下批 {batchOffset}</span>
                )}
                <Button variant="outline" size="sm" onClick={loadIngestionJobs} disabled={isLoadingJobs || isRunningBatch}>
                  <RefreshCcw className={cn("h-4 w-4", isLoadingJobs && "animate-spin")} />
                  刷新进度
                </Button>
                <Button size="sm" onClick={runIngestionBatch} disabled={isRunningBatch} className="bg-blue-600 text-white hover:bg-blue-700">
                  {isRunningBatch ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  补下一批
                </Button>
              </div>
            </div>
          </div>
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
                  <th className="w-[9%] px-3 py-3 font-medium">代码</th>
                  <th className="w-[28%] px-3 py-3 font-medium">所属板块</th>
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
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-slate-700">{member.symbol}</span>
                            <Badge variant="outline" className="bg-white text-slate-500">{member.exchange}</Badge>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          {displaySectorTags.length ? (
                            <div className="flex flex-wrap gap-1.5">
                              {displaySectorTags.map((tag) => (
                                <Badge key={tag} variant="outline" className="border-blue-100 bg-blue-50 text-blue-700">
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

  const loadDetail = useCallback(async (timeframe: KlineTimeframe) => {
    setDetailTimeframe(timeframe);
    setDetail(null);
    setSelectedBarTs(null);
    setDetailError(null);
    setIsLoadingDetail(true);
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "symbol-bars",
          symbol: member.symbol,
          timeframe,
          adjustment,
          limit: klineFetchLimit(timeframe),
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.error ?? "读取 K 线失败");
      const nextDetail = payload.data as StrategyLocalKlineResponse;
      setDetail(nextDetail);
      setSelectedBarTs(nextDetail.bars.at(-1)?.ts ?? null);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsLoadingDetail(false);
    }
  }, [adjustment, member.symbol]);

  const loadDividendEvents = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/quant/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "symbol-dividends",
          symbol: member.symbol,
          limit: 40,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.error ?? "读取分红事件失败");
      setDividendEvents((payload.data?.events ?? []) as StrategyDividendEvent[]);
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
  const [sheetStrategy, setSheetStrategy] = useState<StrategyCatalogItem | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const filteredTemplates = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.templates.filter((t) => {
      if (!lower) return true;
      return [t.id, t.name, t.family, t.description, t.capabilityId, ...t.defaultSymbols, ...t.dataDependencies, ...t.riskControls]
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
    const strategy = sheetStrategy || selectedTemplate;
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
        subtitle={`股票池、策略目录和回测扫描 · 生成于 ${formatDate(data.generatedAt)}`}
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
            {selectedTemplate && view === "scans" && (
              <Button size="sm" onClick={createStrategyWorkspace} disabled={isCreating} className="bg-blue-600 text-white hover:bg-blue-700">
                {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                生成工作空间
              </Button>
            )}
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
            {/* Stats bar */}
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
              {[
                { label: "策略方案", value: data.summary.templates, sub: `${data.summary.readyTemplates} 可回测`, icon: <TrendingUp className="h-3.5 w-3.5" /> },
                { label: "工作空间", value: data.summary.strategyWorkspaces, sub: `${data.summary.backtestWorkspaces} 回测`, icon: <GitBranch className="h-3.5 w-3.5" /> },
                { label: "版本口径", value: data.summary.activeVersions, sub: `${data.templates.reduce((s, t) => s + t.versions.length, 0)} 记录`, icon: <BarChart3 className="h-3.5 w-3.5" /> },
                { label: "回测归档", value: data.summary.archivedReports, sub: "报告与限制", icon: <Database className="h-3.5 w-3.5" /> },
              ].map((item) => (
                <div key={item.label} className="flex min-w-[130px] flex-1 items-center gap-3 rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2.5">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white text-slate-500">{item.icon}</div>
                  <div className="min-w-0"><p className="text-sm font-semibold tabular-nums text-slate-900">{item.value}</p><p className="truncate text-[11px] text-slate-500">{item.sub}</p></div>
                </div>
              ))}
            </div>

            {/* Search + family filter */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="搜索策略方案、参数、数据源..." className="h-9 border-slate-200 bg-white pl-9" />
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" onClick={() => setFamilyFilter(null)}
                className={cn("rounded-md border px-2.5 py-1 text-xs font-medium transition-colors", !familyFilter ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300")}>全部</button>
              {families.map((fam) => (
                <button key={fam} type="button" onClick={() => setFamilyFilter(fam)}
                  className={cn("rounded-md border px-2.5 py-1 text-xs font-medium transition-colors", familyFilter === fam ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300")}>{fam}</button>
              ))}
            </div>

            {/* Card grid */}
            {displayTemplates.length === 0 ? (
              <EmptyState title={keyword || familyFilter ? "没有匹配的策略方案" : "暂无策略方案"} description={keyword ? "尝试其他关键词" : "请运行策略扫描生成模板数据"} className="border-0" />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {displayTemplates.map((t) => (
                  <StrategyCard key={t.id} strategy={t} onClick={() => { setSheetStrategy(t); setSymbol(t.defaultSymbols[0] ?? ""); setSheetOpen(true); }} />
                ))}
              </div>
            )}

            {/* Detail Sheet */}
            <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
              <SheetContent side="right" className="flex w-[560px] max-w-[94vw] flex-col gap-0 p-0 sm:max-w-[640px]">
                {sheetStrategy && (
                  <>
                    <SheetHeader className="border-b px-5 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <SheetTitle className="text-lg">{sheetStrategy.name}</SheetTitle>
                          <SheetDescription className="mt-1">{sheetStrategy.family} · {sheetStrategy.timeframe} · {sheetStrategy.readiness.summary}</SheetDescription>
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", statusClass(sheetStrategy.status))}>{statusLabel(sheetStrategy.status)}</span>
                          <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", riskClass(sheetStrategy.readiness.riskLevel))}>{sheetStrategy.readiness.score}分</span>
                        </div>
                      </div>
                    </SheetHeader>
                    <div className="flex-1 space-y-5 overflow-y-auto p-5">
                      <p className="text-sm leading-6 text-slate-600">{sheetStrategy.description}</p>

                      {/* Parameters */}
                      <section>
                        <h4 className="mb-2 text-sm font-semibold text-slate-900">参数口径</h4>
                        <div className="divide-y divide-slate-100 rounded-md border border-slate-200">
                          {sheetStrategy.parameterSchema.map((p) => (
                            <div key={p.key} className="flex items-start justify-between gap-4 px-3 py-2.5 text-sm">
                              <span className="shrink-0 text-slate-500">{p.label}</span>
                              <span className="min-w-0 break-words text-right font-medium text-slate-900">{p.value}{p.unit ?? ""}<span className="ml-2 text-xs font-normal text-slate-500">{p.description}</span></span>
                            </div>
                          ))}
                        </div>
                      </section>

                      {/* Metrics + Dependencies */}
                      <div className="grid gap-5 sm:grid-cols-2">
                        <section>
                          <h4 className="mb-2 text-sm font-semibold text-slate-900">评估指标</h4>
                          <div className="flex flex-wrap gap-1.5">{sheetStrategy.evaluationMetrics.map((m) => <span key={m} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">{m}</span>)}</div>
                        </section>
                        <section>
                          <h4 className="mb-2 text-sm font-semibold text-slate-900">数据依赖</h4>
                          <div className="space-y-1">{sheetStrategy.dataDependencies.map((ep) => <code key={ep} className="block truncate rounded bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600">{ep}</code>)}</div>
                        </section>
                      </div>

                      {/* Risk & Limitations */}
                      <section>
                        <h4 className="mb-2 text-sm font-semibold text-slate-900">风险与限制</h4>
                        <div className="space-y-2 rounded-md border border-slate-200 p-3 text-sm">
                          {sheetStrategy.riskControls.map((item) => <div key={item} className="flex gap-2 text-slate-700"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /><span>{item}</span></div>)}
                          {sheetStrategy.limitations.map((item) => <div key={item} className="rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">{item}</div>)}
                        </div>
                      </section>

                      {/* Backtest archives */}
                      {sheetStrategy.backtestArchives.length > 0 && (
                        <section>
                          <h4 className="mb-2 text-sm font-semibold text-slate-900">回测归档</h4>
                          <div className="grid gap-3 sm:grid-cols-2">
                            {sheetStrategy.backtestArchives.map((a) => (
                              <div key={a.id} className="rounded-md border border-slate-200 p-3">
                                <div className="flex items-center justify-between gap-2"><p className="text-sm font-medium">{a.title}</p><Badge variant="outline" className="text-[10px]">{a.status}</Badge></div>
                                <p className="mt-1 text-xs text-slate-500">{a.symbol} · {a.period}</p>
                                <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                                  <div><span className="text-slate-500">收益</span><span className="ml-1 font-medium">{a.metrics.totalReturnPct ?? "-"}%</span></div>
                                  <div><span className="text-slate-500">回撤</span><span className="ml-1 font-medium">{a.metrics.maxDrawdownPct ?? "-"}%</span></div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </section>
                      )}

                      {/* Linked workspaces */}
                      {sheetStrategy.linkedWorkspaces.length > 0 && (
                        <section>
                          <h4 className="mb-2 text-sm font-semibold text-slate-900">关联工作空间</h4>
                          <div className="divide-y divide-slate-100 rounded-md border border-slate-200">
                            {sheetStrategy.linkedWorkspaces.map((ws) => (
                              <Link key={ws.id} href={`/${ws.id}/chat`} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm hover:bg-slate-50">
                                <div><p className="font-medium text-slate-900">{ws.name}</p><p className="text-xs text-slate-500">{ws.capabilityId} · {formatDate(ws.updatedAt ?? ws.createdAt)}</p></div>
                                <ArrowRight className="h-4 w-4 text-slate-300" />
                              </Link>
                            ))}
                          </div>
                        </section>
                      )}

                      {/* Create workspace CTA */}
                      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/50 p-4">
                        <Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="输入标的，例如 510300" className="max-w-[180px] bg-white" />
                        <Button onClick={createStrategyWorkspace} disabled={isCreating} className="bg-blue-600 text-white hover:bg-blue-700">
                          {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                          生成工作空间
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </SheetContent>
            </Sheet>
          </>
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
