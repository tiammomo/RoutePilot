"use client";

import { useEffect, useState } from "react";

import type { PublicShareSnapshotResponse } from "@/shared/api/types";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: PublicShareSnapshotResponse };

export function PublicShare({ publicId }: { publicId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    async function load(): Promise<void> {
      try {
        const secret = window.location.hash.slice(1);
        if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
        if (secret) {
          const csrfResponse = await fetch("/api/auth/csrf", { cache: "no-store", credentials: "same-origin" });
          const csrf = await csrfResponse.json() as { token?: unknown };
          if (typeof csrf.token !== "string") throw new Error("无法初始化分享访问");
          const exchanged = await fetch(`/api/share/${encodeURIComponent(publicId)}/exchange`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.token },
            body: JSON.stringify({ secret }),
            cache: "no-store",
            credentials: "same-origin",
          });
          if (!exchanged.ok) throw new Error(exchanged.status === 429 ? "访问尝试过多，请稍后重试" : "分享链接无效或已被撤销");
        }
        const response = await fetch(`/api/share/${encodeURIComponent(publicId)}/snapshot`, { cache: "no-store", credentials: "same-origin" });
        if (!response.ok) throw new Error("分享访问已过期，请重新打开完整链接");
        const data = await response.json() as PublicShareSnapshotResponse;
        if (active) setState({ kind: "ready", data });
      } catch (error) {
        if (active) setState({ kind: "error", message: error instanceof Error ? error.message : "分享方案暂时不可用" });
      }
    }
    void load();
    return () => { active = false; };
  }, [publicId]);

  if (state.kind !== "ready") return <main className="public-share"><div className="gate-loader" /><h1>{state.kind === "loading" ? "正在安全打开旅行方案" : "无法打开旅行方案"}</h1>{state.kind === "error" && <p>{state.message}</p>}</main>;
  const snapshot = state.data.snapshot;
  return (
    <main className="public-share">
      <header><span className="run-kicker">ROUTEPILOT · READ ONLY</span><h1>{snapshot.title}</h1><p>{snapshot.destination.display_name} · {snapshot.date_window.start_date} → {snapshot.date_window.end_date}</p></header>
      {snapshot.days.map((day) => (
        <section key={day.date} className="day-card">
          <header><div><strong>{day.date}</strong></div><div><h2>{day.summary}</h2><small>{day.timezone}</small></div></header>
          <ol className="timeline">
            {day.time_blocks.map((block) => (
              <li key={block.block_id}><time>{block.time_range.start_local_time.slice(0, 5)}</time><i /><div><strong>{block.title}</strong><span>{block.place.display_name}</span>{block.transit_from_previous && <small>{block.transit_from_previous.mode} · {block.transit_from_previous.duration_minutes} 分钟</small>}</div></li>
            ))}
          </ol>
        </section>
      ))}
      <footer><p>这是经过脱敏和坐标降精度处理的只读副本，发布于 {new Date(snapshot.published_at).toLocaleString()}。</p></footer>
    </main>
  );
}
