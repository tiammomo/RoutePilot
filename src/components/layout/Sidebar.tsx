"use client";

import { useRouter } from "next/navigation";
import {
  BarChart3,
  Boxes,
  Gauge,
  Menu,
  PackageCheck,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { QuantCapabilityId } from "@/lib/quant/capabilities";

const ROLE_MODULES: Array<{
  id: string;
  name: string;
  description: string;
  capabilityId: QuantCapabilityId;
  inputPlaceholder: string;
}> = [
  {
    id: "holding-analysis",
    name: "持仓分析",
    description: "识别持仓结构、盈亏、集中度、回撤和调仓约束",
    capabilityId: "portfolio_risk",
    inputPlaceholder:
      "描述你的持仓、成本、可用资金或上传持仓截图，我会按持仓分析角色生成风险与调仓看板",
  },
  {
    id: "stock-selection",
    name: "选股分析",
    description: "从候选标的中比较趋势、财务、估值、流动性和风险",
    capabilityId: "asset_comparison",
    inputPlaceholder:
      "输入候选股票、行业方向或筛选条件，我会按选股分析角色拉取数据并生成对比看板",
  },
  {
    id: "single-stock-diagnosis",
    name: "个股诊断",
    description: "围绕单只股票整合行情、K 线、财务、公告和风险",
    capabilityId: "stock_diagnosis",
    inputPlaceholder:
      "输入股票名称或代码，以及你关心的行情、财务、公告或风险问题",
  },
  {
    id: "timing-analysis",
    name: "技术择时",
    description: "分析价格趋势、均线结构、成交量、回撤和触发条件",
    capabilityId: "technical_analysis",
    inputPlaceholder:
      "输入标的和时间范围，我会按技术择时角色生成 K 线、量价和趋势模板看板",
  },
  {
    id: "fundamental-research",
    name: "基本面研究",
    description: "研究盈利质量、现金流、ROE、公告事件和估值情景",
    capabilityId: "fundamental_analysis",
    inputPlaceholder:
      "输入公司或行业，我会按基本面研究角色整理财务、公告、估值情景和数据质量",
  },
  {
    id: "strategy-backtest",
    name: "策略回测",
    description: "拆解信号规则、样本、参数、交易明细和回测限制",
    capabilityId: "backtest_review",
    inputPlaceholder:
      "描述策略规则、标的和时间窗口，我会按策略回测角色生成可复盘的量化看板",
  },
];

interface SidebarProps {
  selectedCapability: QuantCapabilityId;
  onSelectCapability: (id: QuantCapabilityId) => void;
  onOpenTaskDrawer: () => void;
  onShowSettings: () => void;
  /** Mobile only */
  isMobile?: boolean;
  onCloseMobile?: () => void;
}

function Sidebar({
  selectedCapability,
  onSelectCapability,
  onOpenTaskDrawer,
  onShowSettings,
  isMobile = false,
  onCloseMobile,
}: SidebarProps) {
  const router = useRouter();

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r bg-background/95",
        isMobile ? "w-[286px]" : "w-[260px]"
      )}
    >
      <div className="flex h-14 items-center justify-between border-b px-4">
        <button
          type="button"
          onClick={onOpenTaskDrawer}
          className="flex items-center gap-2 text-foreground hover:text-primary"
          title="打开任务记录"
        >
          <Menu className="h-4 w-4" />
          <span className="text-sm font-semibold">任务记录</span>
        </button>
        {isMobile && (
          <Button
            type="button"
            onClick={onCloseMobile}
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="关闭侧栏"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        <div className="mb-2 px-2">
          <span className="text-xs font-semibold tracking-wide text-muted-foreground">
            角色模块
          </span>
        </div>

        <div className="space-y-1.5">
          {ROLE_MODULES.map((role) => {
            const active = selectedCapability === role.capabilityId;
            return (
              <button
                key={role.id}
                type="button"
                onClick={() => {
                  onSelectCapability(role.capabilityId);
                  onCloseMobile?.();
                }}
                className={cn(
                  "w-full rounded-md border px-3 py-3 text-left transition-colors",
                  active
                    ? "border-primary/20 bg-primary/10 text-primary"
                    : "border-transparent text-foreground hover:border-border hover:bg-muted/60"
                )}
                title={role.description}
                aria-pressed={active}
              >
                <span
                  className={cn(
                    "text-sm font-semibold",
                    active ? "text-primary" : "text-foreground"
                  )}
                >
                  {role.name}
                </span>
                <p
                  className={cn(
                    "mt-1 text-xs leading-5",
                    active ? "text-primary/80" : "text-muted-foreground"
                  )}
                >
                  {role.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Platform navigation */}
      <div className="border-t p-3">
        <Button
          type="button"
          onClick={() => router.push("/evals")}
          variant="ghost"
          className="mb-0.5 w-full justify-start"
        >
          <Gauge className="h-4 w-4" />
          Agent 评测后台
        </Button>
        <Button
          type="button"
          onClick={() => router.push("/skills")}
          variant="ghost"
          className="mb-0.5 w-full justify-start"
        >
          <PackageCheck className="h-4 w-4" />
          Skills 管理
        </Button>
        <Button
          type="button"
          onClick={onShowSettings}
          variant="ghost"
          className="w-full justify-start"
        >
          <Settings className="h-4 w-4" />
          设置
        </Button>
      </div>
    </aside>
  );
}

export { Sidebar, ROLE_MODULES };
export type { SidebarProps };
