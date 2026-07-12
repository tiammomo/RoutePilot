"use client";

import { useState, type FormEvent } from "react";

import { tripApi, ApiError } from "@/shared/api/client";
import type { TripView } from "@/shared/api/types";
import { Icons } from "@/shared/ui/Icons";

const STARTER_TITLES = [
  "北京周末文化之旅",
  "京都红叶慢旅行",
  "上海亲子博物馆之旅",
] as const;

export function TripCreateForm({ onCreated }: { onCreated: (trip: TripView) => void }) {
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanTitle = title.trim();
    if (!cleanTitle || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const trip = await tripApi.create({
        title: cleanTitle,
        locale: "zh-CN",
        timezone: "Asia/Shanghai",
      });
      setTitle("");
      onCreated(trip);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "暂时无法创建旅行");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="trip-create-form" onSubmit={submit}>
      <div className="trip-create-heading">
        <span>第 1 步</span>
        <div>
          <strong>给这次旅行起个名字</strong>
          <small>这里只创建工作区，下一步再填写日期、人数和预算。</small>
        </div>
      </div>
      <label className="sr-only" htmlFor="trip-title">旅行名称</label>
      <div className="trip-create-input">
        <Icons.Spark width="20" height="20" />
        <input
          id="trip-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={160}
          placeholder="例如：十月京都红叶慢旅行"
          autoComplete="off"
          autoFocus
        />
        <button className="primary-button" type="submit" disabled={!title.trim() || submitting}>
          {submitting ? "创建中…" : "下一步"}
          <Icons.Arrow width="17" height="17" />
        </button>
      </div>
      <div className="trip-starters" aria-label="旅行名称示例">
        <span>没想好？试试：</span>
        {STARTER_TITLES.map((starter) => (
          <button
            type="button"
            key={starter}
            onClick={() => {
              setTitle(starter);
              document.getElementById("trip-title")?.focus();
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
