"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { isOfficialArtifact, presentArtifact, selectPrimaryArtifact } from "@/entities/artifact/presentation";
import { loadRunCursor, saveRunCursor } from "@/entities/run/persistence";
import {
  emptyRunState,
  isRunTerminal,
  runEventReducer,
  type RunAction,
  type RunUiState,
} from "@/entities/run/reducer";
import { CommandBar } from "@/features/assistant/CommandBar";
import { AuthControls } from "@/features/auth/AuthControls";
import { ArtifactCanvas } from "./ArtifactCanvas";
import {
  availableArtifactAction,
  latestArtifactVersion,
} from "./artifact-lifecycle";
import { InsightPanel, type InsightTab } from "./InsightPanel";
import { buildPlanningRunInput } from "./run-submission";
import { RunStatus } from "./RunStatus";
import { ApiError, artifactApi, runApi, shareApi, tripApi } from "@/shared/api/client";
import { followRunEvents } from "@/shared/api/sse";
import type {
  ArtifactCommandType,
  ArtifactRecord,
  RunView,
  ShareView,
  TripRequestInput,
  TripView,
} from "@/shared/api/types";
import {
  clearArtifactCommand,
  clearRunSubmission,
  commandFingerprint,
  newIdempotencyKey,
  reserveArtifactCommand,
  reserveRunSubmission,
} from "@/shared/lib/idempotency";
import { Icons } from "@/shared/ui/Icons";
import { StatusBadge } from "@/shared/ui/StatusBadge";

type PageState = "loading" | "ready" | "error" | "offline" | "unauthenticated";
type MobileTab = "plan" | InsightTab;

export function TripWorkspace({ tripId }: { tripId: string }) {
  const [pageState, setPageState] = useState<PageState>("loading");
  const [trip, setTrip] = useState<TripView | null>(null);
  const [trips, setTrips] = useState<TripView[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [selectedArtifactKey, setSelectedArtifactKey] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [commandError, setCommandError] = useState<string | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTab>("plan");
  const [runState, reactDispatch] = useReducer(runEventReducer, emptyRunState);
  const runRef = useRef<RunUiState>(emptyRunState);
  const streamRef = useRef<AbortController | null>(null);
  const submissionRef = useRef<Promise<void> | null>(null);
  const cancellationRef = useRef<Promise<void> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [artifactAction, setArtifactAction] = useState<ArtifactCommandType | null>(null);
  const [shares, setShares] = useState<ShareView[]>([]);
  const [shareBusy, setShareBusy] = useState(false);
  const [latestShareUrl, setLatestShareUrl] = useState<string | null>(null);
  const [resumeValues, setResumeValues] = useState<Record<string, string | number | boolean | string[]>>({});

  const dispatch = useCallback((action: RunAction) => {
    runRef.current = runEventReducer(runRef.current, action);
    reactDispatch(action);
    saveRunCursor(runRef.current);
  }, []);

  const refreshArtifacts = useCallback(async () => {
    const [tripResponse, artifactResponse] = await Promise.all([
      tripApi.get(tripId),
      tripApi.artifacts(tripId),
    ]);
    setTrip(tripResponse);
    setArtifacts(artifactResponse.items);
  }, [tripId]);

  const startStream = useCallback((run: RunView, afterSeq: number) => {
    streamRef.current?.abort();
    const controller = new AbortController();
    streamRef.current = controller;
    dispatch({ type: "snapshot", run, lastSeq: afterSeq });
    if (isRunTerminal(runRef.current)) {
      dispatch({ type: "connection", connection: "closed" });
      return;
    }
    void followRunEvents({
      runId: run.run_id,
      signal: controller.signal,
      getAfterSeq: () => runRef.current.lastSeq,
      isTerminal: () => isRunTerminal(runRef.current),
      onEvent: (event) => {
        if (event.trip_id !== tripId || event.run_id !== runRef.current.runId) return;
        dispatch({ type: "event", event });
        if (
          event.type === "artifact.candidate_updated" ||
          event.type === "artifact.published" ||
          event.type === "run.completed"
        ) {
          void refreshArtifacts().catch(() => undefined);
        }
      },
      onStatus: (status) => {
        dispatch({
          type: "connection",
          connection: status === "live" ? "live" : status,
        });
      },
    }).catch(() => {
      if (!controller.signal.aborted) dispatch({ type: "connection", connection: "error" });
    });
  }, [dispatch, refreshArtifacts, tripId]);

  const load = useCallback(async () => {
    streamRef.current?.abort();
    dispatch({ type: "reset" });
    setPageState(typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "loading");
    setCommandError(null);
    try {
      const [tripResponse, listResponse, artifactResponse] = await Promise.all([
        tripApi.get(tripId),
        tripApi.list(),
        tripApi.artifacts(tripId),
      ]);
      setTrip(tripResponse);
      setTrips(listResponse.items);
      setArtifacts(artifactResponse.items);
      void shareApi.list(tripId).then((response) => setShares(response.items)).catch(() => undefined);
      setPageState("ready");

      const persisted = loadRunCursor(tripId);
      if (persisted) {
        try {
          const run = await runApi.get(persisted.runId);
          if (run.trip_id === tripId) startStream(run, persisted.lastSeq);
        } catch {
          // An expired/deleted Run must not block the still-authorized Trip snapshot.
        }
      }
    } catch (error) {
      setCommandError(error instanceof ApiError ? error.message : "旅行工作区暂时不可用");
      setPageState(
        error instanceof ApiError && error.status === 401
          ? "unauthenticated"
          : typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "error",
      );
    }
  }, [dispatch, startStream, tripId]);

  useEffect(() => {
    void load();
    const offline = () => {
      dispatch({ type: "connection", connection: "offline" });
    };
    window.addEventListener("offline", offline);
    return () => {
      streamRef.current?.abort();
      window.removeEventListener("offline", offline);
    };
    // Trip changes deliberately tear down the prior Run stream before loading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  const selectedArtifact = useMemo(() => {
    if (selectedArtifactKey) {
      const selected = artifacts.find((item) => `${item.artifact_id}:${item.version}` === selectedArtifactKey);
      if (selected) return selected;
    }
    return selectPrimaryArtifact(
      artifacts,
      trip?.current_artifact_id ?? null,
      trip?.current_artifact_version ?? null,
    );
  }, [artifacts, selectedArtifactKey, trip]);
  const presentation = useMemo(
    () => presentArtifact(selectedArtifact, artifacts),
    [artifacts, selectedArtifact],
  );
  const planningBrief = useMemo(
    () => presentArtifact(
      selectPrimaryArtifact(
        artifacts,
        trip?.current_artifact_id ?? null,
        trip?.current_artifact_version ?? null,
      ),
      artifacts,
    ).brief,
    [artifacts, trip?.current_artifact_id, trip?.current_artifact_version],
  );
  const official = isOfficialArtifact(
    selectedArtifact,
    trip?.current_artifact_id ?? null,
    trip?.current_artifact_version ?? null,
  );
  const busy = new Set(["queued", "running", "cancel_requested"]).has(runState.lifecycle);
  const visiblePlanArtifacts = artifacts.filter((artifact) =>
    new Set(["TripSnapshot", "ItineraryPlan"]).has(artifact.artifact_type),
  );
  const selectedLatestVersion = latestArtifactVersion(selectedArtifact, artifacts);
  const availableArtifactCommand = availableArtifactAction(selectedArtifact, artifacts, {
    tripStatus: trip?.status ?? "archived",
    busy,
    currentArtifactId: trip?.current_artifact_id ?? null,
    currentArtifactVersion: trip?.current_artifact_version ?? null,
  });
  const selectedIsHistorical = !!selectedArtifact &&
    selectedLatestVersion !== null &&
    selectedArtifact.version < selectedLatestVersion;
  const filteredTrips = trips.filter(
    (item) => item.status === "active" && item.title.toLocaleLowerCase().includes(filter.toLocaleLowerCase()),
  );

  function submitCommand(message: string, tripRequest: TripRequestInput): Promise<void> {
    if (submissionRef.current) return submissionRef.current;
    if (!trip || busy) return Promise.resolve();
    const operation = (async () => {
      setSubmitting(true);
      setCommandError(null);
      const baseVersion = trip.current_artifact_version;
      const input = buildPlanningRunInput(
        message,
        trip.title,
        trip.current_artifact_id,
        baseVersion,
        tripRequest,
      );
      const pending = reserveRunSubmission(
        trip.trip_id,
        commandFingerprint(message, baseVersion, input.command.payload),
      );
      try {
        const run = await runApi.create(
          trip.trip_id,
          input,
          pending.idempotencyKey,
        );
        clearRunSubmission(trip.trip_id, pending.idempotencyKey);
        startStream(run, 0);
      } catch (error) {
        setCommandError(
          error instanceof ApiError && error.code === "NETWORK_ERROR"
            ? "提交结果未知。命令编号已保留；恢复网络后再次提交同一句话不会创建重复 Run。"
            : error instanceof ApiError ? error.message : "无法提交规划命令",
        );
        throw error;
      } finally {
        setSubmitting(false);
      }
    })();
    submissionRef.current = operation.finally(() => {
      submissionRef.current = null;
    });
    return submissionRef.current;
  }

  async function resumeRun(): Promise<void> {
    const pending = runState.pendingInput;
    if (!runState.runId || !pending || submitting) return;
    setSubmitting(true);
    setCommandError(null);
    try {
      const run = await runApi.resume(
        runState.runId,
        {
          expected_control_version: runState.controlVersion,
          request_id: pending.request_id,
          values: resumeValues,
        },
        newIdempotencyKey("resume"),
      );
      setResumeValues({});
      startStream(run, runState.lastSeq);
    } catch (error) {
      setCommandError(error instanceof ApiError ? error.message : "补充信息未能提交");
    } finally {
      setSubmitting(false);
    }
  }

  function exposeShareUrl(publicId: string, secret: string): void {
    setLatestShareUrl(`${window.location.origin}/share/${encodeURIComponent(publicId)}#${secret}`);
  }

  async function createShare(): Promise<void> {
    const currentTrip = trip;
    if (!currentTrip?.current_artifact_id || !currentTrip.current_artifact_version || shareBusy) return;
    setShareBusy(true);
    setCommandError(null);
    try {
      const result = await shareApi.create(
        currentTrip.trip_id,
        currentTrip.current_artifact_id,
        currentTrip.current_artifact_version,
        newIdempotencyKey("share-create"),
      );
      setShares((current) => [result.share, ...current.filter((item) => item.share_id !== result.share.share_id)]);
      if (result.capability_secret) exposeShareUrl(result.share.public_id, result.capability_secret);
    } catch (error) {
      setCommandError(error instanceof ApiError ? error.message : "分享链接未能创建");
    } finally {
      setShareBusy(false);
    }
  }

  async function rotateShare(share: ShareView): Promise<void> {
    if (shareBusy || !window.confirm("旧链接会立即失效，确定轮换分享链接吗？")) return;
    setShareBusy(true);
    try {
      const result = await shareApi.rotate(share.share_id, share.version, newIdempotencyKey("share-rotate"));
      setShares((current) => current.map((item) => item.share_id === share.share_id ? result.share : item));
      if (result.capability_secret) exposeShareUrl(result.share.public_id, result.capability_secret);
    } catch (error) {
      setCommandError(error instanceof ApiError ? error.message : "分享链接未能轮换");
    } finally {
      setShareBusy(false);
    }
  }

  async function revokeShare(share: ShareView): Promise<void> {
    if (shareBusy || !window.confirm("撤销后该链接及已交换的访问会话都会立即失效，确定继续吗？")) return;
    setShareBusy(true);
    try {
      const result = await shareApi.revoke(share.share_id, share.version, newIdempotencyKey("share-revoke"));
      setShares((current) => current.map((item) => item.share_id === share.share_id ? result.share : item));
      setLatestShareUrl(null);
    } catch (error) {
      setCommandError(error instanceof ApiError ? error.message : "分享链接未能撤销");
    } finally {
      setShareBusy(false);
    }
  }

  function cancelRun(): Promise<void> {
    if (cancellationRef.current) return cancellationRef.current;
    if (!runState.runId || runState.controlVersion < 1) return Promise.resolve();
    const runId = runState.runId;
    const expectedVersion = runState.controlVersion;
    const cursor = runState.lastSeq;
    const idempotencyKey = newIdempotencyKey("cancel");
    const operation = (async () => {
      setCommandError(null);
      try {
        const run = await runApi.cancel(runId, expectedVersion, idempotencyKey);
        dispatch({ type: "snapshot", run, lastSeq: cursor });
      } catch (error) {
        setCommandError(error instanceof ApiError ? error.message : "停止请求未能完成");
      }
    })();
    cancellationRef.current = operation.finally(() => {
      cancellationRef.current = null;
    });
    return cancellationRef.current;
  }

  async function commandArtifact(command: ArtifactCommandType): Promise<void> {
    if (
      !selectedArtifact ||
      artifactAction ||
      !availableArtifactCommand ||
      availableArtifactCommand.type !== command
    ) return;
    if (
      availableArtifactCommand.confirmation &&
      !window.confirm(availableArtifactCommand.confirmation)
    ) return;

    const target = selectedArtifact;
    const pending = reserveArtifactCommand(target.artifact_id, command, target.version);
    setArtifactAction(command);
    setCommandError(null);
    try {
      let updated: ArtifactRecord;
      try {
        updated = await artifactApi.command(
          target.artifact_id,
          { type: command, base_version: target.version },
          pending.idempotencyKey,
        );
      } catch (error) {
        const ambiguous = !(error instanceof ApiError) ||
          error.code === "NETWORK_ERROR" ||
          error.code === "UPSTREAM_UNAVAILABLE" ||
          error.status >= 500;
        if (!ambiguous) clearArtifactCommand(target.artifact_id, pending.idempotencyKey);

        if (
          error instanceof ApiError &&
          (error.code === "VERSION_CONFLICT" || error.code === "ARTIFACT_TRANSITION_CONFLICT")
        ) {
          setSelectedArtifactKey(
            error.currentVersion
              ? `${target.artifact_id}:${error.currentVersion}`
              : null,
          );
          await refreshArtifacts().catch(() => undefined);
          setCommandError(
            error.currentVersion
              ? `方案已更新到 v${error.currentVersion}，已刷新；请核对最新版本后重试。`
              : "方案状态已变化，已刷新；请核对最新版本后重试。",
          );
        } else if (ambiguous) {
          setCommandError(
            "操作结果暂时未知，操作编号已保留；恢复网络后再次点击会安全复用同一请求。",
          );
        } else {
          setCommandError(error instanceof ApiError ? error.message : "方案状态未能更新");
        }
        return;
      }

      clearArtifactCommand(target.artifact_id, pending.idempotencyKey);
      setArtifacts((current) => {
        const reconciled = command === "artifact.publish"
          ? current.map((item) =>
              item.status === "published" &&
              (item.artifact_id !== updated.artifact_id || item.version !== updated.version)
                ? { ...item, status: "superseded" as const }
                : item,
            )
          : current;
        const index = reconciled.findIndex(
          (item) => item.artifact_id === updated.artifact_id && item.version === updated.version,
        );
        if (index < 0) return [updated, ...reconciled];
        const next = [...reconciled];
        next[index] = updated;
        return next;
      });
      setSelectedArtifactKey(`${updated.artifact_id}:${updated.version}`);
      setTrip((current) => {
        if (!current) return current;
        if (command === "artifact.publish") {
          return {
            ...current,
            current_artifact_id: updated.artifact_id,
            current_artifact_version: updated.version,
          };
        }
        if (
          command === "artifact.revoke" &&
          current.current_artifact_id === updated.artifact_id &&
          current.current_artifact_version === updated.version
        ) {
          return { ...current, current_artifact_id: null, current_artifact_version: null };
        }
        return current;
      });
      try {
        await refreshArtifacts();
      } catch {
        setCommandError("方案状态已更新，但最新版本列表暂时无法同步；请稍后刷新。");
      }
    } finally {
      setArtifactAction(null);
    }
  }

  if (pageState !== "ready" || !trip) {
    return (
      <main className="workspace-gate">
        <Link href="/" className="brand"><span className="brand-mark"><Icons.Route /></span><span>RoutePilot</span></Link>
        {pageState === "loading" ? (
          <><div className="gate-loader" /><h1>正在打开旅行工作区</h1><p>同步计划、证据和最近一次 Run…</p></>
        ) : pageState === "unauthenticated" ? (
          <><span className="empty-icon"><Icons.Compass /></span><h1>登录后打开旅行工作区</h1><p>此工作区只通过同源的受信会话访问，不接收浏览器 Bearer Token。</p><a className="primary-button" href="/api/auth/login">安全登录</a><Link href="/">返回首页</Link></>
        ) : (
          <><span className="empty-icon">{pageState === "offline" ? "⌁" : "!"}</span><h1>{pageState === "offline" ? "你现在处于离线状态" : "工作区未能打开"}</h1><p>{commandError}</p><button className="primary-button" type="button" onClick={() => void load()}>重新连接</button><Link href="/trips">返回我的旅行</Link></>
        )}
      </main>
    );
  }

  return (
    <main className="workspace-shell" data-mobile-tab={mobileTab}>
      <aside className="trip-rail">
        <Link href="/" className="brand"><span className="brand-mark"><Icons.Route /></span><span>RoutePilot</span></Link>
        <Link className="rail-new" href="/trips"><Icons.Plus /> 新建旅行</Link>
        <label className="rail-search"><Icons.Search /><span className="sr-only">搜索旅行</span><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="搜索旅行" /></label>
        <nav aria-label="旅行列表">
          <span className="rail-label">进行中</span>
          {filteredTrips.map((item) => (
            <Link href={`/trips/${item.trip_id}`} key={item.trip_id} aria-current={item.trip_id === trip.trip_id ? "page" : undefined}>
              <span className="trip-monogram">{item.title.slice(0, 1)}</span>
              <span><strong>{item.title}</strong><small>{item.current_artifact_id ? "已有正式方案" : "待规划"}</small></span>
            </Link>
          ))}
        </nav>
        <div className="rail-footer"><span className="member-chip">RP</span><span><strong>旅行者</strong><small>成员工作区</small></span></div>
      </aside>

      <section className="workspace-main" id="plan-panel">
        <header className="workspace-header">
          <div className="workspace-mobile-brand"><Link href="/trips" aria-label="返回旅行列表">←</Link><span className="brand-mark"><Icons.Route /></span></div>
          <div>
            <div className="workspace-title-row">
              <h1>{trip.title}</h1>
              {trip.status === "archived" && <StatusBadge>已归档</StatusBadge>}
            </div>
            <p>{trip.timezone} · 所有修改都会保留版本</p>
          </div>
          <div className="workspace-header-actions">
            <button type="button" onClick={() => void refreshArtifacts()}><span aria-hidden="true">↻</span> 刷新</button>
            <AuthControls compact />
            <span className="member-stack"><i>RP</i><i>AI</i></span>
          </div>
        </header>

        <section className="constraint-strip" aria-label="旅行约束">
          <div className="constraint-title"><Icons.Spark /><span><strong>规划约束</strong><small>从 TripBrief 读取，不从回答文本猜测</small></span></div>
          {presentation.brief ? (
            <div className="constraint-chips">
              <span><Icons.Calendar /> {presentation.brief.date_window.start_date} → {presentation.brief.date_window.end_date}</span>
              <span>{presentation.brief.travelers.adults} 位成人</span>
              <span><Icons.Wallet /> {presentation.brief.budget.min_amount}–{presentation.brief.budget.max_amount} {presentation.brief.budget.currency}</span>
              {presentation.brief.preferences?.slice(0, 2).map((item) => <span key={item.preference_id}>{item.value}</span>)}
            </div>
          ) : (
            <div className="constraint-chips muted"><span>日期待确认</span><span>人数待确认</span><span>预算待确认</span></div>
          )}
        </section>

        {runState.runId && <RunStatus state={runState} />}
        {commandError && <div className="inline-alert workspace-alert" role="alert">{commandError}<button type="button" onClick={() => setCommandError(null)}>关闭</button></div>}

        {visiblePlanArtifacts.length > 1 && (
          <div className="artifact-switcher" aria-label="方案版本">
            <span>方案版本</span>
            {visiblePlanArtifacts.slice(0, 8).map((artifact) => (
              <button
                type="button"
                key={`${artifact.artifact_id}:${artifact.version}`}
                aria-pressed={artifact === selectedArtifact}
                onClick={() => setSelectedArtifactKey(`${artifact.artifact_id}:${artifact.version}`)}
              >{artifact.artifact_type === "TripSnapshot" ? "整案" : "计划"} v{artifact.version} · {artifact.status === "published" ? "正式" : artifact.status}</button>
            ))}
          </div>
        )}


        {availableArtifactCommand && (
          <div className="artifact-actions" aria-label="方案操作">
            <span>
              当前版本：{selectedArtifact?.artifact_type} v{selectedArtifact?.version}
              <small>状态 {selectedArtifact?.status}</small>
            </span>
            <button
              type="button"
              data-command={availableArtifactCommand.type}
              disabled={artifactAction !== null || busy}
              onClick={() => void commandArtifact(availableArtifactCommand.type)}
            >
              {artifactAction === availableArtifactCommand.type
                ? "正在更新…"
                : availableArtifactCommand.label}
            </button>
          </div>
        )}

        {selectedIsHistorical && selectedArtifact && selectedLatestVersion && (
          <div className="artifact-actions artifact-actions-readonly" aria-label="历史方案版本">
            <span>
              当前查看：{selectedArtifact.artifact_type} v{selectedArtifact.version}
              <small>历史版本只读；生命周期操作仅适用于最新的 v{selectedLatestVersion}</small>
            </span>
            <button
              type="button"
              data-command="view-latest"
              onClick={() => setSelectedArtifactKey(
                `${selectedArtifact.artifact_id}:${selectedLatestVersion}`,
              )}
            >
              查看最新版本
            </button>
          </div>
        )}

        {runState.lifecycle === "waiting_input" && runState.pendingInput && (
          <form className="artifact-actions run-input-form" onSubmit={(event) => { event.preventDefault(); void resumeRun(); }}>
            <span>{runState.pendingInput.prompt}<small>请在 {new Date(runState.pendingInput.expires_at).toLocaleString()} 前提交</small></span>
            <div className="run-input-fields">
              {runState.pendingInput.fields.map((field) => (
                <label key={field.field_id}>
                  {field.label}
                  {field.input_type === "single_select" ? (
                    <select required={field.required} value={String(resumeValues[field.field_id] ?? "")} onChange={(event) => setResumeValues((current) => ({ ...current, [field.field_id]: event.target.value }))}>
                      <option value="">请选择</option>{field.options.map((option) => <option key={option}>{option}</option>)}
                    </select>
                  ) : field.input_type === "multi_select" ? (
                    <select multiple required={field.required} value={Array.isArray(resumeValues[field.field_id]) ? resumeValues[field.field_id] as string[] : []} onChange={(event) => setResumeValues((current) => ({ ...current, [field.field_id]: Array.from(event.target.selectedOptions, (option) => option.value) }))}>
                      {field.options.map((option) => <option key={option}>{option}</option>)}
                    </select>
                  ) : field.input_type === "confirmation" ? (
                    <input type="checkbox" checked={resumeValues[field.field_id] === true} onChange={(event) => setResumeValues((current) => ({ ...current, [field.field_id]: event.target.checked }))} />
                  ) : (
                    <input type={field.input_type === "date" ? "date" : field.input_type === "number" ? "number" : "text"} required={field.required} value={String(resumeValues[field.field_id] ?? "")} onChange={(event) => setResumeValues((current) => {
                      if (field.input_type === "number" && event.target.value === "") {
                        const next = { ...current };
                        delete next[field.field_id];
                        return next;
                      }
                      return { ...current, [field.field_id]: field.input_type === "number" ? event.target.valueAsNumber : event.target.value };
                    })} />
                  )}
                </label>
              ))}
            </div>
            <button type="submit" disabled={submitting}>{submitting ? "正在恢复…" : "提交并继续规划"}</button>
          </form>
        )}

        {official && trip.current_artifact_id && trip.current_artifact_version && (
          <section className="artifact-actions share-controls" aria-label="只读分享管理">
            <span>安全分享<small>只公开脱敏、坐标降精度的正式方案副本</small></span>
            <button type="button" disabled={shareBusy} onClick={() => void createShare()}>{shareBusy ? "正在处理…" : "创建只读链接"}</button>
            {latestShareUrl && (
              <div className="share-url" role="status">
                <input readOnly value={latestShareUrl} aria-label="新分享链接" />
                <button type="button" onClick={() => void navigator.clipboard.writeText(latestShareUrl)}>复制</button>
                <small>该完整链接只显示在本次页面中，请立即保存。</small>
              </div>
            )}
            {shares.filter((share) => share.status === "active").map((share) => (
              <div className="share-row" key={share.share_id}>
                <span>正式方案 v{share.source_artifact_version} · 链接版本 {share.capability_epoch}</span>
                <button type="button" disabled={shareBusy} onClick={() => void rotateShare(share)}>轮换</button>
                <button type="button" disabled={shareBusy} onClick={() => void revokeShare(share)}>撤销</button>
              </div>
            ))}
          </section>
        )}

        <ArtifactCanvas presentation={presentation} run={runState} official={official} loading={false} />
        <CommandBar
          key={trip.trip_id}
          tripId={trip.trip_id}
          initialBrief={planningBrief}
          busy={busy || submitting}
          disabled={trip.status === "archived"}
          onSubmit={submitCommand}
          onCancel={busy ? cancelRun : undefined}
        />
      </section>

      <InsightPanel
        presentation={presentation}
        run={runState}
        activeTab={mobileTab === "plan" ? "map" : mobileTab}
        onTabChange={(tab) => setMobileTab(tab)}
      />

      <nav className="mobile-workspace-tabs" aria-label="工作区视图">
        {([
          ["plan", "计划", Icons.Route],
          ["map", "地图", Icons.Map],
          ["budget", "预算", Icons.Wallet],
          ["evidence", "证据", Icons.Evidence],
        ] as const).map(([id, label, Icon]) => (
          <button
            type="button"
            key={id}
            aria-pressed={mobileTab === id}
            onClick={() => {
              setMobileTab(id);
              if (id === "plan") document.getElementById("plan-panel")?.scrollIntoView();
            }}
          ><Icon />{label}</button>
        ))}
      </nav>
    </main>
  );
}
