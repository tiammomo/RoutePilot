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

export function TripsScreen() {
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
          <Link href="/">发现</Link>
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
          <span className="eyebrow">开始规划</span>
          <h1>先创建一个旅行工作区</h1>
          <p>现在只需要一个容易识别的名字。进入工作区后，再依次确认目的地、日期、同行人数和预算。</p>
        </div>
        <TripCreateForm onCreated={(trip) => router.push(`/trips/${trip.trip_id}`)} />
      </section>

      <section className="trip-library constrained" aria-labelledby="trip-library-title">
        <div className="section-heading">
          <div>
            <h2 id="trip-library-title">{showArchived ? "已归档" : visibleTrips.length ? "进行中的旅行" : "创建后会发生什么？"}</h2>
            <p>{showArchived ? "随时恢复，不丢失历史版本。" : visibleTrips.length ? "继续规划或打开当前正式方案。" : "RoutePilot 会按清晰的步骤带你完成第一份正式方案。"}</p>
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
                <div><strong>创建工作区</strong><p>先给旅行起一个名字，方便之后识别。</p></div>
              </article>
              <article>
                <span>2</span>
                <div><strong>确认旅行约束</strong><p>填写目的地、日期、同行人、预算和偏好。</p></div>
              </article>
              <article>
                <span>3</span>
                <div><strong>查看正式方案</strong><p>Agent 会研究、规划并校验，结果带证据和版本。</p></div>
              </article>
            </div>
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                document.getElementById("trip-title")?.focus();
                document.getElementById("trip-title")?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
            >
              从第 1 步开始 <Icons.Arrow />
            </button>
          </section>
        )}

        {viewState === "ready" && visibleTrips.length > 0 && (
          <div className="trip-grid">
            {visibleTrips.map((trip, index) => (
              <article className="trip-card" key={trip.trip_id} style={{ "--card-index": index } as React.CSSProperties}>
                <div className="trip-card-art" data-variant={index % 3} aria-hidden="true">
                  <span>{trip.title.slice(0, 1)}</span>
                  <div className="route-line" />
                </div>
                <div className="trip-card-body">
                  <div className="trip-card-meta">
                    <StatusBadge tone={trip.current_artifact_id ? "success" : "brand"}>
                      {trip.current_artifact_id ? "已有正式方案" : "草稿"}
                    </StatusBadge>
                    <span>更新于 {formatDate(trip.updated_at)}</span>
                  </div>
                  <h3><Link href={`/trips/${trip.trip_id}`}>{trip.title}</Link></h3>
                  <p>{trip.timezone} · 版本 {trip.version}</p>
                  <div className="trip-card-actions">
                    <Link className="text-button" href={`/trips/${trip.trip_id}`}>打开工作台 <Icons.Arrow /></Link>
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
