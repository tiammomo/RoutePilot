import {
  Braces,
  CheckCircle2,
  CircleDot,
  Database,
  FileCode2,
  Gauge,
  GitBranch,
  ListChecks,
  Loader2,
  MessageSquareText,
  PanelRightOpen,
  TerminalSquare,
  TriangleAlert,
  Wrench,
  XCircle,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  ConsoleDetailRow as DetailRow,
  consoleRawStatusClass as rawStatusClass,
  formatCompactDate as formatDate,
} from '@/components/quant/console-primitives';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import type { WorkspaceHealthStatus } from '@/lib/quant/workspace-health';
import type {
  GenerationStageId,
  GenerationTimelineEvent,
  GenerationTraceProject,
  GenerationTraceStatus,
} from '@/lib/quant/generation-observability';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

export type TraceDetailKind = 'queue' | 'state' | 'contracts' | 'visual' | 'plan' | 'tools';

export const healthStatusLabel: Record<WorkspaceHealthStatus, string> = {
  healthy: '健康',
  warning: '风险',
  failed: '失败',
  unknown: '待验证',
};

export const traceStatusLabel: Record<GenerationTraceStatus, string> = {
  success: '正常',
  warning: '风险',
  error: '阻断',
  pending: '运行中',
  unknown: '未知',
};

export const traceStageLabel: Record<GenerationStageId, string> = {
  request: '请求',
  planning: '规划',
  data: '数据',
  tooling: '工具',
  artifact: '产物',
  validation: '验证',
  repair: '修复',
  completion: '完成',
  system: '系统',
};

export function healthStatusClass(status: WorkspaceHealthStatus) {
  if (status === 'healthy') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'warning') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (status === 'failed') return 'border-red-200 bg-red-50 text-red-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

export function traceStatusClass(status: GenerationTraceStatus) {
  if (status === 'success') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'warning') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (status === 'error') return 'border-red-200 bg-red-50 text-red-700';
  if (status === 'pending') return 'border-blue-200 bg-blue-50 text-blue-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

export function traceDotClass(status: GenerationTraceStatus) {
  if (status === 'success') return 'bg-emerald-500';
  if (status === 'warning') return 'bg-amber-500';
  if (status === 'error') return 'bg-red-500';
  if (status === 'pending') return 'bg-blue-500';
  return 'bg-slate-300';
}

export function healthStatusIcon(status: WorkspaceHealthStatus) {
  if (status === 'healthy') return <CheckCircle2 className="h-4 w-4" />;
  if (status === 'failed') return <XCircle className="h-4 w-4" />;
  if (status === 'warning') return <TriangleAlert className="h-4 w-4" />;
  return <Gauge className="h-4 w-4" />;
}

export function traceStatusIcon(status: GenerationTraceStatus) {
  if (status === 'success') return <CheckCircle2 className="h-4 w-4" />;
  if (status === 'warning') return <TriangleAlert className="h-4 w-4" />;
  if (status === 'error') return <XCircle className="h-4 w-4" />;
  if (status === 'pending') return <Loader2 className="h-4 w-4 animate-spin" />;
  return <CircleDot className="h-4 w-4" />;
}

export function traceStageIcon(stage: GenerationStageId) {
  if (stage === 'request') return <MessageSquareText className="h-4 w-4" />;
  if (stage === 'planning') return <GitBranch className="h-4 w-4" />;
  if (stage === 'data') return <Database className="h-4 w-4" />;
  if (stage === 'tooling') return <TerminalSquare className="h-4 w-4" />;
  if (stage === 'artifact') return <FileCode2 className="h-4 w-4" />;
  if (stage === 'validation') return <ListChecks className="h-4 w-4" />;
  if (stage === 'repair') return <Wrench className="h-4 w-4" />;
  if (stage === 'completion') return <CheckCircle2 className="h-4 w-4" />;
  return <Gauge className="h-4 w-4" />;
}

function sourceLabel(source: GenerationTimelineEvent['source']) {
  if (source === 'user_request') return '请求';
  if (source === 'message') return '消息';
  if (source === 'tool_usage') return '工具';
  if (source === 'workspace_event') return '事件';
  if (source === 'run_plan') return '计划';
  if (source === 'validation') return '验证';
  return '修复';
}

function artifactUrl(projectId: string, artifactPath: string) {
  return `${API_BASE}/api/projects/${projectId}/artifact?path=${encodeURIComponent(artifactPath)}`;
}

export function TimelineItem({ event }: { event: GenerationTimelineEvent }) {
  return (
    <div className="relative pl-8">
      <div className={`absolute left-0 top-2 h-3 w-3 rounded-full ring-4 ring-white ${traceDotClass(event.status)}`} />
      <div className="absolute bottom-[-18px] left-[5px] top-6 w-px bg-slate-200" />
      <div className="rounded-md border border-slate-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1 text-sm font-semibold text-slate-950">
                {traceStageIcon(event.stage)}
                {event.title}
              </span>
              <Badge variant="outline" className={traceStatusClass(event.status)}>
                {traceStatusLabel[event.status]}
              </Badge>
              <Badge variant="outline" className="bg-white text-slate-500">
                {sourceLabel(event.source)}
              </Badge>
            </div>
            <p className="mt-2 break-words text-sm leading-6 text-slate-600">{event.summary}</p>
          </div>
          <span className="shrink-0 text-xs text-slate-500">{formatDate(event.timestamp)}</span>
        </div>
        {(event.artifactPath || event.requestId) && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
            {event.requestId && <span className="max-w-full break-all rounded bg-slate-50 px-2 py-1">run {event.requestId}</span>}
            {event.artifactPath && <span className="max-w-full break-all rounded bg-slate-50 px-2 py-1">{event.artifactPath}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export function TraceProjectListItem({
  project,
  active,
  onSelect,
}: {
  project: GenerationTraceProject;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-md border px-3 py-3 text-left transition-colors ${
        active ? 'border-blue-200 bg-blue-50' : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950">{project.name}</p>
          <p className="mt-1 truncate text-xs text-slate-500">{project.repoPath}</p>
        </div>
        <Badge variant="outline" className={`${traceStatusClass(project.trace.status)} shrink-0`}>
          {traceStatusLabel[project.trace.status]}
        </Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">{project.trace.summary}</p>
      <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500">
        <span>{traceStageLabel[project.trace.activeStage]}</span>
        <span>{project.trace.eventCount} 事件</span>
      </div>
    </button>
  );
}

export function DetailButton({
  label,
  onClick,
}: {
  label?: string;
  onClick: () => void;
}) {
  return (
    <Button type="button" variant="outline" size="sm" onClick={onClick}>
      <PanelRightOpen className="h-4 w-4" />
      {label ?? '详情'}
    </Button>
  );
}

export function TraceDetailSheet({
  project,
  kind,
  open,
  onOpenChange,
}: {
  project: GenerationTraceProject | null;
  kind: TraceDetailKind;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const titleMap: Record<TraceDetailKind, string> = {
    queue: '生成队列',
    state: '状态机',
    contracts: '产物契约',
    visual: '视觉验收',
    plan: '运行计划',
    tools: '工具画像',
  };

  const description = project ? `${project.name} · ${project.repoPath}` : '未选择工作空间';

  const renderQueue = () => {
    if (!project) return null;
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <DetailRow label="活跃请求" value={project.generationQueue.activeRequestId ?? '-'} />
          <DetailRow label="运行中" value={project.generationQueue.running} />
          <DetailRow label="排队" value={project.generationQueue.queued} />
          <DetailRow label="失败记录" value={project.generationQueue.failed} />
          <DetailRow label="更新时间" value={formatDate(project.generationQueue.updatedAt)} />
          <DetailRow label="产物路径" value={project.generationQueue.path} />
        </div>
        <div className="space-y-3">
          {project.generationQueue.items.length ? (
            project.generationQueue.items.map((item) => (
              <div key={item.requestId} className="rounded-md border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="max-w-full truncate text-sm font-semibold text-slate-950">{item.requestId}</p>
                  <Badge variant="outline" className={rawStatusClass(item.status)}>{item.status}</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600">{item.instructionPreview || '-'}</p>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <span>CLI：{item.cliPreference ?? '-'}</span>
                  <span>模型：{item.selectedModel ?? '-'}</span>
                  <span>排队：{formatDate(item.queuedAt)}</span>
                  <span>开始：{formatDate(item.startedAt)}</span>
                  <span>完成：{formatDate(item.completedAt)}</span>
                </div>
                {item.errorMessage && (
                  <div className="mt-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700">
                    {item.errorMessage}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500">暂无队列记录。</div>
          )}
        </div>
      </div>
    );
  };

  const renderState = () => {
    if (!project) return null;
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <DetailRow label="运行状态" value={project.generationState?.status ?? '-'} />
          <DetailRow label="当前步骤" value={project.generationState?.activeStep ?? '-'} />
          <DetailRow
            label="修复次数"
            value={
              project.generationState
                ? `${project.generationState.repairAttemptCount}/${project.generationState.maxRepairAttempts}`
                : '-'
            }
          />
          <DetailRow label="更新时间" value={formatDate(project.generationState?.updatedAt ?? null)} />
          <DetailRow label="产物路径" value={project.generationState?.path ?? '-'} />
        </div>
        {project.generationState?.error && (
          <div className="rounded-md border border-red-100 bg-red-50 p-4 text-sm text-red-700">
            <p className="font-semibold">{project.generationState.error.step}</p>
            <p className="mt-1 leading-6">{project.generationState.error.message}</p>
          </div>
        )}
        <div className="space-y-3">
          {project.generationState?.steps.length ? (
            project.generationState.steps.map((step) => (
              <div key={step.id} className="rounded-md border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-950">{step.label}</p>
                  <Badge variant="outline" className={rawStatusClass(step.status)}>{step.status}</Badge>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{step.summary || '-'}</p>
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>开始：{formatDate(step.startedAt)}</span>
                  <span>完成：{formatDate(step.completedAt)}</span>
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500">暂无状态机步骤。</div>
          )}
        </div>
      </div>
    );
  };

  const renderContracts = () => {
    if (!project) return null;
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <DetailRow label="状态" value={traceStatusLabel[project.artifactContracts.status]} />
          <DetailRow label="失败" value={project.artifactContracts.failedChecks} />
          <DetailRow label="警告" value={project.artifactContracts.warningChecks} />
          <DetailRow label="更新时间" value={formatDate(project.artifactContracts.updatedAt)} />
          <DetailRow label="产物路径" value={project.artifactContracts.path} />
        </div>
        <div className="space-y-3">
          {project.artifactContracts.checks.length ? (
            project.artifactContracts.checks.map((check) => (
              <div key={check.id} className="rounded-md border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-950">{check.label}</p>
                    <p className="mt-1 truncate font-mono text-xs text-slate-500">{check.path}</p>
                  </div>
                  <Badge variant="outline" className={rawStatusClass(check.status)}>{check.status}</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600">{check.summary}</p>
                {check.details && <p className="mt-2 text-xs leading-5 text-slate-500">{check.details}</p>}
                {check.required && <Badge variant="outline" className="mt-3 bg-white text-slate-500">必需</Badge>}
              </div>
            ))
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500">暂无契约检查。</div>
          )}
        </div>
      </div>
    );
  };

  const renderVisual = () => {
    if (!project) return null;
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <DetailRow label="状态" value={traceStatusLabel[project.visualValidation.status]} />
          <DetailRow label="失败" value={project.visualValidation.failedChecks} />
          <DetailRow label="警告" value={project.visualValidation.warningChecks} />
          <DetailRow label="截图" value={project.visualValidation.screenshots.length} />
          <DetailRow label="更新时间" value={formatDate(project.visualValidation.updatedAt)} />
          <DetailRow label="预览地址" value={project.visualValidation.previewUrl ?? '-'} />
        </div>
        {(project.visualValidation.failures.length > 0 || project.visualValidation.warnings.length > 0) && (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border border-red-100 bg-red-50 p-4">
              <p className="text-sm font-semibold text-red-700">阻断项</p>
              <div className="mt-2 space-y-2 text-sm leading-6 text-red-700">
                {project.visualValidation.failures.length ? project.visualValidation.failures.map((item) => <p key={item}>{item}</p>) : <p>-</p>}
              </div>
            </div>
            <div className="rounded-md border border-amber-100 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-700">警告</p>
              <div className="mt-2 space-y-2 text-sm leading-6 text-amber-700">
                {project.visualValidation.warnings.length ? project.visualValidation.warnings.map((item) => <p key={item}>{item}</p>) : <p>-</p>}
              </div>
            </div>
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {project.visualValidation.viewports.length ? (
            project.visualValidation.viewports.map((viewport) => (
              <div key={viewport.id} className="rounded-md border border-slate-200 bg-white p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-950">{viewport.id}</p>
                    <p className="text-xs text-slate-500">{viewport.width} x {viewport.height}</p>
                  </div>
                  <Badge variant="outline" className={rawStatusClass(viewport.status)}>{viewport.status}</Badge>
                </div>
                <a href={artifactUrl(project.id, viewport.screenshotPath)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-md border border-slate-200 bg-slate-50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={artifactUrl(project.id, viewport.screenshotPath)} alt={`${viewport.id} 截图`} className="h-64 w-full object-contain" />
                </a>
                {(viewport.failures.length > 0 || viewport.warnings.length > 0) && (
                  <div className="mt-3 space-y-2 text-xs leading-5 text-slate-600">
                    {viewport.failures.map((item) => <p key={item} className="text-red-700">{item}</p>)}
                    {viewport.warnings.map((item) => <p key={item} className="text-amber-700">{item}</p>)}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500 md:col-span-2">暂无视觉验收截图。</div>
          )}
        </div>
      </div>
    );
  };

  const renderPlan = () => {
    if (!project) return null;
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <DetailRow label="状态" value={project.runPlan.status ?? '-'} />
          <DetailRow label="请求能力" value={project.runPlan.requestedCapabilityId ?? '-'} />
          <DetailRow label="执行能力" value={project.runPlan.executionCapabilityId ?? '-'} />
          <DetailRow label="标的" value={project.runPlan.symbols.length ? project.runPlan.symbols.join('、') : '-'} />
          <DetailRow label="更新时间" value={formatDate(project.runPlan.updatedAt)} />
        </div>
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-950">预期产物</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {project.runPlan.expectedArtifacts.length ? (
              project.runPlan.expectedArtifacts.map((artifact) => (
                <Badge key={artifact} variant="outline" className="bg-slate-50 text-slate-600">{artifact}</Badge>
              ))
            ) : (
              <span className="text-sm text-slate-500">-</span>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderTools = () => {
    if (!project) return null;
    return (
      <div className="space-y-3">
        {project.topTools.length ? (
          project.topTools.map((tool) => (
            <div key={tool.name} className="rounded-md border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-semibold text-slate-950">{tool.name}</p>
                <span className="text-lg font-semibold text-slate-950">{tool.count}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                <span>{tool.errorCount} 错误</span>
                <span>平均 {tool.averageDurationMs ?? '-'}ms</span>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500">暂无工具调用记录。</div>
        )}
      </div>
    );
  };

  const content = (() => {
    if (kind === 'queue') return renderQueue();
    if (kind === 'state') return renderState();
    if (kind === 'contracts') return renderContracts();
    if (kind === 'visual') return renderVisual();
    if (kind === 'plan') return renderPlan();
    return renderTools();
  })();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full max-w-[92vw] flex-col bg-slate-50 p-0 sm:max-w-[760px]">
        <SheetHeader className="border-b border-slate-200 bg-white px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-base">
            <Braces className="h-4 w-4 text-blue-700" />
            {titleMap[kind]}
          </SheetTitle>
          <SheetDescription className="break-all text-xs">{description}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {content}
        </div>
      </SheetContent>
    </Sheet>
  );
}
