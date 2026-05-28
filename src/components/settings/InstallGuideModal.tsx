"use client";

import Image from "next/image";
import type { CLIOption } from "./tabs/AIAgentsTab";

interface InstallGuideModalProps {
  cli: CLIOption;
  onClose: () => void;
  onRefreshStatus: () => void;
  onCopyToast: (message: string, type: "success" | "error") => void;
}

function getCliAuthLabel(cliId: string) {
  const map: Record<string, string> = {
    gemini: "登录 Gemini（OAuth 或 API Key）",
    glm: "登录 Z.ai DevPack",
    qwen: "登录 Qwen（OAuth 或 API Key）",
    codex: "启动 Codex 并登录",
    claude: "启动 Claude 并登录",
    cursor: "启动 Cursor CLI 并登录",
  };
  return map[cliId] ?? "完成 CLI 认证";
}

function getCliBinary(cliId: string) {
  const map: Record<string, string> = {
    claude: "claude",
    cursor: "cursor-agent",
    codex: "codex",
    qwen: "qwen",
    glm: "zai",
    gemini: "gemini",
  };
  return map[cliId] ?? "";
}

function getCliLogo(cliId: string) {
  switch (cliId) {
    case "claude":
      return <Image src="/claude.png" alt="Claude" width={32} height={32} className="h-8 w-8" />;
    case "cursor":
      return <Image src="/cursor.png" alt="Cursor" width={32} height={32} className="h-8 w-8" />;
    case "codex":
      return <Image src="/oai.png" alt="Codex" width={32} height={32} className="h-8 w-8" />;
    default:
      return null;
  }
}

function InstallGuideModal({ cli, onClose, onRefreshStatus, onCopyToast }: InstallGuideModalProps) {
  const binary = getCliBinary(cli.id);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={onClose} />

      <div
        className="relative w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-slate-200 p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {getCliLogo(cli.id)}
              <div>
                <h3 className="text-lg font-semibold text-slate-900">安装 {cli.name}</h3>
                <p className="text-sm text-slate-600">完成安装和登录后，回到这里刷新状态即可使用</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </div>

        {/* Steps */}
        <div className="space-y-4 p-6">
          {/* Step 1: Install */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-full text-xs text-white"
                style={{ backgroundColor: cli.brandColor }}
              >
                1
              </span>
              安装 CLI
            </div>
            <div className="ml-8 flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
              <code className="flex-1 text-sm text-slate-800">{cli.installCommand}</code>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(cli.installCommand);
                  onCopyToast("命令已复制", "success");
                }}
                className="text-slate-500 hover:text-slate-700"
                title="复制命令"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M9 3h10a2 2 0 012 2v10M9 3H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-2M9 3v2a2 2 0 002 2h6a2 2 0 002-2V3"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>

          {/* Step 2: Authenticate */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-full text-xs text-white"
                style={{ backgroundColor: cli.brandColor }}
              >
                2
              </span>
              {getCliAuthLabel(cli.id)}
            </div>
            {binary && (
              <div className="ml-8 flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
                <code className="flex-1 text-sm text-slate-800">{binary}</code>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(binary);
                    onCopyToast("命令已复制", "success");
                  }}
                  className="text-slate-500 hover:text-slate-700"
                  title="复制命令"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M9 3h10a2 2 0 012 2v10M9 3H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-2M9 3v2a2 2 0 002 2h6a2 2 0 002-2V3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
            )}
          </div>

          {/* Step 3: Test */}
          {binary && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
                <span
                  className="flex h-6 w-6 items-center justify-center rounded-full text-xs text-white"
                  style={{ backgroundColor: cli.brandColor }}
                >
                  3
                </span>
                检查安装状态
              </div>
              <div className="ml-8 flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
                <code className="flex-1 text-sm text-slate-800">{binary} --version</code>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(`${binary} --version`);
                    onCopyToast("命令已复制", "success");
                  }}
                  className="text-slate-500 hover:text-slate-700"
                  title="复制命令"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M9 3h10a2 2 0 012 2v10M9 3H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-2M9 3v2a2 2 0 002 2h6a2 2 0 002-2V3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-between border-t border-slate-200 p-5">
          <button
            onClick={onRefreshStatus}
            className="px-4 py-2 text-sm text-slate-600 transition-colors hover:text-slate-900"
          >
            刷新状态
          </button>
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-800"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
}

export { InstallGuideModal };
export type { InstallGuideModalProps };
