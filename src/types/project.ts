import type { CLIType } from './cli';
import type { TravelCapabilityId } from '@/lib/travel/capabilities';

export type ProjectStatus =
  | 'idle'
  | 'preview_running'
  | 'building'
  | 'initializing'
  | 'active'
  | 'failed'
  | 'running'
  | 'stopped'
  | 'error';

export interface ServiceConnection {
  connected: boolean;
  status: string;
  updatedAt?: string;
  metadata?: Record<string, unknown>;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  status?: ProjectStatus;
  previewUrl?: string | null;
  previewPort?: number | null;
  createdAt: string;
  updatedAt?: string;
  lastActiveAt?: string | null;
  lastMessageAt?: string | null;
  initialPrompt?: string | null;
  services?: {
    github?: ServiceConnection;
    supabase?: ServiceConnection;
    vercel?: ServiceConnection;
  };
  preferredCli?: CLIType | null;
  selectedModel?: string | null;
  fallbackEnabled?: boolean;
  travelCapabilityId?: TravelCapabilityId | null;
  /** @deprecated Legacy compatibility only; new code must use travelCapabilityId. */
  quantCapabilityId?: TravelCapabilityId | null;
}

export interface ProjectSettings {
  preferredCli: CLIType;
  fallbackEnabled: boolean;
  selectedModel?: string | null;
  travelCapabilityId?: TravelCapabilityId | null;
  /** @deprecated Legacy compatibility only; new code must use travelCapabilityId. */
  quantCapabilityId?: TravelCapabilityId | null;
}
