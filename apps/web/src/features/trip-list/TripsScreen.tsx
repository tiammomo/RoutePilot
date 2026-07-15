"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { TripCreateForm } from "@/features/trip-create/TripCreateForm";
import { AuthControls } from "@/features/auth/AuthControls";
import { ApiError, tripApi } from "@/shared/api/client";
import type { TripView } from "@/shared/api/types";
import { formatDate } from "@/shared/lib/format";
import { Icons } from "@/shared/ui/Icons";
import { StatusBadge } from "@/shared/ui/StatusBadge";

type ViewState = "loading" | "ready" | "error" | "offline" | "unauthenticated";

export function TripsScreen({ initialPrompt = "" }: { initialPrompt?: string }) {
  const router = useRouter();
  const [trips, setTrips] = useState<TripView[]>([]);
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [showArchived, setShowArchived] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setViewState(typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "loading");
    setMessage(null);
    try {
      const response = await tripApi.list();
      setTrips(response.items);
      setViewState("ready");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "无法读取旅行列表");
      setViewState(
        error instanceof ApiError && error.status === 401
          ? "unauthenticated"
          : typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "error",
      );
    }
  }, []);

  useEffect(() => {
    void load();
    const offline = () => setViewState("offline");
    const online = () => void load();
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    };
  }, [load]);

  const visibleTrips = useMemo(
    () => trips.filter((trip) => showArchived ? trip.status === "archived" : trip.status !== "archived"),
    [showArchived, trips],
  );

  async function toggleArchive(trip: TripView) {
    setBusyId(trip.trip_id);
    setMessage(null);
    try {
      const updated = trip.status === "archived"
        ? await tripApi.restore(trip.trip_id)
        : await tripApi.archive(trip.trip_id);
      setTrips((current) => current.map((item) => item.trip_id === updated.trip_id ? updated : item));
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "操作未能完成");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="trips-page">
      <header className="site-header constrained">
        <Link href="/" className="brand" aria-label="RoutePilot 首页">
          <span className="brand-mark"><Icons.Route /></span>
          <span>RoutePilot</span>
        </Link>
        <nav aria-label="主导航">
          <Link href="/">问助手</Link>
          <Link href="/trips" aria-current="page">我的旅行</Link>
        </nav>
        <div className="header-account"><AuthControls /><span className="member-chip">RP</span></div>
      </header>

      {viewState === "unauthenticated" ? (
        <section className="auth-gate constrained">
          <span className="empty-icon"><Icons.Compass /></span>
          <h1>登录后继续规划</h1>
          <p>你的旅行、方案版本与证据只会在受信会话中读取。</p>
          <a className="primary-button" href="/api/auth/login">安全登录</a>
        </section>
      ) : <>

      <section className="trips-hero constrained">
        <div>
          <span className="eyebrow">随时问，马上开始</span>
          <h1>从一个真实的旅行问题开始</h1>
          <p>不用给项目起名字，也不用先整理完整需求。直接说你的想法，RoutePilot 会保留上下文，并只补问生成可靠答案所需的信息。</p>
        </div>
        <TripCreateForm initialPrompt={initialPrompt} onCreated={(trip) => router.push(`/trips/${trip.trip_id}`)} />
      </section>

      <section className="trip-library constrained" aria-labelledby="trip-library-title">
        <div className="section-heading">
          <div>
            <h2 id="trip-library-title">{showArchived ? "已归档" : visibleTrips.length ? "最近的旅行对话" : "提问后会发生什么？"}</h2>
            <p>{showArchived ? "随时恢复，不丢失历史版本。" : visibleTrips.length ? "继续追问、调整行程或查看正式方案。" : "RoutePilot 会把问题、约束、证据和最终方案保存在同一个上下文中。"}</p>
          </div>
          <div className="segmented" role="group" aria-label="旅行状态筛选">
            <button type="button" aria-pressed={!showArchived} onClick={() => setShowArchived(false)}>进行中</button>
            <button type="button" aria-pressed={showArchived} onClick={() => setShowArchived(true)}>已归档</button>
          </div>
        </div>

        {message && <div className="inline-alert" role="alert">{message}<button type="button" onClick={() => void load()}>重试</button></div>}

        {viewState === "loading" && (
          <div className="trip-grid" aria-label="正在载入旅行">
            {[0, 1, 2].map((item) => <div className="trip-card skeleton-card" key={item} />)}
          </div>
        )}

        {viewState === "offline" && (
          <div className="empty-state">
            <span className="empty-icon">⌁</span>
            <h3>当前处于离线状态</h3>
            <p>恢复网络后，旅行列表会自动重新连接。</p>
          </div>
        )}

        {viewState === "ready" && !visibleTrips.length && showArchived && (
          <div className="empty-state">
            <span className="empty-icon"><Icons.Compass /></span>
            <h3>还没有归档旅行</h3>
            <p>归档只会整理列表，不会删除计划。</p>
          </div>
        )}

        {viewState === "ready" && !visibleTrips.length && !showArchived && (
          <section className="first-trip-guide" aria-label="首次旅行创建步骤">
            <div className="first-trip-steps">
              <article data-active="true">
                <span>1</span>
                <div><strong>说出旅行问题</strong><p>目的地、预算、同行人或纠结点，都可以直接说。</p></div>
              </article>
              <article>
                <span>2</span>
                <div><strong>只补必要信息</strong><p>生成正式行程前，再确认日期、同行人和预算。</p></div>
              </article>
              <article>
                <span>3</span>
                <div><strong>获得可靠方案</strong><p>Agent 协作研究、规划并校验，结果带证据和版本。</p></div>
              </article>
            </div>
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                document.getElementById("trip-prompt-card")?.focus();
                document.getElementById("trip-prompt-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
            >
              问第一个问题 <Icons.Arrow />
            </button>
          </section>
        )}

        {viewState === "ready" && visibleTrips.length > 0 && (
          <div className="trip-grid">
            {visibleTrips.map((trip, index) => (
              <article className="trip-card" key={trip.trip_id} style={{ "--card-index": index } as React.CSSProperties}>
                <div className="trip-card-art" data-variant={index % 3} aria-hidden="true">
                  <span className="trip-art-kicker">TRAVEL THREAD</span>
                  <div className="trip-art-route"><i /><i /><i /></div>
                  <span className="trip-art-state">{trip.current_artifact_id ? "已形成可执行方案" : "等待你的下一次提问"}</span>
                </div>
                <div className="trip-card-body">
                  <div className="trip-card-meta">
                    <StatusBadge tone={trip.current_artifact_id ? "success" : "brand"}>
                      {trip.current_artifact_id ? "已有正式方案" : "旅行对话"}
                    </StatusBadge>
                    <span>更新于 {formatDate(trip.updated_at)}</span>
                  </div>
                  <h3><Link href={`/trips/${trip.trip_id}`}>{trip.title}</Link></h3>
                  <p>{trip.timezone} · 版本 {trip.version}</p>
                  <div className="trip-card-actions">
                    <Link className="text-button" href={`/trips/${trip.trip_id}`}>{trip.current_artifact_id ? "查看方案" : "继续询问"} <Icons.Arrow /></Link>
                    <button type="button" onClick={() => void toggleArchive(trip)} disabled={busyId === trip.trip_id}>
                      {busyId === trip.trip_id ? "处理中…" : trip.status === "archived" ? "恢复" : "归档"}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      </>}
    </main>
  );
}
