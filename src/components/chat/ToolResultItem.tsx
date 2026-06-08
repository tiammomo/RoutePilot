import React, { useId, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BookOpen,
  CheckSquare,
  Code2,
  FileText,
  Search,
  Terminal,
  Wrench,
  X,
} from 'lucide-react';
import { toRelativePath } from '@/lib/utils/path';

type ToolAction = 'Edited' | 'Created' | 'Read' | 'Deleted' | 'Generated' | 'Searched' | 'Executed';

interface ToolResultItemProps {
  action: ToolAction;
  filePath?: string;
  content?: string;
  toolName?: string;
  input?: string;
  output?: string;
  summary?: string;
  status?: 'executing' | 'done';
  isExpanded?: boolean;
  onToggle?: (nextExpanded: boolean) => void;
}

const toolNameFromAction: Record<ToolAction, string> = {
  Edited: 'Edit',
  Created: 'Write',
  Read: 'Read',
  Deleted: 'Delete',
  Generated: 'Todo List',
  Searched: 'Glob',
  Executed: 'Bash',
};

const normalizeToolName = (toolName: string | undefined, action: ToolAction) => {
  const raw = (toolName || toolNameFromAction[action] || 'Tool').trim();
  const lower = raw.toLowerCase();

  if (/^data-[a-z0-9-]+$/i.test(raw)) return raw;
  if (lower === 'skill' || lower === 'tool' || lower === 'tool_use') return 'Skill';
  if (lower.includes('glob')) return 'Glob';
  if (lower.includes('grep')) return 'Grep';
  if (lower.includes('bash') || lower.includes('shell') || lower.includes('run')) return 'Bash';
  if (lower.includes('read')) return 'Read';
  if (lower.includes('write') || lower.includes('create')) return 'Write';
  if (lower.includes('edit') || lower.includes('patch')) return 'Edit';
  if (lower.includes('todo') || lower.includes('plan')) return 'Todo List';
  if (lower.includes('search') || lower.includes('list') || lower === 'ls') return 'Glob';

  return raw
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
};

const getToolIcon = (toolName: string, action: ToolAction) => {
  const lower = toolName.toLowerCase();
  const className = 'h-3.5 w-3.5 text-slate-500';

  if (lower.includes('skill')) return <Wrench className={className} />;
  if (lower.includes('glob') || lower.includes('grep') || action === 'Searched') return <Search className={className} />;
  if (lower.includes('bash') || action === 'Executed') return <Terminal className={className} />;
  if (lower.includes('read') || action === 'Read') return <BookOpen className={className} />;
  if (lower.includes('todo') || lower.includes('plan') || action === 'Generated') return <CheckSquare className={className} />;
  if (action === 'Edited' || action === 'Created') return <Code2 className={className} />;
  return <FileText className={className} />;
};

const normalizeDisplayTarget = (value: string | undefined) => {
  if (!value) return '';
  const trimmed = value.trim();
  if (!trimmed || trimmed === 'Tool action' || /^Tool:\s*/i.test(trimmed)) return '';
  return toRelativePath(trimmed);
};

const tryParseJson = (value?: string): unknown => {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed || (!trimmed.startsWith('{') && !trimmed.startsWith('['))) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
};

const pickRecordString = (record: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  }
  return '';
};

const extractSkillNameFromJson = (value: unknown): string => {
  if (!value || typeof value !== 'object') return '';
  const record = value as Record<string, unknown>;
  const direct = pickRecordString(record, ['skill', 'skillName', 'skill_name', 'skillId', 'skill_id']);
  if (direct) return direct;
  const nested = record.args ?? record.input ?? record.toolInput ?? record.tool_input;
  return extractSkillNameFromJson(nested);
};

const describeCurlCommand = (command: string) => {
  const lower = command.toLowerCase();
  if (!lower.includes('curl')) return '';
  if (lower.includes('/api/v1/travel/')) return '调用本地旅游接口获取路线、POI、餐厅或通勤数据。';
  return '调用本地接口获取任务数据。';
};

const describeFileTarget = (target: string, action: ToolAction) => {
  const normalized = target.replaceAll('\\', '/');
  if (!normalized) return '';
  if (normalized.endsWith('.travelpilot/run_plan.json')) return '记录本次旅游规划的区域、偏好、数据需求和验收项。';
  if (normalized.endsWith('.travelpilot/events.jsonl')) return '追加可见执行事件，便于复盘每个阶段。';
  if (normalized.endsWith('evidence/sources.json')) return '记录数据来源、接口、抓取时间和来源说明。';
  if (normalized.endsWith('evidence/data_quality.json')) return '记录数据质量、缺失字段、异常和限制。';
  if (normalized.endsWith('data_file/final/itinerary-data.json')) return '写入最终路线数据，页面将基于它渲染方案。';
  if (normalized.endsWith('app/page.tsx')) return action === 'Read' ? '读取页面代码，确认当前渲染结构。' : '生成或更新旅游路线可视化页面。';
  if (normalized.endsWith('app/globals.css')) return action === 'Read' ? '读取页面样式，确认布局基础。' : '更新页面样式，保证布局和响应式体验。';
  if (normalized.endsWith('next.config.js')) return '检查 Next.js 配置，确保预览和构建链路可用。';
  if (normalized.endsWith('package.json')) return '检查项目依赖和脚本，确保 build/dev 可执行。';
  return '';
};

const isLowValueText = (value?: string) => {
  const text = value?.trim();
  if (!text) return true;
  return (
    /^.+\s+已返回结果[，,]?\s*正在进入下一步处理。?$/i.test(text) ||
    /已返回结果[，,]?\s*正在进入下一步处理。?$/i.test(text) ||
    text === '读取项目文件，确认后续修改依据。' ||
    text === '写入项目产物，推进当前分析阶段。' ||
    text === '工具返回异常，需要根据错误信息调整后续步骤。' ||
    /^\(?Bash completed with no output\)?$/i.test(text) ||
    /^Using tool:\s*/i.test(text)
  );
};

const isLowValueCommand = (value?: string) => {
  const command = value?.trim();
  if (!command) return false;
  return (
    /^ls(\s|$)/i.test(command) ||
    /^pwd(\s|$)/i.test(command) ||
    /^mkdir\s+-p(\s|$)/i.test(command) ||
    /^find\s+.+\s+-maxdepth\s+\d+/i.test(command) ||
    /^test\s+-[efd]\s+/i.test(command) ||
    /^echo\s+/i.test(command) ||
    /^whoami(\s|$)/i.test(command)
  );
};

const countArrayValue = (value: unknown): number => {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
  const keys = ['items', 'data', 'rows', 'pois', 'restaurants', 'plans', 'routes', 'edges'];
    for (const key of keys) {
      if (Array.isArray(record[key])) return record[key].length;
    }
  }
  return 0;
};

const summarizeJsonOutput = (value: unknown): string => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '';
  const record = value as Record<string, unknown>;
  const label = pickRecordString(record, ['name', 'title', 'area', 'city']);
  const itemCount = countArrayValue(record.items ?? record.data ?? record.rows ?? record.pois ?? record.restaurants ?? record.plans ?? record.routes);
  if (itemCount > 0) {
    return `接口返回${label ? ` ${label}` : ''} ${itemCount} 条数据。`;
  }

  const status = pickRecordString(record, ['status']);
  if (status === 'ok' || status === 'success') {
    return '数据质量或验证结果通过。';
  }

  return '';
};

const buildToolSummary = ({
  displayToolName,
  action,
  target,
  input,
  output,
  summary,
  status,
}: {
  displayToolName: string;
  action: ToolAction;
  target: string;
  input?: string;
  output?: string;
  summary?: string;
  status: 'executing' | 'done';
}) => {
  const parsedInput = tryParseJson(input);
  const parsedOutput = tryParseJson(output);
  const trimmedSummary = summary?.trim();
  if (trimmedSummary && !isLowValueText(trimmedSummary)) return trimmedSummary;

  const outputSummary = summarizeJsonOutput(parsedOutput);
  if (outputSummary) return outputSummary;

  const skillName = extractSkillNameFromJson(parsedInput) || extractSkillNameFromJson(parsedOutput);
  const effectiveToolName = /^skill$/i.test(displayToolName) && skillName ? skillName : displayToolName;
  const lowerTool = effectiveToolName.toLowerCase();

  if (lowerTool.includes('travel')) return '执行旅游规划工具，推进路线、POI 或通勤数据处理。';

  const curlSummary = describeCurlCommand(target);
  if (curlSummary) return curlSummary;

  const fileSummary = describeFileTarget(target, action);
  if (fileSummary) return fileSummary;

  if (action === 'Generated') return '更新任务清单，记录当前完成度和下一步。';
  if (status === 'executing') return '工具正在执行，等待结果返回。';
  return '';
};

const DetailBlock = ({ title, value }: { title: string; value?: string }) => {
  if (!value) return null;

  return (
    <div>
      <div className="mb-2 text-xs font-semibold text-indigo-700">{title}</div>
      <pre className="max-h-[42vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-900">
        {value}
      </pre>
    </div>
  );
};

const ToolResultItem: React.FC<ToolResultItemProps> = ({
  action,
  filePath,
  content,
  toolName,
  input,
  output,
  summary,
  status = 'done',
  isExpanded: controlledExpanded,
  onToggle,
}) => {
  const [uncontrolledExpanded, setUncontrolledExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'input' | 'output'>('output');
  const dialogTitleId = useId();
  const isControlled = typeof controlledExpanded === 'boolean';
  const isOpen = isControlled ? controlledExpanded : uncontrolledExpanded;
  const displayToolName = normalizeToolName(toolName, action);
  const displayTarget = normalizeDisplayTarget(filePath);
  const detailInput = input?.trim();
  const rawDetailOutput = (output || content)?.trim();
  const detailOutput = isLowValueText(rawDetailOutput) ? undefined : rawDetailOutput;
  const hasDetail = Boolean(detailInput || detailOutput);
  const toolSummary = buildToolSummary({
    displayToolName,
    action,
    target: displayTarget,
    input: detailInput,
    output: detailOutput,
    summary,
    status,
  });
  const genericToolWithoutTarget = ['Bash', 'Read', 'Write', 'Edit', 'Glob', 'Grep'].includes(displayToolName);

  if (
    status === 'done' &&
    genericToolWithoutTarget &&
    (!displayTarget || isLowValueCommand(displayTarget)) &&
    !toolSummary
  ) {
    return null;
  }

  const openDetails = () => {
    if (!hasDetail) return;
    setActiveTab(detailOutput ? 'output' : 'input');
    if (!isControlled) {
      setUncontrolledExpanded(true);
    }
    onToggle?.(true);
  };

  const closeDetails = () => {
    if (!isControlled) {
      setUncontrolledExpanded(false);
    }
    onToggle?.(false);
  };

  return (
    <div className="mb-1.5">
      <button
        type="button"
        className={`group flex max-w-full items-center gap-1.5 text-left text-sm leading-6 text-slate-800 ${
          hasDetail ? 'cursor-pointer hover:text-slate-950' : 'cursor-default'
        }`}
        onClick={openDetails}
        aria-haspopup={hasDetail ? 'dialog' : undefined}
        aria-expanded={hasDetail ? isOpen : undefined}
        disabled={!hasDetail}
      >
        <span className="text-slate-400">•</span>
        <span className="flex h-4 w-4 shrink-0 items-center justify-center">
          {getToolIcon(displayToolName, action)}
        </span>
        <span className="shrink-0 font-semibold text-slate-900">{displayToolName}</span>
        {status === 'executing' && (
          <span className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] leading-4 text-slate-600">
            executing...
          </span>
        )}
        {displayTarget && (
          <code
            className="min-w-0 max-w-[min(42rem,70vw)] truncate rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700 group-hover:bg-slate-200"
            title={displayTarget}
          >
            {displayTarget}
          </code>
        )}
      </button>
      {toolSummary && (
        <div className="ml-[3.05rem] mt-0.5 max-w-[min(46rem,76vw)] text-sm leading-6 text-slate-700">
          {toolSummary}
        </div>
      )}

      <AnimatePresence>
        {isOpen && hasDetail && (
          <motion.div
            className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeDetails}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-labelledby={dialogTitleId}
              className="flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl"
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
              onClick={(event: React.MouseEvent<HTMLDivElement>) => event.stopPropagation()}
            >
              <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-5">
                <h2 id={dialogTitleId} className="text-base font-semibold text-slate-950">
                  {displayToolName}
                </h2>
                <button
                  type="button"
                  onClick={closeDetails}
                  className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  aria-label="关闭工具详情"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="flex shrink-0 border-b border-slate-200 px-5">
                {(['input', 'output'] as const).map(tab => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`border-b-2 px-3 py-3 text-sm transition-colors ${
                      activeTab === tab
                        ? 'border-blue-600 font-medium text-blue-700'
                        : 'border-transparent text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    {tab === 'input' ? '输入' : '输出'}
                  </button>
                ))}
              </div>

              <div className="min-h-[260px] flex-1 space-y-5 overflow-auto px-5 py-5">
                {activeTab === 'input' ? (
                  <>
                    <DetailBlock title="args" value={detailInput} />
                    <div>
                      <div className="mb-2 text-xs font-semibold text-indigo-700">skill</div>
                      <div className="text-sm text-slate-900">{displayToolName}</div>
                    </div>
                  </>
                ) : detailOutput ? (
                  <DetailBlock title="output" value={detailOutput} />
                ) : (
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500">
                    暂无输出，工具可能仍在执行中。
                  </div>
                )}
              </div>

              <div className="flex shrink-0 justify-end border-t border-slate-100 px-5 py-4">
                <button
                  type="button"
                  onClick={closeDetails}
                  className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
                >
                  关闭
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ToolResultItem;
