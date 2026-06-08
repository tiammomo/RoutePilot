"use client";

import Image from "next/image";
import type { CLIStatus } from "@/types/cli";

interface CLIOption {
  id: string;
  name: string;
  icon: string;
  description: string;
  models: { id: string; name: string; description?: string; provider?: string; runtime?: string; external?: boolean }[];
  color: string;
  brandColor: string;
  downloadUrl: string;
  installCommand: string;
  enabled?: boolean;
}

interface AIAgentsTabProps {
  cliOptions: CLIOption[];
  cliStatus: CLIStatus;
  globalSettings: any;
  saveMessage: { type: "success" | "error"; text: string } | null;
  isLoading: boolean;
  apiKeyVisibility: Record<string, boolean>;
  onSetDefaultCli: (cliId: string) => void;
  onSetDefaultModel: (cliId: string, modelId: string) => void;
  onSetCliApiKey: (cliId: string, apiKey: string) => void;
  onToggleApiKeyVisibility: (cliId: string) => void;
  onRefreshCliStatus: () => void;
  onSaveSettings: () => void;
  onOpenInstallModal: (cli: CLIOption) => void;
}

function AIAgentsTab({
  cliOptions,
  cliStatus,
  globalSettings,
  saveMessage,
  isLoading,
  apiKeyVisibility,
  onSetDefaultCli,
  onSetDefaultModel,
  onSetCliApiKey,
  onToggleApiKeyVisibility,
  onRefreshCliStatus,
  onSaveSettings,
  onOpenInstallModal,
}: AIAgentsTabProps) {
  const enabledOptions = cliOptions.filter((cli) => cli.enabled !== false);
  const fixedRuntime = enabledOptions[0];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <h3 className="mb-1 text-lg font-medium text-slate-900">固定运行时</h3>
            <p className="text-sm text-slate-600">
              北京旅行 Agent 默认使用 Claude Code runtime 与 MiniMax M2.7，不在界面暴露切换入口
            </p>
          </div>
          <div className="ml-6 flex items-center gap-2 border-l border-slate-200 pl-6">
            <span className="text-sm text-slate-600">默认</span>
            <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700">
              {fixedRuntime?.name ?? "Claude Code"} / MiniMax M2.7
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {saveMessage && (
            <div
              className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm ${
                saveMessage.type === "success"
                  ? "bg-green-100 text-green-700"
                  : "bg-red-100 text-red-700"
              }`}
            >
              {saveMessage.type === "success" ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              )}
              {saveMessage.text}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={onRefreshCliStatus}
              className="rounded-full border border-slate-200/50 bg-transparent px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-slate-300/50 hover:bg-slate-50"
            >
              刷新状态
            </button>
            <button
              onClick={onSaveSettings}
              disabled={isLoading}
              className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              {isLoading ? "保存中..." : "保存设置"}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {enabledOptions.map((cli) => {
          const status = cliStatus[cli.id];
          const settings = globalSettings.cli_settings?.[cli.id] || {};
          const isInstalled = status?.installed || false;
          const isDefault = globalSettings.default_cli === cli.id;

          return (
            <div
              key={cli.id}
              className={`rounded-xl border py-4 pl-4 pr-8 transition-all ${
                !isInstalled
                  ? "cursor-not-allowed border-slate-200/50 bg-slate-50/50"
                  : isDefault
                    ? ""
                    : "border-slate-200/50"
              }`}
              style={
                isDefault && isInstalled
                  ? {
                      borderColor: cli.brandColor,
                      backgroundColor: `${cli.brandColor}08`,
                    }
                  : {}
              }
            >
              <div className="mb-3 flex items-start gap-3">
                <div className={`flex-shrink-0 ${!isInstalled ? "opacity-40" : ""}`}>
                  {cli.id === "claude" && (
                    <Image src="/claude.png" alt="Claude" width={32} height={32} className="h-8 w-8" />
                  )}
                  {cli.id === "cursor" && (
                    <Image src="/cursor.png" alt="Cursor" width={32} height={32} className="h-8 w-8" />
                  )}
                  {cli.id === "codex" && (
                    <Image src="/oai.png" alt="Codex" width={32} height={32} className="h-8 w-8" />
                  )}
                  {cli.id === "qwen" && (
                    <Image src="/qwen.png" alt="Qwen" width={32} height={32} className="h-8 w-8" />
                  )}
                  {cli.id === "glm" && (
                    <Image src="/glm.svg" alt="GLM" width={32} height={32} className="h-8 w-8" />
                  )}
                </div>
                <div className={`min-w-0 flex-1 ${!isInstalled ? "opacity-40" : ""}`}>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-medium text-slate-900">{cli.name}</h4>
                    {isDefault && isInstalled && (
                      <span className="text-xs font-medium" style={{ color: cli.brandColor }}>
                        默认
                      </span>
                    )}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-600">{cli.description}</p>
                </div>
              </div>

              {isInstalled ? (
                <div onClick={(e) => e.stopPropagation()} className="space-y-3">
                  <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800">
                    {cli.models[0]?.name ?? "MiniMax M2.7"}
                  </div>

                  {settings.model && cli.models.find((m) => m.id === settings.model)?.description && (
                    <p className="text-[11px] leading-snug text-slate-500">
                      {cli.models.find((m) => m.id === settings.model)?.description}
                    </p>
                  )}

                  {(cli.id === "glm" || cli.id === "cursor") && (
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-600">
                        API Key{cli.id === "cursor" ? "（可选）" : ""}
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type={apiKeyVisibility[cli.id] ? "text" : "password"}
                          value={settings.apiKey ?? ""}
                          onChange={(e) => onSetCliApiKey(cli.id, e.target.value)}
                          placeholder={`输入 ${cli.name} API Key`}
                          className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-200"
                        />
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            onToggleApiKeyVisibility(cli.id);
                          }}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:text-slate-900"
                        >
                          {apiKeyVisibility[cli.id] ? "隐藏" : "显示"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => onOpenInstallModal(cli)}
                    className="w-full rounded-full border-2 border-slate-900 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition-all hover:scale-105 hover:bg-slate-800"
                  >
                    查看安装指引
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { AIAgentsTab };
export type { AIAgentsTabProps, CLIOption };
