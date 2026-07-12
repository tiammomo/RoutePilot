"use client";

import type { TripBrief } from "@routepilot/contracts-generated";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { TravelConstraintForm } from "@/features/assistant/TravelConstraintForm";
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
  onSubmit: (message: string, tripRequest: TripRequestInput) => Promise<void>;
  onCancel?: () => Promise<void>;
}

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
  onSubmit,
  onCancel,
}: CommandBarProps) {
  const [message, setMessage] = useState("");
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const [constraintsExpanded, setConstraintsExpanded] = useState(true);
  const [constraintsConfirmed, setConstraintsConfirmed] = useState(false);
  const [showConstraintErrors, setShowConstraintErrors] = useState(false);
  const [storageReady, setStorageReady] = useState(false);
  const [draft, setDraft] = useState<TravelConstraintDraft>(() => seededDraft(initialBrief));
  const validation = useMemo(() => buildTripRequest(draft), [draft]);
  const errors = showConstraintErrors ? validation.errors : {};
  const confirmationError = showConstraintErrors
    ? validation.ok
      ? constraintsConfirmed ? undefined : "请先勾选确认，之后再提交旅行命令。"
      : "请先修正上方标出的旅行约束。"
    : undefined;

  useEffect(() => {
    const persisted = loadTravelConstraintDraft(tripId);
    setDraft(persisted ?? seededDraft(initialBrief));
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

  function confirmConstraints(confirmed: boolean): void {
    if (confirmed && !validation.ok) {
      setShowConstraintErrors(true);
      setConstraintsExpanded(true);
      return;
    }
    setConstraintsConfirmed(confirmed);
    setShowConstraintErrors(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = message.trim();
    if (!clean || busy || disabled) return;
    if (!validation.ok || !constraintsConfirmed) {
      setShowConstraintErrors(true);
      setConstraintsExpanded(true);
      return;
    }
    try {
      await onSubmit(clean, validation.value);
      setMessage("");
    } catch {
      // The workspace renders the normalized public error. Keep the exact command
      // so a network-ambiguous retry can reuse its reserved Idempotency-Key.
    }
  }

  const form = (id: string) => (
    <form className="command-form" onSubmit={submit}>
      <Icons.Spark width="20" height="20" />
      <label className="sr-only" htmlFor={id}>告诉旅行助手要规划或修改什么</label>
      <textarea
        id={id}
        rows={1}
        maxLength={20_000}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="第 3 步：补充最重要的要求，例如“上午轻松、下午看展”"
        disabled={disabled}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      {busy && onCancel ? (
        <button className="stop-button" type="button" onClick={() => void onCancel()}>
          <span aria-hidden="true">■</span> 停止
        </button>
      ) : (
        <button className="send-button" type="submit" disabled={busy || !message.trim() || disabled} aria-label="提交旅行命令">
          <Icons.Arrow width="19" height="19" />
        </button>
      )}
    </form>
  );

  const constraints = (id: string) => (
    <TravelConstraintForm
      idPrefix={id}
      draft={draft}
      errors={errors}
      expanded={constraintsExpanded}
      confirmed={constraintsConfirmed}
      confirmationError={confirmationError}
      disabled={disabled || busy}
      onExpandedChange={setConstraintsExpanded}
      onChange={changeConstraint}
      onConfirm={confirmConstraints}
    />
  );

  return (
    <div className="assistant-command">
      <div className="desktop-command command-composer">
        {constraints("travel-constraints-desktop")}
        {form("assistant-command-desktop")}
      </div>
      <div className="mobile-command">
        <button type="button" className="mobile-command-trigger" onClick={() => setMobileExpanded((value) => !value)} aria-expanded={mobileExpanded}>
          <Icons.Spark width="18" height="18" />
          {busy ? "正在规划，可随时停止" : "第 2 步 · 填写约束并生成方案"}
          <span aria-hidden="true">{mobileExpanded ? "⌄" : "⌃"}</span>
        </button>
        {mobileExpanded && (
          <div className="mobile-composer">
            {constraints("travel-constraints-mobile")}
            {form("assistant-command-mobile")}
          </div>
        )}
      </div>
      <p className="command-hint">填写约束 → 勾选核对确认 → 补充一句重点 → 发送生成方案</p>
    </div>
  );
}
