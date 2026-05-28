"use client";

import { useMemo, useState } from "react";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Database,
  Layers3,
  RefreshCcw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Zap,
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
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { SubNav, type SubNavItem } from "@/components/layout/SubNav";
import { formatCompactDate as formatDate } from "@/components/quant/console-primitives";
import { cn } from "@/lib/utils";
import type {
  CapabilityCenterData,
  CapabilityCenterDataProvider,
  CapabilityCenterItem,
} from "@/lib/quant/capability-center";

type Props = { initialData: CapabilityCenterData };
type TabId = "capabilities" | "sources" | "lakehouse" | "doris";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

// ─── Status helpers ────────────────────────────────────────────
function readinessLabel(s: CapabilityCenterItem["readiness"]["status"]) {
  return s === "ready" ? "可用" : s === "warning" ? "风险" : s === "blocked" ? "阻断" : "规划中";
}
function readinessStyle(s: CapabilityCenterItem["readiness"]["status"]) {
  if (s === "ready") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (s === "warning") return "bg-amber-50 text-amber-700 border-amber-200";
  if (s === "blocked") return "bg-red-50 text-red-700 border-red-200";
  return "bg-blue-50 text-blue-700 border-blue-200";
}
function readinessDot(s: CapabilityCenterItem["readiness"]["status"]) {
  if (s === "ready") return "bg-emerald-500";
  if (s === "warning") return "bg-amber-500";
  if (s === "blocked") return "bg-red-500";
  return "bg-blue-400";
}
function providerStyle(s: string) {
  if (s === "available") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (s === "degraded") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-slate-50 text-slate-600 border-slate-200";
}
function providerLabel(s: string) {
  if (s === "available") return "可用";
  if (s === "degraded") return "降级";
  if (s === "planned") return "规划中";
  return s;
}
const CATEGORY_LABELS: Record<string, string> = {
  "market-data": "行情数据",
  symbol: "证券搜索",
  indicator: "技术指标",
  backtest: "策略回测",
  fundamental: "基本面",
  event: "公告事件",
  "index-etf": "指数/ETF",
  ingestion: "数据入库",
  "research-config": "研究配置",
  "fallback-provider": "可采集兜底源",
  "candidate-provider": "候选数据源",
  "planned-provider": "计划接入",
  "licensed-provider": "授权数据源",
};

// ─── Sub‑nav definition ────────────────────────────────────────
const SUB_NAV_ITEMS: SubNavItem[] = [
  { id: "capabilities", label: "能力矩阵", icon: <Sparkles className="h-4 w-4" /> },
  { id: "sources", label: "数据源", icon: <Database className="h-4 w-4" /> },
  { id: "lakehouse", label: "湖仓", icon: <Building2 className="h-4 w-4" />, disabled: true, tooltip: "即将推出" },
  { id: "doris", label: "Doris", icon: <Server className="h-4 w-4" />, disabled: true, tooltip: "即将推出" },
];

// ─── Status Bar ────────────────────────────────────────────────
function StatusBar({ data }: { data: CapabilityCenterData }) {
  const items = [
    {
      label: "市场 API",
      value: data.marketApi.reachable ? "在线" : "离线",
      dot: data.marketApi.reachable ? "bg-emerald-500" : "bg-red-500",
      sub: data.marketApi.baseUrl,
      icon: <Server className="h-3.5 w-3.5" />,
    },
    {
      label: "能力模块",
      value: `${data.summary.readyCapabilities}/${data.summary.capabilities}`,
      sub: data.summary.blockedCapabilities > 0 ? `${data.summary.blockedCapabilities} 阻断` : "全部就绪",
      icon: <Sparkles className="h-3.5 w-3.5" />,
      warn: data.summary.blockedCapabilities > 0,
    },
    {
      label: "数据源",
      value: `${data.summary.availableProviders}/${data.summary.dataProviders}`,
      sub: data.summary.degradedProviders > 0 ? `${data.summary.degradedProviders} 降级` : "全部可用",
      icon: <Database className="h-3.5 w-3.5" />,
      warn: data.summary.degradedProviders > 0,
    },
    {
      label: "Skills",
      value: data.summary.skills,
      sub: data.summary.skillErrors > 0 ? `${data.summary.skillErrors} 异常` : "全部正常",
      icon: <Layers3 className="h-3.5 w-3.5" />,
      warn: data.summary.skillErrors > 0,
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex min-w-[140px] flex-1 items-center gap-3 rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2.5"
        >
          <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white", item.warn ? "text-amber-600" : "text-slate-500")}>
            {item.icon}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              {item.dot && <span className={cn("h-2 w-2 rounded-full", item.dot)} />}
              <p className="text-sm font-semibold text-slate-900">{item.value}</p>
            </div>
            <p className="truncate text-[11px] text-slate-500">{item.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Capability Row ────────────────────────────────────────────
function CapabilityRow({ cap, onClick }: { cap: CapabilityCenterItem; onClick: () => void }) {
  const ready = cap.readiness.status === "ready";
  const warning = cap.readiness.status === "warning";
  const blocked = cap.readiness.status === "blocked";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-4 rounded-md border px-4 py-3 text-left transition-colors hover:bg-slate-50",
        "border-transparent hover:border-slate-200"
      )}
    >
      <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", readinessDot(cap.readiness.status))} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-slate-900">{cap.name}</p>
        <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{cap.description}</p>
      </div>
      <div className="hidden shrink-0 items-center gap-4 text-xs text-slate-500 md:flex">
        <span className="flex items-center gap-1"><Layers3 className="h-3 w-3" />{cap.requiredSkills.length}{cap.missingSkills.length > 0 && <span className="text-red-500">(-{cap.missingSkills.length})</span>}</span>
        <span className="flex items-center gap-1"><Database className="h-3 w-3" />{cap.dataEndpoints.length}</span>
        <span className="w-12 truncate text-right text-[11px]">{cap.groupId}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className={cn("hidden rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums sm:inline-block", ready ? "bg-emerald-50 text-emerald-700" : warning ? "bg-amber-50 text-amber-700" : blocked ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-600")}>
          {cap.readiness.score}%
        </span>
        <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", readinessStyle(cap.readiness.status))}>
          {readinessLabel(cap.readiness.status)}
        </span>
        <ArrowRight className="h-4 w-4 text-slate-300 transition-colors group-hover:text-slate-500" />
      </div>
    </button>
  );
}

// ─── Provider Card ─────────────────────────────────────────────
function ProviderCard({ provider }: { provider: CapabilityCenterDataProvider }) {
  const available = provider.status === "available";
  const degraded = provider.status === "degraded";
  const cat = CATEGORY_LABELS[provider.category] || provider.category;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{provider.name}</p>
          <p className="mt-0.5 text-xs text-slate-500">{cat}</p>
        </div>
        <span className={cn("flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", providerStyle(provider.status))}>
          <span className={cn("h-1.5 w-1.5 rounded-full", available ? "bg-emerald-500" : degraded ? "bg-amber-500" : "bg-slate-400")} />
          {providerLabel(provider.status)}
        </span>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-600 line-clamp-2">{provider.description}</p>
      {provider.endpoints.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {provider.endpoints.slice(0, 4).map((ep) => (
            <code key={ep} className="max-w-[200px] truncate rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{ep}</code>
          ))}
          {provider.endpoints.length > 4 && <span className="text-[11px] text-slate-400">+{provider.endpoints.length - 4}</span>}
        </div>
      )}
      {provider.limitations.length > 0 && (
        <div className="mt-3 space-y-1 rounded-md border border-amber-100 bg-amber-50/50 px-2.5 py-2">
          {provider.limitations.map((item) => <p key={item} className="text-[11px] leading-5 text-amber-700">{item}</p>)}
        </div>
      )}
    </div>
  );
}

// ─── Capability Sheet ──────────────────────────────────────────
function CapabilitySheet({ cap, open, onOpenChange }: { cap: CapabilityCenterItem | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  if (!cap) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-[480px] max-w-[92vw] flex-col gap-0 p-0 sm:max-w-[560px]">
        <SheetHeader className="border-b px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <SheetTitle className="text-base">{cap.name}</SheetTitle>
              <SheetDescription className="mt-1">{cap.description}</SheetDescription>
            </div>
            <span className={cn("shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold", readinessStyle(cap.readiness.status))}>
              {readinessLabel(cap.readiness.status)} · {cap.readiness.score}%
            </span>
          </div>
        </SheetHeader>
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <div className="grid grid-cols-4 gap-2">
            {[{ label: "分组", value: cap.groupId }, { label: "Agent", value: cap.agentType }, { label: "Skills", value: cap.requiredSkills.length }, { label: "端点", value: cap.dataEndpoints.length }].map((item) => (
              <div key={item.label} className="rounded-md border border-slate-200 bg-slate-50 p-2.5 text-center">
                <p className="text-[11px] text-slate-500">{item.label}</p>
                <p className="mt-1 truncate text-sm font-semibold text-slate-900">{item.value}</p>
              </div>
            ))}
          </div>
          <div className={cn("rounded-md border px-3 py-2.5 text-sm leading-6", cap.readiness.status === "ready" ? "border-emerald-100 bg-emerald-50 text-emerald-800" : cap.readiness.status === "warning" ? "border-amber-100 bg-amber-50 text-amber-800" : cap.readiness.status === "blocked" ? "border-red-100 bg-red-50 text-red-800" : "border-blue-100 bg-blue-50 text-blue-800")}>
            {cap.readiness.summary}
          </div>
          <section>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900"><Layers3 className="h-4 w-4 text-slate-500" />依赖 Skills</h4>
            {cap.requiredSkills.length === 0 && cap.missingSkills.length === 0 ? <p className="text-xs text-slate-500">无依赖</p> : (
              <div className="divide-y divide-slate-100 rounded-md border border-slate-200">
                {cap.requiredSkills.map((skill) => (
                  <div key={skill.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">{skill.name}</p>
                      <p className="truncate text-xs text-slate-500">{skill.requestedId === skill.id ? skill.id : `${skill.requestedId} → ${skill.id}`} · v{skill.version}</p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {skill.viaAlias && <Badge variant="outline" className="text-[10px]">alias</Badge>}
                      <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", skill.health === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700")}>{skill.health}</span>
                    </div>
                  </div>
                ))}
                {cap.missingSkills.map((id) => (
                  <div key={id} className="flex items-center justify-between gap-3 bg-red-50/30 px-3 py-2.5">
                    <p className="text-sm font-medium text-red-700">{id}</p>
                    <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700 text-[10px]">missing</Badge>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900"><Database className="h-4 w-4 text-slate-500" />数据端点</h4>
            {cap.dataEndpoints.length === 0 ? <p className="text-xs text-slate-500">未声明端点</p> : (
              <div className="space-y-1.5">{cap.dataEndpoints.map((ep) => <code key={ep} className="block rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">{ep}</code>)}</div>
            )}
          </section>
          {cap.expectedArtifacts.length > 0 && (
            <section>
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900"><ShieldCheck className="h-4 w-4 text-slate-500" />产物契约</h4>
              <div className="flex flex-wrap gap-1.5">{cap.expectedArtifacts.map((a) => <Badge key={a} variant="outline" className="bg-slate-50 text-xs text-slate-600">{a}</Badge>)}</div>
            </section>
          )}
          {cap.validationRules.length > 0 && (
            <section>
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900"><CheckCircle2 className="h-4 w-4 text-slate-500" />验证规则</h4>
              <div className="space-y-1.5">{cap.validationRules.map((rule) => <div key={rule} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-700">{rule}</div>)}</div>
            </section>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ─── Placeholder tab for future features ───────────────────────
function ComingSoonTab({ title, description, icon }: { title: string; description: string; icon: React.ReactNode }) {
  return (
    <EmptyState
      icon={icon}
      title={title}
      description={description}
      className="mt-8 border-0"
    />
  );
}

// ─── Main Page ─────────────────────────────────────────────────
export default function CapabilityCenterClient({ initialData }: Props) {
  const [data, setData] = useState(initialData);
  const [activeTab, setActiveTab] = useState<TabId>("capabilities");
  const [keyword, setKeyword] = useState("");
  const [selectedCap, setSelectedCap] = useState<CapabilityCenterItem | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const filteredCapabilities = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.capabilities.filter((cap) => {
      if (!lower) return true;
      return [cap.id, cap.name, cap.description, cap.groupId, cap.agentType, ...cap.tags, ...cap.dataEndpoints, ...cap.requiredSkills.map((s) => s.id)]
        .join(" ").toLowerCase().includes(lower);
    });
  }, [data.capabilities, keyword]);

  const filteredProviders = useMemo(() => {
    const lower = keyword.trim().toLowerCase();
    return data.dataProviders.filter((p) => {
      if (!lower) return true;
      return [p.id, p.name, p.category, p.description, p.status, ...p.endpoints]
        .join(" ").toLowerCase().includes(lower);
    });
  }, [data.dataProviders, keyword]);

  const providersByCategory = useMemo(() => {
    const map = new Map<string, CapabilityCenterDataProvider[]>();
    for (const p of filteredProviders) {
      const list = map.get(p.category) || [];
      list.push(p);
      map.set(p.category, list);
    }
    return map;
  }, [filteredProviders]);

  const refresh = async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const r = await fetch(`${API_BASE}/api/quant/capability-center`, { cache: "no-store" });
      const payload = await r.json();
      if (!r.ok || !payload.success) throw new Error(payload.error ?? "刷新失败");
      setData(payload.data);
    } catch (error) {
      setToast(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRefreshing(false);
    }
  };

  const openSheet = (cap: CapabilityCenterItem) => {
    setSelectedCap(cap);
    setSheetOpen(true);
  };

  return (
    <div className="min-h-screen bg-surface text-slate-900">
      <PageHeader
        title="数据平台"
        badge={<Badge variant="outline" className="bg-white text-slate-500">{data.summary.capabilities} 个能力</Badge>}
        subtitle={`市场 API: ${data.marketApi.baseUrl} · 数据生成于 ${formatDate(data.generatedAt)}`}
      />

      {/* Sub‑navigation */}
      <SubNav
        items={SUB_NAV_ITEMS}
        activeId={activeTab}
        onChange={(id) => {
          setActiveTab(id as TabId);
          setKeyword("");
        }}
        actions={
          <Button variant="outline" size="sm" onClick={refresh} disabled={isRefreshing}>
            <RefreshCcw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
            刷新
          </Button>
        }
      />

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 lg:px-6">
        {/* Toast */}
        {toast && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm">{toast}</div>
        )}

        {/* Status Bar (shown on active tabs) */}
        {activeTab !== "lakehouse" && activeTab !== "doris" && (
          <StatusBar data={data} />
        )}

        {/* ── Tab: Capabilities ──────────────────────────── */}
        {activeTab === "capabilities" && (
          <section>
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-600" />
              <h2 className="text-sm font-semibold text-slate-700">
                能力矩阵 <span className="font-normal text-slate-400">{filteredCapabilities.length} 项</span>
              </h2>
              <div className="relative ml-auto w-64">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="搜索能力、Skill、端点..."
                  className="h-9 border-slate-200 bg-white pl-9 text-sm"
                />
              </div>
            </div>

            {filteredCapabilities.length === 0 ? (
              <EmptyState
                title="没有匹配的能力模块"
                description={keyword ? "尝试其他关键词" : "请检查 Skills registry 和数据端点配置"}
                action={keyword ? { label: "清除搜索", onClick: () => setKeyword("") } : { label: "刷新状态", onClick: refresh }}
              />
            ) : (
              <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
                {filteredCapabilities.map((cap) => (
                  <CapabilityRow key={cap.id} cap={cap} onClick={() => openSheet(cap)} />
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── Tab: Data Sources ──────────────────────────── */}
        {activeTab === "sources" && (
          <section>
            <div className="mb-4 flex items-center gap-2">
              <Database className="h-4 w-4 text-blue-600" />
              <h2 className="text-sm font-semibold text-slate-700">
                数据源 <span className="font-normal text-slate-400">{filteredProviders.length} 个</span>
              </h2>
              <div className="relative ml-auto w-64">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="搜索数据源、端点..."
                  className="h-9 border-slate-200 bg-white pl-9 text-sm"
                />
              </div>
            </div>

            {filteredProviders.length === 0 ? (
              <EmptyState
                title="没有匹配的数据源"
                description={keyword ? "尝试其他关键词" : "Market API 暂无可用数据源"}
                action={keyword ? { label: "清除搜索", onClick: () => setKeyword("") } : { label: "刷新状态", onClick: refresh }}
              />
            ) : (
              <div className="space-y-6">
                {Array.from(providersByCategory.entries()).map(([category, providers]) => (
                  <div key={category}>
                    <div className="mb-2 flex items-center gap-2">
                      <Zap className="h-3.5 w-3.5 text-slate-400" />
                      <span className="text-xs font-medium text-slate-500">{CATEGORY_LABELS[category] || category}</span>
                      <span className="text-xs text-slate-400">({providers.length})</span>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {providers.map((p) => <ProviderCard key={p.id} provider={p} />)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── Tab: 湖仓 (placeholder) ────────────────────── */}
        {activeTab === "lakehouse" && (
          <ComingSoonTab
            title="湖仓接入"
            description="支持 Delta Lake、Iceberg、Hudi 等开放湖仓格式的元数据检索与数据预览。功能开发中，敬请期待。"
            icon={<Building2 className="h-8 w-8" />}
          />
        )}

        {/* ── Tab: Doris (placeholder) ───────────────────── */}
        {activeTab === "doris" && (
          <ComingSoonTab
            title="Apache Doris"
            description="高性能实时 OLAP 查询引擎接入，支持大规模金融数据的交互式分析。功能开发中，敬请期待。"
            icon={<Server className="h-8 w-8" />}
          />
        )}

        {/* Capability detail sheet */}
        <CapabilitySheet cap={selectedCap} open={sheetOpen} onOpenChange={setSheetOpen} />
      </main>
    </div>
  );
}
