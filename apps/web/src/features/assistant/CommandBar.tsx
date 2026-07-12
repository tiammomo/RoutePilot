"use client";

import type { TripBrief } from "@routepilot/contracts-generated";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { TravelConstraintForm } from "@/features/assistant/TravelConstraintForm";
import { consumeQuickStartIntent } from "@/features/trip-create/quick-start-intent";
import {
  buildTripRequest,
  createDefaultTravelConstraintDraft,
  loadTravelConstraintDraft,
  saveTravelConstraintDraft,
  type TravelConstraintDraft,
} from "@/features/trip-workspace/travel-constraints";
import type { TripRequestInput } from "@/shared/api/types";
import { Icons } from "@/shared/ui/Icons";

interface CommandBarProps {
  tripId: string;
  initialBrief?: TripBrief | null;
  busy: boolean;
  disabled?: boolean;
  mode: CommandMode;
  onModeChange: (mode: CommandMode) => void;
  onAsk: (message: string) => Promise<void>;
  onSubmit: (message: string, tripRequest: TripRequestInput) => Promise<void>;
  onCancel?: () => Promise<void>;
}

type ConstraintEditorSurface = "desktop" | "mobile";
export type CommandMode = "ask" | "plan";

const DEFAULT_PLANNING_COMMAND = "请根据已确认的行程信息，生成一份真实、可执行并带证据的旅行方案。";

function seededDraft(brief?: TripBrief | null): TravelConstraintDraft {
  const draft = createDefaultTravelConstraintDraft();
  if (!brief) return draft;
  return {
    ...draft,
    destination: brief.destination.display_name,
    start_date: brief.date_window.start_date,
    end_date: brief.date_window.end_date,
    adults: String(brief.travelers.adults),
    seniors: String(brief.travelers.seniors ?? 0),
    budget_min: brief.budget.min_amount,
    budget_max: brief.budget.max_amount,
    currency: brief.budget.currency,
    preferences: (brief.preferences ?? []).map((item) => item.value).join("，"),
    accessibility_needs: (brief.travelers.accessibility_needs ?? []).join("，"),
  };
}

export function CommandBar({
  tripId,
  initialBrief,
  busy,
  disabled,
  mode,
  onModeChange,
  onAsk,
  onSubmit,
  onCancel,
}: CommandBarProps) {
  const [message, setMessage] = useState("");
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const [constraintEditor, setConstraintEditor] = useState<ConstraintEditorSurface | null>(null);
  const [constraintsConfirmed, setConstraintsConfirmed] = useState(Boolean(initialBrief));
  const [showConstraintErrors, setShowConstraintErrors] = useState(false);
  const [storageReady, setStorageReady] = useState(false);
  const quickStartSubmitted = useRef(false);
  const [draft, setDraft] = useState<TravelConstraintDraft>(() => seededDraft(initialBrief));
  const validation = useMemo(() => buildTripRequest(draft), [draft]);
  const errors = showConstraintErrors ? validation.errors : {};
  const confirmationError = showConstraintErrors
    ? validation.ok
      ? constraintsConfirmed ? undefined : "请先保存行程信息，再生成方案。"
      : "还有信息需要补充或修正。"
    : undefined;

  useEffect(() => {
    const persisted = loadTravelConstraintDraft(tripId);
    const quickStart = consumeQuickStartIntent(tripId);
    const nextDraft = persisted ?? seededDraft(initialBrief);
    setDraft(
      quickStart?.destination && !nextDraft.destination.trim()
        ? { ...nextDraft, destination: quickStart.destination }
        : nextDraft,
    );
    if (quickStart?.prompt) {
      setMessage(quickStart.prompt);
      onModeChange("ask");
      if (!quickStartSubmitted.current) {
        quickStartSubmitted.current = true;
        void onAsk(quickStart.prompt).then(() => setMessage("")).catch(() => undefined);
      }
    }
    setConstraintsConfirmed(!persisted && Boolean(initialBrief));
    setStorageReady(true);
    // This component is keyed by Trip ID; the initial brief is a one-time seed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  useEffect(() => {
    if (storageReady) saveTravelConstraintDraft(tripId, draft);
  }, [draft, storageReady, tripId]);

  function changeConstraint(field: keyof TravelConstraintDraft, value: string): void {
    setDraft((current) => ({ ...current, [field]: value }));
    setConstraintsConfirmed(false);
  }

  function confirmConstraints(): boolean {
    if (!validation.ok) {
      setShowConstraintErrors(true);
      return false;
    }
    setConstraintsConfirmed(true);
    setShowConstraintErrors(false);
    setConstraintEditor(null);
    return true;
  }

  async function submit(event: FormEvent<HTMLFormElement>, surface: ConstraintEditorSurface) {
    event.preventDefault();
    const clean = message.trim() || DEFAULT_PLANNING_COMMAND;
    if (busy || disabled) return;
    if (!validation.ok) {
      setShowConstraintErrors(true);
      setConstraintEditor(surface);
      return;
    }
    if (!constraintsConfirmed) setConstraintsConfirmed(true);
    try {
      await onSubmit(clean, validation.value);
      setMessage("");
    } catch {
      // The workspace renders the normalized public error. Keep the exact command
      // so a network-ambiguous retry can reuse its reserved Idempotency-Key.
    }
  }

  async function submitAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = message.trim();
    if (!clean || busy || disabled) return;
    try {
      await onAsk(clean);
      setMessage("");
    } catch {
      // Preserve the exact question for an idempotent retry after an ambiguous failure.
    }
  }

  const actionButton = (label: string, ariaLabel: string) => busy && onCancel ? (
    <button className="stop-button" type="button" onClick={() => void onCancel()}>
      <span aria-hidden="true">■</span> 停止
    </button>
  ) : (
    <button className="send-button" type="submit" disabled={busy || disabled || (mode === "ask" && !message.trim())} aria-label={ariaLabel}>
      <span>{label}</span>
      <Icons.Arrow width="19" height="19" />
    </button>
  );

  const askForm = (id: string) => (
    <form className="command-form" onSubmit={(event) => void submitAsk(event)}>
      <Icons.Spark width="20" height="20" />
      <label className="sr-only" htmlFor={id}>继续询问旅行助手</label>
      <textarea
        id={id}
        rows={1}
        maxLength={20_000}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="继续问旅行助手，例如“哪个区域住宿最方便？”"
        disabled={disabled}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      {actionButton("发送问题", "发送旅行问题")}
    </form>
  );

  const planForm = (id: string, surface: ConstraintEditorSurface) => (
    <form className="command-form" onSubmit={(event) => void submit(event, surface)}>
      <Icons.Spark width="20" height="20" />
      <label className="sr-only" htmlFor={id}>告诉旅行助手要规划或修改什么</label>
      <textarea
        id={id}
        rows={1}
        maxLength={20_000}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="继续追问或补充要求（选填），例如“上午轻松、下午看展”"
        disabled={disabled}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      {actionButton("获取方案", "获取可靠旅行方案")}
    </form>
  );

  const constraints = (id: string, surface: ConstraintEditorSurface) => (
    <TravelConstraintForm
      idPrefix={id}
      draft={draft}
      errors={errors}
      expanded={constraintEditor === surface}
      ready={validation.ok}
      confirmed={constraintsConfirmed}
      confirmationError={confirmationError}
      disabled={disabled || busy}
      onExpandedChange={(expanded) => setConstraintEditor(expanded ? surface : null)}
      onChange={changeConstraint}
      onConfirm={confirmConstraints}
    />
  );

  return (
    <div className="assistant-command">
      <div className="desktop-command command-composer">
        <div className="command-mode-switch" role="tablist" aria-label="助手模式">
          <button type="button" role="tab" aria-selected={mode === "ask"} onClick={() => onModeChange("ask")}>快速问答</button>
          <button type="button" role="tab" aria-selected={mode === "plan"} onClick={() => onModeChange("plan")}>生成行程</button>
        </div>
        {mode === "plan" && constraints("travel-constraints-desktop", "desktop")}
        {mode === "ask" ? askForm("assistant-question-desktop") : planForm("assistant-command-desktop", "desktop")}
      </div>
      <div className="mobile-command">
        <button type="button" className="mobile-command-trigger" onClick={() => setMobileExpanded((value) => !value)} aria-expanded={mobileExpanded}>
          <Icons.Spark width="18" height="18" />
          {busy ? "助手正在处理，可随时停止" : mode === "ask" ? "继续问旅行助手" : constraintsConfirmed ? "补充要求或直接生成" : "完善行程信息"}
          <span aria-hidden="true">{mobileExpanded ? "⌄" : "⌃"}</span>
        </button>
        {mobileExpanded && (
          <div className="mobile-composer">
            <div className="command-mode-switch" role="tablist" aria-label="助手模式">
              <button type="button" role="tab" aria-selected={mode === "ask"} onClick={() => onModeChange("ask")}>快速问答</button>
              <button type="button" role="tab" aria-selected={mode === "plan"} onClick={() => onModeChange("plan")}>生成行程</button>
            </div>
            {mode === "plan" && constraints("travel-constraints-mobile", "mobile")}
            {mode === "ask" ? askForm("assistant-question-mobile") : planForm("assistant-command-mobile", "mobile")}
          </div>
        )}
      </div>
      <p className="command-hint">{mode === "ask" ? "快速问答不要求先填写日期和预算，事实结论会附来源" : "点击“获取方案”即确认上方信息；需要调整时点“核对”"}</p>
    </div>
  );
}
