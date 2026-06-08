"use client";
import { useState, useEffect, useCallback } from "react";
import { AnimatePresence } from "framer-motion";
import { MotionDiv } from "@/lib/motion";
import { FaCog } from "react-icons/fa";
import ServiceConnectionModal from "@/components/modals/ServiceConnectionModal";
import { useGlobalSettings } from "@/contexts/GlobalSettingsContext";
import { getModelDefinitionsForCli, normalizeModelId } from "@/lib/constants/cliModels";
import { fetchCliStatusSnapshot, createCliStatusFallback } from "@/hooks/useCLI";
import type { CLIStatus } from "@/types/cli";

import { GeneralTab } from "./tabs/GeneralTab";
import { AIAgentsTab, type CLIOption } from "./tabs/AIAgentsTab";
import { ServicesTab, type ServiceToken } from "./tabs/ServicesTab";
import { InfrastructureTab, type InfrastructureHealth } from "./tabs/InfrastructureTab";
import { AboutTab } from "./tabs/AboutTab";
import { InstallGuideModal } from "./InstallGuideModal";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

type SettingsTab = "general" | "ai-agents" | "services" | "infrastructure" | "about";

interface GlobalSettingsProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: SettingsTab;
}

const CLI_OPTIONS: CLIOption[] = [
  {
    id: "claude",
    name: "Claude Code",
    icon: "",
    description: "Claude Code runtime with Anthropic-compatible model providers",
    color: "from-orange-500 to-red-600",
    brandColor: "#DE7356",
    downloadUrl: "https://docs.anthropic.com/en/docs/claude-code/overview",
    installCommand: "npm install -g @anthropic-ai/claude-code",
    enabled: true,
    models: getModelDefinitionsForCli("claude").map(({ id, name, description, provider, external }) => ({
      id, name, description, provider, external,
    })),
  },
];

function getProviderIcon(provider: string) {
  if (provider === "github") {
    return (
      <svg width="20" height="20" viewBox="0 0 98 96" fill="none">
        <path
          fillRule="evenodd"
          clipRule="evenodd"
          d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (provider === "supabase") {
    return (
      <svg width="20" height="20" viewBox="0 0 109 113" fill="none">
        <path
          d="M63.7076 110.284C60.8481 113.885 55.0502 111.912 54.9813 107.314L53.9738 40.0627L99.1935 40.0627C107.384 40.0627 111.952 49.5228 106.859 55.9374L63.7076 110.284Z"
          fill="url(#paint0_linear)"
        />
        <path
          d="M45.317 2.07103C48.1765 -1.53037 53.9745 0.442937 54.0434 5.041L54.4849 72.2922H9.83113C1.64038 72.2922 -2.92775 62.8321 2.1655 56.4175L45.317 2.07103Z"
          fill="#3ECF8E"
        />
        <defs>
          <linearGradient
            id="paint0_linear"
            x1="53.9738"
            y1="54.974"
            x2="94.1635"
            y2="71.8295"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#249361" />
            <stop offset="1" stopColor="#3ECF8E" />
          </linearGradient>
        </defs>
      </svg>
    );
  }
  if (provider === "vercel") {
    return (
      <svg width="20" height="20" viewBox="0 0 76 65" fill="none">
        <path d="M37.5274 0L75.0548 65H0L37.5274 0Z" fill="currentColor" />
      </svg>
    );
  }
  return null;
}

export default function GlobalSettings({ isOpen, onClose, initialTab = "general" }: GlobalSettingsProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);
  const [serviceModalOpen, setServiceModalOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<"github" | "supabase" | "vercel" | null>(null);
  const [tokens, setTokens] = useState<{ [key: string]: ServiceToken | null }>({
    github: null,
    supabase: null,
    vercel: null,
  });
  const [cliStatus, setCLIStatus] = useState<CLIStatus>({});
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const { settings: globalSettings, setSettings: setGlobalSettings, refresh: refreshGlobalSettings } = useGlobalSettings();
  const [isLoading, setIsLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [selectedCLI, setSelectedCLI] = useState<CLIOption | null>(null);
  const [apiKeyVisibility, setApiKeyVisibility] = useState<Record<string, boolean>>({});
  const [infrastructure, setInfrastructure] = useState<InfrastructureHealth | null>(null);
  const [infrastructureError, setInfrastructureError] = useState<string | null>(null);
  const [infrastructureLoading, setInfrastructureLoading] = useState(false);

  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadAllTokens = useCallback(async () => {
    const providers = ["github", "supabase", "vercel"];
    const newTokens: { [key: string]: ServiceToken | null } = {};
    for (const provider of providers) {
      try {
        const response = await fetch(`${API_BASE}/api/tokens/${provider}`);
        newTokens[provider] = response.ok ? await response.json() : null;
      } catch {
        newTokens[provider] = null;
      }
    }
    setTokens(newTokens);
  }, []);

  const handleServiceClick = (provider: "github" | "supabase" | "vercel") => {
    setSelectedProvider(provider);
    setServiceModalOpen(true);
  };

  const handleServiceModalClose = () => {
    setServiceModalOpen(false);
    setSelectedProvider(null);
    loadAllTokens();
  };

  const loadGlobalSettings = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/settings/global`);
      if (response.ok) {
        const settings = await response.json();
        if (settings?.cli_settings) {
          for (const [cli, config] of Object.entries(settings.cli_settings)) {
            if (config && typeof config === "object" && "model" in config) {
              (config as any).model = normalizeModelId(cli, (config as any).model as string);
            }
          }
        }
        setGlobalSettings(settings);
      }
    } catch (error) {
      console.error("Failed to load global settings:", error);
    }
  }, [setGlobalSettings]);

  const checkCLIStatus = useCallback(async () => {
    const checkingStatus: CLIStatus = CLI_OPTIONS.reduce((acc, cli) => {
      acc[cli.id] = { installed: true, checking: true };
      return acc;
    }, {} as CLIStatus);
    setCLIStatus(checkingStatus);
    try {
      const status = await fetchCliStatusSnapshot();
      setCLIStatus(status);
    } catch {
      setCLIStatus(createCliStatusFallback());
    }
  }, []);

  const loadInfrastructureHealth = useCallback(async () => {
    setInfrastructureLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/infrastructure/health`);
      const payload = await response.json();
      setInfrastructure(payload.data ?? null);
      setInfrastructureError(response.ok ? null : payload.error ?? "基础组件检查失败");
    } catch (error) {
      setInfrastructure(null);
      setInfrastructureError(error instanceof Error ? error.message : "基础组件检查失败");
    } finally {
      setInfrastructureLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadAllTokens();
      loadGlobalSettings();
      checkCLIStatus();
      loadInfrastructureHealth();
    }
  }, [isOpen, loadAllTokens, loadGlobalSettings, checkCLIStatus, loadInfrastructureHealth]);

  const saveGlobalSettings = async () => {
    setIsLoading(true);
    setSaveMessage(null);
    try {
      const payload = JSON.parse(JSON.stringify(globalSettings));
      if (payload?.cli_settings) {
        for (const [cli, config] of Object.entries(payload.cli_settings)) {
          if (config && typeof config === "object" && "model" in config) {
            (config as any).model = normalizeModelId(cli, (config as any).model as string);
          }
        }
      }
      const response = await fetch(`${API_BASE}/api/settings/global`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Failed to save settings");
      setSaveMessage({ type: "success", text: "设置已保存" });
      try { await refreshGlobalSettings(); } catch {}
      setTimeout(() => setSaveMessage(null), 3000);
    } catch {
      setSaveMessage({ type: "error", text: "设置保存失败，请稍后重试" });
      setTimeout(() => setSaveMessage(null), 5000);
    } finally {
      setIsLoading(false);
    }
  };

  const setDefaultCLI = (cliId: string) => {
    if (!cliStatus[cliId]?.installed) return;
    setGlobalSettings((prev) => ({ ...prev, default_cli: cliId }));
  };

  const setDefaultModel = (cliId: string, modelId: string) => {
    setGlobalSettings((prev) => ({
      ...prev,
      cli_settings: {
        ...(prev?.cli_settings ?? {}),
        [cliId]: { ...(prev?.cli_settings?.[cliId] ?? {}), model: normalizeModelId(cliId, modelId) },
      },
    }));
  };

  const setCliApiKey = (cliId: string, apiKey: string) => {
    setGlobalSettings((prev) => {
      const nextCliSettings = { ...(prev?.cli_settings ?? {}) };
      const existing = { ...(nextCliSettings[cliId] ?? {}) };
      const trimmed = apiKey.trim();
      if (trimmed.length > 0) {
        existing.apiKey = trimmed;
        nextCliSettings[cliId] = existing;
      } else {
        delete existing.apiKey;
        if (Object.keys(existing).length > 0) nextCliSettings[cliId] = existing;
        else delete nextCliSettings[cliId];
      }
      return { ...prev, cli_settings: nextCliSettings };
    });
  };

  const toggleApiKeyVisibility = (cliId: string) => {
    setApiKeyVisibility((prev) => ({ ...prev, [cliId]: !prev[cliId] }));
  };

  // Derived data
  const defaultCli = CLI_OPTIONS.find((c) => c.id === globalSettings.default_cli);
  const defaultCliSettings = defaultCli ? globalSettings.cli_settings?.[defaultCli.id] || {} : {};
  const defaultModel = defaultCli?.models.find((m) => m.id === defaultCliSettings.model);
  const installedAgentCount = CLI_OPTIONS.filter((c) => c.enabled !== false && cliStatus[c.id]?.installed).length;
  const configuredServiceCount = Object.values(tokens).filter(Boolean).length;

  if (!isOpen) return null;

  const tabConfigs = [
    { id: "general" as const, label: "生成与模型" },
    { id: "ai-agents" as const, label: "智能体" },
    { id: "services" as const, label: "服务令牌" },
    { id: "infrastructure" as const, label: "基础组件" },
    { id: "about" as const, label: "关于" },
  ];

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={onClose} />

        <MotionDiv
          className="relative flex h-[700px] w-full max-w-5xl flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl"
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.2 }}
        >
          {/* Header */}
          <div className="border-b border-slate-200 p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-slate-600">
                  <FaCog size={20} />
                </span>
                <div>
                  <h2 className="text-xl font-semibold text-slate-900">平台设置</h2>
                  <p className="text-sm text-slate-600">管理生成工作空间使用的智能体、模型与服务令牌</p>
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

          {/* Tab navigation */}
          <div className="border-b border-slate-200">
            <nav className="flex px-5">
              {tabConfigs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-all ${
                    activeTab === tab.id
                      ? "border-[#DE7356] text-slate-900"
                      : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-700"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-300 scrollbar-track-transparent">
            {activeTab === "general" && (
              <GeneralTab
                defaultCliName={defaultCli?.name ?? "未配置"}
                isDefaultCliInstalled={Boolean(cliStatus[globalSettings.default_cli]?.installed)}
                defaultModelName={defaultModel?.name ?? "未选择模型"}
                configuredServiceCount={configuredServiceCount}
                installedAgentCount={installedAgentCount}
                totalAgentCount={CLI_OPTIONS.filter((c) => c.enabled !== false).length}
                onNavigateToAgents={() => setActiveTab("ai-agents")}
                onNavigateToServices={() => setActiveTab("services")}
              />
            )}

            {activeTab === "ai-agents" && (
              <AIAgentsTab
                cliOptions={CLI_OPTIONS}
                cliStatus={cliStatus}
                globalSettings={globalSettings}
                saveMessage={saveMessage}
                isLoading={isLoading}
                apiKeyVisibility={apiKeyVisibility}
                onSetDefaultCli={setDefaultCLI}
                onSetDefaultModel={setDefaultModel}
                onSetCliApiKey={setCliApiKey}
                onToggleApiKeyVisibility={toggleApiKeyVisibility}
                onRefreshCliStatus={checkCLIStatus}
                onSaveSettings={saveGlobalSettings}
                onOpenInstallModal={(cli) => {
                  setSelectedCLI(cli);
                  setInstallModalOpen(true);
                }}
              />
            )}

            {activeTab === "services" && (
              <ServicesTab
                tokens={tokens}
                getProviderIcon={getProviderIcon}
                onServiceClick={handleServiceClick}
              />
            )}

            {activeTab === "infrastructure" && (
              <InfrastructureTab
                infrastructure={infrastructure}
                infrastructureError={infrastructureError}
                infrastructureLoading={infrastructureLoading}
                onRefresh={loadInfrastructureHealth}
                onCopyCommand={(cmd) => {
                  navigator.clipboard.writeText(cmd);
                  showToast("命令已复制", "success");
                }}
              />
            )}

            {activeTab === "about" && <AboutTab />}
          </div>
        </MotionDiv>

        {/* Service Connection Modal */}
        {selectedProvider && (
          <ServiceConnectionModal
            key={`service-token-${selectedProvider}`}
            isOpen={serviceModalOpen}
            onClose={handleServiceModalClose}
            provider={selectedProvider}
          />
        )}

        {/* Install Guide Modal */}
        {installModalOpen && selectedCLI && (
          <InstallGuideModal
            cli={selectedCLI}
            onClose={() => {
              setInstallModalOpen(false);
              setSelectedCLI(null);
            }}
            onRefreshStatus={checkCLIStatus}
            onCopyToast={showToast}
          />
        )}

        {/* Toast */}
        {toast && (
          <div
            className={`fixed bottom-4 right-4 z-[80] animate-slide-in-up rounded-lg px-4 py-3 shadow-2xl transition-all ${
              toast.type === "success" ? "bg-green-500 text-white" : "bg-red-500 text-white"
            }`}
          >
            <div className="flex items-center gap-2">
              {toast.type === "success" ? (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : null}
              <span className="font-medium">{toast.message}</span>
            </div>
          </div>
        )}
      </div>
    </AnimatePresence>
  );
}
