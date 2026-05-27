"use client";
import { useEffect, useState, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useRouter } from 'next/navigation';
import GlobalSettings from '@/components/settings/GlobalSettings';
import { useGlobalSettings } from '@/contexts/GlobalSettingsContext';
import { getDefaultModelForCli, getModelDisplayName } from '@/lib/constants/cliModels';
import {
  ArrowUp,
  Boxes,
  Gauge,
  Image as ImageIcon,
  Menu,
  PackageCheck,
  Pencil,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import type { Project as ProjectSummary } from '@/types/project';
import { fetchCliStatusSnapshot, createCliStatusFallback } from '@/hooks/useCLI';
import type { CLIStatus } from '@/types/cli';
import {
  ACTIVE_CLI_BRAND_COLORS,
  ACTIVE_CLI_MODEL_OPTIONS,
  ACTIVE_CLI_OPTIONS,
  ACTIVE_CLI_OPTIONS_MAP,
  DEFAULT_ACTIVE_CLI,
  normalizeModelForCli,
  sanitizeActiveCli,
  type ActiveCliId,
} from '@/lib/utils/cliOptions';
import {
  DEFAULT_QUANT_CAPABILITY_ID,
  getQuantCapability,
  type QuantCapabilityId,
} from '@/lib/quant/capabilities';

// Ensure fetch is available
const fetchAPI = globalThis.fetch || fetch;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

// Define assistant brand colors
const ASSISTANT_OPTIONS = ACTIVE_CLI_OPTIONS.map(({ id, name }) => ({
  id,
  name,
}));

const assistantBrandColors = ACTIVE_CLI_BRAND_COLORS;

const MODEL_OPTIONS_BY_ASSISTANT = ACTIVE_CLI_MODEL_OPTIONS;

const ROLE_MODULES: Array<{
  id: string;
  name: string;
  description: string;
  capabilityId: QuantCapabilityId;
  inputPlaceholder: string;
}> = [
  {
    id: 'holding-analysis',
    name: '持仓分析',
    description: '识别持仓结构、盈亏、集中度、回撤和调仓约束',
    capabilityId: 'portfolio_risk',
    inputPlaceholder: '描述你的持仓、成本、可用资金或上传持仓截图，我会按持仓分析角色生成风险与调仓看板',
  },
  {
    id: 'stock-selection',
    name: '选股分析',
    description: '从候选标的中比较趋势、财务、估值、流动性和风险',
    capabilityId: 'asset_comparison',
    inputPlaceholder: '输入候选股票、行业方向或筛选条件，我会按选股分析角色拉取数据并生成对比看板',
  },
  {
    id: 'single-stock-diagnosis',
    name: '个股诊断',
    description: '围绕单只股票整合行情、K 线、财务、公告和风险',
    capabilityId: 'stock_diagnosis',
    inputPlaceholder: '输入股票名称或代码，以及你关心的行情、财务、公告或风险问题',
  },
  {
    id: 'timing-analysis',
    name: '技术择时',
    description: '分析价格趋势、均线结构、成交量、回撤和触发条件',
    capabilityId: 'technical_analysis',
    inputPlaceholder: '输入标的和时间范围，我会按技术择时角色生成 K 线、量价和趋势模板看板',
  },
  {
    id: 'fundamental-research',
    name: '基本面研究',
    description: '研究盈利质量、现金流、ROE、公告事件和估值情景',
    capabilityId: 'fundamental_analysis',
    inputPlaceholder: '输入公司或行业，我会按基本面研究角色整理财务、公告、估值情景和数据质量',
  },
  {
    id: 'strategy-backtest',
    name: '策略回测',
    description: '拆解信号规则、样本、参数、交易明细和回测限制',
    capabilityId: 'backtest_review',
    inputPlaceholder: '描述策略规则、标的和时间窗口，我会按策略回测角色生成可复盘的量化看板',
  },
];

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [showGlobalSettings, setShowGlobalSettings] = useState(false);
  const [globalSettingsTab, setGlobalSettingsTab] = useState<'general' | 'ai-assistant'>('ai-assistant');
  const [editingProject, setEditingProject] = useState<ProjectSummary | null>(null);
  const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; project: ProjectSummary | null }>({ isOpen: false, project: null });
  const [isDeleting, setIsDeleting] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [prompt, setPrompt] = useState('');
  const DEFAULT_ASSISTANT: ActiveCliId = DEFAULT_ACTIVE_CLI;
  const DEFAULT_MODEL = getDefaultModelForCli(DEFAULT_ASSISTANT);
  const sanitizeAssistant = useCallback(
    (cli?: string | null) => sanitizeActiveCli(cli, DEFAULT_ASSISTANT),
    [DEFAULT_ASSISTANT]
  );
  const normalizeModelForAssistant = useCallback(
    (assistant: string, model?: string | null) => normalizeModelForCli(assistant, model, DEFAULT_ASSISTANT),
    [DEFAULT_ASSISTANT]
  );

  const normalizeProjectPayload = useCallback((project: any): ProjectSummary => {
    const preferred = sanitizeAssistant(project?.preferredCli ?? project?.preferred_cli);
    const selected = normalizeModelForAssistant(preferred, project?.selectedModel ?? project?.selected_model);

    return {
      id: project.id,
      name: project.name,
      description: project.description ?? null,
      status: project.status,
      previewUrl: project.previewUrl ?? project.preview_url ?? null,
      createdAt: project.createdAt ?? project.created_at ?? new Date().toISOString(),
      updatedAt: project.updatedAt ?? project.updated_at,
      lastActiveAt: project.lastActiveAt ?? project.last_active_at ?? null,
      lastMessageAt: project.lastMessageAt ?? project.last_message_at ?? null,
      initialPrompt: project.initialPrompt ?? project.initial_prompt ?? null,
      services: project.services,
      preferredCli: preferred as ProjectSummary['preferredCli'],
      selectedModel: selected,
      fallbackEnabled: project.fallbackEnabled ?? project.fallback_enabled ?? false,
      quantCapabilityId: getQuantCapability(project.quantCapabilityId ?? project.quant_capability_id).id,
    };
  }, [sanitizeAssistant, normalizeModelForAssistant]);
  const [selectedAssistant, setSelectedAssistant] = useState<ActiveCliId>(DEFAULT_ASSISTANT);
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL);
  const [selectedCapability, setSelectedCapability] = useState<QuantCapabilityId>(DEFAULT_QUANT_CAPABILITY_ID);
  const [usingGlobalDefaults, setUsingGlobalDefaults] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false);
  const [projectSearch, setProjectSearch] = useState('');
  const [cliStatus, setCLIStatus] = useState<CLIStatus>(() => createCliStatusFallback());
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  // 根据当前 Agent 获取可用模型
  const availableModels = MODEL_OPTIONS_BY_ASSISTANT[selectedAssistant] || [];
  
  // 同步全局设置，直到用户在当前页面手动覆盖
  const { settings: globalSettings } = useGlobalSettings();
  
  // 判断是否是刷新进入，而不是站内导航
  useEffect(() => {
    const isPageRefresh = !sessionStorage.getItem('navigationFlag');
    
    if (isPageRefresh) {
      // 刷新或首次加载时使用全局默认值
      sessionStorage.setItem('navigationFlag', 'true');
      setIsInitialLoad(true);
      setUsingGlobalDefaults(true);
    } else {
      // 站内导航时延续本轮会话的选择
      const storedAssistantRaw = sessionStorage.getItem('selectedAssistant');
      const storedModelRaw = sessionStorage.getItem('selectedModel');

      if (storedModelRaw) {
        const storedAssistant = sanitizeAssistant(storedAssistantRaw);
        const storedModel = normalizeModelForAssistant(storedAssistant, storedModelRaw);
        setSelectedAssistant(storedAssistant);
        setSelectedModel(storedModel);
        setUsingGlobalDefaults(false);
        setIsInitialLoad(false);
        return;
      }
    }
    
    // 卸载时无需主动清理，页面刷新由 beforeunload 处理
    return () => {
      // 保留站内导航标记
    };
  }, [sanitizeAssistant, normalizeModelForAssistant]);
  
  // Apply global settings when using defaults
  useEffect(() => {
    if (!usingGlobalDefaults || !isInitialLoad) return;
    
    const cli = sanitizeAssistant(globalSettings?.default_cli);
    setSelectedAssistant(cli);
    const modelFromGlobal = globalSettings?.cli_settings?.[cli]?.model;
    setSelectedModel(normalizeModelForAssistant(cli, modelFromGlobal));
  }, [globalSettings, usingGlobalDefaults, isInitialLoad, sanitizeAssistant, normalizeModelForAssistant]);
  
  // 用户手动切换后写入会话缓存
  useEffect(() => {
    if (!isInitialLoad && selectedAssistant && selectedModel) {
      const normalizedAssistant = sanitizeAssistant(selectedAssistant);
      sessionStorage.setItem('selectedAssistant', normalizedAssistant);
      sessionStorage.setItem('selectedModel', normalizeModelForAssistant(normalizedAssistant, selectedModel));
    }
  }, [selectedAssistant, selectedModel, isInitialLoad, sanitizeAssistant, normalizeModelForAssistant]);
  
  // 页面真正卸载时清理导航标记
  useEffect(() => {
    const handleBeforeUnload = () => {
      sessionStorage.removeItem('navigationFlag');
    };
    
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<{ id: string; name: string; url: string; path: string; file?: File }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const router = useRouter();
  const prefetchTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const openTaskDrawer = useCallback(() => {
    setTaskDrawerOpen(true);
  }, []);

  // 检查 CLI 安装状态
  useEffect(() => {
    const optimisticStatus = createCliStatusFallback();
    const checkingStatus = ASSISTANT_OPTIONS.reduce<CLIStatus>((acc, cli) => {
      const previous = acc[cli.id] ?? {
        installed: true,
        available: true,
        configured: true,
      };
      acc[cli.id] = {
        ...previous,
        checking: true,
      };
      return acc;
    }, optimisticStatus);
    setCLIStatus(checkingStatus);

    fetchCliStatusSnapshot()
      .then((status) => setCLIStatus(status))
      .catch((error) => {
        console.error('Failed to check CLI status:', error);
        setCLIStatus(createCliStatusFallback());
      });
  }, []);

  // 格式化任务时间
  const formatTime = (dateString: string | null) => {
    if (!dateString) return '暂无记录';
    
    // 服务端可能返回不带 Z 的 UTC 时间，这里补齐时区避免被解析成本地时间
    let utcDateString = dateString;
    
    // 判断是否已经包含时区信息
    const hasTimezone = dateString.endsWith('Z') || 
                       dateString.includes('+') || 
                       dateString.match(/[-+]\d{2}:\d{2}$/);
    
    if (!hasTimezone) {
      // 补 Z 表示 UTC
      utcDateString = dateString + 'Z';
    }
    
    // 按 UTC 解析后计算相对时间
    const date = new Date(utcDateString);
    const now = new Date();
    // Calculate the actual time difference
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins} 分钟前`;
    if (diffHours < 24) return `${diffHours} 小时前`;
    if (diffDays < 30) return `${diffDays} 天前`;
    
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    });
  };

  // 格式化 CLI 和模型信息
  const formatCliInfo = (cli?: string, model?: string) => {
    const normalizedCli = sanitizeAssistant(cli);
    const assistantOption = ACTIVE_CLI_OPTIONS_MAP[normalizedCli];
    const cliName = assistantOption?.name ?? 'Claude Code';
    const modelId = normalizeModelForAssistant(normalizedCli, model);
    const modelLabel = getModelDisplayName(normalizedCli, modelId);
    return `${cliName} • ${modelLabel}`;
  };

  const formatFullTime = (dateString: string) => {
    return new Date(dateString).toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const load = useCallback(async () => {
    try {
      const r = await fetchAPI(`${API_BASE}/api/projects`);
      if (!r.ok) {
        console.warn('Failed to load projects: HTTP', r.status);
        setProjects([]);
        return;
      }

      const payload = await r.json();
      if (payload?.success === false) {
        console.error('Failed to load projects:', payload?.error || payload?.message);
        setProjects([]);
        return;
      }

      const items: unknown[] = Array.isArray(payload?.data)
        ? payload.data
        : Array.isArray(payload)
        ? payload
        : [];

      const normalized: ProjectSummary[] = items
        .filter((project): project is Record<string, unknown> => Boolean(project && typeof project === 'object'))
        .map((project) => normalizeProjectPayload(project));

      const sortedProjects = normalized.sort((a, b) => {
        const aTime = a.lastMessageAt ?? a.createdAt;
        const bTime = b.lastMessageAt ?? b.createdAt;
        if (!aTime) return 1;
        if (!bTime) return -1;
        return new Date(bTime).getTime() - new Date(aTime).getTime();
      });

      setProjects(sortedProjects);
    } catch (error) {
      console.warn('Failed to load projects:', error);
      setProjects([]);
    }
  }, [normalizeProjectPayload]);
  
  async function onCreated() { await load(); }
  
  async function start(projectId: string) {
    try {
      await fetchAPI(`${API_BASE}/api/projects/${projectId}/preview/start`, { method: 'POST' });
      await load();
    } catch (error) {
      console.warn('Failed to start project:', error);
    }
  }
  
  async function stop(projectId: string) {
    try {
      await fetchAPI(`${API_BASE}/api/projects/${projectId}/preview/stop`, { method: 'POST' });
      await load();
    } catch (error) {
      console.warn('Failed to stop project:', error);
    }
  }

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const openDeleteModal = (project: ProjectSummary) => {
    setDeleteModal({ isOpen: true, project });
  };

  const closeDeleteModal = () => {
    setDeleteModal({ isOpen: false, project: null });
  };

  async function deleteProject() {
    if (!deleteModal.project) return;
    
    setIsDeleting(true);
    try {
      const response = await fetchAPI(`${API_BASE}/api/projects/${deleteModal.project.id}`, { method: 'DELETE' });
      
      if (response.ok) {
        showToast('任务已删除', 'success');
        await load();
        closeDeleteModal();
      } else {
        const errorData = await response.json().catch(() => ({ detail: '删除任务失败' }));
        showToast(errorData.detail || '删除任务失败', 'error');
      }
    } catch (error) {
      console.warn('Failed to delete project:', error);
      showToast('删除任务失败，请重试', 'error');
    } finally {
      setIsDeleting(false);
    }
  }

  async function updateProject(projectId: string, newName: string) {
    try {
      const response = await fetchAPI(`${API_BASE}/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName })
      });
      
      if (response.ok) {
        showToast('任务名称已更新', 'success');
        await load();
        setEditingProject(null);
      } else {
        const errorData = await response.json().catch(() => ({ detail: '更新任务失败' }));
        showToast(errorData.detail || '更新任务失败', 'error');
      }
    } catch (error) {
      console.warn('Failed to update project:', error);
      showToast('更新任务失败，请重试', 'error');
    }
  }

  // Handle files (for both drag drop and file input)
  const handleFiles = useCallback(async (files: FileList | File[]) => {
    setIsUploading(true);
    
    try {
      const filesArray = Array.from(files as ArrayLike<File>);
      const imagesToAdd = filesArray
        .filter(file => file.type.startsWith('image/'))
        .map(file => ({
          id: crypto.randomUUID(),
          name: file.name,
          url: URL.createObjectURL(file),
          path: '',
          file,
        }));

      if (imagesToAdd.length > 0) {
        setUploadedImages(prev => [...prev, ...imagesToAdd]);
      }
    } catch (error) {
      console.error('Image processing failed:', error);
      showToast('Failed to process image. Please try again.', 'error');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [showToast]);

  // Handle image upload - store locally first, upload after project creation
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    
    await handleFiles(files);
  };

  // Drag and drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set to false if we're leaving the container completely
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFiles(files);
    }
  };

  // Remove uploaded image
  const removeImage = (id: string) => {
    setUploadedImages(prev => {
      const imageToRemove = prev.find(img => img.id === id);
      if (imageToRemove) {
        URL.revokeObjectURL(imageToRemove.url);
      }
      return prev.filter(img => img.id !== id);
    });
  };

  const handleSubmit = async () => {
    if ((!prompt.trim() && uploadedImages.length === 0) || isCreatingProject) return;
    
    setIsCreatingProject(true);
    
    // Generate a unique project ID
    const projectId = `project-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    try {
      // Create a new project first
      const response = await fetchAPI(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          name: prompt.slice(0, 50) + (prompt.length > 50 ? '...' : ''),
          initialPrompt: prompt.trim(),
          preferredCli: selectedAssistant,
          selectedModel,
          quantCapabilityId: selectedCapability,
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        console.error('Failed to create project:', errorData);
        showToast('Failed to create project', 'error');
        setIsCreatingProject(false);
        return;
      }
      
      const payload = await response.json();
      const projectData = (payload && typeof payload === 'object') ? (payload.data ?? payload) : payload;
      const createdProjectId: string | undefined = projectData?.id ?? projectId;
      if (!createdProjectId) {
        console.error('Create project response missing id:', payload);
        showToast('Failed to create project (invalid response)', 'error');
        setIsCreatingProject(false);
        return;
      }
      if (createdProjectId !== projectId) {
        console.warn('Project ID mismatch between request and response:', {
          requestedId: projectId,
          responseId: createdProjectId,
          payload
        });
      }
      
      // 如有图片，先上传图片
      let imageData: any[] = [];
      
      if (uploadedImages.length > 0) {
        try {
          for (let i = 0; i < uploadedImages.length; i++) {
            const image = uploadedImages[i];
            if (!image.file) continue;
            
            const formData = new FormData();
            formData.append('file', image.file);

            const uploadResponse = await fetchAPI(`${API_BASE}/api/assets/${createdProjectId}/upload`, {
              method: 'POST',
              body: formData
            });

            if (uploadResponse.ok) {
              const result = await uploadResponse.json();
              // Track image data for API
              imageData.push({
                name: result.filename || image.name,
                path: result.absolute_path,
                public_url: typeof result.public_url === 'string' ? result.public_url : undefined
              });
            }
          }
        } catch (uploadError) {
          console.error('Image upload failed:', uploadError);
          showToast('Images could not be uploaded, but project was created', 'error');
        }
      }
      
      // Execute initial prompt directly with images
      if (prompt.trim()) {
        try {
          const actResponse = await fetchAPI(`${API_BASE}/api/chat/${createdProjectId}/act`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              instruction: prompt.trim(), // Original prompt without image paths
              images: imageData,
              isInitialPrompt: true,
              cliPreference: selectedAssistant,
              selectedModel,
              quantCapabilityId: selectedCapability,
            })
          });
          
          if (actResponse.ok) {
            // Successfully kicked off ACT with image payloads
          } else {
            console.error('❌ ACT failed:', await actResponse.text());
          }
        } catch (actError) {
          console.error('❌ ACT API error:', actError);
        }
      }
      
      // Navigate to chat page with model and CLI parameters
      uploadedImages.forEach(image => {
        if (image.url) {
          URL.revokeObjectURL(image.url);
        }
      });
      setUploadedImages([]);
      setPrompt('');

      const params = new URLSearchParams();
      if (selectedAssistant) params.set('cli', selectedAssistant);
      if (selectedModel) params.set('model', selectedModel);
      router.push(`/${createdProjectId}/chat${params.toString() ? '?' + params.toString() : ''}`);
      
    } catch (error) {
      console.error('Failed to create project:', error);
      showToast('Failed to create project', 'error');
    } finally {
      setIsCreatingProject(false);
    }
  };

  useEffect(() => { 
    load();
    
    // Handle clipboard paste for images
    const handlePaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      
      const imageFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
      }
      
      if (imageFiles.length > 0) {
        e.preventDefault();
        const fileList = {
          length: imageFiles.length,
          item: (index: number) => imageFiles[index],
          [Symbol.iterator]: function* () {
            for (let i = 0; i < imageFiles.length; i++) {
              yield imageFiles[i];
            }
          }
        } as FileList;
        
        // Convert to FileList-like object
        Object.defineProperty(fileList, 'length', { value: imageFiles.length });
        imageFiles.forEach((file, index) => {
          Object.defineProperty(fileList, index, { value: file });
        });
        
        handleFiles(fileList);
      }
    };
    
    document.addEventListener('paste', handlePaste);
    const timers = prefetchTimers.current;

    // Cleanup prefetch timers
    return () => {
      timers.forEach(timer => clearTimeout(timer));
      timers.clear();
      document.removeEventListener('paste', handlePaste);
    };
  }, [selectedAssistant, handleFiles, load]);

  // Update models when assistant changes
  const isAssistantSelectable = useCallback((assistant: string) => {
    const status = cliStatus[assistant];
    if (!status || status.checking) return true;
    return Boolean(status.installed || status.available || status.configured);
  }, [cliStatus]);

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

  const selectedModelLabel =
    availableModels.find((model) => model.id === selectedModel)?.name ??
    getModelDisplayName(selectedAssistant, selectedModel);
  const selectedRoleModule =
    ROLE_MODULES.find((role) => role.capabilityId === selectedCapability) ?? ROLE_MODULES[0];
  const runningProjects = projects.filter((project) => project.previewUrl || project.status === 'running').length;
  const recentProjects = projects.slice(0, 8);
  const filteredProjects = projects.filter((project) => {
    const keyword = projectSearch.trim().toLowerCase();
    if (!keyword) return true;
    return [
      project.name,
      project.description,
      project.initialPrompt,
      getQuantCapability(project.quantCapabilityId).shortName,
      formatCliInfo(project.preferredCli ?? undefined, project.selectedModel ?? undefined),
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword));
  });
  const openProject = (project: ProjectSummary) => {
    const params = new URLSearchParams();
    if (selectedAssistant) params.set('cli', selectedAssistant);
    if (selectedModel) params.set('model', selectedModel);
    router.push(`/${project.id}/chat${params.toString() ? '?' + params.toString() : ''}`);
  };

  const renderProjectItem = (project: ProjectSummary) => {
    const projectCli = sanitizeAssistant(project.preferredCli);
    const projectColor = assistantBrandColors[projectCli] || assistantBrandColors[DEFAULT_ASSISTANT];
    const capability = getQuantCapability(project.quantCapabilityId);

    return (
      <div
        key={project.id}
        className="group rounded-lg border border-transparent px-3 py-2.5 transition-colors hover:border-red-100 hover:bg-red-50/70"
      >
        {editingProject?.id === project.id ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target as HTMLFormElement);
              const newName = formData.get('name') as string;
              if (newName.trim()) {
                updateProject(project.id, newName.trim());
              }
            }}
            className="space-y-2"
          >
            <input
              name="name"
              defaultValue={project.name}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm outline-none focus:ring-1 focus:ring-ring"
              autoFocus
              onBlur={() => setEditingProject(null)}
            />
            <div className="flex gap-2">
              <Button type="submit" size="sm" className="h-8">
                保存
              </Button>
              <Button
                type="button"
                onClick={() => setEditingProject(null)}
                size="sm"
                variant="outline"
                className="h-8"
              >
                取消
              </Button>
            </div>
          </form>
        ) : (
          <div className="flex items-start gap-2">
            <button type="button" onClick={() => openProject(project)} className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-2">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: projectColor }}
                />
                <h3 className="truncate text-sm font-semibold text-gray-900">{project.name}</h3>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-gray-500">
                <span>{formatTime(project.lastMessageAt || project.createdAt)}</span>
                <span>•</span>
                <span>{capability.shortName}</span>
              </div>
              <div className="mt-1 truncate text-[11px] text-gray-400">
                {formatCliInfo(projectCli, project.selectedModel ?? undefined)}
              </div>
            </button>
            <div className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                type="button"
                onClick={() => setEditingProject(project)}
                className="rounded-md p-1 text-gray-400 hover:bg-white hover:text-red-500"
                title="重命名"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => openDeleteModal(project)}
                className="rounded-md p-1 text-gray-400 hover:bg-white hover:text-red-500"
                title="删除"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderTaskRecordItem = (project: ProjectSummary) => {
    const projectCli = sanitizeAssistant(project.preferredCli);
    const capability = getQuantCapability(project.quantCapabilityId);
    const title = project.name || project.initialPrompt || '未命名任务';
    const isEditing = editingProject?.id === project.id;

    return (
      <div
        key={project.id}
        className="group relative border-b border-gray-100 px-4 py-3 transition-colors hover:bg-gray-50"
      >
        {isEditing ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
              const newName = String(formData.get('name') || '').trim();
              if (newName) {
                updateProject(project.id, newName);
              }
            }}
            className="space-y-2"
          >
            <input
              name="name"
              defaultValue={title}
              autoFocus
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-medium shadow-sm outline-none focus:ring-1 focus:ring-ring"
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  setEditingProject(null);
                }
              }}
            />
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                onClick={() => setEditingProject(null)}
                size="sm"
                variant="outline"
                className="h-8"
              >
                取消
              </Button>
              <Button
                type="submit"
                size="sm"
                className="h-8"
              >
                保存
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <button
              type="button"
              onClick={() => openProject(project)}
              className="block w-full min-w-0 text-left"
            >
              <div className="truncate text-sm font-semibold text-gray-950">{title}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-gray-500">
                <span>{formatTime(project.lastMessageAt || project.createdAt)}</span>
                <span>@{project.id.slice(-8)}</span>
              </div>
              <div className="mt-1 truncate text-xs text-gray-400">
                {capability.shortName} · {formatCliInfo(projectCli, project.selectedModel ?? undefined)}
              </div>
            </button>
            <div className="pointer-events-none absolute right-3 top-3 z-10 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                type="button"
                onClick={() => setEditingProject(project)}
                className="pointer-events-auto rounded-md p-1.5 text-gray-400 hover:bg-white hover:text-red-500"
                title="重命名任务"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => openDeleteModal(project)}
                className="pointer-events-auto rounded-md p-1.5 text-gray-400 hover:bg-white hover:text-red-500"
                title="删除任务"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderTaskHistoryDrawer = () => {
    return (
      <Sheet open={taskDrawerOpen} onOpenChange={setTaskDrawerOpen}>
        <SheetContent side="left" className="flex w-full max-w-[420px] flex-col p-0 sm:max-w-[420px]">
          <SheetHeader className="border-b px-4 py-3">
            <div className="flex items-baseline gap-1.5">
              <SheetTitle className="text-base">任务记录</SheetTitle>
              <SheetDescription className="text-xs">({projects.length})</SheetDescription>
            </div>
          </SheetHeader>

          <div className="border-b bg-muted/30 px-4 py-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={projectSearch}
                onChange={(event) => setProjectSearch(event.target.value)}
                placeholder="搜索对话标题、用户或内容..."
                className="pl-9"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {filteredProjects.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-muted-foreground">
                暂无匹配的任务记录
              </div>
            ) : (
              filteredProjects.map(renderTaskRecordItem)
            )}
          </div>
        </SheetContent>
      </Sheet>
    );
  };

  const renderTaskSidebar = (isMobile = false) => (
    <aside
      className={`flex h-full flex-col border-r bg-background/95 ${
        isMobile ? 'w-[286px]' : 'w-[260px]'
      }`}
    >
      <div className="flex h-16 items-center justify-between border-b px-4">
        <button
          type="button"
          onClick={openTaskDrawer}
          className="flex items-center gap-2 text-foreground hover:text-primary"
          title="打开任务记录"
        >
          <Menu className="h-4 w-4" />
          <span className="text-base font-semibold">任务记录</span>
        </button>
        {isMobile && (
          <Button
            type="button"
            onClick={() => setSidebarOpen(false)}
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            title="关闭"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        <div className="mb-3 px-2">
          <div className="text-xs font-semibold tracking-wide text-muted-foreground">角色模块</div>
        </div>

        <div className="space-y-1.5">
          {ROLE_MODULES.map((role) => {
            const active = selectedCapability === role.capabilityId;
            return (
            <button
              key={role.id}
              type="button"
              onClick={() => {
                setSelectedCapability(role.capabilityId);
                if (isMobile) {
                  setSidebarOpen(false);
                }
              }}
              className={`w-full rounded-md border px-3 py-3 text-left transition-colors ${
                active
                  ? 'border-primary/20 bg-primary/10 text-primary'
                  : 'border-transparent text-foreground hover:border-border hover:bg-muted/60'
              }`}
              title={role.description}
              aria-pressed={active}
            >
              <div className={`text-sm font-semibold ${active ? 'text-primary' : 'text-foreground'}`}>
                {role.name}
              </div>
              <div className={`mt-1 text-xs leading-5 ${active ? 'text-primary/80' : 'text-muted-foreground'}`}>
                {role.description}
              </div>
            </button>
            );
          })}
        </div>

      </div>

      <div className="border-t p-3">
        <Button
          type="button"
          onClick={() => router.push('/workspaces')}
          variant="ghost"
          className="mb-1 w-full justify-start"
        >
          <ShieldCheck className="h-4 w-4" />
          工作空间运维台
        </Button>
        <Button
          type="button"
          onClick={() => router.push('/capabilities')}
          variant="ghost"
          className="mb-1 w-full justify-start"
        >
          <Boxes className="h-4 w-4" />
          能力与数据源中心
        </Button>
        <Button
          type="button"
          onClick={() => router.push('/evals')}
          variant="ghost"
          className="mb-1 w-full justify-start"
        >
          <Gauge className="h-4 w-4" />
          Agent 评测后台
        </Button>
        <Button
          type="button"
          onClick={() => router.push('/skills')}
          variant="ghost"
          className="mb-1 w-full justify-start"
        >
          <PackageCheck className="h-4 w-4" />
          Skills 管理
        </Button>
        <Button
          type="button"
          onClick={() => setShowGlobalSettings(true)}
          variant="ghost"
          className="w-full justify-start"
        >
          <Settings className="h-4 w-4" />
          模型与数据源设置
        </Button>
      </div>
    </aside>
  );


  return (
    <div className="relative flex h-screen overflow-hidden bg-background text-foreground">
      {/* 柔和底部背景，保持输入区聚焦 */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-background" />
        <div className="absolute inset-x-0 bottom-0 h-2/3 bg-[radial-gradient(ellipse_at_bottom,rgba(220,38,38,0.13),rgba(255,255,255,0)_66%)]" />
      </div>
      
      {/* 页面主体 */}
      <div className="relative z-10 flex h-full w-full">
        <div className="hidden lg:block">
          {renderTaskSidebar()}
        </div>

        {sidebarOpen && (
          <div className="fixed inset-0 z-40 bg-black/20 lg:hidden" onClick={() => setSidebarOpen(false)}>
            <div className="h-full" onClick={(event) => event.stopPropagation()}>
              {renderTaskSidebar(true)}
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 shrink-0 items-center justify-between border-b bg-background/85 px-4 backdrop-blur md:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <Button
                type="button"
                onClick={() => setSidebarOpen(true)}
                size="icon"
                variant="ghost"
                className="lg:hidden"
                title="打开任务记录"
              >
                <Menu className="h-5 w-5" />
              </Button>
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-base font-bold text-primary-foreground shadow-sm">
                Q
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-base font-bold md:text-lg">QuantPilot</h1>
                <div className="mt-1 hidden items-center gap-2 text-xs text-muted-foreground md:flex">
                  <span>任务 {projects.length}</span>
                  <span>•</span>
                  <span>运行中 {runningProjects}</span>
                  <span>•</span>
                  <span>{selectedModelLabel}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                onClick={() => setShowGlobalSettings(true)}
                size="icon"
                variant="secondary"
                title="模型与数据源设置"
              >
                <Settings className="h-4 w-4" />
              </Button>
            </div>
          </header>

          <main className="relative flex-1 overflow-y-auto">
            <div className="relative mx-auto flex min-h-full w-full max-w-6xl -translate-y-6 flex-col items-center justify-center px-4 py-8 md:-translate-y-12 md:px-8 lg:-translate-y-14">
              <div className="mb-6 text-center">
                <h2 className="text-3xl font-bold tracking-normal text-primary md:text-5xl">
                  QuantPilot
                </h2>
                <p className="mt-3 text-sm text-muted-foreground md:text-base">
                  选择角色模块，描述真实需求，等待任务完成并生成可验证的量化看板
                </p>
              </div>

              {uploadedImages.length > 0 && (
                <div className="mb-3 flex w-full max-w-4xl flex-wrap gap-2">
                  {uploadedImages.map((image, index) => (
                    <div key={image.id} className="group relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={image.url}
                        alt={image.name}
                        className="h-16 w-16 rounded-lg border border-gray-200 object-cover"
                      />
                      <span className="absolute bottom-1 left-1 rounded bg-black/55 px-1 text-[10px] text-white">
                        图 {index + 1}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeImage(image.id)}
                        className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs text-white opacity-0 transition-opacity hover:bg-red-600 group-hover:opacity-100"
                        title="移除图片"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  handleSubmit();
                }}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                className={`relative w-full max-w-4xl rounded-lg border bg-card text-card-foreground shadow-lg transition-colors ${
                  isDragOver ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <Textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder={selectedRoleModule.inputPlaceholder}
                  disabled={isCreatingProject}
                  className="min-h-[128px] resize-none border-0 px-5 py-4 text-[16px] leading-6 shadow-none focus-visible:ring-0"
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      if (event.metaKey || event.ctrlKey) {
                        event.preventDefault();
                        handleSubmit();
                      } else if (!event.shiftKey) {
                        event.preventDefault();
                        handleSubmit();
                      }
                    }
                  }}
                />

                {isDragOver && (
                  <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-lg border-2 border-dashed border-primary bg-primary/10">
                    <div className="text-center text-primary">
                      <ImageIcon className="mx-auto mb-2 h-6 w-6" />
                      <div className="text-sm font-semibold">将图片拖到这里</div>
                      <div className="mt-1 text-xs">支持 JPG、PNG、GIF、WEBP</div>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 border-t px-3 py-3">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="relative h-9 w-9"
                    title="上传图片"
                    asChild
                  >
                    <label>
                      <ImageIcon className="h-4 w-4" />
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        onChange={handleImageUpload}
                        disabled={isUploading || isCreatingProject}
                        className="sr-only"
                      />
                    </label>
                  </Button>

                  <Select value={selectedAssistant} onValueChange={handleAssistantChange}>
                    <SelectTrigger className="w-[160px]">
                      <SelectValue placeholder="选择助手" />
                    </SelectTrigger>
                    <SelectContent>
                      {ASSISTANT_OPTIONS.map((option) => (
                        <SelectItem
                          key={option.id}
                          value={option.id}
                          disabled={!isAssistantSelectable(option.id)}
                        >
                          {option.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Badge variant="secondary" className="h-9 rounded-md px-3 text-sm text-primary">
                    {selectedRoleModule.name}
                  </Badge>

                  <Select value={selectedModel} onValueChange={handleModelChange}>
                    <SelectTrigger className="w-[170px]">
                      <SelectValue placeholder="选择模型" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Button
                    type="submit"
                    disabled={(!prompt.trim() && uploadedImages.length === 0) || isCreatingProject}
                    size="icon"
                    className="ml-auto h-9 w-9"
                    title="提交任务"
                  >
                    {isCreatingProject ? (
                      <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                    ) : (
                      <ArrowUp className="h-5 w-5" />
                    )}
                  </Button>
                </div>
              </form>

            </div>
          </main>
        </div>


      {/* 任务记录抽屉 */}
      {renderTaskHistoryDrawer()}

      {/* 全局设置弹窗 */}
      <GlobalSettings
        isOpen={showGlobalSettings}
        onClose={() => setShowGlobalSettings(false)}
      />

      <AlertDialog open={deleteModal.isOpen && Boolean(deleteModal.project)} onOpenChange={(open) => {
        if (!open) closeDeleteModal();
      }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除任务</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{deleteModal.project?.name}</strong> 吗？该任务的项目文件与对话记录将被永久删除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                deleteProject();
              }}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <>
                  <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  删除中...
                </>
              ) : (
                '删除任务'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 轻提示 */}
      {toast && (
        <div className="fixed bottom-4 right-4 z-50">
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 50, scale: 0.9 }}
          >
            <div className={`flex max-w-sm items-center gap-3 rounded-lg border px-6 py-4 shadow-lg backdrop-blur-lg ${
              toast.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-destructive/20 bg-destructive/10 text-destructive'
            }`}>
              {toast.type === 'success' ? (
                <svg className="h-5 w-5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="h-5 w-5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
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
