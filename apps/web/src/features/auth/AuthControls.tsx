"use client";

import { useEffect, useState } from "react";

type AuthState = "loading" | "anonymous" | "oidc" | "development" | "error";

interface SessionResponse {
  authenticated?: unknown;
  mode?: unknown;
}

export function AuthControls({ compact = false }: { compact?: boolean }) {
  const [state, setState] = useState<AuthState>("loading");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/auth/session", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("session unavailable");
        const payload = await response.json() as SessionResponse;
        if (payload.authenticated !== true) return "anonymous" as const;
        return payload.mode === "development" ? "development" as const : "oidc" as const;
      })
      .then(setState)
      .catch(() => {
        if (!controller.signal.aborted) setState("error");
      });
    return () => controller.abort();
  }, []);

  async function logout(): Promise<void> {
    if (busy) return;
    setBusy(true);
    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!csrfResponse.ok) throw new Error("request protection unavailable");
      const csrf = await csrfResponse.json() as { token?: unknown };
      if (typeof csrf.token !== "string" || csrf.token.length < 20) throw new Error("invalid request protection");
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": csrf.token,
        },
      });
      if (!response.ok) throw new Error("logout failed");
      const payload = await response.json() as { logout_url?: unknown };
      if (typeof payload.logout_url !== "string" || payload.logout_url.length > 2_048) {
        throw new Error("invalid logout destination");
      }
      const destination = new URL(payload.logout_url, window.location.origin);
      if (destination.protocol !== "https:" && destination.origin !== window.location.origin) {
        throw new Error("invalid logout destination");
      }
      window.location.assign(destination.toString());
    } catch {
      setState("error");
      setBusy(false);
    }
  }

  if (state === "anonymous") {
    return <a className={compact ? "auth-link compact" : "auth-link"} href="/api/auth/login">登录</a>;
  }
  if (state === "oidc") {
    return (
      <button className={compact ? "auth-link compact" : "auth-link"} type="button" disabled={busy} onClick={() => void logout()}>
        {busy ? "正在退出…" : "退出登录"}
      </button>
    );
  }
  if (state === "development") {
    return <span className="auth-mode" title="本地开发身份">本地身份</span>;
  }
  if (state === "error") {
    return <a className={compact ? "auth-link compact" : "auth-link"} href="/api/auth/login">重新登录</a>;
  }
  return <span className="auth-mode" aria-label="正在确认登录状态">···</span>;
}
