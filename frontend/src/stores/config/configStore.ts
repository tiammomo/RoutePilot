import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { ModelInfo } from '@/types';
import { apiService } from '@/services/api';
import { logger } from '@/utils/logger';

// 默认模型 - 快速加载，无需等待 API
const DEFAULT_MODELS: ModelInfo[] = [
  {
    model_id: 'minimax-m2-5',
    name: 'MiniMax M2.5',
    provider: 'anthropic',
    model: 'MiniMax-M2.5'
  }
];

interface ConfigState {
  // API 配置
  apiBase: string;
  setApiBase: (base: string) => void;

  // 模型配置 - 立即使用默认值
  availableModels: ModelInfo[];
  currentModelId: string | null;
  loadingModels: boolean;
  loadModels: () => Promise<void>;
  setCurrentModelId: (modelId: string) => Promise<void>;
}

export const useConfigStore = create<ConfigState>()(
  devtools(
    persist(
      (set, get) => ({
        apiBase:
          typeof window !== 'undefined'
            ? window.ENV?.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:38000'
            : 'http://localhost:38000',

        // 立即使用默认模型，无需等待
        availableModels: DEFAULT_MODELS,
        currentModelId: 'minimax-m2-5',
        loadingModels: false,

        setApiBase: (apiBase) =>
          set({ apiBase }, false, 'config/setApiBase'),

        loadModels: async () => {
          set({ loadingModels: true }, false, 'config/loadModels/start');
          try {
            const data = await apiService.getAvailableModels();
            if (data.success && data.models.length > 0) {
              // 成功获取后更新模型列表
              const currentId = get().currentModelId;
              const modelExists = data.models.some(m => m.model_id === currentId);
              set(
                {
                  availableModels: data.models,
                  currentModelId: modelExists ? currentId : data.models[0].model_id,
                  loadingModels: false,
                },
                false,
                'config/loadModels/success'
              );
            } else {
              // API 返回空列表，保持默认模型
              set({ loadingModels: false }, false, 'config/loadModels/empty');
            }
          } catch (error) {
            // 加载失败，保持默认模型
            logger.warn('加载模型列表失败，使用默认模型');
            set({ loadingModels: false }, false, 'config/loadModels/error');
          }
        },

        setCurrentModelId: async (modelId) => {
          const { currentModelId } = get();
          if (currentModelId === modelId) return;

          set({ currentModelId: modelId }, false, 'config/setCurrentModelId');

          try {
            const { useSessionStore } = await import('@/stores/session/sessionStore');
            const { currentSessionId } = useSessionStore.getState();
            if (currentSessionId) {
              await apiService.setSessionModel(currentSessionId, modelId);
            }
          } catch (error) {
            logger.error('设置会话模型失败:', error);
          }
        },
      }),
      {
        name: 'config-storage',
        partialize: (state) => ({
          apiBase: state.apiBase,
          currentModelId: state.currentModelId,
        }),
      }
    ),
    { name: 'ConfigStore' }
  )
);
