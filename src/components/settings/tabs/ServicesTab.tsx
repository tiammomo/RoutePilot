"use client";

import type { ReactNode } from "react";

interface ServiceToken {
  id: string;
  provider: string;
  token: string;
  name?: string;
  created_at: string;
  last_used?: string;
}

const SERVICE_LABELS: Record<string, string> = {
  github: "GitHub",
  supabase: "Supabase",
  vercel: "Vercel",
};

interface ServicesTabProps {
  tokens: { [key: string]: ServiceToken | null };
  getProviderIcon: (provider: string) => ReactNode;
  onServiceClick: (provider: "github" | "supabase" | "vercel") => void;
}

function ServicesTab({ tokens, getProviderIcon, onServiceClick }: ServicesTabProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-4 text-lg font-medium text-slate-900">服务令牌</h3>
        <p className="mb-6 text-sm text-slate-600">
          配置 GitHub、Supabase 与 Vercel 令牌。令牌会被所有工作空间复用，用于仓库创建、数据库接入和部署发布。
        </p>

        <div className="space-y-4">
          {Object.entries(tokens).map(([provider, token]) => (
            <div
              key={provider}
              className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-4"
            >
              <div className="flex items-center gap-3">
                <div className="text-slate-700">{getProviderIcon(provider)}</div>
                <div>
                  <p className="font-medium text-slate-900">{SERVICE_LABELS[provider] ?? provider}</p>
                  <p className="text-sm text-slate-600">
                    {token ? (
                      <>已配置令牌 · {new Date(token.created_at).toLocaleDateString()}</>
                    ) : (
                      "未配置令牌"
                    )}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {token && <div className="h-2 w-2 animate-pulse rounded-full bg-green-400" />}
                <button
                  onClick={() => onServiceClick(provider as "github" | "supabase" | "vercel")}
                  className="rounded-lg bg-slate-200 px-3 py-1.5 text-sm text-slate-700 transition-all hover:bg-slate-300"
                >
                  {token ? "更新令牌" : "添加令牌"}
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-[#DE7356]" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fillRule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-slate-900">令牌使用范围</h3>
              <div className="mt-2 text-sm text-slate-700">
                <p>
                  这里保存的是平台级凭据。具体项目绑定到哪个 GitHub 仓库、Supabase 项目或 Vercel 项目，
                  仍在对应工作空间的项目设置中完成。
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export { ServicesTab, SERVICE_LABELS };
export type { ServicesTabProps, ServiceToken };
