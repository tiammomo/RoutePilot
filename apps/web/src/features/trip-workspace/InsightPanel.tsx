"use client";

import { useMemo, useState } from "react";

import type { ArtifactPresentation } from "@/entities/artifact/presentation";
import type { RunUiState } from "@/entities/run/reducer";
import { StaticMapAdapter, type MapMarker } from "@/features/map/MapAdapter";
import { formatDate, formatMoney } from "@/shared/lib/format";
import { Icons } from "@/shared/ui/Icons";
import { StatusBadge } from "@/shared/ui/StatusBadge";

export type InsightTab = "map" | "evidence" | "budget" | "risk";

const TABS: Array<{ id: InsightTab; label: string }> = [
  { id: "map", label: "地图" },
  { id: "evidence", label: "证据" },
  { id: "budget", label: "预算" },
  { id: "risk", label: "风险" },
];

export function InsightPanel({
  presentation,
  run,
  activeTab,
  onTabChange,
}: {
  presentation: ArtifactPresentation;
  run: RunUiState;
  activeTab?: InsightTab;
  onTabChange?: (tab: InsightTab) => void;
}) {
  const [internalTab, setInternalTab] = useState<InsightTab>("map");
  const tab = activeTab ?? internalTab;
  const setTab = onTabChange ?? setInternalTab;
  const [selectedMarker, setSelectedMarker] = useState<string>();
  const plan = presentation.itinerary;
  const markers = useMemo<MapMarker[]>(() =>
    plan?.days.flatMap((day) => day.time_blocks).map((block, index) => ({
      id: block.block_id,
      label: block.place_ref.display_name,
      place: block.place_ref,
      order: index + 1,
    })) ?? [], [plan]);
  const evidenceCount = presentation.evidence?.evidence.length ?? 0;
  const riskCount = (presentation.validation?.blockers?.length ?? 0) +
    (presentation.validation?.warnings?.length ?? 0) + run.risks.length;
  const tabMeta: Record<InsightTab, string> = {
    map: `${markers.length} 站`,
    evidence: `${evidenceCount} 条`,
    budget: plan ? "有范围" : "待估算",
    risk: `${riskCount} 项`,
  };

  return (
    <aside className="insight-panel" aria-label="旅行计划详情">
      <div className="insight-tabs" role="tablist" aria-label="地图、证据、预算和风险">
        {TABS.map((item) => (
          <button
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            key={item.id}
            onClick={() => setTab(item.id)}
          ><span>{item.label}</span><small>{tabMeta[item.id]}</small></button>
        ))}
      </div>

      <div className="insight-content" role="tabpanel">
        {tab === "map" && (
          <div className="insight-section">
            <div className="panel-heading"><div><span>ROUTE VIEW</span><h2>地点与动线</h2></div><StatusBadge>{markers.length} 站</StatusBadge></div>
            <StaticMapAdapter markers={markers} selectedId={selectedMarker} onSelect={setSelectedMarker} />
            <div className="marker-list">
              {markers.slice(0, 8).map((marker) => (
                <button key={marker.id} type="button" data-selected={selectedMarker === marker.id} onClick={() => setSelectedMarker(marker.id)}>
                  <span>{marker.order}</span><span><strong>{marker.label}</strong><small>{marker.place.address || marker.place.timezone}</small></span>
                </button>
              ))}
            </div>
          </div>
        )}

        {tab === "evidence" && (
          <div className="insight-section">
            <div className="panel-heading"><div><span>EVIDENCE</span><h2>为什么这样选</h2></div><StatusBadge tone="brand">可追溯</StatusBadge></div>
            {presentation.evidence?.evidence.length ? (
              <ul className="evidence-list">
                {presentation.evidence.evidence.map((item) => (
                  <li key={item.evidence_id}>
                    <div><Icons.Evidence /><span><strong>{item.title}</strong><small>{item.source.name} · {formatDate(item.retrieved_at)}</small></span></div>
                    <p>{item.summary}</p>
                    <StatusBadge tone={item.freshness.status === "fresh" ? "success" : "warning"}>{item.freshness.status}</StatusBadge>
                  </li>
                ))}
              </ul>
            ) : <PanelEmpty icon={<Icons.Evidence />} title="证据正在汇集" description="Research Agent 的来源、更新时间和冲突会显示在这里。" />}
          </div>
        )}

        {tab === "budget" && (
          <div className="insight-section">
            <div className="panel-heading"><div><span>BUDGET</span><h2>预算概览</h2></div><Icons.Wallet /></div>
            {plan ? (
              <>
                <div className="budget-total">
                  <span>预计总计</span>
                  <strong>{formatMoney(plan.budget_summary.estimated_total.min_amount, plan.budget_summary.estimated_total.max_amount, plan.budget_summary.estimated_total.currency)}</strong>
                  <small>含 {String(plan.budget_summary.contingency_percent)}% 机动空间</small>
                </div>
                <ul className="budget-list">
                  {plan.budget_summary.category_totals?.map((item) => (
                    <li key={item.category}><span>{item.category}</span><strong>{formatMoney(item.cost.min_amount, item.cost.max_amount, item.cost.currency)}</strong></li>
                  ))}
                </ul>
              </>
            ) : <PanelEmpty icon={<Icons.Wallet />} title="尚无预算估算" description="确定性预算服务完成后，这里会展示范围而非虚假精确值。" />}
          </div>
        )}

        {tab === "risk" && (
          <div className="insight-section">
            <div className="panel-heading"><div><span>VALIDATION</span><h2>风险与约束</h2></div><Icons.Warning /></div>
            {(presentation.validation?.blockers?.length || presentation.validation?.warnings?.length || run.risks.length) ? (
              <ul className="risk-list">
                {presentation.validation?.blockers?.map((risk) => <RiskItem key={risk.issue_id} severity={risk.severity} message={risk.message} />)}
                {presentation.validation?.warnings?.map((risk) => <RiskItem key={risk.issue_id} severity={risk.severity} message={risk.message} />)}
                {run.risks.map((risk) => <RiskItem key={risk.id} severity={risk.severity} message={risk.message} />)}
              </ul>
            ) : <PanelEmpty icon={<Icons.Check />} title="目前没有公开风险" description="时间、路线与预算会由确定性校验验证，语义风险由 Verifier 独立审查。" />}
          </div>
        )}
      </div>
    </aside>
  );
}

function PanelEmpty({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return <div className="panel-empty"><span>{icon}</span><strong>{title}</strong><p>{description}</p></div>;
}

function RiskItem({ severity, message }: { severity: string; message: string }) {
  return <li data-severity={severity}><Icons.Warning /><div><StatusBadge tone={severity === "critical" || severity === "high" ? "danger" : "warning"}>{severity}</StatusBadge><p>{message}</p></div></li>;
}
