import type { ArtifactPresentation } from "@/entities/artifact/presentation";
import type { RunUiState } from "@/entities/run/reducer";
import { formatDate, formatMoney } from "@/shared/lib/format";
import { Icons } from "@/shared/ui/Icons";
import { StatusBadge } from "@/shared/ui/StatusBadge";

function timeLabel(time: string): string {
  return time.slice(0, 5);
}

export function ArtifactCanvas({
  presentation,
  run,
  official,
  loading,
}: {
  presentation: ArtifactPresentation;
  run: RunUiState;
  official: boolean;
  loading: boolean;
}) {
  if (loading) {
    return <div className="itinerary-skeleton" aria-label="正在载入计划">{[0, 1, 2].map((item) => <span key={item} />)}</div>;
  }

  const plan = presentation.itinerary;
  if (plan) {
    return (
      <section className="itinerary-canvas" aria-label="行程计划">
        <div className="canvas-heading">
          <div>
            <span className="eyebrow">ITINERARY</span>
            <h2>你的逐日计划</h2>
          </div>
          <StatusBadge tone={official ? "success" : "warning"}>
            {official ? "当前正式方案" : `候选 · ${plan.status}`}
          </StatusBadge>
        </div>
        {plan.days.map((day, dayIndex) => (
          <article className="day-card" key={day.date}>
            <header>
              <span className="day-number">DAY {dayIndex + 1}</span>
              <div>
                <h3>{formatDate(day.date, { month: "long", day: "numeric", weekday: "long" })}</h3>
                <p>{day.day_summary}</p>
              </div>
              <span className="day-cost">
                {formatMoney(day.daily_cost.min_amount, day.daily_cost.max_amount, day.daily_cost.currency)}
              </span>
            </header>
            <ol className="timeline">
              {day.time_blocks.map((block) => {
                const supportingEvidence = presentation.evidence?.evidence.find((item) =>
                  block.evidence_refs.includes(item.evidence_id),
                );
                return (
                    <li key={block.block_id}>
                      <time>{timeLabel(block.time_range.start_local_time)}</time>
                      <span className="timeline-node" data-category={block.category}><Icons.Map /></span>
                      <div className="time-block">
                        <div className="time-block-heading">
                          <div>
                            <span className="block-category">{block.category.replace("_", " ")}</span>
                            <h4>{block.title}</h4>
                          </div>
                          <span>{block.duration_minutes} 分钟</span>
                        </div>
                        <p className="block-place">{block.place_ref.display_name}{block.place_ref.address ? ` · ${block.place_ref.address}` : ""}</p>
                        {supportingEvidence && (
                          <p className="block-summary">{supportingEvidence.summary}</p>
                        )}
                        <div className="block-facts">
                          {block.transit_from_previous && (
                            <span><Icons.Route /> {block.transit_from_previous.duration_min_minutes}–{block.transit_from_previous.duration_max_minutes} 分钟</span>
                          )}
                          <span title={supportingEvidence?.source.uri ?? undefined}>
                            <Icons.Evidence /> {supportingEvidence?.source.name ?? `${block.evidence_refs.length} 条证据`}
                          </span>
                          {supportingEvidence && (
                            <span>状态：{supportingEvidence.freshness.status}</span>
                          )}
                          {block.cost_range && <span><Icons.Wallet /> {formatMoney(block.cost_range.min_amount, block.cost_range.max_amount, block.cost_range.currency)}</span>}
                        </div>
                      </div>
                    </li>
                );
              })}
            </ol>
          </article>
        ))}
      </section>
    );
  }

  const running = new Set(["queued", "running", "cancel_requested"]).has(run.lifecycle);
  return (
    <section className="canvas-empty">
      <div className="empty-orbit" aria-hidden="true"><span /><span /><Icons.Compass /></div>
      <span className="eyebrow">{running ? "正在生成" : "第 2 步 · 确认约束"}</span>
      <h2>{running ? "Agent 正在研究并校验你的方案" : "填写约束，然后生成第一版方案"}</h2>
      <p>{running ? "研究、规划和校验结果会逐步出现在这里，你可以随时停止。" : "在页面底部填写目的地、日期、同行人数和预算，勾选确认后，再补充一句最重要的要求。"}</p>
      {!running && (
        <>
          <div className="workspace-guide-steps" aria-label="生成方案步骤">
            <span><b>1</b> 填写旅行约束</span>
            <span><b>2</b> 勾选核对确认</span>
            <span><b>3</b> 补充重点并发送</span>
          </div>
          <div className="prompt-examples" aria-label="重点要求示例">
            <small>重点要求示例</small><span>带父母，尽量少走路</span><span>上午轻松，下午看展</span><span>保留故宫，避开夜市</span>
          </div>
        </>
      )}
    </section>
  );
}
