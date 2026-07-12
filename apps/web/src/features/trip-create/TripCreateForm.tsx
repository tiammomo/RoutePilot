"use client";

import { useState, type FormEvent } from "react";

import { tripApi, ApiError } from "@/shared/api/client";
import type { TripView } from "@/shared/api/types";
import { Icons } from "@/shared/ui/Icons";
import { deriveTripTitle, saveQuickStartIntent } from "./quick-start-intent";

const STARTER_PROMPTS = [
  "带父母去北京 4 天，少走路，怎么安排？",
  "第一次去京都，住哪里出行最方便？",
  "8000 元两个人去大理 5 天够吗？",
] as const;

export function TripCreateForm({
  onCreated,
  variant = "card",
  initialPrompt = "",
}: {
  onCreated: (trip: TripView) => void;
  variant?: "card" | "hero";
  initialPrompt?: string;
}) {
  const [prompt, setPrompt] = useState(initialPrompt.slice(0, 2_000));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const trip = await tripApi.create({
        title: deriveTripTitle(cleanPrompt),
        locale: "zh-CN",
        timezone: "Asia/Shanghai",
      });
      saveQuickStartIntent(trip.trip_id, cleanPrompt);
      setPrompt("");
      onCreated(trip);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "暂时无法创建旅行");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="trip-create-form" data-variant={variant} onSubmit={submit}>
      <div className="trip-create-heading">
        <span><Icons.Spark width="13" height="13" /> 旅行助手</span>
        <div>
          <strong>{variant === "hero" ? "现在最想解决什么旅行问题？" : "直接说说你想怎么旅行"}</strong>
          <small>说目的地、同行人或偏好都可以；信息不够时，助手只追问必要内容。</small>
        </div>
      </div>
      <label className="sr-only" htmlFor={`trip-prompt-${variant}`}>旅行问题或需求</label>
      <div className="trip-create-input">
        <textarea
          id={`trip-prompt-${variant}`}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          maxLength={2_000}
          rows={variant === "hero" ? 2 : 1}
          placeholder="例如：十月带父母去北京 4 天，希望少走路、住得方便"
          autoComplete="off"
          autoFocus
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button className="primary-button" type="submit" disabled={!prompt.trim() || submitting}>
          {submitting ? "正在准备…" : "问问助手"}
          <Icons.Arrow width="17" height="17" />
        </button>
      </div>
      <div className="trip-starters" aria-label="常见旅行问题示例">
        <span>可以这样问：</span>
        {STARTER_PROMPTS.map((starter) => (
          <button
            type="button"
            key={starter}
            onClick={() => {
              setPrompt(starter);
              document.getElementById(`trip-prompt-${variant}`)?.focus();
            }}
          >
            {starter}
          </button>
        ))}
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
    </form>
  );
}
