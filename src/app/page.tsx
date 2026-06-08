"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  ArrowUp,
  Bot,
  CheckCircle2,
  Edit3,
  XCircle,
} from "lucide-react";
import { useGlobalSettings } from "@/contexts/GlobalSettingsContext";
import { getDefaultModelForCli } from "@/lib/constants/cliModels";
import { Button } from "@/components/ui/button";
import { ROLE_MODULES } from "@/components/layout/Sidebar";
import type { UploadedImage } from "@/components/task/CreateTaskForm";
import { fetchCliStatusSnapshot, createCliStatusFallback } from "@/hooks/useCLI";
import type { CLIStatus } from "@/types/cli";
import {
  ACTIVE_CLI_MODEL_OPTIONS,
  ACTIVE_CLI_OPTIONS,
  DEFAULT_ACTIVE_CLI,
  normalizeModelForCli,
  sanitizeActiveCli,
  type ActiveCliId,
} from "@/lib/utils/cliOptions";
import {
  DEFAULT_TRAVEL_CAPABILITY_ID,
  type TravelCapabilityId,
} from "@/lib/travel/capabilities";

const fetchAPI = globalThis.fetch || fetch;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const ASSISTANT_OPTIONS = ACTIVE_CLI_OPTIONS.map(({ id, name }) => ({ id, name }));
export default function HomePage() {
  // --- State ---
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

  const [selectedAssistant, setSelectedAssistant] =
    useState<ActiveCliId>(DEFAULT_ASSISTANT);
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL);
  const [selectedCapability, setSelectedCapability] =
    useState<TravelCapabilityId>(DEFAULT_TRAVEL_CAPABILITY_ID);
  const [usingGlobalDefaults, setUsingGlobalDefaults] = useState(true);
  const [cliStatus, setCLIStatus] = useState<CLIStatus>(() =>
    createCliStatusFallback()
  );
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [homeInputMode, setHomeInputMode] = useState<"chat" | "form">("chat");
  const [tripForm, setTripForm] = useState({
    area: "前门",
    duration: "4小时",
    budget: "200",
    persona: "朋友/情侣",
    meal: "中午吃饭",
    preferences: ["少走路", "不想排队"],
  });

  const router = useRouter();
  const prefetchTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const { settings: globalSettings } = useGlobalSettings();

  const selectedRoleModule =
    ROLE_MODULES.find((r) => r.capabilityId === selectedCapability) ??
    ROLE_MODULES[0];
  const scenicImages = [
    "/travel-images/qianmen.jpg",
    "/travel-images/forbidden-city.jpg",
    "/travel-images/temple-of-heaven.jpg",
    "/travel-images/temple-of-heaven.jpg",
  ];
  const formFieldClass =
    "h-12 w-full rounded-[1.35rem] border border-white/60 bg-white/40 px-4 text-sm font-semibold text-neutral-800 outline-none transition focus:border-white focus:bg-white/65 focus:ring-2 focus:ring-white/70";
  const areaOptions = [
    "前门",
    "故宫",
    "天安门",
    "王府井",
    "什刹海",
    "北海",
    "南锣鼓巷",
    "雍和宫",
    "颐和园",
    "奥林匹克公园",
    "三里屯",
    "798",
  ];
  const preferenceOptions = ["少走路", "不想排队", "经典文化", "亲子友好", "室内优先"];
  const quickSamples = [
    "前门附近4小时，中午吃饭，预算200以内",
    "故宫附近文化路线，少走路，不吃饭",
    "带老人去北海附近，中午安排吃饭",
  ];

  const toggleTripPreference = (preference: string) => {
    setTripForm((current) => ({
      ...current,
      preferences: current.preferences.includes(preference)
        ? current.preferences.filter((item) => item !== preference)
        : [...current.preferences, preference],
    }));
  };

  const buildTripFormPrompt = () => {
    const preferenceText =
      tripForm.preferences.length > 0
        ? `，偏好${tripForm.preferences.join("、")}`
        : "";
    return `${tripForm.area || "北京"}附近游玩${tripForm.duration || "4小时"}，${tripForm.meal}，预算${tripForm.budget || "200"}以内，同行人群${tripForm.persona}，采用${selectedRoleModule.name}能力${preferenceText}`;
  };

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

  useEffect(() => {
    const timers = prefetchTimers.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  // --- Actions ---
  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      setToast({ message, type });
      setTimeout(() => setToast(null), 4000);
    },
    []
  );

  const handleSubmit = async (promptOverride?: string) => {
    const promptToSubmit = (promptOverride ?? prompt).trim();
    if ((!promptToSubmit && uploadedImages.length === 0) || isCreatingProject)
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
          name: promptToSubmit.slice(0, 50) + (promptToSubmit.length > 50 ? "..." : ""),
          initialPrompt: promptToSubmit,
          preferredCli: selectedAssistant,
          selectedModel,
          travelCapabilityId: selectedCapability,
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
      if (promptToSubmit) {
        await fetchAPI(`${API_BASE}/api/chat/${createdProjectId}/act`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            instruction: promptToSubmit,
            images: imageData,
            isInitialPrompt: true,
            cliPreference: selectedAssistant,
            selectedModel,
            travelCapabilityId: selectedCapability,
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

  // --- Render ---
  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-50 text-foreground">
      <main className="relative flex min-h-screen flex-col overflow-y-auto">
            <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden bg-slate-50">
              <div className="absolute inset-0 bg-gradient-to-br from-slate-100 to-white opacity-50" />
              <div
                className="travel-photo-left absolute -left-28 top-64 h-[720px] w-[900px] overflow-hidden border-[7px] border-white bg-white shadow-2xl"
                style={{ transform: "rotate(-8.5deg) translateY(58px)" }}
              >
                <Image
                  src={scenicImages[0]}
                  alt=""
                  fill
                  sizes="900px"
                  className="object-cover saturate-150 contrast-115 brightness-105"
                />
              </div>
              <div
                className="travel-photo-right absolute right-12 top-12 h-[410px] w-[520px] overflow-hidden border-[7px] border-white bg-white shadow-2xl"
                style={{ transform: "rotate(10deg) translateY(20px)" }}
              >
                <Image
                  src={scenicImages[1]}
                  alt=""
                  fill
                  sizes="520px"
                  className="object-cover saturate-150 contrast-115 brightness-105"
                />
              </div>
              <div
                className="travel-photo-temple absolute -right-28 bottom-10 h-[330px] w-[500px] overflow-hidden border-[7px] border-white bg-white shadow-2xl"
                style={{ transform: "rotate(-4deg)" }}
              >
                <Image
                  src={scenicImages[2]}
                  alt=""
                  fill
                  sizes="500px"
                  className="object-cover saturate-150 contrast-115 brightness-105"
                />
              </div>
              <div
                className="travel-photo-small absolute left-[38%] top-40 h-[250px] w-[380px] overflow-hidden border-[6px] border-white bg-white shadow-xl"
                style={{ transform: "rotate(-6deg)" }}
              >
                <Image
                  src={scenicImages[3]}
                  alt=""
                  fill
                  sizes="380px"
                  className="object-cover opacity-70 saturate-105 contrast-105 brightness-125"
                />
              </div>
              <div className="absolute inset-0 bg-white/5 mix-blend-overlay" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.16),rgba(248,250,252,0.36)_54%,rgba(248,250,252,0.72)_100%)]" />
            </div>

            <section className="relative z-10 pt-20 pb-6 lg:pt-28 lg:pb-8">
              <div className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 text-center">
                <h2 className="mb-4 text-4xl font-black leading-[0.98] tracking-tight text-neutral-900 drop-shadow-sm sm:text-5xl lg:text-6xl">
                  把北京的一天，排成想出发的路线
                </h2>
                <p className="mb-8 max-w-2xl text-lg font-semibold leading-8 text-neutral-700 drop-shadow-sm">
                  从红墙金瓦到胡同烟火，按你的时间、预算和脚力，拼出一条真正走得动、吃得好、少踩坑的北京计划。
                </p>
                <div className="mx-auto flex w-fit items-center justify-center rounded-full border border-white/50 bg-white/40 p-1.5 text-xs font-black uppercase tracking-[0.15em] shadow-sm backdrop-blur-md">
                  {[
                    { label: "AI 对话", value: "chat" as const, icon: Bot },
                    { label: "表单填写", value: "form" as const, icon: Edit3 },
                  ].map((mode) => {
                    const active = homeInputMode === mode.value;
                    const Icon = mode.icon;
                    return (
                      <button
                        key={mode.label}
                        type="button"
                        onClick={() => setHomeInputMode(mode.value)}
                        style={active ? { backgroundColor: "#211e1a" } : undefined}
                        className={`relative z-10 flex items-center gap-2 rounded-full px-6 py-2.5 transition-all duration-300 ${
                          active
                            ? "bg-neutral-900 text-white shadow-md"
                            : "text-neutral-700 hover:bg-white/50 hover:text-neutral-950"
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {mode.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </section>

            <section className="relative z-10 pb-24">
              <div className="mx-auto w-full max-w-6xl px-4">
              <div className="travel-glass-panel w-full rounded-[3rem] border border-white/40 bg-white/60 p-6 shadow-2xl shadow-black/5 backdrop-blur-xl md:p-10">
                {homeInputMode === "form" && (
                <div className="text-left">
                  <div className="mb-10 grid gap-6 md:grid-cols-2">
                    <label className="space-y-2 text-sm font-semibold text-[#4b5563]">
                      目标游玩区域
                      <select
                        value={tripForm.area}
                        onChange={(event) =>
                          setTripForm((current) => ({
                            ...current,
                            area: event.target.value,
                          }))
                        }
                        className={formFieldClass}
                      >
                        {areaOptions.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="space-y-2 text-sm font-semibold text-[#4b5563]">
                      餐饮需求
                      <select
                        value={tripForm.meal}
                        onChange={(event) =>
                          setTripForm((current) => ({
                            ...current,
                            meal: event.target.value,
                          }))
                        }
                        className={formFieldClass}
                      >
                        {["中午吃饭", "不吃饭", "想喝咖啡", "安排下午茶", "晚上吃饭"].map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="mb-10">
                    <div className="mb-5 flex items-center justify-between">
                      <label className="text-sm font-black uppercase tracking-[0.1em] text-neutral-900">
                        游玩时长
                      </label>
                      <span className="rounded-full bg-neutral-900 px-3 py-1 text-xs font-black uppercase tracking-wider text-white shadow-md">
                        {tripForm.duration}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
                      {["3小时", "4小时", "半日", "1天", "2天", "3天"].map((item) => {
                        const active = tripForm.duration === item;
                        return (
                          <button
                            key={item}
                            type="button"
                            style={
                              active
                                ? {
                                    backgroundColor: "#211e1a",
                                    borderColor: "#211e1a",
                                    color: "#ffffff",
                                  }
                                : undefined
                            }
                            onClick={() =>
                              setTripForm((current) => ({
                                ...current,
                                duration: item,
                              }))
                            }
                            className={`rounded-full border px-4 py-2.5 text-sm font-black transition ${
                              active
                                ? "border-neutral-900 bg-neutral-900 text-white shadow-md"
                                : "border-white/70 bg-white/65 text-neutral-950 hover:bg-white"
                            }`}
                          >
                            {item}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="mb-10 grid gap-6 md:grid-cols-2">
                    <div>
                      <label className="mb-4 block text-sm font-black uppercase tracking-[0.1em] text-neutral-900">
                        同行人群
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        {["朋友/情侣", "老人", "亲子", "独自出行"].map((item) => {
                          const active = tripForm.persona === item;
                          return (
                            <button
                              key={item}
                              type="button"
                              style={
                                active
                                  ? {
                                      backgroundColor: "#211e1a",
                                      borderColor: "#211e1a",
                                      color: "#ffffff",
                                    }
                                  : undefined
                              }
                              onClick={() =>
                                setTripForm((current) => ({
                                  ...current,
                                  persona: item,
                                }))
                              }
                              className={`rounded-full border px-4 py-2.5 text-sm font-black transition ${
                                active
                                  ? "border-neutral-900 bg-neutral-900 text-white shadow-md"
                                  : "border-white/70 bg-white/65 text-neutral-950 hover:bg-white"
                              }`}
                            >
                              {item}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <label className="space-y-4 text-sm font-black uppercase tracking-[0.1em] text-neutral-900">
                      预算
                      <input
                        value={tripForm.budget}
                        onChange={(event) =>
                          setTripForm((current) => ({
                            ...current,
                            budget: event.target.value,
                          }))
                        }
                        className={formFieldClass}
                        placeholder="如：200"
                      />
                    </label>
                  </div>

                  <div className="mb-10">
                    <label className="mb-4 block text-sm font-black uppercase tracking-[0.1em] text-neutral-900">
                      北京旅游核心能力
                    </label>
                    <div className="flex flex-wrap gap-2.5">
                      {ROLE_MODULES.map((role) => {
                        const active = selectedCapability === role.capabilityId;
                        return (
                          <button
                            key={role.id}
                            type="button"
                            style={
                              active
                                ? {
                                    backgroundColor: "#211e1a",
                                    borderColor: "#211e1a",
                                    color: "#ffffff",
                                  }
                                : undefined
                            }
                            onClick={() => setSelectedCapability(role.capabilityId)}
                            aria-pressed={active}
                            className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all duration-200 ${
                              active
                                ? "border-neutral-900 bg-neutral-900 text-white shadow-md"
                                : "border-white/70 bg-white/65 text-neutral-950 hover:bg-white"
                            }`}
                          >
                            {role.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="mb-10">
                    <label className="mb-4 block text-sm font-black uppercase tracking-[0.1em] text-neutral-900">
                      兴趣偏好
                    </label>
                    <div className="flex flex-wrap gap-2.5">
                      {preferenceOptions.map((label) => {
                        const active = tripForm.preferences.includes(label);
                        return (
                          <button
                            key={label}
                            type="button"
                            style={
                              active
                                ? {
                                    backgroundColor: "#211e1a",
                                    borderColor: "#211e1a",
                                    color: "#ffffff",
                                  }
                                : undefined
                            }
                            onClick={() => toggleTripPreference(label)}
                            aria-pressed={active}
                            className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all duration-200 ${
                              active
                                ? "border-neutral-900 bg-neutral-900 text-white shadow-md"
                                : "border-white/70 bg-white/65 text-neutral-950 hover:bg-white"
                            }`}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex justify-center">
                    <Button
                      type="button"
                      style={{ backgroundColor: "#211e1a", color: "#ffffff" }}
                      onClick={() => handleSubmit(buildTripFormPrompt())}
                      disabled={isCreatingProject}
                      className="h-16 rounded-full bg-neutral-900 px-12 text-xl font-black text-white shadow-lg shadow-black/30 transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isCreatingProject ? "规划中..." : "开启我的规划"}
                    </Button>
                  </div>
                </div>
                )}
                {homeInputMode === "chat" && (
                <div className="flex min-h-[280px] flex-col font-sans">
                  <div className="mb-4 max-h-[420px] flex-1 space-y-6 overflow-y-auto pr-2">
                    <div className="flex justify-start">
                      <div className="max-w-[95%] rounded-3xl rounded-bl-[2px] bg-white/80 px-5 py-4 text-[15px] leading-relaxed text-neutral-800 shadow-sm backdrop-blur-md">
                        你好，今天想把北京怎么逛？
                        <br />
                        比如：想看红墙古建、找地道吃的，还是带家人轻松走一圈？
                      </div>
                    </div>
                  </div>

                  <div className="group relative mt-2 w-full">
                    <div className="absolute -inset-1 rounded-[2rem] bg-[#173f35]/18 opacity-80 blur-lg" />
                    <div className="relative flex flex-col rounded-[2rem] border border-[#173f35]/35 bg-white p-2 shadow-xl shadow-[#173f35]/15 backdrop-blur-xl transition-all duration-300 focus-within:border-[#173f35] focus-within:ring-4 focus-within:ring-[#173f35]/10">
                    <textarea
                      value={prompt}
                      onChange={(event) => setPrompt(event.target.value)}
                      placeholder="写下你的北京想法，例如：周六下午想从故宫开始，吃点地道的，别走太累..."
                      disabled={isCreatingProject}
                        className="min-h-[56px] w-full resize-none bg-white px-4 pb-1 pt-3 text-[15px] font-semibold leading-6 text-neutral-950 outline-none transition-all placeholder:text-neutral-500"
                      maxLength={500}
                    />
                    <div className="mt-1 flex items-center justify-between px-3 pb-1 pt-1">
                      <div className="flex items-center gap-3">
                        <span className="px-1 text-[11px] font-medium text-neutral-600">
                          {prompt.length}/500
                        </span>
                        <span className="hidden rounded-full bg-white/50 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-neutral-700 sm:inline-flex">
                          {selectedRoleModule.name}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleSubmit()}
                        disabled={(!prompt.trim() && uploadedImages.length === 0) || isCreatingProject}
                          className="flex h-12 w-12 items-center justify-center rounded-full bg-[#173f35] text-white shadow-lg shadow-[#173f35]/30 transition hover:bg-[#205447] disabled:cursor-not-allowed disabled:bg-neutral-300 disabled:text-neutral-500 disabled:shadow-none"
                        aria-label="开始规划"
                      >
                        <ArrowUp className="h-5 w-5" />
                      </button>
                    </div>
                    </div>
                  </div>
                </div>
                )}
                <div className="mt-7 flex flex-wrap justify-center gap-x-8 gap-y-3 px-4">
                  {quickSamples.map((sample) => (
                    <button
                      key={sample}
                      type="button"
                      onClick={() => setPrompt(sample)}
                      className="rounded-full px-2 text-sm font-black text-[#6c4a7a] transition hover:text-[#b73522]"
                    >
                      {sample}
                    </button>
                  ))}
                </div>
              </div>
              </div>
            </section>

          </main>
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
                  <CheckCircle2 className="h-5 w-5 shrink-0" />
                ) : (
                  <XCircle className="h-5 w-5 shrink-0" />
                )}
                <p className="text-sm font-medium">{toast.message}</p>
              </div>
            </motion.div>
          </div>
        )}
    </div>
  );
}
