"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Boxes,
  Pencil,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import GlobalSettings from "@/components/settings/GlobalSettings";
import { useGlobalSettings } from "@/contexts/GlobalSettingsContext";
import { getDefaultModelForCli, getModelDisplayName } from "@/lib/constants/cliModels";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Sidebar, ROLE_MODULES } from "@/components/layout/Sidebar";
import { TaskDrawer } from "@/components/task/TaskDrawer";
import { CreateTaskForm } from "@/components/task/CreateTaskForm";
import type { UploadedImage } from "@/components/task/CreateTaskForm";
import type { Project as ProjectSummary } from "@/types/project";
import { fetchCliStatusSnapshot, createCliStatusFallback } from "@/hooks/useCLI";
import type { CLIStatus } from "@/types/cli";
import {
  ACTIVE_CLI_BRAND_COLORS,
  ACTIVE_CLI_MODEL_OPTIONS,
  ACTIVE_CLI_OPTIONS,
  ACTIVE_CLI_OPTIONS_MAP,
  DEFAULT_ACTIVE_CLI,
  normalizeModelForCli,
  sanitizeActiveCli,
  type ActiveCliId,
} from "@/lib/utils/cliOptions";
import {
  DEFAULT_QUANT_CAPABILITY_ID,
  getQuantCapability,
  type QuantCapabilityId,
} from "@/lib/quant/capabilities";

const fetchAPI = globalThis.fetch || fetch;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const ASSISTANT_OPTIONS = ACTIVE_CLI_OPTIONS.map(({ id, name }) => ({ id, name }));
const assistantBrandColors = ACTIVE_CLI_BRAND_COLORS;
const MODEL_OPTIONS_BY_ASSISTANT = ACTIVE_CLI_MODEL_OPTIONS;

export default function HomePage() {
  // --- State ---
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [showGlobalSettings, setShowGlobalSettings] = useState(false);
  const [editingProject, setEditingProject] = useState<ProjectSummary | null>(null);
  const [deleteModal, setDeleteModal] = useState<{
    isOpen: boolean;
    project: ProjectSummary | null;
  }>({ isOpen: false, project: null });
  const [isDeleting, setIsDeleting] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);
  const [prompt, setPrompt] = useState("");

  const DEFAULT_ASSISTANT: ActiveCliId = DEFAULT_ACTIVE_CLI;
  const DEFAULT_MODEL = getDefaultModelForCli(DEFAULT_ASSISTANT);

  const sanitizeAssistant = useCallback(
    (cli?: string | null) => sanitizeActiveCli(cli, DEFAULT_ASSISTANT),
    [DEFAULT_ASSISTANT]
  );
  const normalizeModelForAssistant = useCallback(
    (assistant: string, model?: string | null) =>
      normalizeModelForCli(assistant, model, DEFAULT_ASSISTANT),
    [DEFAULT_ASSISTANT]
  );

  const normalizeProjectPayload = useCallback(
    (project: any): ProjectSummary => {
      const preferred = sanitizeAssistant(
        project?.preferredCli ?? project?.preferred_cli
      );
      const selected = normalizeModelForAssistant(
        preferred,
        project?.selectedModel ?? project?.selected_model
      );
      return {
        id: project.id,
        name: project.name,
        description: project.description ?? null,
        status: project.status,
        previewUrl: project.previewUrl ?? project.preview_url ?? null,
        createdAt:
          project.createdAt ?? project.created_at ?? new Date().toISOString(),
        updatedAt: project.updatedAt ?? project.updated_at,
        lastActiveAt: project.lastActiveAt ?? project.last_active_at ?? null,
        lastMessageAt:
          project.lastMessageAt ?? project.last_message_at ?? null,
        initialPrompt: project.initialPrompt ?? project.initial_prompt ?? null,
        services: project.services,
        preferredCli: preferred as ProjectSummary["preferredCli"],
        selectedModel: selected,
        fallbackEnabled:
          project.fallbackEnabled ?? project.fallback_enabled ?? false,
        quantCapabilityId: getQuantCapability(
          project.quantCapabilityId ?? project.quant_capability_id
        ).id,
      };
    },
    [sanitizeAssistant, normalizeModelForAssistant]
  );

  const [selectedAssistant, setSelectedAssistant] =
    useState<ActiveCliId>(DEFAULT_ASSISTANT);
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL);
  const [selectedCapability, setSelectedCapability] =
    useState<QuantCapabilityId>(DEFAULT_QUANT_CAPABILITY_ID);
  const [usingGlobalDefaults, setUsingGlobalDefaults] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false);
  const [cliStatus, setCLIStatus] = useState<CLIStatus>(() =>
    createCliStatusFallback()
  );
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isCreatingProject, setIsCreatingProject] = useState(false);

  const router = useRouter();
  const prefetchTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const { settings: globalSettings } = useGlobalSettings();

  const availableModels =
    MODEL_OPTIONS_BY_ASSISTANT[selectedAssistant] || [];
  const selectedModelLabel =
    availableModels.find((m) => m.id === selectedModel)?.name ??
    getModelDisplayName(selectedAssistant, selectedModel);
  const selectedRoleModule =
    ROLE_MODULES.find((r) => r.capabilityId === selectedCapability) ??
    ROLE_MODULES[0];
  const runningProjects = projects.filter(
    (p) => p.previewUrl || p.status === "running"
  ).length;

  // --- Session persistence ---
  useEffect(() => {
    const isPageRefresh = !sessionStorage.getItem("navigationFlag");
    if (isPageRefresh) {
      sessionStorage.setItem("navigationFlag", "true");
      setIsInitialLoad(true);
      setUsingGlobalDefaults(true);
    } else {
      const storedAssistantRaw = sessionStorage.getItem("selectedAssistant");
      const storedModelRaw = sessionStorage.getItem("selectedModel");
      if (storedModelRaw) {
        setSelectedAssistant(sanitizeAssistant(storedAssistantRaw));
        setSelectedModel(
          normalizeModelForAssistant(
            sanitizeAssistant(storedAssistantRaw),
            storedModelRaw
          )
        );
        setUsingGlobalDefaults(false);
        setIsInitialLoad(false);
        return;
      }
    }
    return () => {};
  }, [sanitizeAssistant, normalizeModelForAssistant]);

  useEffect(() => {
    if (!usingGlobalDefaults || !isInitialLoad) return;
    const cli = sanitizeAssistant(globalSettings?.default_cli);
    setSelectedAssistant(cli);
    const modelFromGlobal = globalSettings?.cli_settings?.[cli]?.model;
    setSelectedModel(normalizeModelForAssistant(cli, modelFromGlobal));
  }, [
    globalSettings,
    usingGlobalDefaults,
    isInitialLoad,
    sanitizeAssistant,
    normalizeModelForAssistant,
  ]);

  useEffect(() => {
    if (!isInitialLoad && selectedAssistant && selectedModel) {
      const normalizedAssistant = sanitizeAssistant(selectedAssistant);
      sessionStorage.setItem("selectedAssistant", normalizedAssistant);
      sessionStorage.setItem(
        "selectedModel",
        normalizeModelForAssistant(normalizedAssistant, selectedModel)
      );
    }
  }, [
    selectedAssistant,
    selectedModel,
    isInitialLoad,
    sanitizeAssistant,
    normalizeModelForAssistant,
  ]);

  useEffect(() => {
    const handleBeforeUnload = () =>
      sessionStorage.removeItem("navigationFlag");
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  // --- CLI status ---
  useEffect(() => {
    const checkingStatus = ASSISTANT_OPTIONS.reduce<CLIStatus>(
      (acc, cli) => {
        acc[cli.id] = { installed: true, available: true, configured: true, checking: true };
        return acc;
      },
      createCliStatusFallback()
    );
    setCLIStatus(checkingStatus);
    fetchCliStatusSnapshot()
      .then(setCLIStatus)
      .catch((err) => {
        console.error("Failed to check CLI status:", err);
        setCLIStatus(createCliStatusFallback());
      });
  }, []);

  // --- Data loading ---
  const load = useCallback(async () => {
    try {
      const r = await fetchAPI(`${API_BASE}/api/projects`);
      if (!r.ok) {
        setProjects([]);
        return;
      }
      const payload = await r.json();
      if (payload?.success === false) {
        setProjects([]);
        return;
      }
      const items: unknown[] = Array.isArray(payload?.data)
        ? payload.data
        : Array.isArray(payload)
          ? payload
          : [];
      const normalized: ProjectSummary[] = items
        .filter((p): p is Record<string, unknown> => Boolean(p && typeof p === "object"))
        .map(normalizeProjectPayload);
      const sorted = normalized.sort((a, b) => {
        const aTime = a.lastMessageAt ?? a.createdAt;
        const bTime = b.lastMessageAt ?? b.createdAt;
        if (!aTime) return 1;
        if (!bTime) return -1;
        return new Date(bTime).getTime() - new Date(aTime).getTime();
      });
      setProjects(sorted);
    } catch {
      setProjects([]);
    }
  }, [normalizeProjectPayload]);

  useEffect(() => {
    load();
    const timers = prefetchTimers.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, [load]);

  // --- Format helpers ---
  const formatTime = (dateString: string | null) => {
    if (!dateString) return "暂无记录";
    let utc = dateString;
    if (!dateString.endsWith("Z") && !dateString.includes("+") && !dateString.match(/[-+]\d{2}:\d{2}$/)) {
      utc = dateString + "Z";
    }
    const date = new Date(utc);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    if (diffMins < 1) return "刚刚";
    if (diffMins < 60) return `${diffMins} 分钟前`;
    if (diffHours < 24) return `${diffHours} 小时前`;
    if (diffDays < 30) return `${diffDays} 天前`;
    return date.toLocaleDateString("zh-CN", {
      month: "short",
      day: "numeric",
      year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  };

  const formatCliInfo = (cli?: string, model?: string) => {
    const normalizedCli = sanitizeAssistant(cli);
    const opt = ACTIVE_CLI_OPTIONS_MAP[normalizedCli];
    const name = opt?.name ?? "Claude Code";
    const modelId = normalizeModelForAssistant(normalizedCli, model);
    const label = getModelDisplayName(normalizedCli, modelId);
    return `${name} · ${label}`;
  };

  const getCapabilityShortName = (capabilityId?: string | null) =>
    getQuantCapability(capabilityId).shortName;

  // --- Actions ---
  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      setToast({ message, type });
      setTimeout(() => setToast(null), 4000);
    },
    []
  );

  const openDeleteModal = (project: ProjectSummary) =>
    setDeleteModal({ isOpen: true, project });
  const closeDeleteModal = () =>
    setDeleteModal({ isOpen: false, project: null });

  const deleteProject = async () => {
    if (!deleteModal.project) return;
    setIsDeleting(true);
    try {
      const r = await fetchAPI(
        `${API_BASE}/api/projects/${deleteModal.project.id}`,
        { method: "DELETE" }
      );
      if (r.ok) {
        showToast("任务已删除", "success");
        await load();
        closeDeleteModal();
      } else {
        const err = await r.json().catch(() => ({ detail: "删除任务失败" }));
        showToast(err.detail || "删除任务失败", "error");
      }
    } catch {
      showToast("删除任务失败，请重试", "error");
    } finally {
      setIsDeleting(false);
    }
  };

  const updateProject = async (projectId: string, newName: string) => {
    try {
      const r = await fetchAPI(`${API_BASE}/api/projects/${projectId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName }),
      });
      if (r.ok) {
        showToast("任务名称已更新", "success");
        await load();
        setEditingProject(null);
      } else {
        const err = await r.json().catch(() => ({ detail: "更新任务失败" }));
        showToast(err.detail || "更新任务失败", "error");
      }
    } catch {
      showToast("更新任务失败，请重试", "error");
    }
  };

  const openProject = (project: ProjectSummary) => {
    const params = new URLSearchParams();
    if (selectedAssistant) params.set("cli", selectedAssistant);
    if (selectedModel) params.set("model", selectedModel);
    router.push(
      `/${project.id}/chat${params.toString() ? "?" + params.toString() : ""}`
    );
  };

  const handleSubmit = async () => {
    if ((!prompt.trim() && uploadedImages.length === 0) || isCreatingProject)
      return;
    setIsCreatingProject(true);
    const projectId = `project-${Date.now()}-${Math.random()
      .toString(36)
      .substr(2, 9)}`;

    try {
      const r = await fetchAPI(`${API_BASE}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          name: prompt.slice(0, 50) + (prompt.length > 50 ? "..." : ""),
          initialPrompt: prompt.trim(),
          preferredCli: selectedAssistant,
          selectedModel,
          quantCapabilityId: selectedCapability,
        }),
      });
      if (!r.ok) {
        showToast("Failed to create project", "error");
        setIsCreatingProject(false);
        return;
      }
      const payload = await r.json();
      const projectData =
        payload && typeof payload === "object" ? payload.data ?? payload : payload;
      const createdProjectId: string | undefined = projectData?.id ?? projectId;

      // Upload images
      let imageData: any[] = [];
      if (uploadedImages.length > 0) {
        for (const image of uploadedImages) {
          if (!image.file) continue;
          const fd = new FormData();
          fd.append("file", image.file);
          const uploadR = await fetchAPI(
            `${API_BASE}/api/assets/${createdProjectId}/upload`,
            { method: "POST", body: fd }
          );
          if (uploadR.ok) {
            const result = await uploadR.json();
            imageData.push({
              name: result.filename || image.name,
              path: result.absolute_path,
              public_url:
                typeof result.public_url === "string"
                  ? result.public_url
                  : undefined,
            });
          }
        }
      }

      // Fire initial prompt
      if (prompt.trim()) {
        await fetchAPI(`${API_BASE}/api/chat/${createdProjectId}/act`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            instruction: prompt.trim(),
            images: imageData,
            isInitialPrompt: true,
            cliPreference: selectedAssistant,
            selectedModel,
            quantCapabilityId: selectedCapability,
          }),
        }).catch(() => null);
      }

      // Cleanup and navigate
      uploadedImages.forEach((img) => {
        if (img.url) URL.revokeObjectURL(img.url);
      });
      setUploadedImages([]);
      setPrompt("");
      const params = new URLSearchParams();
      if (selectedAssistant) params.set("cli", selectedAssistant);
      if (selectedModel) params.set("model", selectedModel);
      router.push(
        `/${createdProjectId}/chat${params.toString() ? "?" + params.toString() : ""}`
      );
    } catch {
      showToast("Failed to create project", "error");
    } finally {
      setIsCreatingProject(false);
    }
  };

  // --- Assistant/model handlers ---
  const isAssistantSelectable = useCallback(
    (assistant: string) => {
      const status = cliStatus[assistant];
      if (!status || status.checking) return true;
      return Boolean(status.installed || status.available || status.configured);
    },
    [cliStatus]
  );

  const handleAssistantChange = (assistant: string) => {
    if (!isAssistantSelectable(assistant)) return;
    const sanitized = sanitizeAssistant(assistant);
    setUsingGlobalDefaults(false);
    setIsInitialLoad(false);
    setSelectedAssistant(sanitized);
    setSelectedModel(getDefaultModelForCli(sanitized));
  };

  const handleModelChange = (modelId: string) => {
    setUsingGlobalDefaults(false);
    setIsInitialLoad(false);
    setSelectedModel(normalizeModelForAssistant(selectedAssistant, modelId));
  };

  // --- Render ---
  return (
    <div className="relative flex h-screen overflow-hidden bg-background text-foreground">
      <div className="relative z-10 flex h-full w-full">
        {/* Desktop sidebar */}
        <div className="hidden lg:block">
          <Sidebar
            selectedCapability={selectedCapability}
            onSelectCapability={setSelectedCapability}
            onOpenTaskDrawer={() => setTaskDrawerOpen(true)}
            onShowSettings={() => setShowGlobalSettings(true)}
          />
        </div>

        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/20 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <div className="h-full" onClick={(e) => e.stopPropagation()}>
              <Sidebar
                selectedCapability={selectedCapability}
                onSelectCapability={setSelectedCapability}
                onOpenTaskDrawer={() => setTaskDrawerOpen(true)}
                onShowSettings={() => setShowGlobalSettings(true)}
                isMobile
                onCloseMobile={() => setSidebarOpen(false)}
              />
            </div>
          </div>
        )}

        {/* Main content */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Top bar */}
          <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background/85 px-4 backdrop-blur md:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <Button
                type="button"
                onClick={() => setSidebarOpen(true)}
                size="icon"
                variant="ghost"
                className="lg:hidden"
                aria-label="打开任务记录"
              >
                <Pencil className="h-5 w-5" />
              </Button>
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary text-base font-bold text-primary-foreground shadow-sm">
                Q
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-base font-bold md:text-lg">
                  QuantPilot
                </h1>
                <div className="mt-0.5 hidden items-center gap-2 text-xs text-muted-foreground md:flex">
                  <span>任务 {projects.length}</span>
                  <span>·</span>
                  <span>运行中 {runningProjects}</span>
                  <span>·</span>
                  <span>{selectedModelLabel}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                onClick={() => router.push("/strategies")}
                variant="ghost"
                className="inline-flex gap-1.5 px-2 text-xs font-medium sm:gap-2 sm:px-3 sm:text-sm"
              >
                <BarChart3 className="h-4 w-4" />
                策略平台
              </Button>
              <Button
                type="button"
                onClick={() => router.push("/workspaces")}
                variant="ghost"
                className="inline-flex gap-1.5 px-2 text-xs font-medium sm:gap-2 sm:px-3 sm:text-sm"
              >
                <ShieldCheck className="h-4 w-4" />
                运维平台
              </Button>
              <Button
                type="button"
                onClick={() => router.push("/capabilities")}
                variant="ghost"
                className="inline-flex gap-1.5 px-2 text-xs font-medium sm:gap-2 sm:px-3 sm:text-sm"
              >
                <Boxes className="h-4 w-4" />
                数据平台
              </Button>
            </div>
          </header>

          {/* Main area */}
          <main className="relative flex-1 overflow-y-auto">
            <div className="relative mx-auto flex min-h-full w-full max-w-6xl -translate-y-6 flex-col items-center justify-center px-4 py-8 md:-translate-y-12 md:px-8 lg:-translate-y-14">
              {/* Title */}
              <div className="mb-6 text-center">
                <h2 className="text-3xl font-bold tracking-normal text-primary md:text-5xl">
                  QuantPilot
                </h2>
                <p className="mt-3 text-sm text-muted-foreground md:text-base">
                  选择角色模块，描述真实需求，等待任务完成并生成可验证的量化看板
                </p>
              </div>

              {/* Create form */}
              <CreateTaskForm
                prompt={prompt}
                onPromptChange={setPrompt}
                isCreating={isCreatingProject}
                onSubmit={handleSubmit}
                uploadedImages={uploadedImages}
                onImagesChange={setUploadedImages}
                selectedAssistant={selectedAssistant}
                onAssistantChange={handleAssistantChange}
                assistantOptions={ASSISTANT_OPTIONS}
                isAssistantSelectable={isAssistantSelectable}
                selectedModel={selectedModel}
                onModelChange={handleModelChange}
                modelOptions={availableModels}
                selectedRole={selectedRoleModule}
              />
            </div>
          </main>
        </div>

        {/* Task drawer */}
        <TaskDrawer
          open={taskDrawerOpen}
          onOpenChange={setTaskDrawerOpen}
          projects={projects}
          editingProject={editingProject}
          onEditProject={setEditingProject}
          onUpdateProject={updateProject}
          onOpenProject={openProject}
          onDeleteProject={openDeleteModal}
          formatTime={formatTime}
          formatCliInfo={formatCliInfo}
          getCapabilityShortName={getCapabilityShortName}
        />

        {/* Global settings */}
        <GlobalSettings
          isOpen={showGlobalSettings}
          onClose={() => setShowGlobalSettings(false)}
        />

        {/* Delete confirmation */}
        <AlertDialog
          open={deleteModal.isOpen && Boolean(deleteModal.project)}
          onOpenChange={(open) => {
            if (!open) closeDeleteModal();
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>删除任务</AlertDialogTitle>
              <AlertDialogDescription>
                确定要删除 <strong>{deleteModal.project?.name}</strong>{" "}
                吗？该任务的项目文件与对话记录将被永久删除。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isDeleting}>取消</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  deleteProject();
                }}
                disabled={isDeleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isDeleting ? "删除中..." : "删除任务"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Toast */}
        {toast && (
          <div className="fixed bottom-4 right-4 z-50">
            <motion.div
              initial={{ opacity: 0, y: 50, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 50, scale: 0.9 }}
            >
              <div
                className={`flex max-w-sm items-center gap-3 rounded-lg border px-6 py-4 shadow-lg backdrop-blur-lg ${
                  toast.type === "success"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-destructive/20 bg-destructive/10 text-destructive"
                }`}
              >
                {toast.type === "success" ? (
                  <svg
                    className="h-5 w-5 shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                ) : (
                  <svg
                    className="h-5 w-5 shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
                <p className="text-sm font-medium">{toast.message}</p>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  );
}
