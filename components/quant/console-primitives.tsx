import type { ReactNode } from 'react';

export function formatCompactDate(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function consoleRawStatusClass(status?: string | null) {
  const normalized = String(status ?? '').toLowerCase();
  if (['success', 'passed', 'completed', 'healthy', 'ok', 'available', 'ready'].includes(normalized)) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (['warning', 'queued', 'needs_clarification', 'repairing', 'cancelled', 'skipped', 'degraded'].includes(normalized)) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  if (['failed', 'error', 'blocked'].includes(normalized)) {
    return 'border-red-200 bg-red-50 text-red-700';
  }
  if (['running', 'pending', 'planned'].includes(normalized)) {
    return 'border-blue-200 bg-blue-50 text-blue-700';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

export function ConsoleDetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-2.5 text-sm last:border-b-0">
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className="min-w-0 break-words text-right font-medium text-slate-900">{value}</span>
    </div>
  );
}

export function ConsoleStatCard({
  label,
  value,
  helper,
  icon,
}: {
  label: string;
  value: string | number;
  helper: string;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
          <p className="mt-1 truncate text-xs text-slate-500">{helper}</p>
        </div>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-700">
          {icon}
        </div>
      </div>
    </div>
  );
}

export function ConsolePanel({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-900">
          {icon}
          <h2 className="truncate">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
