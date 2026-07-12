import type { RunUiState } from "@/entities/run/reducer";
import { StatusBadge } from "@/shared/ui/StatusBadge";

const CONNECTION_LABELS: Record<RunUiState["connection"], string> = {
  idle: "尚未开始",
  connecting: "正在连接",
  live: "实时同步",
  reconnecting: "正在恢复连接",
  offline: "离线，等待网络",
  closed: "同步完成",
  error: "连接异常",
};

const LIFECYCLE_LABELS: Record<RunUiState["lifecycle"], string> = {
  idle: "准备规划",
  queued: "已排队",
  running: "规划中",
  waiting_input: "等待补充",
  waiting_approval: "等待确认",
  cancel_requested: "正在停止",
  completed: "已完成",
  failed: "未完成",
  canceled: "已停止",
};

export function RunStatus({ state }: { state: RunUiState }) {
  const active = new Set(["queued", "running", "cancel_requested"]).has(state.lifecycle);
  const tone = state.lifecycle === "completed" ? "success" : state.lifecycle === "failed" ? "danger" : active ? "brand" : "neutral";
  return (
    <section className="run-status" aria-live="polite" aria-label="规划运行状态">
      <div className="run-status-top">
        <div>
          <span className="run-kicker">RUN STATUS</span>
          <strong>{state.phaseLabel || LIFECYCLE_LABELS[state.lifecycle]}</strong>
        </div>
        <StatusBadge tone={tone}>{LIFECYCLE_LABELS[state.lifecycle]}</StatusBadge>
      </div>
      {active && (
        <div className="progress-track" aria-label={`规划进度 ${state.progress}%`} role="progressbar" aria-valuenow={state.progress} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${Math.max(4, state.progress)}%` }} />
        </div>
      )}
      <div className="run-meta">
        <span className="connection-dot" data-state={state.connection} />
        {CONNECTION_LABELS[state.connection]}
        {state.lastSeq > 0 && <span>· 已同步至事件 {state.lastSeq}</span>}
      </div>
      {state.publicError && (
        <div className="run-error" role="alert">
          <strong>{state.publicError.message}</strong>
          <span>错误码：{state.publicError.code}</span>
        </div>
      )}
      {(state.candidate || state.published) && (
        <div className="artifact-state-row">
          {state.candidate && <StatusBadge tone="warning">候选 v{state.candidate.version}</StatusBadge>}
          {state.published && <StatusBadge tone="success">正式 v{state.published.version}</StatusBadge>}
        </div>
      )}
    </section>
  );
}
