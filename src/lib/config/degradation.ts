export type DegradationMode = 'auto' | 'strict' | 'offline';

export interface ComponentDegradationConfig {
  enabled: boolean;
  required: boolean;
}

export interface RuntimeDegradationConfig {
  mode: DegradationMode;
  components: {
    database: ComponentDegradationConfig;
    marketApi: ComponentDegradationConfig;
    observability: ComponentDegradationConfig;
    redis: ComponentDegradationConfig;
  };
}

const FALSE_VALUES = new Set(['0', 'false', 'no', 'off', 'disabled']);
const TRUE_VALUES = new Set(['1', 'true', 'yes', 'on', 'enabled']);

function normalizeMode(value: string | undefined): DegradationMode {
  const normalized = value?.trim().toLowerCase();
  if (normalized === 'strict' || normalized === 'offline') return normalized;
  return 'auto';
}

function envFlag(name: string, fallback: boolean): boolean {
  const value = process.env[name]?.trim().toLowerCase();
  if (!value) return fallback;
  if (FALSE_VALUES.has(value)) return false;
  if (TRUE_VALUES.has(value)) return true;
  return fallback;
}

export function getRuntimeDegradationConfig(): RuntimeDegradationConfig {
  const mode = normalizeMode(process.env.QUANTPILOT_DEGRADATION_MODE);
  const offline = mode === 'offline';
  const strict = mode === 'strict';

  return {
    mode,
    components: {
      database: {
        enabled: envFlag('QUANTPILOT_DATABASE_ENABLED', true),
        required: offline ? false : envFlag('QUANTPILOT_DATABASE_REQUIRED', true),
      },
      marketApi: {
        enabled: offline ? false : envFlag('QUANTPILOT_MARKET_API_ENABLED', true),
        required: !offline && envFlag('QUANTPILOT_MARKET_API_REQUIRED', strict),
      },
      observability: {
        enabled: offline ? false : envFlag('QUANTPILOT_OBSERVABILITY_ENABLED', true),
        required: !offline && envFlag('QUANTPILOT_OBSERVABILITY_REQUIRED', strict),
      },
      redis: {
        enabled: offline ? false : envFlag('QUANTPILOT_REDIS_CACHE_ENABLED', true),
        required: !offline && envFlag('QUANTPILOT_REDIS_REQUIRED', strict),
      },
    },
  };
}

export function componentUnavailableStatus(component: ComponentDegradationConfig): 'failed' | 'warning' | 'unknown' {
  if (!component.enabled) return 'unknown';
  return component.required ? 'failed' : 'warning';
}

export function componentUnavailableSummary(component: ComponentDegradationConfig, label: string): string {
  if (!component.enabled) return `${label} 已按降级配置停用`;
  return component.required ? `${label} 不可用，当前配置要求必须可用` : `${label} 不可用，已进入降级模式`;
}

export function componentModeSummary(component: ComponentDegradationConfig): 'disabled' | 'required' | 'optional' {
  if (!component.enabled) return 'disabled';
  return component.required ? 'required' : 'optional';
}

export function isDegradedMode(config = getRuntimeDegradationConfig()): boolean {
  return config.mode !== 'strict';
}
