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
  question,
  onConvertToPlan,
}: {
  presentation: ArtifactPresentation;
  run: RunUiState;
  official: boolean;
  loading: boolean;
  question?: string;
  onConvertToPlan?: () => void;
}) {
  if (loading) {
    return <div className="itinerary-skeleton" aria-label="正在载入计划">{[0, 1, 2].map((item) => <span key={item} />)}</div>;
  }

  const plan = presentation.itinerary;
  const answer = presentation.record?.artifact_type === "TravelAnswer" ? presentation.answer : null;
  if (answer) {
    return (
      <section className="answer-canvas" aria-label="旅行问答结果">
        <header className="answer-heading">
          <div><span className="eyebrow">GROUNDED ANSWER</span><h2>旅行助手的回答</h2></div>
          <StatusBadge tone={answer.answer_status === "answered" ? "success" : "warning"}>
            {answer.answer_status === "answered" ? "已核验来源" : "证据不足"}
          </StatusBadge>
        </header>
        <blockquote>“{answer.question}”</blockquote>
        <p className="answer-summary">{answer.summary}</p>
        <div className="answer-sections">
          {(answer.sections ?? []).map((section) => (
            <article key={`${section.heading}:${section.body}`}>
              <h3>{section.heading}</h3>
              <p>{section.body}</p>
              {!!section.evidence_refs?.length && <small>{section.evidence_refs.length} 条证据支持</small>}
            </article>
          ))}
        </div>
        {!!answer.limitations?.length && (
          <aside className="answer-limitations"><strong>出发前提醒</strong>{answer.limitations.map((item) => <p key={item}>{item}</p>)}</aside>
        )}
        {!!answer.citations?.length && (
          <section className="answer-sources" aria-label="回答来源">
            <h3>参考来源</h3>
            <div>{answer.citations.slice(0, 8).map((citation) => citation.source.uri ? (
              <a key={citation.citation_id} href={citation.source.uri} target="_blank" rel="noreferrer noopener">
                <span>{citation.title}</span><small>{citation.source.name} · {citation.source.version}</small>
              </a>
            ) : (
              <span key={citation.citation_id}><b>{citation.title}</b><small>{citation.source.name} · {citation.source.version}</small></span>
            ))}</div>
          </section>
        )}
        <footer className="answer-next-step">
          <div><strong>需要一份完整行程吗？</strong><small>再确认日期、同行人数和预算，就能把这份回答转成逐日计划。</small></div>
          <button type="button" className="primary-button" onClick={onConvertToPlan}>转成行程 <Icons.Arrow /></button>
        </footer>
      </section>
    );
  }
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
      <span className="eyebrow">{running ? "正在回答" : "问题已收到"}</span>
      {!running && question && <blockquote className="canvas-question">“{question}”</blockquote>}
      <h2>{running ? "Agent 正在研究并校验你的方案" : "再确认几项必要信息，就可以开始"}</h2>
      <p>{running ? "研究、规划和校验结果会逐步出现在这里，你可以随时停止。" : "你的原问题已经保留。点击页面底部的“完善行程信息”，确认目的地、日期、人数和预算；偏好可以跳过。"}</p>
      {!running && (
        <>
          <div className="workspace-guide-steps" aria-label="生成方案步骤">
            <span><b>1</b> 完善基本信息</span>
            <span><b>2</b> 直接生成方案</span>
            <span><b>3</b> 在方案上继续调整</span>
          </div>
          <div className="prompt-examples" aria-label="重点要求示例">
            <small>重点要求示例</small><span>带父母，尽量少走路</span><span>上午轻松，下午看展</span><span>保留故宫，避开夜市</span>
          </div>
        </>
      )}
    </section>
  );
}
