export * from './project';
export * from './cli';
export * from './chat';
export * from './realtime';

// Modal / global settings types (moved from types/client/modal.ts)
export interface CreateProjectCLIOption {
  id: string; name: string; icon: string; description: string;
  models: Array<{ id: string; name: string; description?: string; supportsImages?: boolean; provider?: string; runtime?: string; external?: boolean }>;
  color: string; features: string[]; downloadUrl?: string; installCommand?: string; enabled?: boolean;
}
export interface CLIConfig { enabled?: boolean; model?: string; }
export interface GlobalSettings {
  apiKeys?: { anthropic?: string; github?: string; vercel?: string; supabase?: string };
  preferences?: { theme?: 'light' | 'dark' | 'system'; autoSave?: boolean };
  cli_settings?: { [cliId: string]: CLIConfig };
  default_cli?: string;
  fallback_enabled?: boolean;
}
