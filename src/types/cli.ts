import { CLAUDE_MODEL_DEFINITIONS } from '@/lib/constants/cliModels';

/**
 * Frontend CLI Type Definitions (claude-only variant)
 */

export type CLIType = 'claude';

export interface CLIModel {
  id: string;
  name: string;
  description?: string;
  supportsImages?: boolean;
  provider?: string;
  runtime?: string;
  external?: boolean;
}

export interface CLIOption {
  id: CLIType;
  name: string;
  description: string;
  icon?: string;
  available: boolean;
  configured: boolean;
  enabled?: boolean;
  models?: CLIModel[];
  color?: string;
  brandColor?: string;
  downloadUrl?: string;
  installCommand?: string;
  features?: string[];
}

export type CLIStatusEntry = {
  installed: boolean;
  checking: boolean;
  version?: string;
  error?: string;
  available?: boolean;
  configured?: boolean;
  models?: string[];
};

export type CLIStatus = Record<string, CLIStatusEntry>;

export interface CLIPreference {
  preferredCli: CLIType;
  fallbackEnabled: boolean;
  selectedModel?: string;
}

export const CLI_OPTIONS: CLIOption[] = [
  {
    id: 'claude',
    name: 'Claude Code',
    description: 'Claude Code runtime with Anthropic-compatible model providers',
    icon: '/claude.png',
    available: true,
    configured: true,
    enabled: true,
    color: 'from-orange-500 to-red-600',
    brandColor: '#DE7356',
    downloadUrl: 'https://docs.anthropic.com/en/docs/claude-code/overview',
    installCommand: 'npm install -g @anthropic-ai/claude-code',
    features: ['Anthropic-compatible runtime', 'External model routing', 'Code generation'],
    models: CLAUDE_MODEL_DEFINITIONS.map(({ id, name, description, supportsImages, provider, runtime, external }) => ({
      id,
      name,
      description,
      supportsImages,
      provider,
      runtime,
      external,
    })),
  },
];
