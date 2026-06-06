"use client";
import { useEffect, useState, useRef, useCallback, useMemo, type ChangeEvent, type KeyboardEvent, type UIEvent } from 'react';
import { AnimatePresence } from 'framer-motion';
import { MotionDiv, MotionH3, MotionP, MotionButton } from '@/lib/motion';
import { useRouter, useSearchParams, useParams, usePathname } from 'next/navigation';
import dynamic from 'next/dynamic';
import { FaCode, FaDesktop, FaMobileAlt, FaPlay, FaStop, FaSync, FaCog, FaRocket, FaFolder, FaFolderOpen, FaFile, FaFileCode, FaCss3Alt, FaHtml5, FaJs, FaReact, FaPython, FaDocker, FaGitAlt, FaMarkdown, FaDatabase, FaPhp, FaJava, FaRust, FaVuejs, FaLock, FaHome, FaChevronUp, FaChevronRight, FaChevronDown, FaArrowLeft, FaArrowRight, FaRedo } from 'react-icons/fa';
import { SiTypescript, SiGo, SiRuby, SiSvelte, SiJson, SiYaml, SiCplusplus } from 'react-icons/si';
import { VscJson } from 'react-icons/vsc';
import ChatLog from '@/components/chat/ChatLog';
import { ProjectSettings } from '@/components/settings/ProjectSettings';
import ChatInput from '@/components/chat/ChatInput';
import { ChatErrorBoundary } from '@/components/ErrorBoundary';
import { useUserRequests } from '@/hooks/useUserRequests';
import { useGlobalSettings } from '@/contexts/GlobalSettingsContext';
import { getDefaultModelForCli, getModelDisplayName } from '@/lib/constants/cliModels';
import {
  ACTIVE_CLI_BRAND_COLORS,
  ACTIVE_CLI_IDS,
  ACTIVE_CLI_MODEL_OPTIONS,
  ACTIVE_CLI_NAME_MAP,
  DEFAULT_ACTIVE_CLI,
  buildActiveModelOptions,
  normalizeModelForCli,
  sanitizeActiveCli,
  type ActiveCliId,
  type ActiveModelOption,
} from '@/lib/utils/cliOptions';

// No longer loading ProjectSettings (managed by global settings on main page)

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

const assistantBrandColors = ACTIVE_CLI_BRAND_COLORS;

const CLI_LABELS = ACTIVE_CLI_NAME_MAP;

const CLI_ORDER = ACTIVE_CLI_IDS;

const VISIBLE_PROCESS_INSTRUCTIONS = `

请默认使用中文输出可见的执行过程摘要。不要暴露隐藏推理链，只写用户可验证的任务拆解、数据路径、工具动作和执行状态。

请在正式执行或回答前，先用如下格式输出：
### 任务拆解
| 维度 | 初步识别 | 状态 |
| --- | --- | --- |
| 出行区域 | 北京城区、商圈、景区或用户指定范围 | 明确/需确认 |
| 时间预算 | 半日/一日/多日、开始时间、用餐时间 | 明确/需确认 |
| 人群偏好 | 亲子、老人、低步行、低排队、拍照、美食等 | 明确/需确认 |
| 数据需求 | POI、餐厅、UGC 证据、通勤边、预算和风险提示 | 明确/需确认 |
| 输出形式 | 路线方案、时间轴、地图/卡片页面、数据文件或验证结果 | 明确/需确认 |

### 执行计划
1. 确认可直接推断的条件和需要补充的信息。
2. 按 .travelpilot/run_plan.json 规划 POI、餐厅、通勤和 UGC 数据路径。
3. 获取本地旅游数据后进行质量检查，再生成路线方案或可视化页面。
4. 做 build、HTTP、数据文件和核心路线字段检查。

### 当前状态
- 已明确：
- 待确认：
- 下一步：

后续执行过程中，请把工具调用组织成“阶段化执行日志”，不要只连续输出工具名：
- 每组 Bash/Read/Write/Edit 前后都用 1-2 句中文说明：本步目标、输入数据、得到的结果或下一步。
- 数据请求完成后说明接口、区域、记录数、关键字段和数据质量；不要只展示命令。
- 写入文件后说明文件用途，例如 run_plan、sources、data_quality、itinerary-data、页面代码分别解决什么问题。
- 验证阶段逐项说明 build、HTTP 200、数据文件和路线字段检查结果。
- Todo List 要持续更新，失败或待处理项写明原因。
- 最终可视化页面和数据都准备完成后，再呈现或说明预览结果。`;

const appendVisibleProcessInstructions = (message: string) => {
  const travelProcessInstructions = `

Please handle this as a Beijing travel route planning task. Identify area, duration, budget, meal, low-queue, low-walk, elderly/family, and replan constraints, then use local POI/UGC data to generate an executable itinerary.

Focus on route options, timeline, lunch/coffee/entertainment labels, budget, total duration, estimated walking/transfer, UGC evidence, and risk notes. Distance and queue are static local estimates, not realtime navigation.`;
  if (message.includes('Beijing travel route planning task')) {
    return message;
  }
  return `${message}${travelProcessInstructions}`;
};

const sanitizeCli = (cli?: string | null) => sanitizeActiveCli(cli, DEFAULT_ACTIVE_CLI);

const sanitizeModel = (cli: string, model?: string | null) => normalizeModelForCli(cli, model, DEFAULT_ACTIVE_CLI);

function normalizeBudgetBreakdown(items: Array<{ label: string; value: number }>, totalBudget: number) {
  const total = Math.max(0, Math.round(Number(totalBudget || 0)));
  if (!total) return items.map((item) => ({ ...item, value: 0 }));
  const rawSum = items.reduce((sum, item) => sum + Math.max(0, Number(item.value || 0)), 0);
  if (rawSum <= 0) {
    return items.map((item, index) => ({ ...item, value: index === items.length - 1 ? total : 0 }));
  }
  let remaining = total;
  return items.map((item, index) => {
    const value = index === items.length - 1
      ? remaining
      : Math.min(remaining, Math.round((Math.max(0, Number(item.value || 0)) / rawSum) * total));
    remaining -= value;
    return { ...item, value };
  });
}

// Function to convert hex to CSS filter for tinting white images
// Since the original image is white (#FFFFFF), we can apply filters more accurately
const hexToFilter = (hex: string): string => {
  // For white source images, we need to invert and adjust
  const filters: { [key: string]: string } = {
    '#DE7356': 'brightness(0) saturate(100%) invert(52%) sepia(73%) saturate(562%) hue-rotate(336deg) brightness(95%) contrast(91%)',
    '#000000': 'brightness(0) saturate(100%)',
    '#11A97D': 'brightness(0) saturate(100%) invert(57%) sepia(30%) saturate(747%) hue-rotate(109deg) brightness(90%) contrast(92%)',
    '#1677FF': 'brightness(0) saturate(100%) invert(40%) sepia(86%) saturate(1806%) hue-rotate(201deg) brightness(98%) contrast(98%)',
  };
  return filters[hex] || filters['#DE7356'];
};

type Entry = { path: string; type: 'file'|'dir'; size?: number };
type ProjectStatus = 'initializing' | 'active' | 'failed';
type PreviewValidationState = 'unknown' | 'running' | 'passed' | 'failed';

type PreviewValidationRepairPlan = {
  status: 'needed';
  repairPlanPath?: string;
  steps?: Array<{
    checkId?: string;
    checkName?: string;
    summary?: string;
    actions?: string[];
  }>;
};

type CliStatusSnapshot = {
  available?: boolean;
  configured?: boolean;
  models?: string[];
};

type ModelOption = Omit<ActiveModelOption, 'cli'> & { cli: string; supportsImages?: boolean };

const buildModelOptions = (statuses: Record<string, CliStatusSnapshot>): ModelOption[] =>
  buildActiveModelOptions(statuses).map(option => ({
    ...option,
    cli: option.cli,
  }));

// TreeView component for VSCode-style file explorer
interface TreeViewProps {
  entries: Entry[];
  selectedFile: string;
  expandedFolders: Set<string>;
  folderContents: Map<string, Entry[]>;
  onToggleFolder: (path: string) => void;
  onSelectFile: (path: string) => void;
  onLoadFolder: (path: string) => Promise<void>;
  level: number;
  parentPath?: string;
  getFileIcon: (entry: Entry) => React.ReactElement;
}

function TreeView({ entries, selectedFile, expandedFolders, folderContents, onToggleFolder, onSelectFile, onLoadFolder, level, parentPath = '', getFileIcon }: TreeViewProps) {
  // Ensure entries is an array
  if (!entries || !Array.isArray(entries)) {
    return null;
  }

  // Group entries by directory
  const sortedEntries = [...entries].sort((a, b) => {
    // Directories first
    if (a.type === 'dir' && b.type === 'file') return -1;
    if (a.type === 'file' && b.type === 'dir') return 1;
    // Then alphabetical
    return a.path.localeCompare(b.path);
  });

  return (
    <>
      {sortedEntries.map((entry, index) => {
        // entry.path should already be the full path from API
        const fullPath = entry.path;
        let entryKey =
          fullPath && typeof fullPath === 'string' && fullPath.trim().length > 0
            ? fullPath.trim()
            : (entry as any)?.name && typeof (entry as any).name === 'string' && (entry as any).name.trim().length > 0
            ? `${parentPath || 'root'}::__named_${(entry as any).name.trim()}`
            : '';
        if (!entryKey || entryKey.trim().length === 0) {
          entryKey = `${parentPath || 'root'}::__entry_${level}_${index}_${entry.type}`;
        }
        const isExpanded = expandedFolders.has(fullPath);
        const indent = level * 8;

        return (
          <div key={entryKey}>
            <div
              className={`group flex items-center h-[22px] px-2 cursor-pointer ${
                selectedFile === fullPath
                  ? 'bg-blue-100 '
                  : 'hover:bg-slate-100 '
              }`}
              style={{ paddingLeft: `${8 + indent}px` }}
              onClick={async () => {
                if (entry.type === 'dir') {
                  // Load folder contents if not already loaded
                  if (!folderContents.has(fullPath)) {
                    await onLoadFolder(fullPath);
                  }
                  onToggleFolder(fullPath);
                } else {
                  onSelectFile(fullPath);
                }
              }}
            >
              {/* Chevron for folders */}
              <div className="w-4 flex items-center justify-center mr-0.5">
                {entry.type === 'dir' && (
                  isExpanded ?
                    <span className="w-2.5 h-2.5 text-slate-600 flex items-center justify-center"><FaChevronDown size={10} /></span> :
                    <span className="w-2.5 h-2.5 text-slate-600 flex items-center justify-center"><FaChevronRight size={10} /></span>
                )}
              </div>

              {/* Icon */}
              <span className="w-4 h-4 flex items-center justify-center mr-1.5">
                {entry.type === 'dir' ? (
                  isExpanded ?
                    <span className="text-amber-600 w-4 h-4 flex items-center justify-center"><FaFolderOpen size={16} /></span> :
                    <span className="text-amber-600 w-4 h-4 flex items-center justify-center"><FaFolder size={16} /></span>
                ) : (
                  getFileIcon(entry)
                )}
              </span>

              {/* File/Folder name */}
              <span className={`text-[13px] leading-[22px] ${
                selectedFile === fullPath ? 'text-blue-700 ' : 'text-slate-700 '
              }`} style={{ fontFamily: "'Segoe UI', Tahoma, sans-serif" }}>
                {level === 0 ? (entry.path.split('/').pop() || entry.path) : (entry.path.split('/').pop() || entry.path)}
              </span>
            </div>

            {/* Render children if expanded */}
            {entry.type === 'dir' && isExpanded && folderContents.has(fullPath) && (
              <TreeView
                entries={folderContents.get(fullPath) || []}
                selectedFile={selectedFile}
                expandedFolders={expandedFolders}
                folderContents={folderContents}
                onToggleFolder={onToggleFolder}
                onSelectFile={onSelectFile}
                onLoadFolder={onLoadFolder}
                level={level + 1}
                parentPath={fullPath}
                getFileIcon={getFileIcon}
              />
            )}
          </div>
        );
      })}
    </>
  );
}

type TravelItineraryData = {
  parsed_request?: Record<string, any>;
  agent_trace?: Array<Record<string, any>>;
  session_state_summary?: Record<string, any>;
  planning_response?: {
    resolved_area?: string;
    route_mode?: string;
    day_count?: number;
    daily_itinerary?: Array<Record<string, any>>;
    evidence_summary?: Record<string, any>;
    generation_metrics?: Record<string, any>;
    proposals?: Array<Record<string, any>>;
    route_patch_summary?: Record<string, any>;
    constraint_judgement?: Record<string, any>;
    llm_rerank?: Record<string, any>;
    final_selected_proposal_id?: string;
    natural_language_explanation?: string;
    planning_advice?: Record<string, any>;
    wiki_retrieval?: Record<string, any>;
    route_draft?: Record<string, any>;
    validator_result?: Record<string, any>;
    repair_actions?: string[];
  };
};

function TravelItineraryPreview({ data }: { data: TravelItineraryData }) {
  const planning = data.planning_response ?? {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const dailyItinerary = Array.isArray(planning.daily_itinerary) ? planning.daily_itinerary : [];
  const primary = proposals[0];
  const stops = Array.isArray(primary?.pois) ? primary.pois : [];
  const naturalLanguageExplanation = String(planning.natural_language_explanation || '');
  const wikiHits = Array.isArray(planning.wiki_retrieval?.hits) ? planning.wiki_retrieval.hits.slice(0, 5) : [];
  const routePatchSummary = planning.route_patch_summary;
  const selectedReasons = Array.isArray(primary?.selection_reasons) ? primary.selection_reasons : [];
  const constraintJudgement =
    (primary?.constraint_judgement as Record<string, any> | undefined) ??
    (planning.constraint_judgement as Record<string, any> | undefined) ??
    null;
  const keptStops = Array.isArray(routePatchSummary?.kept) ? routePatchSummary.kept : [];
  const removedStops = Array.isArray(routePatchSummary?.removed) ? routePatchSummary.removed : [];
  const addedStops = Array.isArray(routePatchSummary?.added) ? routePatchSummary.added : [];
  const hasRouteDiff = keptStops.length > 0 || removedStops.length > 0 || addedStops.length > 0 || Boolean(routePatchSummary?.reordered);

  return (
    <div className="h-full w-full overflow-y-auto bg-[#f7f2ea] text-slate-950">
      <div className="mx-auto max-w-6xl px-8 py-10">
        <div className="rounded-[2rem] border border-[#e3d5bf] bg-white/90 p-8 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-[#b75f38]">Beijing Travel Agent</p>
              <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-950">
                {dailyItinerary.length > 1 ? '北京多日智能行程' : '北京智能路线方案'}
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
                已基于本地北京 POI、UGC 特征、价格、营业时间和坐标距离估算生成。排队风险为历史文本信号，转移时间不是实时导航。
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-2xl bg-[#173f35] px-4 py-3 text-white">
                <p className="text-xs text-white/70">区域</p>
                <p className="mt-1 font-bold">{planning.resolved_area || '北京'}</p>
              </div>
              <div className="rounded-2xl bg-[#e77b55] px-4 py-3 text-white">
                <p className="text-xs text-white/70">{dailyItinerary.length > 1 ? '天数' : '方案数'}</p>
                <p className="mt-1 font-bold">{dailyItinerary.length > 1 ? dailyItinerary.length : proposals.length}</p>
              </div>
              <div className="rounded-2xl bg-[#f1c979] px-4 py-3 text-slate-950">
                <p className="text-xs text-slate-600">10 秒内</p>
                <p className="mt-1 font-bold">{planning.generation_metrics?.within_10s ? '通过' : '待确认'}</p>
              </div>
            </div>
          </div>
        </div>

        {dailyItinerary.length > 1 ? (
          <div className="mt-6 grid gap-5">
            {dailyItinerary.map((day: Record<string, any>, index: number) => {
              const proposal = day.proposal || {};
              const dayStops = Array.isArray(proposal.pois) ? proposal.pois : [];
              return (
                <div key={day.day ?? index} className="rounded-[2rem] border border-[#e3d5bf] bg-white p-6 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-[#b75f38]">{day.title || `第 ${index + 1} 天`}</p>
                      <h2 className="mt-1 text-2xl font-black">{day.theme || proposal.display_title || '日程方案'}</h2>
                    </div>
                    <div className="flex gap-2 text-sm font-bold">
                      <span className="rounded-full bg-[#173f35] px-3 py-1.5 text-white">{proposal.total_route_duration_min ?? '-'} 分钟</span>
                      <span className="rounded-full bg-[#f1c979] px-3 py-1.5 text-slate-950">{proposal.total_budget_estimate ?? '-'} 元</span>
                    </div>
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {dayStops.map((stop: Record<string, any>, stopIndex: number) => (
                      <div key={`${stop.poi_id ?? stop.name}-${stopIndex}`} className="rounded-2xl border border-slate-100 bg-[#fffaf2] p-4">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#e77b55] text-sm font-black text-white">{stopIndex + 1}</span>
                          <span className="rounded-full bg-white px-2 py-1 text-xs font-semibold text-slate-600">{stop.arrival_time} - {stop.departure_time}</span>
                        </div>
                        <h3 className="mt-3 font-black">
                          {stop.name}
                          {stop.meal_slot === 'lunch' ? <span className="ml-2 rounded-full bg-[#f1c979] px-2 py-0.5 text-xs text-slate-950">午餐</span> : null}
                          {stop.meal_slot === 'snack' ? <span className="ml-2 rounded-full bg-[#ffe7c2] px-2 py-0.5 text-xs text-slate-950">下午茶</span> : null}
                        </h3>
                        <p className="mt-1 text-sm text-slate-600">{stop.recommendation_reason}</p>
                      </div>
                    ))}
                  </div>
                  {Array.isArray(proposal.risks) && proposal.risks.length > 0 ? (
                    <p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">{proposal.risks.slice(0, 2).join('；')}</p>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : primary ? (
          <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-[2rem] border border-[#e3d5bf] bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-[#b75f38]">推荐主方案</p>
                  <h2 className="mt-1 text-2xl font-black">{primary.display_title || primary.title || '路线方案'}</h2>
                </div>
                <div className="rounded-full bg-[#173f35] px-4 py-2 text-sm font-bold text-white">
                  {primary.total_route_duration_min ?? '-'} 分钟
                </div>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-3">
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">预算估算</p>
                  <p className="mt-1 text-xl font-black">{primary.total_budget_estimate ?? '-'} 元</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">转移时间</p>
                  <p className="mt-1 text-xl font-black">{primary.total_transfer_minutes ?? '-'} 分钟</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">步行距离</p>
                  <p className="mt-1 text-xl font-black">{primary.total_walking_distance_m ?? '-'} 米</p>
                </div>
              </div>
              {hasRouteDiff ? (
                <div className="mt-5 rounded-2xl border border-[#f1d2bf] bg-[#fff6ed] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#b75f38]">Route Diff</p>
                  <div className="mt-3 space-y-2 text-sm text-slate-700">
                    {keptStops.length > 0 ? (
                      <p>
                        <span className="font-semibold text-slate-950">保留：</span>
                        {keptStops.join('、')}
                      </p>
                    ) : null}
                    {removedStops.length > 0 ? (
                      <p>
                        <span className="font-semibold text-slate-950">删除：</span>
                        {removedStops.join('、')}
                      </p>
                    ) : null}
                    {addedStops.length > 0 ? (
                      <p>
                        <span className="font-semibold text-slate-950">新增：</span>
                        {addedStops.join('、')}
                      </p>
                    ) : null}
                    {routePatchSummary?.reordered ? (
                      <p>
                        <span className="font-semibold text-slate-950">调整：</span>
                        为了满足少走路、预算或室内偏好，系统对顺序做了局部重排。
                      </p>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {constraintJudgement ? (
                <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Constraint Judge</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-xs text-slate-500">校验结果</p>
                      <p className="mt-1 text-sm font-black text-slate-950">
                        {constraintJudgement.passes ? '通过' : '需关注风险'}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-xs text-slate-500">覆盖要求</p>
                      <p className="mt-1 text-sm font-black text-slate-950">
                        {constraintJudgement.coverage_passes ? '满足' : '部分缺失'}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-xs text-slate-500">预算约束</p>
                      <p className="mt-1 text-sm font-black text-slate-950">
                        {constraintJudgement.budget_passes ? '满足' : '可能超预算'}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-xs text-slate-500">时长约束</p>
                      <p className="mt-1 text-sm font-black text-slate-950">
                        {constraintJudgement.duration_passes ? '满足' : '可能超时'}
                      </p>
                    </div>
                  </div>
                  {Array.isArray(constraintJudgement.notes) && constraintJudgement.notes.length > 0 ? (
                    <p className="mt-3 text-xs leading-5 text-slate-600">
                      {constraintJudgement.notes.join('；')}
                    </p>
                  ) : null}
                </div>
              ) : null}
              <div className="mt-6 space-y-4">
                {stops.map((stop: Record<string, any>, index: number) => (
                  <div key={`${stop.poi_id ?? stop.name}-${index}`} className="flex gap-4 rounded-2xl border border-slate-100 bg-[#fffaf2] p-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#e77b55] font-black text-white">{index + 1}</div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="font-black text-slate-950">
                          {stop.name}
                          {stop.meal_slot === 'lunch' ? <span className="ml-2 rounded-full bg-[#f1c979] px-2 py-0.5 text-xs text-slate-950">午餐</span> : null}
                          {stop.meal_slot === 'snack' ? <span className="ml-2 rounded-full bg-[#ffe7c2] px-2 py-0.5 text-xs text-slate-950">下午茶</span> : null}
                        </h3>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                          {stop.arrival_time} - {stop.departure_time}
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-slate-600">{stop.recommendation_reason}</p>
                      <p className="mt-2 text-xs text-slate-500">{stop.opening_hours_note}</p>
                      {selectedReasons.find((item: Record<string, any>) => item.poi_id === stop.poi_id)?.reason ? (
                        <p className="mt-2 text-xs text-[#b75f38]">
                          入选原因：{selectedReasons.find((item: Record<string, any>) => item.poi_id === stop.poi_id)?.reason}
                        </p>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-6">
              {planning.llm_rerank ? (
                <div className="rounded-[1.5rem] border border-[#e3d5bf] bg-white p-5 shadow-sm">
                  <h3 className="font-black">方案选择依据</h3>
                  <div className="mt-3 space-y-2 text-sm text-slate-600">
                    <p>主推方案: {planning.final_selected_proposal_id || planning.llm_rerank.primary_proposal_id || '-'}</p>
                    <p>是否生效: {planning.llm_rerank.llm_used || planning.llm_rerank.rerank_source === 'wiki_local' ? '是' : '否'}</p>
                    <p>选择来源: {planning.llm_rerank.rerank_source === 'wiki_local' ? '本地知识库证据' : planning.llm_rerank.llm_used ? '偏好理解' : '本地规划规则'}</p>
                    <p>数据库召回: {planning.generation_metrics?.database_recall_used ? '已启用' : '未启用'}</p>
                    <p>耗时: {planning.llm_rerank.elapsed_ms ?? 0} ms</p>
                  </div>
                </div>
              ) : null}
              {wikiHits.length > 0 ? (
                <div className="rounded-[1.5rem] border border-[#e3d5bf] bg-white p-5 shadow-sm">
                  <h3 className="font-black">Obsidian Wiki 证据</h3>
                  <p className="mt-2 text-xs text-slate-500">{planning.wiki_retrieval?.vault_path || 'travel-data/wiki'}</p>
                  <div className="mt-3 space-y-2 text-sm text-slate-600">
                    {wikiHits.map((hit: Record<string, any>, index: number) => (
                      <p key={`${hit.path ?? hit.title}-${index}`}>
                        {hit.title} · {hit.type} · score {hit.score}
                      </p>
                    ))}
                  </div>
                </div>
              ) : null}
              {proposals.map((proposal, index) => (
                <div key={proposal.proposal_id ?? index} className="rounded-[1.5rem] border border-[#e3d5bf] bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h3 className="font-black">{proposal.display_title || proposal.title || `方案 ${index + 1}`}</h3>
                    <span className="text-sm font-bold text-[#b75f38]">{proposal.total_budget_estimate ?? '-'} 元</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    {Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.join(' → ') : '暂无路线'}
                  </p>
                  {Array.isArray(proposal.risks) && proposal.risks.length > 0 ? (
                    <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                      {proposal.risks.slice(0, 2).join('；')}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-6 rounded-[2rem] border border-dashed border-[#d7c3a6] bg-white/70 p-8 text-center text-slate-600">
            输入北京游玩目标后，路线方案会显示在这里。
          </div>
        )}
      </div>
    </div>
  );
}

function TravelItineraryPreviewV2({ data }: { data: TravelItineraryData }) {
  const planning = data.planning_response ?? {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const dailyItinerary = Array.isArray(planning.daily_itinerary) ? planning.daily_itinerary : [];
  const primary = proposals[0];
  const stops = Array.isArray(primary?.pois) ? primary.pois : [];
  const naturalLanguageExplanation = String(planning.natural_language_explanation || '');
  const routePatchSummary = planning.route_patch_summary;
  const selectedReasons = Array.isArray(primary?.selection_reasons) ? primary.selection_reasons : [];
  const constraintJudgement =
    (primary?.constraint_judgement as Record<string, any> | undefined) ??
    (planning.constraint_judgement as Record<string, any> | undefined) ??
    null;
  const keptStops = Array.isArray(routePatchSummary?.kept) ? routePatchSummary.kept : [];
  const removedStops = Array.isArray(routePatchSummary?.removed) ? routePatchSummary.removed : [];
  const addedStops = Array.isArray(routePatchSummary?.added) ? routePatchSummary.added : [];
  const hasRouteDiff = keptStops.length > 0 || removedStops.length > 0 || addedStops.length > 0 || Boolean(routePatchSummary?.reordered);
  const reasonFor = (poiId?: string) =>
    selectedReasons.find((item: Record<string, any>) => item.poi_id === poiId)?.reason;
  const transferSummary = primary?.transfer_source_summary || primary?.quality_summary?.commute || {};
  const commuteEdgesUsed = Number(transferSummary.commute_edges_used || 0);
  const coordinateEstimatesUsed = Number(transferSummary.coordinate_estimates_used || 0);
  const commuteHitRate = Number(transferSummary.commute_edge_hit_rate || 0);
  const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);
  const selectedPlan = proposals[selectedPlanIndex] || primary;
  const selectedStops = Array.isArray(selectedPlan?.pois) ? selectedPlan.pois : stops;
  const dayCount = dailyItinerary.length || planning.day_count || 1;
  const isMultiDay = dailyItinerary.length > 1;
  const destination = planning.resolved_area || data.parsed_request?.area || '北京';
  const routeTitle =
    selectedPlan?.display_title ||
    selectedPlan?.title ||
    (dayCount > 1 ? '北京多日深度行程' : '北京一日灵感路线');
  const heroTitle = dayCount > 1 ? `${destination}：${dayCount} 天游玩灵感` : `${destination}：一日之间，千年风华`;
  const totalBudget = Number(selectedPlan?.total_budget_estimate || primary?.total_budget_estimate || 0);
  const budgetLevel = totalBudget >= 450 ? '舒适型' : totalBudget >= 220 ? '均衡型' : '轻预算';
  const activityGroups = selectedStops.reduce((groups: Record<string, Record<string, any>[]>, stop: Record<string, any>) => {
    const hour = Number(String(stop.arrival_time || '').split(':')[0]);
    const label = stop.meal_slot === 'lunch' ? '午餐' : stop.meal_slot === 'snack' ? '下午茶' : hour >= 17 ? '傍晚' : hour >= 13 ? '下午' : '上午';
    groups[label] = [...(groups[label] || []), stop];
    return groups;
  }, {});
  const groupOrder = ['上午', '午餐', '下午', '下午茶', '傍晚', '晚餐'];
  const visibleGroups = groupOrder
    .map(label => ({ label, stops: activityGroups[label] || [] }))
    .filter(group => group.stops.length > 0);
  const estimatedTransportBudget = Math.max(0, Math.round(Number(selectedPlan?.total_transfer_minutes || 0) * 2));
  const estimatedFoodBudget = selectedStops
    .filter((stop: Record<string, any>) => stop.meal_slot || String(stop.poi_type || '').toLowerCase() === 'food')
    .reduce((sum: number, stop: Record<string, any>) => sum + Math.max(0, Number(stop.estimated_cost || 0)), 0);
  const estimatedTicketBudget = selectedStops
    .filter((stop: Record<string, any>) => !stop.meal_slot && String(stop.poi_type || '').toLowerCase() !== 'food')
    .reduce((sum: number, stop: Record<string, any>) => sum + Math.max(0, Number(stop.estimated_cost || 0)), 0);
  const estimatedOtherBudget = Math.max(0, totalBudget - estimatedTransportBudget - estimatedTicketBudget - estimatedFoodBudget);
  const budgetItems = normalizeBudgetBreakdown([
    { label: '交通', value: estimatedTransportBudget },
    { label: '门票', value: estimatedTicketBudget },
    { label: '餐饮', value: estimatedFoodBudget },
    { label: '其他', value: estimatedOtherBudget },
  ], totalBudget);
  const planAdvice = [
    selectedStops.length >= 4 ? '这条路线把核心游览点和餐饮停留串在同一条顺路动线上。' : '这条路线控制停留数量，优先保证时间宽松和移动顺畅。',
    Number(selectedPlan?.total_walking_distance_m || 0) > 1800 ? '步行量偏高，建议穿舒适鞋并保留中途休息。' : '步行压力较低，可以把更多时间留给拍照、吃饭和临时停留。',
    commuteEdgesUsed > 0 ? '部分路段已匹配本地通勤数据，时间估算更稳。' : '交通时间按坐标和常规速度估算，出发前可再看实时导航。',
  ];
  const alternatives = proposals.filter((_, index) => index !== selectedPlanIndex);
  const coverImages = [
    '/travel-images/qianmen.jpg',
    '/travel-images/forbidden-city.jpg',
    '/travel-images/temple-of-heaven.jpg',
    '/travel-images/beijing-street.jpg',
  ];
  const isTechnicalText = (value?: string | null) =>
    Boolean(
      value &&
        /(MiniMax|Obsidian|LLM|JSON|planner|fallback|http\d+|agent|score=|meal type|rating|stay about|data_file|travel_|poi_id|兜底|合规)/i.test(value),
    );
  const cleanNarrative =
    naturalLanguageExplanation && !isTechnicalText(naturalLanguageExplanation)
      ? naturalLanguageExplanation
      : `围绕 ${routeTitle} 安排游览、吃喝与移动节奏，把经典景观、胡同烟火和可执行时间放在同一条顺路的线上。`;
  const stopKind = (stop: Record<string, any>) => {
    const name = String(stop.name || '').toLowerCase();
    const poiType = String(stop.poi_type || '').toLowerCase();
    const category = String(stop.category || '').toLowerCase();
    if (stop.meal_slot === 'lunch' || poiType === 'food') return /咖啡|茶|coffee|cafe/.test(name) ? '咖啡茶饮' : '餐饮';
    if (stop.meal_slot === 'snack') return '咖啡茶饮';
    if (poiType === 'culture' || category === 'attraction') return '文化景点';
    if (/咖啡|茶|coffee|cafe/.test(name)) return '咖啡茶饮';
    if (/餐|小吃|烤鸭|涮肉|烧麦|炸酱/.test(name)) return '餐饮';
    if (/胡同|鼓楼|故宫|寺|庙|公园|景|museum/.test(name)) return '文化景点';
    return '停留点';
  };
  const stopDescription = (stop: Record<string, any>) => {
    const raw = String(stop.recommendation_reason || '');
    if (raw && !isTechnicalText(raw)) return raw;
    const rating = raw.match(/rating\s+([\d.]+)/i)?.[1] || stop.rating || stop.score;
    const stay = stop.duration_minutes ?? stop.stay_minutes;
    const kind = stopKind(stop);
    const fragments = [
      `${stop.name || '这一站'}是本次路线里的${kind}`,
      rating ? `本地评分约 ${rating}` : '',
      stay ? `建议停留约 ${stay} 分钟` : '',
      stop.meal_slot === 'lunch' ? '可作为午餐停留' : stop.meal_slot === 'snack' ? '适合安排咖啡或下午茶' : '',
    ].filter(Boolean);
    return `${fragments.join('，')}。`;
  };
  const selectionDescription = (stop: Record<string, any>) => {
    const raw = String(reasonFor(stop.poi_id) || '');
    if (raw && !isTechnicalText(raw)) return raw;
    const kind = stopKind(stop);
    if (kind === '餐饮') return '补足用餐体验，并尽量减少路线折返。';
    if (kind === '咖啡茶饮') return '适合作为途中短暂停留，让行程节奏更舒服。';
    return '与当前区域和游玩节奏匹配，适合作为顺路停留点。';
  };

  const MetricPill = ({ label, value, tone = 'light' }: { label: string; value: any; tone?: 'light' | 'dark' | 'gold' }) => (
    <div className={tone === 'dark' ? 'rounded-[1.35rem] bg-[#173f35] px-5 py-4 text-white' : tone === 'gold' ? 'rounded-[1.35rem] bg-[#f4c66f] px-5 py-4 text-[#101828]' : 'rounded-[1.35rem] border border-[#eadcc9] bg-white/85 px-5 py-4 text-[#101828]'}>
      <p className={tone === 'dark' ? 'text-xs text-white/60' : 'text-xs text-[#758195]'}>{label}</p>
      <p className="mt-1 text-xl font-black">{value}</p>
    </div>
  );

  const StopBadge = ({ stop }: { stop: Record<string, any> }) => {
    if (stop.meal_slot === 'lunch') {
      return <span className="rounded-full bg-[#ffe4a8] px-2.5 py-1 text-[11px] font-black text-[#8a4a18]">午餐</span>;
    }
    if (stop.meal_slot === 'snack') {
      return <span className="rounded-full bg-[#fde9d7] px-2.5 py-1 text-[11px] font-black text-[#a14d2b]">下午茶</span>;
    }
    return <span className="rounded-full bg-[#eaf6ef] px-2.5 py-1 text-[11px] font-black text-[#236247]">景点</span>;
  };

  return (
    <div className="h-full w-full overflow-y-auto bg-[#f6f0e8] text-[#101828]">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-[1.5rem] border border-[#eadcc9] bg-[#fffaf4]/95 px-5 py-4 shadow-sm backdrop-blur">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#173f35] text-lg font-black text-white">游</div>
            <div>
              <p className="text-lg font-black tracking-tight">北京旅行灵感</p>
              <p className="text-xs font-semibold text-[#7f8a9d]">{destination} · {dayCount} 天 · 私人路线建议</p>
            </div>
          </div>
          {proposals.length > 1 ? (
            <div className="flex max-w-full gap-2 overflow-x-auto rounded-2xl border border-[#eadcc9] bg-white p-1">
              {proposals.map((proposal, index) => (
                <button
                  key={proposal.proposal_id ?? index}
                  onClick={() => setSelectedPlanIndex(index)}
                  className={`whitespace-nowrap rounded-xl px-4 py-2 text-sm font-black transition ${
                    selectedPlanIndex === index
                      ? 'bg-white text-[#173f35] shadow-sm'
                      : 'text-[#667085] hover:bg-white/55 hover:text-[#173f35]'
                  }`}
                >
                  {index === 0 ? '推荐' : `备选 ${index}`} · {proposal.total_budget_estimate ?? '-'} 元
                </button>
              ))}
            </div>
          ) : null}
        </header>

        {selectedPlan ? (
          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
            <main className="min-w-0 overflow-hidden rounded-[1.75rem] border border-[#eadcc9] bg-[#fffaf4] shadow-[0_24px_90px_rgba(92,64,33,0.12)]">
              <section className="relative min-h-[360px] overflow-hidden bg-[#fffaf4] p-6 text-white sm:p-8 lg:p-10">
                <div className="absolute inset-0">
                  <img src={coverImages[selectedPlanIndex % coverImages.length]} alt="" className="h-full w-full object-cover opacity-85 saturate-125" />
                  <div className="absolute inset-0 bg-gradient-to-r from-black/68 via-black/28 to-black/8" />
                  <div className="absolute inset-x-0 bottom-0 h-36 bg-gradient-to-t from-[#fffaf4] to-transparent" />
                </div>
                <div className="relative z-10 max-w-3xl">
                  <div className="mb-8 inline-flex items-center gap-2 rounded-full bg-white/16 px-4 py-2 text-sm font-bold backdrop-blur">
                    <span>{destination}</span>
                    <span className="h-1 w-1 rounded-full bg-white/70" />
                    <span>{dayCount} 天</span>
                    <span className="h-1 w-1 rounded-full bg-white/70" />
                    <span>{budgetLevel}</span>
                  </div>
                  <p className="text-sm font-black tracking-[0.28em] text-[#ffd28a]">北京旅行规划</p>
                  <h1 className="mt-4 max-w-3xl text-4xl font-black leading-tight tracking-tight sm:text-5xl lg:text-6xl">
                    {heroTitle}
                  </h1>
                  <p className="mt-5 max-w-2xl text-base leading-7 text-white/86">
                    {cleanNarrative}
                  </p>
                  <div className="mt-8 grid max-w-2xl grid-cols-3 gap-3 text-center">
                    <MetricPill label="站点数" value={`${selectedStops.length}`} tone="gold" />
                    <MetricPill label="预算" value={`${selectedPlan.total_budget_estimate ?? '-'} 元`} />
                    <MetricPill label="总时长" value={`${selectedPlan.total_route_duration_min ?? '-'} 分钟`} tone="dark" />
                  </div>
                </div>
              </section>

              <section className="p-5 sm:p-8 lg:p-10">
                <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <p className="text-sm font-black text-[#c46b42]">{isMultiDay ? `${dayCount} 天游玩安排` : '第 1 天'}</p>
                    <h2 className="mt-1 text-3xl font-black tracking-tight">{isMultiDay ? '每天都有独立路线和时间表' : routeTitle}</h2>
                  </div>
                  <button className="rounded-full bg-[#173f35] px-5 py-3 text-sm font-black text-white shadow-sm transition hover:bg-[#205447]">
                    优化行程
                  </button>
                </div>

                {isMultiDay ? (
                  <div className="space-y-8">
                    {dailyItinerary.map((day: Record<string, any>, dayIndex: number) => {
                      const dayProposal = day.proposal || {};
                      const dayStops = Array.isArray(dayProposal.pois) ? dayProposal.pois : [];
                      return (
                        <section key={day.day ?? dayIndex} id={`trip-day-${dayIndex + 1}`} className="scroll-mt-8 rounded-[1.75rem] border border-[#eadcc9] bg-white p-5 shadow-sm sm:p-6">
                          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-black text-[#c46b42]">{day.title || `第 ${dayIndex + 1} 天`}</p>
                              <h3 className="mt-1 text-2xl font-black tracking-tight">{day.area || destination} · {day.theme || dayProposal.display_title || '日程方案'}</h3>
                            </div>
                            <div className="flex gap-2 text-sm font-black">
                              <span className="rounded-full bg-[#173f35] px-3 py-1.5 text-white">{dayProposal.total_route_duration_min ?? '-'} 分钟</span>
                              <span className="rounded-full bg-[#f4c66f] px-3 py-1.5 text-[#101828]">{dayProposal.total_budget_estimate ?? '-'} 元</span>
                            </div>
                          </div>
                          <div className="space-y-4">
                            {dayStops.map((stop: Record<string, any>, index: number) => {
                              const previousStop = dayStops[index - 1] as Record<string, any> | undefined;
                              return (
                                <article key={`${stop.poi_id ?? stop.name}-${dayIndex}-${index}`} className="rounded-[1.35rem] border border-[#eadcc9] bg-[#fffaf4] p-4">
                                  <div className="flex flex-col gap-4 md:flex-row md:items-start">
                                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#ef7f55] text-base font-black text-white shadow-sm">
                                      {index + 1}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                      <div className="flex flex-wrap items-start justify-between gap-3">
                                        <div>
                                          <div className="flex flex-wrap items-center gap-2">
                                            <h4 className="text-xl font-black tracking-tight">{stop.name}</h4>
                                            <StopBadge stop={stop} />
                                          </div>
                                          <p className="mt-2 text-sm font-semibold text-[#667085]">{stop.arrival_time || '--:--'} - {stop.departure_time || '--:--'}</p>
                                        </div>
                                        <div className="rounded-full bg-[#f8efe5] px-4 py-2 text-sm font-black text-[#a75933]">
                                          约 {stop.duration_minutes ?? stop.stay_minutes ?? '-'} 分钟
                                        </div>
                                      </div>
                                      <p className="mt-3 text-sm leading-7 text-[#344054]">{stopDescription(stop)}</p>
                                      {previousStop ? (
                                        <p className="mt-3 rounded-2xl bg-[#eef8f3] p-3 text-sm leading-6 text-[#236247]">
                                          上一站：{previousStop.name} → {stop.name}，约 {stop.transfer_from_previous_minutes ?? '-'} 分钟 · {stop.transfer_from_previous_meters ?? '-'} 米
                                        </p>
                                      ) : null}
                                    </div>
                                  </div>
                                </article>
                              );
                            })}
                          </div>
                        </section>
                      );
                    })}
                  </div>
                ) : (
                  <div className="space-y-9">
                    {visibleGroups.map(group => (
                      <section key={group.label} id={`trip-section-${group.label}`} className="scroll-mt-8">
                        <div className="mb-4 flex items-center gap-3">
                          <div className="h-px flex-1 bg-[#eadcc9]" />
                          <span className="rounded-full border border-[#eadcc9] bg-white px-4 py-1.5 text-sm font-black text-[#9c5834]">{group.label}</span>
                          <div className="h-px flex-1 bg-[#eadcc9]" />
                        </div>
                        <div className="space-y-5">
                          {group.stops.map((stop: Record<string, any>, index: number) => {
                            const globalIndex = selectedStops.findIndex((item: Record<string, any>) => item === stop);
                            const previousStop = selectedStops[globalIndex - 1] as Record<string, any> | undefined;
                            return (
                              <article key={`${stop.poi_id ?? stop.name}-${group.label}-${index}`} className="group rounded-[1.75rem] border border-[#eadcc9] bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(92,64,33,0.12)] sm:p-6">
                                <div className="flex flex-col gap-4 md:flex-row md:items-start">
                                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#ef7f55] text-lg font-black text-white shadow-sm">
                                    {globalIndex + 1 || index + 1}
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                      <div>
                                        <div className="flex flex-wrap items-center gap-2">
                                          <h3 className="text-2xl font-black tracking-tight">{stop.name}</h3>
                                          <StopBadge stop={stop} />
                                        </div>
                                        <p className="mt-2 text-sm font-semibold text-[#667085]">{stop.arrival_time || '--:--'} - {stop.departure_time || '--:--'}</p>
                                      </div>
                                      <div className="rounded-full bg-[#f8efe5] px-4 py-2 text-sm font-black text-[#a75933]">
                                        约 {stop.duration_minutes ?? stop.stay_minutes ?? '-'} 分钟
                                      </div>
                                    </div>
                                    <p className="mt-4 text-base leading-8 text-[#344054]">{stopDescription(stop)}</p>
                                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                                      {stop.opening_hours_note ? (
                                        <div className="rounded-2xl bg-[#fff8ed] p-3 text-sm leading-6 text-[#7a4d27]">
                                          <span className="font-black">到访提醒</span>
                                          <p>{stop.opening_hours_note}</p>
                                        </div>
                                      ) : null}
                                      {previousStop ? (
                                        <div className="rounded-2xl bg-[#eef8f3] p-3 text-sm leading-6 text-[#236247]">
                                          <span className="font-black">上一站过来</span>
                                          <p>{previousStop.name} → {stop.name}</p>
                                          <p>{stop.transfer_from_previous_minutes ?? '-'} 分钟 · {stop.transfer_from_previous_meters ?? '-'} 米</p>
                                        </div>
                                      ) : null}
                                      {selectionDescription(stop) ? (
                                        <div className="rounded-2xl bg-[#f7f4ff] p-3 text-sm leading-6 text-[#5141a4]">
                                          <span className="font-black">为什么选它</span>
                                          <p>{selectionDescription(stop)}</p>
                                        </div>
                                      ) : null}
                                    </div>
                                  </div>
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      </section>
                    ))}
                  </div>
                )}

                {hasRouteDiff ? (
                  <section className="mt-10 rounded-[1.75rem] border border-[#eadcc9] bg-[#fff6ec] p-6">
                    <p className="text-sm font-black text-[#c46b42]">本次调整</p>
                    <div className="mt-4 grid gap-3 text-sm leading-6 text-[#5f4636] md:grid-cols-3">
                      {keptStops.length > 0 ? <p><span className="font-black text-[#101828]">保留：</span>{keptStops.join('、')}</p> : null}
                      {removedStops.length > 0 ? <p><span className="font-black text-[#101828]">移除：</span>{removedStops.join('、')}</p> : null}
                      {addedStops.length > 0 ? <p><span className="font-black text-[#101828]">加入：</span>{addedStops.join('、')}</p> : null}
                    </div>
                  </section>
                ) : null}

                {alternatives.length > 0 ? (
                  <section className="mt-10">
                    <p className="text-sm font-black text-[#c46b42]">备选方案</p>
                    <h2 className="mt-1 text-2xl font-black">换一种节奏，也可以这样玩</h2>
                    <div className="mt-5 grid gap-4 md:grid-cols-2">
                      {alternatives.map((proposal, index) => (
                        <button
                          key={proposal.proposal_id ?? index}
                          onClick={() => setSelectedPlanIndex(proposals.indexOf(proposal))}
                          className="rounded-[1.5rem] border border-[#eadcc9] bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-[#ef7f55] hover:shadow-md"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <h3 className="font-black">{proposal.display_title || proposal.title || `方案 ${index + 2}`}</h3>
                            <span className="rounded-full bg-[#fff1e7] px-3 py-1 text-sm font-black text-[#c46b42]">{proposal.total_budget_estimate ?? '-'} 元</span>
                          </div>
                          <p className="mt-3 text-sm leading-6 text-[#667085]">
                            {Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.join(' → ') : '暂无路线'}
                          </p>
                        </button>
                      ))}
                    </div>
                  </section>
                ) : null}
              </section>
            </main>

            <aside className="space-y-5 xl:sticky xl:top-5">
              <section className="rounded-[1.75rem] border border-[#eadcc9] bg-white p-6 shadow-sm">
                <p className="text-sm font-black text-[#c46b42]">行程概览</p>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-[#173f35] p-4 text-white">
                    <p className="text-xs font-bold text-white/65">目的地</p>
                    <p className="mt-1 text-xl font-black">{destination}</p>
                  </div>
                  <div className="rounded-2xl bg-[#f4c66f] p-4 text-[#101828]">
                    <p className="text-xs font-bold text-[#7a5a23]">天数</p>
                    <p className="mt-1 text-xl font-black">{dayCount} 天</p>
                  </div>
                  <div className="rounded-2xl bg-[#f8efe5] p-4 text-[#101828]">
                    <p className="text-xs font-bold text-[#8a6b53]">站点</p>
                    <p className="mt-1 text-xl font-black">{selectedStops.length} 站</p>
                  </div>
                  <div className="rounded-2xl bg-[#eef8f3] p-4 text-[#173f35]">
                    <p className="text-xs font-bold text-[#236247]">步行</p>
                    <p className="mt-1 text-xl font-black">{selectedPlan.total_walking_distance_m ?? '-'} 米</p>
                  </div>
                </div>
                <div className="mt-5 rounded-2xl bg-[#fff8ed] p-4 text-sm leading-6 text-[#7a4d27]">
                  按你的出行要求生成当前路线，优先兼顾时间、预算、步行距离和餐饮停留。
                </div>
              </section>

              <section className="rounded-[1.75rem] border border-[#eadcc9] bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-black text-[#c46b42]">预估预算</p>
                    <p className="mt-1 text-2xl font-black">{budgetLevel}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-black">{selectedPlan.total_budget_estimate ?? '-'}</p>
                    <p className="text-xs font-bold text-[#667085]">CNY 总计</p>
                  </div>
                </div>
                <div className="mt-5 space-y-3">
                  {budgetItems.map(item => (
                    <div key={item.label}>
                      <div className="mb-1 flex items-center justify-between text-sm font-bold">
                        <span>{item.label}</span>
                        <span>{item.value}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-[#f1e6d8]">
                        <div className="h-full rounded-full bg-[#ef7f55]" style={{ width: `${Math.min(100, totalBudget ? (item.value / Math.max(totalBudget, 1)) * 100 : 25)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-[1.75rem] border border-[#eadcc9] bg-white p-6 shadow-sm">
                <p className="text-sm font-black text-[#c46b42]">路线目录</p>
                <div className="mt-4 space-y-2">
                  {isMultiDay ? dailyItinerary.map((day: Record<string, any>, index: number) => {
                    const dayStops = Array.isArray(day.proposal?.pois) ? day.proposal.pois : [];
                    return (
                      <a key={day.day ?? index} href={`#trip-day-${index + 1}`} className="flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-black text-[#344054] transition hover:bg-[#fff4e8] hover:text-[#c46b42]">
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#f8efe5] text-xs text-[#a75933]">{index + 1}</span>
                        <span>{day.title || `第 ${index + 1} 天`}</span>
                        <span className="ml-auto text-xs font-bold text-[#98a2b3]">{dayStops.length} 站</span>
                      </a>
                    );
                  }) : visibleGroups.map((group, index) => (
                    <a key={group.label} href={`#trip-section-${group.label}`} className="flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-black text-[#344054] transition hover:bg-[#fff4e8] hover:text-[#c46b42]">
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#f8efe5] text-xs text-[#a75933]">{index + 1}</span>
                      <span>{group.label}</span>
                      <span className="ml-auto text-xs font-bold text-[#98a2b3]">{group.stops.length} 站</span>
                    </a>
                  ))}
                </div>
              </section>

              <section className="rounded-[1.75rem] border border-[#eadcc9] bg-white p-6 shadow-sm">
                <p className="text-sm font-black text-[#c46b42]">旅行建议</p>
                <ol className="mt-4 space-y-3 text-sm leading-6 text-[#344054]">
                  {planAdvice.map((advice, index) => (
                    <li key={advice} className="flex gap-3">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#173f35] text-xs font-black text-white">{index + 1}</span>
                      <span>{advice}</span>
                    </li>
                  ))}
                </ol>
                <div className="mt-5 rounded-2xl bg-[#eef8f3] p-4 text-sm leading-6 text-[#236247]">
                  本地旅行数据命中 {commuteEdgesUsed} 段通勤，{coordinateEstimatesUsed} 段使用距离估算；排队和热度为历史数据参考。
                </div>
              </section>
            </aside>
          </div>
        ) : (
          <div className="rounded-[2rem] border border-dashed border-[#d7c3a6] bg-white/70 p-10 text-center text-slate-600">
            输入北京游玩目标后，这里会生成一份旅行报告式行程。
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const params = useParams<{ project_id: string }>();
  const pathname = usePathname();
  const routeProjectId = params?.project_id;
  const projectIdFromParams = Array.isArray(routeProjectId) ? routeProjectId[0] : routeProjectId;
  const projectId =
    projectIdFromParams ??
    pathname?.split('/').filter(Boolean).find((segment) => segment.startsWith('project-')) ??
    '';
  const router = useRouter();
  const searchParams = useSearchParams();

  // NEW: UserRequests state management
  const {
    hasActiveRequests,
    createRequest,
    startRequest,
    completeRequest
  } = useUserRequests({ projectId });

  const [projectName, setProjectName] = useState<string>('');
  const [projectDescription, setProjectDescription] = useState<string>('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const [tree, setTree] = useState<Entry[]>([]);
  const [content, setContent] = useState<string>('');
  const [editedContent, setEditedContent] = useState<string>('');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isSavingFile, setIsSavingFile] = useState(false);
  const [saveFeedback, setSaveFeedback] = useState<'idle' | 'success' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [currentPath, setCurrentPath] = useState<string>('.');
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['']));
  const [folderContents, setFolderContents] = useState<Map<string, Entry[]>>(new Map());
  const [prompt, setPrompt] = useState('');

  // Ref to store add/remove message handlers from ChatLog
  const messageHandlersRef = useRef<{
    add: (message: any) => void;
    remove: (messageId: string) => void;
  } | null>(null);

  // Ref to track pending requests for deduplication
  const pendingRequestsRef = useRef<Set<string>>(new Set());

  // Stable message handlers to prevent reassignment issues
  const stableMessageHandlers = useRef<{
    add: (message: any) => void;
    remove: (messageId: string) => void;
  } | null>(null);

  // Track active optimistic messages by requestId
  const optimisticMessagesRef = useRef<Map<string, any>>(new Map());
  const [mode, setMode] = useState<'act' | 'chat'>('act');
  const [isRunning, setIsRunning] = useState(false);
  const [isPausingAgent, setIsPausingAgent] = useState(false);
  const [isSseFallbackActive, setIsSseFallbackActive] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [deviceMode, setDeviceMode] = useState<'desktop'|'mobile'>('desktop');
  const [showGlobalSettings, setShowGlobalSettings] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<{name: string; url: string; base64?: string; path?: string}[]>([]);
  const [isInitializing, setIsInitializing] = useState(true);
  // Initialize states with default values, will be loaded from localStorage in useEffect
  const [hasInitialPrompt, setHasInitialPrompt] = useState<boolean>(false);
  const [agentWorkComplete, setAgentWorkComplete] = useState<boolean>(false);
  const [projectStatus, setProjectStatus] = useState<ProjectStatus>('initializing');
  const [initializationMessage, setInitializationMessage] = useState('Starting project initialization...');
  const [initialPromptSent, setInitialPromptSent] = useState(false);
  const initialPromptSentRef = useRef(false);
  const [showPublishPanel, setShowPublishPanel] = useState(false);
  const [publishLoading, setPublishLoading] = useState(false);
  const [githubConnected, setGithubConnected] = useState<boolean | null>(null);
  const [vercelConnected, setVercelConnected] = useState<boolean | null>(null);
  const [publishedUrl, setPublishedUrl] = useState<string | null>(null);
  const [deploymentId, setDeploymentId] = useState<string | null>(null);
  const [deploymentStatus, setDeploymentStatus] = useState<'idle' | 'deploying' | 'ready' | 'error'>('idle');
  const deployPollRef = useRef<NodeJS.Timeout | null>(null);
  const [isStartingPreview, setIsStartingPreview] = useState(false);
  const [previewInitializationMessage, setPreviewInitializationMessage] = useState('正在启动预览服务...');
  const [previewValidationState, setPreviewValidationState] = useState<PreviewValidationState>('unknown');
  const [previewValidationMessage, setPreviewValidationMessage] = useState<string | null>(null);
  const [previewRepairPlan, setPreviewRepairPlan] = useState<PreviewValidationRepairPlan | null>(null);
  const [travelItinerary, setTravelItinerary] = useState<TravelItineraryData | null>(null);
  const [cliStatuses, setCliStatuses] = useState<Record<string, CliStatusSnapshot>>({});
  const [conversationId, setConversationId] = useState<string>(() => {
    if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
      return window.crypto.randomUUID();
    }
    return '';
  });
  const [preferredCli, setPreferredCli] = useState<ActiveCliId>(DEFAULT_ACTIVE_CLI);
  const [selectedModel, setSelectedModel] = useState<string>(getDefaultModelForCli(DEFAULT_ACTIVE_CLI));
  const [usingGlobalDefaults, setUsingGlobalDefaults] = useState<boolean>(true);
  const [isUpdatingModel, setIsUpdatingModel] = useState<boolean>(false);
  const [currentRoute, setCurrentRoute] = useState<string>('/');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const shouldShowPreviewFrame = Boolean(previewUrl) && !isStartingPreview;
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const lineNumberRef = useRef<HTMLDivElement>(null);
  const editedContentRef = useRef<string>('');
  const [isFileUpdating, setIsFileUpdating] = useState(false);
  const activeBrandColor =
    assistantBrandColors[preferredCli] || assistantBrandColors[DEFAULT_ACTIVE_CLI];
  const modelOptions = useMemo(() => buildModelOptions(cliStatuses), [cliStatuses]);
  const cliOptions = useMemo(
    () => CLI_ORDER.map(cli => ({
      id: cli,
      name: CLI_LABELS[cli] || cli,
      available: Boolean(cliStatuses[cli]?.available && cliStatuses[cli]?.configured)
    })),
    [cliStatuses]
  );

  const updatePreferredCli = useCallback((cli: string) => {
    const sanitized = sanitizeCli(cli);
    setPreferredCli(sanitized);
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('selectedAssistant', sanitized);
    }
  }, []);

  const updateSelectedModel = useCallback((model: string, cliOverride?: string) => {
    const effectiveCli = cliOverride ? sanitizeCli(cliOverride) : preferredCli;
    const sanitized = sanitizeModel(effectiveCli, model);
    setSelectedModel(sanitized);
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('selectedModel', sanitized);
    }
  }, [preferredCli]);

  useEffect(() => {
    previewUrlRef.current = previewUrl;
  }, [previewUrl]);

  const sendInitialPrompt = useCallback(async (initialPrompt: string) => {
    if (initialPromptSent) {
      return;
    }

    setAgentWorkComplete(false);
    localStorage.setItem(`project_${projectId}_taskComplete`, 'false');

    const requestId = crypto.randomUUID();

    try {
      setIsRunning(true);
      setInitialPromptSent(true);

      const requestBody = {
        instruction: appendVisibleProcessInstructions(initialPrompt),
        displayInstruction: initialPrompt.trim(),
        images: [],
        isInitialPrompt: true,
        travelCapabilityId: 'mixed_food_route',
        cliPreference: preferredCli,
        conversationId: conversationId || undefined,
        requestId: `${requestId}-progress`,
        selectedModel,
      };

      const r = await fetch(`${API_BASE}/api/chat/${projectId}/act`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!r.ok) {
        const errorText = await r.text();
        console.error('❌ API Error:', errorText);
        setInitialPromptSent(false);
        return;
      }

      const result = await r.json();
      const returnedConversationId =
        typeof result?.conversationId === 'string'
          ? result.conversationId
          : typeof result?.conversation_id === 'string'
          ? result.conversation_id
          : undefined;
      if (returnedConversationId) {
        setConversationId(returnedConversationId);
      }

      const resolvedRequestId =
        typeof result?.requestId === 'string'
          ? result.requestId
          : typeof result?.request_id === 'string'
          ? result.request_id
          : requestId;
      const userMessageId =
        typeof result?.userMessageId === 'string'
          ? result.userMessageId
          : typeof result?.user_message_id === 'string'
          ? result.user_message_id
          : '';

      createRequest(resolvedRequestId, userMessageId, initialPrompt, 'act');
      setPrompt('');

      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('initial_prompt');
      window.history.replaceState({}, '', newUrl.toString());
    } catch (error) {
      console.error('Error sending initial prompt:', error);
      setInitialPromptSent(false);
    } finally {
      setIsRunning(false);
    }
  }, [initialPromptSent, preferredCli, conversationId, projectId, selectedModel, createRequest]);

  // Guarded trigger that can be called from multiple places safely
  const triggerInitialPromptIfNeeded = useCallback(() => {
    const initialPromptFromUrl = searchParams?.get('initial_prompt');
    if (!initialPromptFromUrl) return;
    if (initialPromptSentRef.current) return;
    // Synchronously guard to prevent double ACT calls
    initialPromptSentRef.current = true;
    setInitialPromptSent(true);

    // Store the selected model and assistant in sessionStorage when returning
    const cliFromUrl = searchParams?.get('cli');
    const modelFromUrl = searchParams?.get('model');
    if (cliFromUrl) {
      const sanitizedCli = sanitizeCli(cliFromUrl);
      sessionStorage.setItem('selectedAssistant', sanitizedCli);
      if (modelFromUrl) {
        sessionStorage.setItem('selectedModel', sanitizeModel(sanitizedCli, modelFromUrl));
      }
    } else if (modelFromUrl) {
      sessionStorage.setItem('selectedModel', sanitizeModel(preferredCli, modelFromUrl));
    }

    // Don't show the initial prompt in the input field
    // setPrompt(initialPromptFromUrl);
    setTimeout(() => {
      sendInitialPrompt(initialPromptFromUrl);
    }, 300);
  }, [searchParams, sendInitialPrompt, preferredCli]);

const loadCliStatuses = useCallback(() => {
  const snapshot: Record<string, CliStatusSnapshot> = {};
  ACTIVE_CLI_IDS.forEach(id => {
    const models = ACTIVE_CLI_MODEL_OPTIONS[id]?.map(model => model.id) ?? [];
    snapshot[id] = {
      available: true,
      configured: true,
      models,
    };
  });
  setCliStatuses(snapshot);
}, []);

const persistProjectPreferences = useCallback(
  async (changes: { preferredCli?: string; selectedModel?: string }) => {
    if (!projectId) return;
    const payload: Record<string, unknown> = {};
    if (changes.preferredCli) {
      const sanitizedPreferredCli = sanitizeCli(changes.preferredCli);
      payload.preferredCli = sanitizedPreferredCli;
      payload.preferred_cli = sanitizedPreferredCli;
    }
    if (changes.selectedModel) {
      const targetCli = sanitizeCli(changes.preferredCli ?? preferredCli);
      const normalized = sanitizeModel(targetCli, changes.selectedModel);
      payload.selectedModel = normalized;
      payload.selected_model = normalized;
    }
    if (Object.keys(payload).length === 0) return;

    const response = await fetch(`${API_BASE}/api/projects/${projectId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || 'Failed to update project preferences');
    }

    const result = await response.json().catch(() => null);
    return result?.data ?? result;
  },
  [projectId, preferredCli]
);

  const handleModelChange = useCallback(
    async (option: ModelOption, opts?: { skipCliUpdate?: boolean; overrideCli?: string }) => {
      if (!projectId || !option) return;

      const { skipCliUpdate = false, overrideCli } = opts || {};
      const targetCli = sanitizeCli(overrideCli ?? option.cli);
      const sanitizedModelId = sanitizeModel(targetCli, option.id);

      const previousCli = preferredCli;
      const previousModel = selectedModel;

      if (targetCli === previousCli && sanitizedModelId === previousModel) {
        return;
      }

      setUsingGlobalDefaults(false);
      updatePreferredCli(targetCli);
      updateSelectedModel(option.id, targetCli);

      setIsUpdatingModel(true);

      try {
        const preferenceChanges: { preferredCli?: string; selectedModel?: string } = {
          selectedModel: sanitizedModelId,
        };
        if (!skipCliUpdate && targetCli !== previousCli) {
          preferenceChanges.preferredCli = targetCli;
        }

        await persistProjectPreferences(preferenceChanges);

        const cliLabel = CLI_LABELS[targetCli] || targetCli;
        const modelLabel = getModelDisplayName(targetCli, sanitizedModelId);
        try {
          await fetch(`${API_BASE}/api/chat/${projectId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              content: `Switched to ${cliLabel} (${modelLabel})`,
              role: 'system',
              message_type: 'info',
              cli_source: targetCli,
              conversation_id: conversationId || undefined,
            }),
          });
        } catch (messageError) {
          console.warn('Failed to record model switch message:', messageError);
        }

        loadCliStatuses();
      } catch (error) {
        console.error('Failed to update model preference:', error);
        updatePreferredCli(previousCli);
        updateSelectedModel(previousModel, previousCli);
        alert('Failed to update model. Please try again.');
      } finally {
        setIsUpdatingModel(false);
      }
    },
    [projectId, preferredCli, selectedModel, conversationId, loadCliStatuses, persistProjectPreferences, updatePreferredCli, updateSelectedModel]
  );

  useEffect(() => {
    loadCliStatuses();
  }, [loadCliStatuses]);

  const handleCliChange = useCallback(
    async (cliId: string) => {
      if (!projectId) return;
      if (cliId === preferredCli) return;

      setUsingGlobalDefaults(false);

      const candidateModels = modelOptions.filter(option => option.cli === cliId);
      const fallbackOption =
        candidateModels.find(option => option.id === selectedModel && option.available) ||
        candidateModels.find(option => option.available) ||
        candidateModels[0];

      if (fallbackOption) {
        await handleModelChange(fallbackOption, { overrideCli: cliId });
        return;
      }

      const previousCli = preferredCli;
      const previousModel = selectedModel;
      setIsUpdatingModel(true);

      try {
        updatePreferredCli(cliId);
        const defaultModel = getDefaultModelForCli(cliId);
        updateSelectedModel(defaultModel, cliId);
        await persistProjectPreferences({ preferredCli: cliId, selectedModel: defaultModel });
        loadCliStatuses();
      } catch (error) {
        console.error('Failed to update CLI preference:', error);
        updatePreferredCli(previousCli);
        updateSelectedModel(previousModel, previousCli);
        alert('Failed to update CLI. Please try again.');
      } finally {
        setIsUpdatingModel(false);
      }
    },
    [projectId, preferredCli, selectedModel, modelOptions, handleModelChange, loadCliStatuses, persistProjectPreferences, updatePreferredCli, updateSelectedModel]
  );

  useEffect(() => {
    if (!modelOptions.length) return;
    const hasSelected = modelOptions.some(option => option.cli === preferredCli && option.id === selectedModel);
    if (!hasSelected) {
      const fallbackOption = modelOptions.find(option => option.cli === preferredCli && option.available)
        || modelOptions.find(option => option.cli === preferredCli)
        || modelOptions.find(option => option.available)
        || modelOptions[0];
      if (fallbackOption) {
        void handleModelChange(fallbackOption);
      }
    }
  }, [modelOptions, preferredCli, selectedModel, handleModelChange]);

  const loadDeployStatus = useCallback(async () => {
    try {
      // Use the same API as ServiceSettings to check actual project service connections
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/services`);
      if (response.status === 404) {
        setGithubConnected(false);
        setVercelConnected(false);
        setPublishedUrl(null);
        setDeploymentStatus('idle');
        return;
      }

      if (response.ok) {
        const connections = await response.json();
        const githubConnection = connections.find((conn: any) => conn.provider === 'github');
        const vercelConnection = connections.find((conn: any) => conn.provider === 'vercel');

        // Check actual project connections (not just token existence)
        setGithubConnected(!!githubConnection);
        setVercelConnected(!!vercelConnection);

        // Set published URL only if actually deployed
        if (vercelConnection && vercelConnection.service_data) {
          const sd = vercelConnection.service_data;
          // Only use actual deployment URLs, not predicted ones
          const rawUrl = sd.last_deployment_url || null;
          const url = rawUrl ? (String(rawUrl).startsWith('http') ? String(rawUrl) : `https://${rawUrl}`) : null;
          setPublishedUrl(url || null);
          if (url) {
            setDeploymentStatus('ready');
          } else {
            setDeploymentStatus('idle');
          }
        } else {
          setPublishedUrl(null);
          setDeploymentStatus('idle');
        }
      } else {
        setGithubConnected(false);
        setVercelConnected(false);
        setPublishedUrl(null);
        setDeploymentStatus('idle');
      }

    } catch (e) {
      console.warn('Failed to load deploy status', e);
      setGithubConnected(false);
      setVercelConnected(false);
      setPublishedUrl(null);
      setDeploymentStatus('idle');
    }
  }, [projectId]);

  const startDeploymentPolling = useCallback((depId: string) => {
    if (deployPollRef.current) clearInterval(deployPollRef.current);
    setDeploymentStatus('deploying');
    setDeploymentId(depId);

    console.log('🔍 Monitoring deployment:', depId);

    deployPollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/api/projects/${projectId}/vercel/deployment/current`);
        if (r.status === 404) {
          setDeploymentStatus('idle');
          setDeploymentId(null);
          setPublishLoading(false);
          if (deployPollRef.current) {
            clearInterval(deployPollRef.current);
            deployPollRef.current = null;
          }
          return;
        }
        if (!r.ok) return;
        const data = await r.json();

        // Stop polling if no active deployment (completed)
        if (!data.has_deployment) {
          console.log('🔍 Deployment completed - no active deployment');

          // Set final deployment URL
          if (data.last_deployment_url) {
            const url = String(data.last_deployment_url).startsWith('http') ? data.last_deployment_url : `https://${data.last_deployment_url}`;
            console.log('🔍 Deployment complete! URL:', url);
            setPublishedUrl(url);
            setDeploymentStatus('ready');
          } else {
            setDeploymentStatus('idle');
          }

          // End publish loading state (important: release loading even if no deployment)
          setPublishLoading(false);

          if (deployPollRef.current) {
            clearInterval(deployPollRef.current);
            deployPollRef.current = null;
          }
          return;
        }

        // If there is an active deployment
        const status = data.status;

        // Log only status changes
        if (status && status !== 'QUEUED') {
          console.log('🔍 Deployment status:', status);
        }

        // Check if deployment is ready or failed
        const isReady = status === 'READY';
        const isBuilding = status === 'BUILDING' || status === 'QUEUED';
        const isError = status === 'ERROR';

        if (isError) {
          console.error('🔍 Deployment failed:', status);
          setDeploymentStatus('error');

          // End publish loading state
          setPublishLoading(false);

          // Close publish panel after error (with delay to show error message)
          setTimeout(() => {
            setShowPublishPanel(false);
          }, 3000); // Show error for 3 seconds before closing

          if (deployPollRef.current) {
            clearInterval(deployPollRef.current);
            deployPollRef.current = null;
          }
          return;
        }

        if (isReady && data.deployment_url) {
          const url = String(data.deployment_url).startsWith('http') ? data.deployment_url : `https://${data.deployment_url}`;
          console.log('🔍 Deployment complete! URL:', url);
          setPublishedUrl(url);
          setDeploymentStatus('ready');

          // End publish loading state
          setPublishLoading(false);

          // Keep panel open to show the published URL

          if (deployPollRef.current) {
            clearInterval(deployPollRef.current);
            deployPollRef.current = null;
          }
        } else if (isBuilding) {
          setDeploymentStatus('deploying');
        }
      } catch (error) {
        console.error('🔍 Polling error:', error);
      }
    }, 1000); // Changed to 1 second interval
  }, [projectId]);

  const checkCurrentDeployment = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/vercel/deployment/current`);
      if (response.status === 404) {
        return;
      }

      if (response.ok) {
        const data = await response.json();
        if (data.has_deployment) {
          setDeploymentId(data.deployment_id);
          setDeploymentStatus('deploying');
          setPublishLoading(false);
          setShowPublishPanel(true);
          startDeploymentPolling(data.deployment_id);
          console.log('🔍 Resuming deployment monitoring:', data.deployment_id);
        }
      }
    } catch (e) {
      console.warn('Failed to check current deployment', e);
    }
  }, [projectId, startDeploymentPolling]);

  const readPreviewValidationStatus = useCallback(async (): Promise<PreviewValidationState> => {
    return previewValidationState;
  }, [previewValidationState]);

  const start = useCallback(async (options: { requireValidation?: boolean } = {}) => {
    try {
      setIsStartingPreview(true);
      setPreviewInitializationMessage(
        options.requireValidation ? '正在检查路线看板生成状态...' : '正在启动预览服务...'
      );

      if (options.requireValidation) {
        const validationState = await readPreviewValidationStatus();
        if (validationState !== 'passed') {
          setPreviewInitializationMessage(
            validationState === 'failed'
              ? '路线看板校验未通过，暂不展示预览。'
              : '路线看板尚未生成完成，暂不展示预览。'
          );
          setIsStartingPreview(false);
          return;
        }
      }

      // Simulate progress updates
      setTimeout(() => setPreviewInitializationMessage('正在检查依赖...'), 1000);
      setTimeout(() => setPreviewInitializationMessage('正在构建和验证看板...'), 2500);

      const r = await fetch(`${API_BASE}/api/projects/${projectId}/preview/start`, { method: 'POST' });
      if (!r.ok) {
        let errorMessage = r.statusText || '预览启动失败';
        try {
          const payload = await r.json();
          if (typeof payload?.error === 'string' && payload.error.trim()) {
            errorMessage = payload.error.trim();
          }
        } catch {
          // 响应体不是 JSON 时使用 HTTP 状态文本。
        }
        console.warn('[Preview] start failed:', errorMessage);
        setPreviewInitializationMessage(`预览启动失败：${errorMessage}`);
        setTimeout(() => setIsStartingPreview(false), 2000);
        return;
      }
      const payload = await r.json();
      const data = payload?.data ?? payload ?? {};
      const nextPreviewUrl =
        typeof data.url === 'string'
          ? data.url
          : typeof data.previewUrl === 'string'
          ? data.previewUrl
          : typeof payload?.url === 'string'
          ? payload.url
          : typeof payload?.previewUrl === 'string'
          ? payload.previewUrl
          : null;

      setPreviewInitializationMessage('预览已就绪');
      setTimeout(() => {
        setPreviewUrl(nextPreviewUrl);
        setIsStartingPreview(false);
        setCurrentRoute('/'); // Reset to root route when starting
      }, 1000);
    } catch (error) {
      console.warn('[Preview] start request failed:', error);
      setPreviewInitializationMessage('预览启动异常');
      setTimeout(() => setIsStartingPreview(false), 2000);
    }
  }, [projectId, readPreviewValidationStatus]);

  // Navigate to specific route in iframe
  const navigateToRoute = (route: string) => {
    if (previewUrl && iframeRef.current) {
      const baseUrl = previewUrl.split('?')[0]; // Remove any query params
      // Ensure route starts with /
      const normalizedRoute = route.startsWith('/') ? route : `/${route}`;
      const newUrl = `${baseUrl}${normalizedRoute}`;
      iframeRef.current.src = newUrl;
      setCurrentRoute(normalizedRoute);
    }
  };

  const refreshPreview = useCallback(() => {
    if (!previewUrl || !iframeRef.current) {
      return;
    }

    try {
      const normalizedRoute =
        currentRoute && currentRoute.startsWith('/')
          ? currentRoute
          : `/${currentRoute || ''}`;
      const baseUrl = previewUrl.split('?')[0] || previewUrl;
      const url = new URL(baseUrl + normalizedRoute);
      url.searchParams.set('_ts', Date.now().toString());
      iframeRef.current.src = url.toString();
    } catch (error) {
      console.warn('Failed to refresh preview iframe:', error);
    }
  }, [previewUrl, currentRoute]);


  const stop = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/projects/${projectId}/preview/stop`, { method: 'POST' });
      setPreviewUrl(null);
    } catch (error) {
      console.error('Error stopping preview:', error);
    }
  }, [projectId]);

  const loadSubdirectory = useCallback(async (dir: string): Promise<Entry[]> => {
    try {
      const r = await fetch(`${API_BASE}/api/repo/${projectId}/tree?dir=${encodeURIComponent(dir)}`);
      const data = await r.json();
      return Array.isArray(data) ? data : [];
    } catch (error) {
      console.error('Failed to load subdirectory:', error);
      return [];
    }
  }, [projectId]);

  const loadTree = useCallback(async (dir = '.') => {
    try {
      const r = await fetch(`${API_BASE}/api/repo/${projectId}/tree?dir=${encodeURIComponent(dir)}`);
      const data = await r.json();

      // Ensure data is an array
      if (Array.isArray(data)) {
        setTree(data);

        // Load contents for all directories in the root
        const newFolderContents = new Map();

        // Process each directory
        for (const entry of data) {
          if (entry.type === 'dir') {
            try {
              const subContents = await loadSubdirectory(entry.path);
              newFolderContents.set(entry.path, subContents);
            } catch (err) {
              console.error(`Failed to load contents for ${entry.path}:`, err);
            }
          }
        }

        setFolderContents(newFolderContents);
      } else {
        console.error('Tree data is not an array:', data);
        setTree([]);
      }

      setCurrentPath(dir);
    } catch (error) {
      console.error('Failed to load tree:', error);
      setTree([]);
    }
  }, [projectId, loadSubdirectory]);

  const loadTravelItinerary = useCallback(async () => {
    if (!projectId) return;
    try {
      const params = new URLSearchParams({
        path: 'data_file/final/itinerary-data.json',
        ts: Date.now().toString(),
      });
      const response = await fetch(
        `${API_BASE}/api/projects/${projectId}/artifact?${params.toString()}`,
        { cache: 'no-store' },
      );
      if (!response.ok) {
        setTravelItinerary(null);
        return;
      }
      const data = await response.json();
      setTravelItinerary(data);
    } catch (error) {
      console.warn('Failed to load travel itinerary artifact:', error);
      setTravelItinerary(null);
    }
  }, [projectId]);

  const scheduleTravelItineraryRefresh = useCallback(() => {
    void loadTravelItinerary();
    const timers = [350, 1200, 2500].map((delay) =>
      window.setTimeout(() => {
        void loadTravelItinerary();
      }, delay),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [loadTravelItinerary]);

  useEffect(() => {
    void loadTravelItinerary();
  }, [loadTravelItinerary]);

  // Load subdirectory contents

  // Load folder contents
  const handleLoadFolder = useCallback(async (path: string) => {
    const contents = await loadSubdirectory(path);
    setFolderContents(prev => {
      const newMap = new Map(prev);
      newMap.set(path, contents);

      // Also load nested directories
      for (const entry of contents) {
        if (entry.type === 'dir') {
          const fullPath = `${path}/${entry.path}`;
          // Don't load if already loaded
          if (!newMap.has(fullPath)) {
            loadSubdirectory(fullPath).then(subContents => {
              setFolderContents(prev2 => new Map(prev2).set(fullPath, subContents));
            });
          }
        }
      }

      return newMap;
    });
  }, [loadSubdirectory]);

  // Toggle folder expansion
  function toggleFolder(path: string) {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(path)) {
        newSet.delete(path);
      } else {
        newSet.add(path);
      }
      return newSet;
    });
  }

  // Build tree structure from flat list
  function buildTreeStructure(entries: Entry[]): Map<string, Entry[]> {
    const structure = new Map<string, Entry[]>();

    // Initialize with root
    structure.set('', []);

    entries.forEach(entry => {
      const parts = entry.path.split('/');
      const parentPath = parts.slice(0, -1).join('/');

      if (!structure.has(parentPath)) {
        structure.set(parentPath, []);
      }
      structure.get(parentPath)?.push(entry);

      // If it's a directory, ensure it exists in the structure
      if (entry.type === 'dir') {
        if (!structure.has(entry.path)) {
          structure.set(entry.path, []);
        }
      }
    });

    return structure;
  }

  const openFile = useCallback(async (path: string) => {
    try {
      if (hasUnsavedChanges && path !== selectedFile) {
        const shouldDiscard =
          typeof window !== 'undefined'
            ? window.confirm('You have unsaved changes. Discard them and open the new file?')
            : true;
        if (!shouldDiscard) {
          return;
        }
      }

      setSaveFeedback('idle');
      setSaveError(null);

      const r = await fetch(`${API_BASE}/api/repo/${projectId}/file?path=${encodeURIComponent(path)}`);

      if (!r.ok) {
        console.error('Failed to load file:', r.status, r.statusText);
        const fallback = '// Failed to load file content';
        setContent(fallback);
        setEditedContent(fallback);
        editedContentRef.current = fallback;
        setHasUnsavedChanges(false);
        setSelectedFile(path);
        return;
      }

      const data = await r.json();
      const fileContent = typeof data?.content === 'string' ? data.content : '';
      setContent(fileContent);
      setEditedContent(fileContent);
      editedContentRef.current = fileContent;
      setHasUnsavedChanges(false);
      setSelectedFile(path);
      setIsFileUpdating(false);

      requestAnimationFrame(() => {
        if (editorRef.current) {
          editorRef.current.scrollTop = 0;
          editorRef.current.scrollLeft = 0;
        }
        if (highlightRef.current) {
          highlightRef.current.scrollTop = 0;
          highlightRef.current.scrollLeft = 0;
        }
        if (lineNumberRef.current) {
          lineNumberRef.current.scrollTop = 0;
        }
      });
    } catch (error) {
      console.error('Error opening file:', error);
      const fallback = '// Error loading file';
      setContent(fallback);
      setEditedContent(fallback);
      editedContentRef.current = fallback;
      setHasUnsavedChanges(false);
      setSelectedFile(path);
    }
  }, [projectId, hasUnsavedChanges, selectedFile]);

  // Reload currently selected file
  const reloadCurrentFile = useCallback(async () => {
    if (selectedFile && !showPreview && !hasUnsavedChanges) {
      try {
        const r = await fetch(`${API_BASE}/api/repo/${projectId}/file?path=${encodeURIComponent(selectedFile)}`);
        if (r.ok) {
          const data = await r.json();
          const newContent = data.content || '';
          if (newContent !== content) {
            setIsFileUpdating(true);
            setContent(newContent);
            setEditedContent(newContent);
            editedContentRef.current = newContent;
            setHasUnsavedChanges(false);
            setSaveFeedback('idle');
            setSaveError(null);
            setTimeout(() => setIsFileUpdating(false), 500);
          }
        }
      } catch (error) {
        // Silently fail - this is a background refresh
      }
    }
  }, [projectId, selectedFile, showPreview, hasUnsavedChanges, content]);

  const highlightedCode = useMemo(() => editedContent || ' ', [editedContent]);

  const onEditorChange = useCallback((event: ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    setEditedContent(value);
    editedContentRef.current = value;
    setHasUnsavedChanges(value !== content);
    setSaveFeedback('idle');
    setSaveError(null);
    if (isFileUpdating) {
      setIsFileUpdating(false);
    }
  }, [content, isFileUpdating]);

  const handleEditorScroll = useCallback((event: UIEvent<HTMLTextAreaElement>) => {
    const { scrollTop, scrollLeft } = event.currentTarget;
    if (highlightRef.current) {
      highlightRef.current.scrollTop = scrollTop;
      highlightRef.current.scrollLeft = scrollLeft;
    }
    if (lineNumberRef.current) {
      lineNumberRef.current.scrollTop = scrollTop;
    }
  }, []);

  const handleSaveFile = useCallback(async () => {
    if (!selectedFile || isSavingFile || !hasUnsavedChanges) {
      return;
    }

    const contentToSave = editedContentRef.current;
    setIsSavingFile(true);
    setSaveFeedback('idle');
    setSaveError(null);

    try {
      const response = await fetch(`${API_BASE}/api/repo/${projectId}/file`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedFile, content: contentToSave }),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to save file';
        try {
          const data = await response.clone().json();
          errorMessage = data?.error || data?.message || errorMessage;
        } catch {
          const text = await response.text().catch(() => '');
          if (text) {
            errorMessage = text;
          }
        }
        throw new Error(errorMessage);
      }

      setContent(contentToSave);
      setSaveFeedback('success');

      if (editedContentRef.current === contentToSave) {
        setHasUnsavedChanges(false);
        setIsFileUpdating(true);
        setTimeout(() => setIsFileUpdating(false), 800);
      }

      refreshPreview();
    } catch (error) {
      console.error('Failed to save file:', error);
      setSaveFeedback('error');
      setSaveError(error instanceof Error ? error.message : 'Failed to save file');
    } finally {
      setIsSavingFile(false);
    }
  }, [selectedFile, isSavingFile, hasUnsavedChanges, projectId, refreshPreview]);

  const handleEditorKeyDown = useCallback((event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      handleSaveFile();
      return;
    }

    if (event.key === 'Tab') {
      event.preventDefault();
      const el = event.currentTarget;
      const start = el.selectionStart ?? 0;
      const end = el.selectionEnd ?? 0;
      const indent = '  ';
      const value = editedContent;
      const newValue = value.slice(0, start) + indent + value.slice(end);

      setEditedContent(newValue);
      editedContentRef.current = newValue;
      setHasUnsavedChanges(newValue !== content);
      setSaveFeedback('idle');
      setSaveError(null);
      if (isFileUpdating) {
        setIsFileUpdating(false);
      }

      requestAnimationFrame(() => {
        const position = start + indent.length;
        el.selectionStart = position;
        el.selectionEnd = position;
        if (highlightRef.current) {
          highlightRef.current.scrollTop = el.scrollTop;
          highlightRef.current.scrollLeft = el.scrollLeft;
        }
        if (lineNumberRef.current) {
          lineNumberRef.current.scrollTop = el.scrollTop;
        }
      });
    }
  }, [handleSaveFile, editedContent, content, isFileUpdating]);

  useEffect(() => {
    if (saveFeedback === 'success') {
      const timer = setTimeout(() => setSaveFeedback('idle'), 1800);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [saveFeedback]);

  useEffect(() => {
    if (editorRef.current && highlightRef.current && lineNumberRef.current) {
      const { scrollTop, scrollLeft } = editorRef.current;
      highlightRef.current.scrollTop = scrollTop;
      highlightRef.current.scrollLeft = scrollLeft;
      lineNumberRef.current.scrollTop = scrollTop;
    }
  }, [editedContent]);

  // Get file extension for syntax highlighting
  function getFileLanguage(path: string): string {
    const ext = path.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'tsx':
      case 'ts':
        return 'typescript';
      case 'jsx':
      case 'js':
      case 'mjs':
        return 'javascript';
      case 'css':
        return 'css';
      case 'scss':
      case 'sass':
        return 'scss';
      case 'html':
      case 'htm':
        return 'html';
      case 'json':
        return 'json';
      case 'md':
      case 'markdown':
        return 'markdown';
      case 'py':
        return 'python';
      case 'sh':
      case 'bash':
        return 'bash';
      case 'yaml':
      case 'yml':
        return 'yaml';
      case 'xml':
        return 'xml';
      case 'sql':
        return 'sql';
      case 'php':
        return 'php';
      case 'java':
        return 'java';
      case 'c':
        return 'c';
      case 'cpp':
      case 'cc':
      case 'cxx':
        return 'cpp';
      case 'rs':
        return 'rust';
      case 'go':
        return 'go';
      case 'rb':
        return 'ruby';
      case 'vue':
        return 'vue';
      case 'svelte':
        return 'svelte';
      case 'dockerfile':
        return 'dockerfile';
      case 'toml':
        return 'toml';
      case 'ini':
        return 'ini';
      case 'conf':
      case 'config':
        return 'nginx';
      default:
        return 'plaintext';
    }
  }

  // Get file icon based on type
  function getFileIcon(entry: Entry): React.ReactElement {
    if (entry.type === 'dir') {
      return <span className="text-blue-500"><FaFolder size={16} /></span>;
    }

    const ext = entry.path.split('.').pop()?.toLowerCase();
    const filename = entry.path.split('/').pop()?.toLowerCase();

    // Special files
    if (filename === 'package.json') return <span className="text-green-600"><VscJson size={16} /></span>;
    if (filename === 'dockerfile') return <span className="text-blue-400"><FaDocker size={16} /></span>;
    if (filename?.startsWith('.env')) return <span className="text-yellow-500"><FaLock size={16} /></span>;
    if (filename === 'readme.md') return <span className="text-slate-600"><FaMarkdown size={16} /></span>;
    if (filename?.includes('config')) return <span className="text-slate-500"><FaCog size={16} /></span>;

    switch (ext) {
      case 'tsx':
        return <span className="text-cyan-400"><FaReact size={16} /></span>;
      case 'ts':
        return <span className="text-blue-600"><SiTypescript size={16} /></span>;
      case 'jsx':
        return <span className="text-cyan-400"><FaReact size={16} /></span>;
      case 'js':
      case 'mjs':
        return <span className="text-yellow-400"><FaJs size={16} /></span>;
      case 'css':
        return <span className="text-blue-500"><FaCss3Alt size={16} /></span>;
      case 'scss':
      case 'sass':
        return <span className="text-pink-500"><FaCss3Alt size={16} /></span>;
      case 'html':
      case 'htm':
        return <span className="text-orange-500"><FaHtml5 size={16} /></span>;
      case 'json':
        return <span className="text-yellow-600"><VscJson size={16} /></span>;
      case 'md':
      case 'markdown':
        return <span className="text-slate-600"><FaMarkdown size={16} /></span>;
      case 'py':
        return <span className="text-blue-400"><FaPython size={16} /></span>;
      case 'sh':
      case 'bash':
        return <span className="text-green-500"><FaFileCode size={16} /></span>;
      case 'yaml':
      case 'yml':
        return <span className="text-red-500"><SiYaml size={16} /></span>;
      case 'xml':
        return <span className="text-orange-600"><FaFileCode size={16} /></span>;
      case 'sql':
        return <span className="text-blue-600"><FaDatabase size={16} /></span>;
      case 'php':
        return <span className="text-indigo-500"><FaPhp size={16} /></span>;
      case 'java':
        return <span className="text-red-600"><FaJava size={16} /></span>;
      case 'c':
        return <span className="text-blue-700"><FaFileCode size={16} /></span>;
      case 'cpp':
      case 'cc':
      case 'cxx':
        return <span className="text-blue-600"><SiCplusplus size={16} /></span>;
      case 'rs':
        return <span className="text-orange-700"><FaRust size={16} /></span>;
      case 'go':
        return <span className="text-cyan-500"><SiGo size={16} /></span>;
      case 'rb':
        return <span className="text-red-500"><SiRuby size={16} /></span>;
      case 'vue':
        return <span className="text-green-500"><FaVuejs size={16} /></span>;
      case 'svelte':
        return <span className="text-orange-600"><SiSvelte size={16} /></span>;
      case 'dockerfile':
        return <span className="text-blue-400"><FaDocker size={16} /></span>;
      case 'toml':
      case 'ini':
      case 'conf':
      case 'config':
        return <span className="text-slate-500"><FaCog size={16} /></span>;
      default:
        return <span className="text-slate-400"><FaFile size={16} /></span>;
    }
  }

  // Ensure we only trigger dependency installation once per page lifecycle
  const installTriggeredRef = useRef(false);

  const startDependencyInstallation = useCallback(async () => {
    if (installTriggeredRef.current) {
      return;
    }
    installTriggeredRef.current = true;
    try {
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/install-dependencies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.warn('⚠️ Failed to start dependency installation:', errorText);
        // allow retry on next attempt if initial trigger failed
        installTriggeredRef.current = false;
      }
    } catch (error) {
      console.error('❌ Error starting dependency installation:', error);
      // allow retry if network error
      installTriggeredRef.current = false;
    }
  }, [projectId]);

  const loadSettings = useCallback(async (projectSettings?: { cli?: string; model?: string }) => {
    try {
      console.log('🔧 loadSettings called with project settings:', projectSettings);

      const hasCliSet = projectSettings?.cli || preferredCli;
      const hasModelSet = projectSettings?.model || selectedModel;

      if (!hasCliSet || !hasModelSet) {
        console.log('⚠️ Missing CLI or model, loading global settings');
        const globalResponse = await fetch(`${API_BASE}/api/settings/global`);
        if (globalResponse.ok) {
          const globalSettings = await globalResponse.json();
          const defaultCli = sanitizeCli(globalSettings.default_cli || globalSettings.defaultCli);
          const cliToUse = sanitizeCli(hasCliSet || defaultCli);

          if (!hasCliSet) {
            console.log('🔄 Setting CLI from global:', cliToUse);
            updatePreferredCli(cliToUse);
          }

          if (!hasModelSet) {
            const cliSettings = globalSettings.cli_settings?.[cliToUse] || globalSettings.cliSettings?.[cliToUse];
            if (cliSettings?.model) {
              updateSelectedModel(cliSettings.model, cliToUse);
            } else {
              updateSelectedModel(getDefaultModelForCli(cliToUse), cliToUse);
            }
          }
        } else {
          const response = await fetch(`${API_BASE}/api/settings`);
          if (response.ok) {
            const settings = await response.json();
            if (!hasCliSet) updatePreferredCli(settings.preferred_cli || settings.default_cli || DEFAULT_ACTIVE_CLI);
            if (!hasModelSet) {
              const cli = sanitizeCli(settings.preferred_cli || settings.default_cli || preferredCli || DEFAULT_ACTIVE_CLI);
              updateSelectedModel(getDefaultModelForCli(cli), cli);
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
      const hasCliSet = projectSettings?.cli || preferredCli;
      const hasModelSet = projectSettings?.model || selectedModel;
      if (!hasCliSet) updatePreferredCli(DEFAULT_ACTIVE_CLI);
      if (!hasModelSet) updateSelectedModel(getDefaultModelForCli(DEFAULT_ACTIVE_CLI), DEFAULT_ACTIVE_CLI);
    }
  }, [preferredCli, selectedModel, updatePreferredCli, updateSelectedModel]);

  const loadProjectInfo = useCallback(async (): Promise<{ cli?: string; model?: string; status?: ProjectStatus }> => {
    try {
      const r = await fetch(`${API_BASE}/api/projects/${projectId}`);
      if (!r.ok) {
        setProjectName(`Project ${projectId.slice(0, 8)}`);
        setProjectDescription('');
        setHasInitialPrompt(false);
        localStorage.setItem(`project_${projectId}_hasInitialPrompt`, 'false');
        setProjectStatus('active');
        setIsInitializing(false);
        setUsingGlobalDefaults(true);
        return {};
      }

      const payload = await r.json();
      const project = payload?.data ?? payload;
      const rawPreferredCli =
        typeof project?.preferredCli === 'string'
          ? project.preferredCli
          : typeof project?.preferred_cli === 'string'
          ? project.preferred_cli
          : undefined;
      const rawSelectedModel =
        typeof project?.selectedModel === 'string'
          ? project.selectedModel
          : typeof project?.selected_model === 'string'
          ? project.selected_model
          : undefined;

      console.log('📋 Loading project info:', {
        preferredCli: rawPreferredCli,
        selectedModel: rawSelectedModel,
      });

      setProjectName(project.name || `Project ${projectId.slice(0, 8)}`);

      const projectCli = sanitizeCli(rawPreferredCli || preferredCli);
      if (rawPreferredCli) {
        updatePreferredCli(projectCli);
      }
      if (rawSelectedModel) {
        updateSelectedModel(rawSelectedModel, projectCli);
      } else {
        updateSelectedModel(getDefaultModelForCli(projectCli), projectCli);
      }

      const followGlobal = !rawPreferredCli && !rawSelectedModel;
      setUsingGlobalDefaults(followGlobal);
      setProjectDescription(project.description || '');
      const loadedPreviewUrl =
        typeof project.previewUrl === 'string'
          ? project.previewUrl
          : typeof project.preview_url === 'string'
          ? project.preview_url
          : typeof project.url === 'string'
          ? project.url
          : null;
      const validationState = await readPreviewValidationStatus();
      if (validationState === 'passed' || loadedPreviewUrl) {
        setAgentWorkComplete(true);
        localStorage.setItem(`project_${projectId}_taskComplete`, 'true');
        setPreviewUrl(loadedPreviewUrl);
      } else {
        setPreviewUrl(null);
        if (validationState === 'failed') {
          setPreviewInitializationMessage('路线看板校验未通过，暂不展示预览。');
        }
      }

      if (project.initial_prompt) {
        setHasInitialPrompt(true);
        localStorage.setItem(`project_${projectId}_hasInitialPrompt`, 'true');
      } else {
        setHasInitialPrompt(false);
        localStorage.setItem(`project_${projectId}_hasInitialPrompt`, 'false');
      }

      if (project.status === 'initializing') {
        setProjectStatus('initializing');
        setIsInitializing(true);
      } else {
        setProjectStatus('active');
        setIsInitializing(false);
        startDependencyInstallation();
        triggerInitialPromptIfNeeded();
      }

      const normalizedModel = rawSelectedModel
        ? sanitizeModel(projectCli, rawSelectedModel)
        : getDefaultModelForCli(projectCli);

      return {
        cli: rawPreferredCli ? projectCli : undefined,
        model: normalizedModel,
        status: project.status as ProjectStatus | undefined,
      };
    } catch (error) {
      console.error('Failed to load project info:', error);
      setProjectName(`Project ${projectId.slice(0, 8)}`);
      setProjectDescription('');
      setHasInitialPrompt(false);
      localStorage.setItem(`project_${projectId}_hasInitialPrompt`, 'false');
      setProjectStatus('active');
      setIsInitializing(false);
      setUsingGlobalDefaults(true);
      return {};
    }
  }, [
    projectId,
    readPreviewValidationStatus,
    startDependencyInstallation,
    triggerInitialPromptIfNeeded,
    updatePreferredCli,
    updateSelectedModel,
    preferredCli,
  ]);

  const loadProjectInfoRef = useRef(loadProjectInfo);
  useEffect(() => {
    loadProjectInfoRef.current = loadProjectInfo;
  }, [loadProjectInfo]);

  useEffect(() => {
    if (!searchParams) return;
    const cliParam = searchParams.get('cli');
    const modelParam = searchParams.get('model');
    if (!cliParam && !modelParam) {
      return;
    }
    const sanitizedCli = cliParam ? sanitizeCli(cliParam) : preferredCli;
    if (cliParam) {
      setUsingGlobalDefaults(false);
      updatePreferredCli(sanitizedCli);
    }
    if (modelParam) {
      setUsingGlobalDefaults(false);
      updateSelectedModel(modelParam, sanitizedCli);
    }
  }, [searchParams, preferredCli, updatePreferredCli, updateSelectedModel, setUsingGlobalDefaults]);

  const loadSettingsRef = useRef(loadSettings);
  useEffect(() => {
    loadSettingsRef.current = loadSettings;
  }, [loadSettings]);

  const loadTreeRef = useRef(loadTree);
  useEffect(() => {
    loadTreeRef.current = loadTree;
  }, [loadTree]);

  const loadTravelItineraryRef = useRef(loadTravelItinerary);
  useEffect(() => {
    loadTravelItineraryRef.current = loadTravelItinerary;
  }, [loadTravelItinerary]);

  const loadDeployStatusRef = useRef(loadDeployStatus);
  useEffect(() => {
    loadDeployStatusRef.current = loadDeployStatus;
  }, [loadDeployStatus]);

  const checkCurrentDeploymentRef = useRef(checkCurrentDeployment);
  useEffect(() => {
    checkCurrentDeploymentRef.current = checkCurrentDeployment;
  }, [checkCurrentDeployment]);

  // Stable message handlers with useCallback to prevent reassignment
  const createStableMessageHandlers = useCallback(() => {
    const addMessage = (message: any) => {
      console.log('🔄 [StableHandler] Adding message via stable handler:', {
        messageId: message.id,
        role: message.role,
        isOptimistic: message.isOptimistic,
        requestId: message.requestId
      });

      // Track optimistic messages by requestId
      if (message.isOptimistic && message.requestId) {
        optimisticMessagesRef.current.set(message.requestId, message);
        console.log('🔄 [StableHandler] Tracking optimistic message:', {
          requestId: message.requestId,
          tempId: message.id
        });
      }

      // Also call the current handlers if they exist
      if (messageHandlersRef.current) {
        messageHandlersRef.current.add(message);
      }
    };

    const removeMessage = (messageId: string) => {
      console.log('🔄 [StableHandler] Removing message via stable handler:', messageId);

      // Remove from optimistic messages tracking if it's an optimistic message
      const optimisticMessage = Array.from(optimisticMessagesRef.current.values())
        .find(msg => msg.id === messageId);
      if (optimisticMessage && optimisticMessage.requestId) {
        optimisticMessagesRef.current.delete(optimisticMessage.requestId);
        console.log('🔄 [StableHandler] Removed optimistic message tracking:', {
          requestId: optimisticMessage.requestId,
          tempId: messageId
        });
      }

      // Also call the current handlers if they exist
      if (messageHandlersRef.current) {
        messageHandlersRef.current.remove(messageId);
      }
    };

    return { add: addMessage, remove: removeMessage };
  }, []);

  // Initialize stable handlers once
  useEffect(() => {
    stableMessageHandlers.current = createStableMessageHandlers();
    const optimisticMessages = optimisticMessagesRef.current;

    return () => {
      stableMessageHandlers.current = null;
      optimisticMessages.clear();
    };
  }, [createStableMessageHandlers]);

  // Handle image upload with base64 conversion
  const handleImageUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files) {
      Array.from(files).forEach(file => {
        if (file.type.startsWith('image/')) {
          const url = URL.createObjectURL(file);

          // Convert to base64
          const reader = new FileReader();
          reader.onload = (e) => {
            const base64 = e.target?.result as string;
            setUploadedImages(prev => [...prev, {
              name: file.name,
              url,
              base64
            }]);
          };
          reader.readAsDataURL(file);
        }
      });
    }
  };

  // Remove uploaded image
  const removeUploadedImage = (index: number) => {
    setUploadedImages(prev => {
      const newImages = [...prev];
      URL.revokeObjectURL(newImages[index].url);
      newImages.splice(index, 1);
      return newImages;
    });
  };

  async function runAct(messageOverride?: string, externalImages?: any[]) {
    const visibleMessage = (messageOverride || prompt).trim();
    let finalMessage = visibleMessage;
    const imagesToUse = externalImages || uploadedImages;

    if (!finalMessage.trim() && imagesToUse.length === 0) {
      alert('Please enter a task description or upload an image.');
      return;
    }

    if (mode === 'chat') {
      finalMessage = finalMessage + "\n\nDo not modify code, only answer to the user's request.";
    }

    // Create request fingerprint for deduplication
    const requestFingerprint = JSON.stringify({
      message: visibleMessage,
      imageCount: imagesToUse.length,
      cliPreference: preferredCli,
      model: selectedModel,
      mode
    });

    // Check for duplicate pending requests
    if (pendingRequestsRef.current.has(requestFingerprint)) {
      console.log('🔄 [DEBUG] Duplicate request detected, skipping:', requestFingerprint);
      return;
    }

    setIsRunning(true);
    setPreviewInitializationMessage('正在准备数据和可视化看板，验证通过后自动展示...');
    const requestId = crypto.randomUUID();
    let tempUserMessageId: string | null = null;
    const tempProgressMessageIds: string[] = [];
    const clearProgressMessages = () => {
      while (tempProgressMessageIds.length > 0) {
        const id = tempProgressMessageIds.pop();
        if (!id) continue;
        if (stableMessageHandlers.current) {
          stableMessageHandlers.current.remove(id);
        } else if (messageHandlersRef.current) {
          messageHandlersRef.current.remove(id);
        }
      }
    };

    // Add to pending requests
    pendingRequestsRef.current.add(requestFingerprint);

    try {
      const uploadImageFromBase64 = async (img: { base64: string; name?: string }) => {
        const base64String = img.base64;
        const match = base64String.match(/^data:(.*?);base64,(.*)$/);
        const mimeType = match && match[1] ? match[1] : 'image/png';
        const base64Data = match && match[2] ? match[2] : base64String;

        const byteString = atob(base64Data);
        const buffer = new Uint8Array(byteString.length);
        for (let i = 0; i < byteString.length; i += 1) {
          buffer[i] = byteString.charCodeAt(i);
        }

        const extension = (() => {
          if (mimeType.includes('png')) return 'png';
          if (mimeType.includes('jpeg') || mimeType.includes('jpg')) return 'jpg';
          if (mimeType.includes('gif')) return 'gif';
          if (mimeType.includes('webp')) return 'webp';
          if (mimeType.includes('svg')) return 'svg';
          return 'png';
        })();

        const inferredName = img.name && img.name.trim().length > 0 ? img.name.trim() : `image-${crypto.randomUUID()}.${extension}`;
        const hasExtension = /\.[a-zA-Z0-9]+$/.test(inferredName);
        const filename = hasExtension ? inferredName : `${inferredName}.${extension}`;

        const file = new File([buffer], filename, { type: mimeType });
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/api/assets/${projectId}/upload`, {
          method: 'POST',
          body: formData
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Upload failed');
        }

        const result = await response.json();
        return {
          name: result.filename || filename,
          path: result.absolute_path,
          url: `/api/assets/${projectId}/${result.filename}`,
          public_url: typeof result.public_url === 'string' ? result.public_url : undefined,
          publicUrl: typeof result.public_url === 'string' ? result.public_url : undefined,
        };
      };

      console.log('🖼️ Processing images in runAct:', {
          imageCount: imagesToUse.length,
          cli: preferredCli,
          requestId
        });
      const processedImages: { name: string; path: string; url?: string; public_url?: string; publicUrl?: string }[] = [];

      for (let i = 0; i < imagesToUse.length; i += 1) {
        const image = imagesToUse[i];
        console.log(`🖼️ Processing image ${i}:`, {
          id: image.id,
          filename: image.filename,
          hasPath: !!image.path,
          hasPublicUrl: !!image.publicUrl,
          hasAssetUrl: !!image.assetUrl
        });
        if (image?.path) {
          const name = image.filename || image.name || `Image ${i + 1}`;
          const candidateUrl = typeof image.assetUrl === 'string' ? image.assetUrl : undefined;
          const candidatePublicUrl = typeof image.publicUrl === 'string' ? image.publicUrl : undefined;
          const processedImage = {
            name,
            path: image.path,
            url: candidateUrl && candidateUrl.startsWith('/') ? candidateUrl : undefined,
            public_url: candidatePublicUrl,
            publicUrl: candidatePublicUrl,
          };
          console.log(`🖼️ Created processed image ${i}:`, processedImage);
          processedImages.push(processedImage);
          continue;
        }

        if (image?.base64) {
          try {
            const uploaded = await uploadImageFromBase64({ base64: image.base64, name: image.name });
            processedImages.push(uploaded);
          } catch (uploadError) {
            console.error('Image upload failed:', uploadError);
            alert('Failed to upload image. Please try again.');
            setIsRunning(false);
            // Remove from pending requests
            pendingRequestsRef.current.delete(requestFingerprint);
            return;
          }
        }
      }

      const requestBody = {
        instruction: finalMessage,
        displayInstruction: visibleMessage,
        images: processedImages,
        isInitialPrompt: mode === 'act' && !travelItinerary,
        travelCapabilityId: 'mixed_food_route',
        cliPreference: preferredCli,
        conversationId: conversationId || undefined,
        requestId: `${requestId}-progress`,
        selectedModel,
      };

      console.log('📸 Sending request to act API:', {
        messageLength: finalMessage.length,
        imageCount: processedImages.length,
        cli: preferredCli,
        requestId,
        images: processedImages.map(img => ({
          name: img.name,
          hasPath: !!img.path,
          hasUrl: !!img.url,
          hasPublicUrl: !!img.publicUrl
        }))
      });

      // Optimistically add user message to UI BEFORE API call for instant feedback
      tempUserMessageId = requestId + '-user-temp';
      if (messageHandlersRef.current) {
        const optimisticUserMessage = {
          id: tempUserMessageId,
          projectId: projectId,
          role: 'user' as const,
          messageType: 'chat' as const,
          content: visibleMessage,
          conversationId: conversationId || null,
          requestId: requestId,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          isStreaming: false,
          isFinal: false,
          isOptimistic: true,
          metadata:
            processedImages.length > 0
              ? {
                  attachments: processedImages.map((img) => ({
                    name: img.name,
                    path: img.path,
                    url: img.url,
                    publicUrl: img.publicUrl ?? img.public_url,
                  })),
                }
              : undefined,
        };
        console.log('🔄 [Optimistic] Adding optimistic user message via stable handler:', {
          tempId: tempUserMessageId,
          requestId,
          content: finalMessage.substring(0, 50) + '...'
        });

        // Use stable handlers instead of direct messageHandlersRef to prevent reassignment issues
        if (stableMessageHandlers.current) {
          stableMessageHandlers.current.add(optimisticUserMessage);
        } else if (messageHandlersRef.current) {
          // Fallback to direct handlers if stable handlers aren't ready yet
          messageHandlersRef.current.add(optimisticUserMessage);
        }
      }

      const addLocalProgressMessage = (content: string, step: number, isFinalStep = false) => {
        const now = new Date().toISOString();
        const id = `${requestId}-travel-progress-step-${step}-${isFinalStep ? 'done' : 'running'}`;
        const displayContent = step === 0
          ? '旅游规划任务已提交，等待路线结果...'
          : content;
        tempProgressMessageIds.push(id);
        const message = {
          id,
          projectId,
          role: 'assistant' as const,
          messageType: 'chat' as const,
          content: displayContent,
          conversationId: conversationId || null,
          requestId: `${requestId}-progress-step-${step}-${isFinalStep ? 'done' : 'running'}`,
          createdAt: now,
          updatedAt: now,
          isStreaming: !isFinalStep,
          isFinal: isFinalStep,
          isOptimistic: true,
          metadata: {
            type: 'travel_progress',
            step,
            localOnly: true,
          },
        };
        if (stableMessageHandlers.current) {
          stableMessageHandlers.current.add(message);
        } else if (messageHandlersRef.current) {
          messageHandlersRef.current.add(message);
        }
      };

      const wait = (_ms: number) => Promise.resolve();
      const planningSteps = [
        ['需求解析', '正在识别区域、时长、预算、餐饮、少走路/少排队等约束', '已识别本轮需求和约束'],
        ['本地数据检索', '正在读取本地北京 POI，筛选景点、餐饮、咖啡和娱乐候选', '已从本地数据筛出候选点'],
        ['UGC 证据整理', '正在读取本地评价特征，检查排队、性价比、环境和适老/亲子信号', '已整理排队、性价比、环境证据'],
        mode === 'chat'
          ? ['动态重规划', '正在保留原路线骨架，并定位需要替换/删除的目标地点', '已尽量保留原景点骨架，仅局部替换目标地点']
          : ['路线优化', '正在组合均衡、预算优先、效率优先 3 套路线', '已生成多套候选路线'],
        ['约束校验', '正在复核预算、总时长、午餐 11:30、餐饮+文化覆盖和风险', '已完成预算、时长、午餐标签和风险校验'],
      ];
      addLocalProgressMessage('开始北京旅游路线规划。', 0);
      for (let index = 0; false && index < planningSteps.length; index += 1) {
        const [stepName, runningText, doneText] = planningSteps[index];
        addLocalProgressMessage(`${stepName}：${runningText}...`, index + 1);
        await wait(350);
        addLocalProgressMessage(`${stepName}：${doneText}`, index + 1, true);
        await wait(120);
      }
      addLocalProgressMessage('等待路线结果写入并刷新右侧“北京智能路线方案”...', planningSteps.length + 1);

      // Add timeout to prevent indefinite waiting
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000);

      let r: Response;
      try {
        r = await fetch(`${API_BASE}/api/chat/${projectId}/act`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!r.ok) {
          const errorText = await r.text();
          console.error('API Error:', errorText);

          if (tempUserMessageId) {
            console.log('🔄 [Optimistic] Removing optimistic user message due to API error via stable handler:', tempUserMessageId);
            if (stableMessageHandlers.current) {
              stableMessageHandlers.current.remove(tempUserMessageId);
            } else if (messageHandlersRef.current) {
              messageHandlersRef.current.remove(tempUserMessageId);
            }
          }

          alert(`Failed to send message: ${r.status} ${r.statusText}\n${errorText}`);
          return;
        }
      } catch (fetchError: any) {
        clearTimeout(timeoutId);
        if (fetchError.name === 'AbortError') {
          if (tempUserMessageId) {
            console.log('🔄 [Optimistic] Removing optimistic user message due to timeout via stable handler:', tempUserMessageId);
            if (stableMessageHandlers.current) {
              stableMessageHandlers.current.remove(tempUserMessageId);
            } else if (messageHandlersRef.current) {
              messageHandlersRef.current.remove(tempUserMessageId);
            }
          }
          clearProgressMessages();

          alert('Request timed out after 60 seconds. Please check your connection and try again.');
          return;
        }
        throw fetchError;
      }

      const result = await r.json();

      console.log('📸 Act API response received:', {
        success: result.success,
        userMessageId: result.userMessageId,
        conversationId: result.conversationId,
        requestId: result.requestId,
        hasAttachments: processedImages.length > 0
      });

      const returnedConversationId =
        typeof result?.conversationId === 'string'
          ? result.conversationId
          : typeof result?.conversation_id === 'string'
          ? result.conversation_id
          : undefined;
      if (returnedConversationId) {
        setConversationId(returnedConversationId);
      }

      const resolvedRequestId =
        typeof result?.requestId === 'string'
          ? result.requestId
          : typeof result?.request_id === 'string'
          ? result.request_id
          : requestId;
      const userMessageId =
        typeof result?.userMessageId === 'string'
          ? result.userMessageId
          : typeof result?.user_message_id === 'string'
          ? result.user_message_id
          : '';

      createRequest(resolvedRequestId, userMessageId, finalMessage, mode);

      if (result?.status === 'travel_clarification_required') {
        const now = new Date().toISOString();
        const clarificationMessage = {
          id: `${resolvedRequestId}-travel-clarification-local`,
          projectId,
          role: 'assistant' as const,
          messageType: 'chat' as const,
          content: String(result?.message || '还需要补充具体地点或约束后再重规划。'),
          conversationId: returnedConversationId ?? (conversationId || null),
          requestId: `${resolvedRequestId}-clarification`,
          createdAt: now,
          updatedAt: now,
          isStreaming: false,
          isFinal: true,
          metadata: {
            type: 'travel_clarification_required',
            reason: result?.reason,
            localOnly: true,
          },
        };
        if (stableMessageHandlers.current) {
          stableMessageHandlers.current.add(clarificationMessage);
        } else if (messageHandlersRef.current) {
          messageHandlersRef.current.add(clarificationMessage);
        }
        setPrompt('');
        return;
      }

      if (
        (result?.status === 'travel_plan_completed' || result?.status === 'travel_replan_completed') &&
        result?.travelItinerary
      ) {
        setTravelItinerary(result.travelItinerary as TravelItineraryData);
      }

      // Refresh data after completion
      await loadTree('.');
      scheduleTravelItineraryRefresh();

      if (
        (result?.status === 'travel_plan_completed' || result?.status === 'travel_replan_completed') &&
        !result?.assistantMessageId
      ) {
        const now = new Date().toISOString();
        const localAssistantMessage = {
          id: `${resolvedRequestId}-travel-assistant-local`,
          projectId,
          role: 'assistant' as const,
          messageType: 'chat' as const,
          content:
            result.status === 'travel_replan_completed'
              ? [
                  '动态重规划完成。',
                  '',
                  '- 已识别本轮调整要求',
                  '- 已从本地数据重新筛选候选点',
                  '- 已保留排队/性价比/环境证据',
                  '- 已尽量保留原景点骨架，仅局部替换目标地点',
                  '- 已复核预算、总时长、午餐标签和风险',
                  '- 已更新右侧旅行规划页',
                  '',
                  `方案数：${result.proposalCount ?? 0}`,
                  '可以继续输入想增删的地点、预算或节奏要求。',
                ].join('\n')
              : [
                  '北京旅游路线规划完成。',
                  '',
                  '- 已解析目标、约束和偏好',
                  '- 已读取本地北京 POI 候选',
                  '- 已整理本地评价信号',
                  '- 已生成均衡、预算优先、效率优先方案',
                  '- 已复核预算、时长、午餐标签和风险',
                  '- 已更新右侧旅行规划页',
                  '',
                  `方案数：${result.proposalCount ?? 0}`,
                  '可以继续输入想增删的地点、预算或节奏要求。',
                ].join('\n'),
          conversationId: returnedConversationId ?? (conversationId || null),
          requestId: `${resolvedRequestId}-local-assistant`,
          createdAt: now,
          updatedAt: now,
          isStreaming: false,
          isFinal: true,
          metadata: {
            type: result.status,
            itineraryPath: result.itineraryPath,
            proposalCount: result.proposalCount,
            localOnly: true,
          },
        };

        if (stableMessageHandlers.current) {
          stableMessageHandlers.current.add(localAssistantMessage);
        } else if (messageHandlersRef.current) {
          messageHandlersRef.current.add(localAssistantMessage);
        }
      }

      // Reset prompt and uploaded images
      setPrompt('');
      // Clean up old format images if any
      if (uploadedImages && uploadedImages.length > 0) {
        uploadedImages.forEach(img => {
          if (img.url) URL.revokeObjectURL(img.url);
        });
        setUploadedImages([]);
      }

    } catch (error: any) {
      console.error('Act execution error:', error);

      if (tempUserMessageId) {
        console.log('🔄 [Optimistic] Removing optimistic user message due to execution error via stable handler:', tempUserMessageId);
        if (stableMessageHandlers.current) {
          stableMessageHandlers.current.remove(tempUserMessageId);
        } else if (messageHandlersRef.current) {
          messageHandlersRef.current.remove(tempUserMessageId);
        }
      }
      clearProgressMessages();

      const errorMessage = error?.message || String(error);
      alert(`Failed to send message: ${errorMessage}\n\nPlease try again. If the problem persists, check the console for details.`);
    } finally {
      setIsRunning(false);
      // Remove from pending requests
      pendingRequestsRef.current.delete(requestFingerprint);
    }
  }

  const pauseAgent = useCallback(async () => {
    if (isPausingAgent) {
      return;
    }

    setIsPausingAgent(true);
    try {
      const response = await fetch(`${API_BASE}/api/chat/${projectId}/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '用户暂停了当前任务' }),
      });

      if (!response.ok) {
        let message = '暂停失败';
        try {
          const payload = await response.json();
          message = payload?.message || payload?.error || message;
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      setIsRunning(false);
      setAgentWorkComplete(false);
      setPreviewInitializationMessage('任务已暂停。');
      pendingRequestsRef.current.clear();
    } catch (error) {
      console.warn('[Chat] failed to pause agent:', error);
      alert(error instanceof Error ? error.message : '暂停失败，请稍后重试。');
    } finally {
      setIsPausingAgent(false);
    }
  }, [isPausingAgent, projectId]);


  // Handle project status updates via callback from ChatLog
  const handleProjectStatusUpdate = (status: string, message?: string) => {
    const previousStatus = projectStatus;

    if (
      status === 'travel_plan_completed' ||
      status === 'travel_replan_completed' ||
      status === 'completed' ||
      status === 'rendering'
    ) {
      scheduleTravelItineraryRefresh();
    }

    if (status === 'validation_running') {
      setPreviewValidationState('running');
      setPreviewValidationMessage(message ?? '正在执行路线看板校验。');
      setPreviewRepairPlan(null);
      setPreviewInitializationMessage(message ?? '正在执行路线看板校验，通过后展示预览。');
      return;
    }

    if (status === 'agent_paused') {
      setIsRunning(false);
      setIsPausingAgent(false);
      setPreviewInitializationMessage(message ?? '任务已暂停。');
      pendingRequestsRef.current.clear();
      return;
    }

    if (status === 'validation_failed') {
      setPreviewValidationState('failed');
      setPreviewValidationMessage(message ?? '路线看板校验未通过，请查看摘要。');
      setPreviewUrl(null);
      setIsStartingPreview(false);
      setPreviewInitializationMessage(message ?? '路线看板校验未通过，暂不展示预览。');
      return;
    }

    if (status === 'validation_passed') {
      setPreviewValidationState('passed');
      setPreviewValidationMessage(message ?? '路线看板已生成，可手动打开预览或发布后查看。');
      setPreviewRepairPlan(null);
      setPreviewUrl(null);
      setIsStartingPreview(false);
      setPreviewInitializationMessage(message ?? '路线看板已生成，可手动打开预览或发布后查看。');
      return;
    }

    // Ignore if status is the same (prevent duplicates)
    if (previousStatus === status) {
      return;
    }

    setProjectStatus(status as ProjectStatus);
    if (message) {
      setInitializationMessage(message);
    }

    // If project becomes active, stop showing loading UI
    if (status === 'active') {
      setIsInitializing(false);

      // Handle only when transitioning from initializing → active
      if (previousStatus === 'initializing') {

        // Start dependency installation
        startDependencyInstallation();
        loadTreeRef.current?.('.');
      }

      // Initial prompt: trigger once with shared guard (handles active-via-WS case)
      triggerInitialPromptIfNeeded();
    } else if (status === 'failed') {
      setIsInitializing(false);
    }
  };

  // Function to start dependency installation in background
  const handleRetryInitialization = async () => {
    setProjectStatus('initializing');
    setIsInitializing(true);
    setInitializationMessage('Retrying project initialization...');

    try {
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/retry-initialization`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error('Failed to retry initialization');
      }
    } catch (error) {
      console.error('Failed to retry initialization:', error);
      setProjectStatus('failed');
      setInitializationMessage('Failed to retry initialization. Please try again.');
    }
  };

  // Load states from localStorage when projectId changes
  useEffect(() => {
    if (typeof window !== 'undefined' && projectId) {
      const storedHasInitialPrompt = localStorage.getItem(`project_${projectId}_hasInitialPrompt`);
      const storedTaskComplete = localStorage.getItem(`project_${projectId}_taskComplete`);

      if (storedHasInitialPrompt !== null) {
        setHasInitialPrompt(storedHasInitialPrompt === 'true');
      }
      if (storedTaskComplete !== null) {
        setAgentWorkComplete(storedTaskComplete === 'true');
      }
    }
  }, [projectId]);

  // Poll for file changes in code view
  useEffect(() => {
    if (!showPreview && selectedFile && !hasUnsavedChanges) {
      const interval = setInterval(() => {
        reloadCurrentFile();
      }, 2000); // Check every 2 seconds

      return () => clearInterval(interval);
    }
  }, [showPreview, selectedFile, hasUnsavedChanges, reloadCurrentFile]);


  useEffect(() => {
    if (!projectId) {
      return;
    }

    let canceled = false;

    const initializeChat = async () => {
      try {
        const projectSettings = await loadProjectInfoRef.current?.();
        if (canceled) return;

        await loadSettingsRef.current?.(projectSettings);
        if (canceled) return;

        await loadTreeRef.current?.('.');
        if (canceled) return;

        await loadTravelItineraryRef.current?.();
        if (canceled) return;

        await loadDeployStatusRef.current?.();
        if (canceled) return;

        checkCurrentDeploymentRef.current?.();
      } catch (error) {
        console.error('Failed to initialize chat view:', error);
      }
    };

    initializeChat();

    const handleServicesUpdate = () => {
      loadDeployStatusRef.current?.();
    };

    const handleBeforeUnload = () => {
      navigator.sendBeacon(`${API_BASE}/api/projects/${projectId}/preview/stop`);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('services-updated', handleServicesUpdate);

    return () => {
      canceled = true;
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('services-updated', handleServicesUpdate);

      const currentPreview = previewUrlRef.current;
      if (currentPreview) {
        fetch(`${API_BASE}/api/projects/${projectId}/preview/stop`, { method: 'POST' }).catch(() => {});
      }
    };
  }, [projectId]);

  // Cleanup pending requests on unmount
  useEffect(() => {
    const pendingRequests = pendingRequestsRef.current;
    return () => {
      pendingRequests.clear();
    };
  }, []);

  // React to global settings changes when using global defaults
  const { settings: globalSettings } = useGlobalSettings();
  useEffect(() => {
    if (!usingGlobalDefaults) return;
    if (!globalSettings) return;

    const cli = sanitizeCli(globalSettings.default_cli);
    updatePreferredCli(cli);

    const modelFromGlobal = globalSettings.cli_settings?.[cli]?.model;
    if (modelFromGlobal) {
      updateSelectedModel(modelFromGlobal, cli);
    } else {
      updateSelectedModel(getDefaultModelForCli(cli), cli);
    }
  }, [globalSettings, usingGlobalDefaults, updatePreferredCli, updateSelectedModel]);


  // Show loading UI if project is initializing

  return (
    <>
      <style jsx global>{`
        .qp-code-preview {
          color: #374151;
        }
      `}</style>

      <div className="h-screen bg-white flex relative overflow-hidden">
        <div className="h-full w-full flex">
          {/* Left: Chat window */}
          <div
            style={{ width: '22%' }}
            className="h-full border-r border-slate-200 flex flex-col"
          >
            {/* Chat header */}
            <div className="bg-white border-b border-slate-200 p-4 h-[73px] flex items-center">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => router.push('/')}
                  className="flex items-center justify-center w-8 h-8 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
                  title="Back to home"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M19 12H5M12 19L5 12L12 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <div>
                  <h1 className="text-lg font-semibold text-slate-900 ">{projectName || 'Loading...'}</h1>
                  {projectDescription && (
                    <p className="text-sm text-slate-500 ">
                      {projectDescription}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Chat log area */}
            <div className="flex-1 min-h-0">
              <ChatErrorBoundary>
                <ChatLog
                  projectId={projectId}
                  onAddUserMessage={(handlers) => {
                    console.log('🔄 [HandlerSetup] ChatLog provided new handlers, updating references');
                    messageHandlersRef.current = handlers;

                    // Also update stable handlers if they exist
                    if (stableMessageHandlers.current) {
                      console.log('🔄 [HandlerSetup] Updating stable handlers reference');
                      // Note: stableMessageHandlers.current already has its own add/remove logic
                      // We don't replace it completely, just keep the reference to handlers
                    }
                  }}
                  onSessionStatusChange={(isRunningValue) => {
                  console.log('🔍 [DEBUG] Session status change:', isRunningValue);
                  setIsRunning(isRunningValue);
                  // Track agent task completion and auto-start preview
                  if (!isRunningValue && hasInitialPrompt && !agentWorkComplete && !previewUrl) {
                    setAgentWorkComplete(true);
                    setPreviewValidationState('passed');
                    setPreviewValidationMessage('路线看板已生成，可打开预览。');
                    // Save to localStorage
                    localStorage.setItem(`project_${projectId}_taskComplete`, 'true');
                  }
                }}
                onSseFallbackActive={(active) => {
                  console.log('🔄 [SSE] Fallback status:', active);
                  setIsSseFallbackActive(active);
                }}
                onProjectStatusUpdate={handleProjectStatusUpdate}
                startRequest={startRequest}
                completeRequest={completeRequest}
              />
              </ChatErrorBoundary>
            </div>

            {/* Simple input area */}
            <div className="p-4 rounded-bl-2xl">
              <ChatInput
                onSendMessage={(message, images) => {
                  // Pass images to runAct
                  runAct(message, images);
                }}
                disabled={isRunning}
                placeholder={mode === 'act' ? "描述你的北京游玩目标、时间、预算和偏好..." : "继续调整北京路线细节..."}
                mode={mode}
                onModeChange={setMode}
                projectId={projectId}
                preferredCli={preferredCli}
                selectedModel={selectedModel}
                modelOptions={modelOptions}
                onModelChange={handleModelChange}
                modelChangeDisabled={isUpdatingModel}
                cliOptions={cliOptions}
                onCliChange={handleCliChange}
                cliChangeDisabled={isUpdatingModel}
                isRunning={isRunning}
                onPause={pauseAgent}
                isPausing={isPausingAgent}
              />
            </div>
          </div>

          {/* Right: Preview/Code area */}
          <div className="h-full flex flex-col bg-[#f6f0e8]" style={{ width: '78%' }}>
            {/* Content area */}
            <div className="flex-1 min-h-0 flex flex-col">
              {/* Controls Bar */}
              <div className="bg-white border-b border-slate-200 px-4 h-[73px] flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {/* Toggle switch */}
                  <div className="flex items-center bg-slate-100 rounded-lg p-1">
                    <button
                      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                        showPreview
                          ? 'bg-white text-slate-900 '
                          : 'text-slate-600 hover:text-slate-900 '
                      }`}
                      onClick={() => setShowPreview(true)}
                    >
                      <span className="w-4 h-4 flex items-center justify-center"><FaDesktop size={16} /></span>
                    </button>
                    <button
                      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                        !showPreview
                          ? 'bg-white text-slate-900 '
                          : 'text-slate-600 hover:text-slate-900 '
                      }`}
                      onClick={() => setShowPreview(false)}
                    >
                      <span className="w-4 h-4 flex items-center justify-center"><FaCode size={16} /></span>
                    </button>
                  </div>

                  {/* Center Controls */}
                  {showPreview && shouldShowPreviewFrame && (
                    <div className="flex items-center gap-3">
                      {/* Route Navigation */}
                      <div className="h-9 flex items-center bg-slate-100 rounded-lg px-3 border border-slate-200 ">
                        <span className="text-slate-400 mr-2">
                          <FaHome size={12} />
                        </span>
                        <span className="text-sm text-slate-500 mr-1">/</span>
                        <input
                          type="text"
                          value={currentRoute.startsWith('/') ? currentRoute.slice(1) : currentRoute}
                          onChange={(e) => {
                            const value = e.target.value;
                            setCurrentRoute(value ? `/${value}` : '/');
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              navigateToRoute(currentRoute);
                            }
                          }}
                          className="bg-transparent text-sm text-slate-700 outline-none w-40"
                          placeholder="route"
                        />
                        <button
                          onClick={() => navigateToRoute(currentRoute)}
                          className="ml-2 text-slate-500 hover:text-slate-700 "
                        >
                          <FaArrowRight size={12} />
                        </button>
                      </div>

                      {/* Action Buttons Group */}
                      <div className="flex items-center gap-1.5">
                        <button
                          className="h-9 w-9 flex items-center justify-center bg-slate-100 text-slate-600 hover:text-slate-900 hover:bg-slate-200 rounded-lg transition-colors"
                          onClick={() => {
                            const iframe = document.querySelector('iframe');
                            if (iframe) {
                              iframe.src = iframe.src;
                            }
                          }}
                          title="Refresh preview"
                        >
                          <FaRedo size={14} />
                        </button>

                        {/* Device Mode Toggle */}
                        <div className="h-9 flex items-center gap-1 bg-slate-100 rounded-lg px-1 border border-slate-200 ">
                          <button
                            aria-label="Desktop preview"
                            className={`h-7 w-7 flex items-center justify-center rounded transition-colors ${
                              deviceMode === 'desktop'
                                ? 'text-blue-600 bg-blue-50 '
                                : 'text-slate-400 hover:text-slate-600 '
                            }`}
                            onClick={() => setDeviceMode('desktop')}
                          >
                            <FaDesktop size={14} />
                          </button>
                          <button
                            aria-label="Mobile preview"
                            className={`h-7 w-7 flex items-center justify-center rounded transition-colors ${
                              deviceMode === 'mobile'
                                ? 'text-blue-600 bg-blue-50 '
                                : 'text-slate-400 hover:text-slate-600 '
                            }`}
                            onClick={() => setDeviceMode('mobile')}
                          >
                            <FaMobileAlt size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* Settings Button */}
                  <button
                    onClick={() => setShowGlobalSettings(true)}
                    className="h-9 w-9 flex items-center justify-center bg-slate-100 text-slate-600 hover:text-slate-900 hover:bg-slate-200 rounded-lg transition-colors"
                    title="Settings"
                  >
                    <FaCog size={16} />
                  </button>

                  {/* Stop Button */}
                  {showPreview && shouldShowPreviewFrame && (
                    <button
                      className="h-9 px-3 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                      onClick={stop}
                    >
                      <FaStop size={12} />
                      Stop
                    </button>
                  )}

                  {/* Publish/Update */}
                  {showPreview && shouldShowPreviewFrame && (
                    <div className="relative">
                    <button
                      className="h-9 flex items-center gap-2 px-3 bg-black text-white rounded-lg text-sm font-medium transition-colors hover:bg-slate-900 border border-black/10 shadow-sm"
                      onClick={() => setShowPublishPanel(true)}
                    >
                      <FaRocket size={14} />
                      Publish
                      {deploymentStatus === 'deploying' && (
                        <span className="ml-2 inline-block w-2 h-2 rounded-full bg-amber-400"></span>
                      )}
                      {deploymentStatus === 'ready' && (
                        <span className="ml-2 inline-block w-2 h-2 rounded-full bg-emerald-400"></span>
                      )}
                    </button>
                    {false && showPublishPanel && (
                      <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-slate-200 z-50 p-5">
                        <h3 className="text-lg font-semibold text-slate-900 mb-4">Publish Project</h3>

                        {/* Deployment Status Display */}
                        {deploymentStatus === 'deploying' && (
                          <div className="mb-4 p-4 bg-blue-50 rounded-lg border border-blue-200 ">
                            <div className="flex items-center gap-2 mb-2">
                              <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                              <p className="text-sm font-medium text-blue-700 ">Deployment in progress...</p>
                            </div>
                            <p className="text-xs text-blue-600 ">Building and deploying your project. This may take a few minutes.</p>
                          </div>
                        )}

                        {deploymentStatus === 'ready' && publishedUrl && (
                          <div className="mb-4 p-4 bg-green-50 rounded-lg border border-green-200 ">
                            <p className="text-sm font-medium text-green-700 mb-2">Currently published at:</p>
                            <a
                              href={publishedUrl ?? undefined}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm text-green-600 font-mono hover:underline break-all"
                            >
                              {publishedUrl}
                            </a>
                          </div>
                        )}

                        {deploymentStatus === 'error' && (
                          <div className="mb-4 p-4 bg-red-50 rounded-lg border border-red-200 ">
                            <p className="text-sm font-medium text-red-700 mb-2">Deployment failed</p>
                            <p className="text-xs text-red-600 ">There was an error during deployment. Please try again.</p>
                          </div>
                        )}

                        <div className="space-y-4">
                          {!githubConnected || !vercelConnected ? (
                            <div className="p-4 bg-amber-50 rounded-lg border border-amber-200 ">
                              <p className="text-sm font-medium text-slate-900 mb-3">To publish, connect the following services:</p>
                              <div className="space-y-2">
                                {!githubConnected && (
                                  <div className="flex items-center gap-2 text-amber-700 ">
                                    <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                    </svg>
                                    <span className="text-sm">GitHub repository not connected</span>
                                  </div>
                                )}
                                {!vercelConnected && (
                                  <div className="flex items-center gap-2 text-amber-700 ">
                                    <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                    </svg>
                                    <span className="text-sm">Vercel project not connected</span>
                                  </div>
                                )}
                              </div>
                              <p className="mt-3 text-sm text-slate-600 ">
                                Go to
                                <button
                                  onClick={() => {
                                    setShowPublishPanel(false);
                                    setShowGlobalSettings(true);
                                  }}
                                  className="text-indigo-600 hover:text-indigo-500 underline font-medium mx-1"
                                >
                                  Settings → Service Integrations
                                </button>
                                to connect.
                              </p>
                            </div>
                          ) : null}

                          <button
                            disabled={publishLoading || deploymentStatus === 'deploying' || !githubConnected || !vercelConnected}
                            onClick={async () => {
                              console.log('🚀 Publish started');

                              setPublishLoading(true);
                              try {
                                // Push to GitHub
                                console.log('🚀 Pushing to GitHub...');
                                const pushRes = await fetch(`${API_BASE}/api/projects/${projectId}/github/push`, { method: 'POST' });
                                if (!pushRes.ok) {
                                  const errorText = await pushRes.text();
                                  console.error('🚀 GitHub push failed:', errorText);
                                  throw new Error(errorText);
                                }

                                // Deploy to Vercel
                                console.log('🚀 Deploying to Vercel...');
                                const deployUrl = `${API_BASE}/api/projects/${projectId}/vercel/deploy`;

                                const vercelRes = await fetch(deployUrl, {
                                  method: 'POST'
                                });
                                if (!vercelRes.ok) {
                                  const responseText = await vercelRes.text();
                                  console.error('🚀 Vercel deploy failed:', responseText);
                                }
                                if (vercelRes.ok) {
                                  const data = await vercelRes.json();
                                  console.log('🚀 Deployment started, polling for status...');

                                  // Set deploying status BEFORE ending publishLoading to prevent gap
                                  setDeploymentStatus('deploying');

                                  if (data.deployment_id) {
                                    startDeploymentPolling(data.deployment_id);
                                  }

                                  // Only set URL if deployment is already ready
                                  if (data.status === 'READY' && data.deployment_url) {
                                    const url = data.deployment_url.startsWith('http') ? data.deployment_url : `https://${data.deployment_url}`;
                                    setPublishedUrl(url);
                                    setDeploymentStatus('ready');
                                  }
                                } else {
                                  const errorText = await vercelRes.text();
                                  console.error('🚀 Vercel deploy failed:', vercelRes.status, errorText);
                                  // if Vercel not connected, just close
                                  setDeploymentStatus('idle');
                                  setPublishLoading(false); // Stop loading even on Vercel deployment failure
                                }
                                // Keep panel open to show deployment progress
                              } catch (e) {
                                console.error('🚀 Publish failed:', e);
                                alert('Publish failed. Check Settings and tokens.');
                                setDeploymentStatus('idle');
                                setPublishLoading(false); // Stop loading on error
                                // Close panel after error
                                setTimeout(() => {
                                  setShowPublishPanel(false);
                                }, 1000);
                              } finally {
                                loadDeployStatus();
                              }
                            }}
                            className={`w-full px-4 py-3 rounded-lg font-medium text-white transition-colors ${
                              publishLoading || deploymentStatus === 'deploying' || !githubConnected || !vercelConnected
                                ? 'bg-slate-400 cursor-not-allowed'
                                : 'bg-indigo-600 hover:bg-indigo-700 '
                            }`}
                          >
                            {publishLoading
                              ? 'Publishing...'
                              : deploymentStatus === 'deploying'
                              ? 'Deploying...'
                              : !githubConnected || !vercelConnected
                              ? 'Connect Services First'
                              : deploymentStatus === 'ready' && publishedUrl ? 'Update' : 'Publish'
                            }
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                  )}
                </div>
              </div>

              {/* Content Area */}
              <div className="flex-1 relative bg-[#f6f0e8] overflow-hidden">
                <AnimatePresence initial={false}>
                  {showPreview ? (
                  <MotionDiv
                    key="preview"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{ height: '100%' }}
                  >
                {travelItinerary ? (
                  <TravelItineraryPreviewV2 data={travelItinerary} />
                ) : shouldShowPreviewFrame ? (
                  <div className="relative w-full h-full bg-slate-100 flex items-center justify-center">
                    <div
                      className={`bg-white ${
                        deviceMode === 'mobile'
                          ? 'w-[375px] h-[667px] rounded-[25px] border-8 border-slate-800 shadow-2xl'
                          : 'w-full h-full'
                      } overflow-hidden`}
                    >
                      <iframe
                        ref={iframeRef}
                        className="w-full h-full border-none bg-white "
                        src={previewUrl ?? undefined}
                        onError={() => {
                          // Show error overlay
                          const overlay = document.getElementById('iframe-error-overlay');
                          if (overlay) overlay.style.display = 'flex';
                        }}
                        onLoad={() => {
                          // Hide error overlay when loaded successfully
                          const overlay = document.getElementById('iframe-error-overlay');
                          if (overlay) overlay.style.display = 'none';
                        }}
                      />

                      {/* Error overlay */}
                    <div
                      id="iframe-error-overlay"
                      className="absolute inset-0 bg-slate-50 flex items-center justify-center z-10"
                      style={{ display: 'none' }}
                    >
                      <div className="text-center max-w-md mx-auto p-6">
                        <div className="text-4xl mb-4">🔄</div>
                        <h3 className="text-lg font-semibold text-slate-800 mb-2">
                          Connection Issue
                        </h3>
                        <p className="text-slate-600 mb-4">
                          The preview couldn&apos;t load properly. Try clicking the refresh button to reload the page.
                        </p>
                        <button
                          className="flex items-center gap-2 mx-auto px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors"
                          onClick={() => {
                            const iframe = document.querySelector('iframe');
                            if (iframe) {
                              iframe.src = iframe.src;
                            }
                            const overlay = document.getElementById('iframe-error-overlay');
                            if (overlay) overlay.style.display = 'none';
                          }}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M1 4v6h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                          Refresh Now
                        </button>
                      </div>
                    </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full w-full flex items-center justify-center bg-slate-50 relative">
                    {/* Gradient background similar to main page */}
                    <div className="absolute inset-0">
                      <div className="absolute inset-0 bg-white " />
                      <div
                        className="absolute inset-0 hidden transition-all duration-1000 ease-in-out"
                        style={{
                          background: `radial-gradient(circle at 50% 100%,
                            ${activeBrandColor}66 0%,
                            ${activeBrandColor}4D 25%,
                            ${activeBrandColor}33 50%,
                            transparent 70%)`
                        }}
                      />
                      {/* Light mode gradient - subtle */}
                      <div
                        className="absolute inset-0 block transition-all duration-1000 ease-in-out"
                        style={{
                          background: `radial-gradient(circle at 50% 100%,
                            ${activeBrandColor}40 0%,
                            ${activeBrandColor}26 25%,
                            transparent 50%)`
                        }}
                      />
                    </div>

                    {/* Content with z-index to be above gradient */}
                    <div className="relative z-10 w-full h-full flex items-center justify-center">
                    {isStartingPreview ? (
                      <MotionDiv
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="text-center"
                      >
                        {/* QuantPilot 图标与加载状态 */}
                        <div className="w-40 h-40 mx-auto mb-6 relative">
                          <div
                            className="w-full h-full"
                            style={{
                              backgroundColor: activeBrandColor,
                              mask: 'url(/Symbol_white.png) no-repeat center/contain',
                              WebkitMask: 'url(/Symbol_white.png) no-repeat center/contain',
                              opacity: 0.9
                            }}
                          />

                          {/* Loading spinner in center */}
                          <div className="absolute inset-0 flex items-center justify-center">
                            <div
                              className="w-14 h-14 border-4 rounded-full animate-spin"
                              style={{
                                borderTopColor: 'transparent',
                                borderRightColor: activeBrandColor,
                                borderBottomColor: activeBrandColor,
                                borderLeftColor: activeBrandColor,
                              }}
                            />
                          </div>
                        </div>

                        {/* Content */}
                        <h3 className="text-xl font-semibold text-slate-900 mb-3">
                          正在准备可视化看板
                        </h3>

                        <div className="flex items-center justify-center gap-1 text-slate-600 ">
                          <span>{previewInitializationMessage}</span>
                          <MotionDiv
                            className="flex gap-1 ml-2"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                          >
                            <MotionDiv
                              animate={{ opacity: [0, 1, 0] }}
                              transition={{ duration: 1.5, repeat: Infinity, delay: 0 }}
                              className="w-1 h-1 bg-slate-600 rounded-full"
                            />
                            <MotionDiv
                              animate={{ opacity: [0, 1, 0] }}
                              transition={{ duration: 1.5, repeat: Infinity, delay: 0.3 }}
                              className="w-1 h-1 bg-slate-600 rounded-full"
                            />
                            <MotionDiv
                              animate={{ opacity: [0, 1, 0] }}
                              transition={{ duration: 1.5, repeat: Infinity, delay: 0.6 }}
                              className="w-1 h-1 bg-slate-600 rounded-full"
                            />
                          </MotionDiv>
                        </div>
                      </MotionDiv>
                    ) : (
                    <div className="text-center">
                      <MotionDiv
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, ease: "easeOut" }}
                      >
                        {/* QuantPilot 图标 */}
                        {hasActiveRequests ? (
                          <>
                            <div className="w-40 h-40 mx-auto mb-6 relative">
                              <MotionDiv
                                animate={{ rotate: 360 }}
                                transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                                style={{ transformOrigin: "center center" }}
                                className="w-full h-full"
                              >
                          <div
                            className="w-full h-full"
                            style={{
                              backgroundColor: activeBrandColor,
                              mask: 'url(/Symbol_white.png) no-repeat center/contain',
                              WebkitMask: 'url(/Symbol_white.png) no-repeat center/contain',
                              opacity: 0.9
                            }}
                          />
                              </MotionDiv>
                            </div>

                            <h3 className="text-2xl font-bold mb-3 relative overflow-hidden inline-block">
                              <span
                                className="relative"
                                style={{
                                  background: `linear-gradient(90deg,
                                    #6b7280 0%,
                                    #6b7280 30%,
                                    #ffffff 50%,
                                    #6b7280 70%,
                                    #6b7280 100%)`,
                                  backgroundSize: '200% 100%',
                                  WebkitBackgroundClip: 'text',
                                  backgroundClip: 'text',
                                  WebkitTextFillColor: 'transparent',
                                  animation: 'shimmerText 5s linear infinite'
                                }}
                              >
                                正在生成看板...
                              </span>
                              <style>{`
                                @keyframes shimmerText {
                                  0% {
                                    background-position: 200% center;
                                  }
                                  100% {
                                    background-position: -200% center;
                                  }
                                }
                              `}</style>
                            </h3>
                          </>
                        ) : (
                          <>
                            <div
                              onClick={!isRunning && !isStartingPreview ? () => start({ requireValidation: true }) : undefined}
                              className={`w-40 h-40 mx-auto mb-6 relative ${!isRunning && !isStartingPreview ? 'cursor-pointer group' : ''}`}
                            >
                              {/* QuantPilot 启动动画图标 */}
                              <MotionDiv
                                className="w-full h-full"
                                animate={isStartingPreview ? { rotate: 360 } : {}}
                                transition={{ duration: 6, repeat: isStartingPreview ? Infinity : 0, ease: "linear" }}
                              >
                                <div
                                  className="w-full h-full"
                                  style={{
                                    backgroundColor: activeBrandColor,
                                    mask: 'url(/Symbol_white.png) no-repeat center/contain',
                                    WebkitMask: 'url(/Symbol_white.png) no-repeat center/contain',
                                    opacity: 0.9
                                  }}
                                />
                              </MotionDiv>

                              {/* Icon in Center - Play or Loading */}
                              <div className="absolute inset-0 flex items-center justify-center">
                                {isStartingPreview ? (
                                  <div
                                    className="w-14 h-14 border-4 rounded-full animate-spin"
                                    style={{
                                      borderTopColor: 'transparent',
                                      borderRightColor: activeBrandColor,
                                      borderBottomColor: activeBrandColor,
                                      borderLeftColor: activeBrandColor,
                                    }}
                                  />
                                ) : (
                                  <MotionDiv
                                    className="flex items-center justify-center"
                                    whileHover={{ scale: 1.2 }}
                                    whileTap={{ scale: 0.9 }}
                                  >
                                    <FaPlay
                                      size={32}
                                    />
                                  </MotionDiv>
                                )}
                              </div>
                            </div>

                            <h3 className="text-2xl font-bold text-slate-900 mb-3">
                              {previewValidationState === 'failed' ? '路线看板校验未通过' : '路线看板待生成'}
                            </h3>

                            <p className="text-slate-600 max-w-lg mx-auto">
                              {previewValidationState === 'failed'
                                ? previewValidationMessage ?? '路线看板校验未通过，暂不展示预览。'
                                : previewValidationState === 'running'
                                ? '正在执行路线看板校验，通过后会自动展示最终结果'
                                : '数据获取、页面生成和校验完成后会自动展示最终路线看板'}
                            </p>
                            {previewValidationState === 'failed' && previewRepairPlan?.steps?.length ? (
                              <div className="mt-5 w-full max-w-2xl rounded-lg border border-red-100 bg-red-50/70 p-4 text-left shadow-sm">
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-sm font-semibold text-red-900">修复计划</p>
                                  {previewRepairPlan.repairPlanPath ? (
                                    <code className="rounded bg-white/80 px-2 py-1 text-xs text-red-700">
                                      {previewRepairPlan.repairPlanPath}
                                    </code>
                                  ) : null}
                                </div>
                                <div className="mt-3 space-y-3">
                                  {previewRepairPlan.steps.slice(0, 3).map((step, index) => (
                                    <div key={`${step.checkId ?? step.checkName ?? index}-${index}`} className="rounded-md bg-white/80 p-3">
                                      <div className="flex items-start gap-2">
                                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-100 text-xs font-semibold text-red-700">
                                          {index + 1}
                                        </span>
                                        <div className="min-w-0">
                                          <p className="text-sm font-semibold text-slate-900">
                                            {step.checkName || step.checkId || '失败检查项'}
                                          </p>
                                          {step.summary ? (
                                            <p className="mt-1 text-xs leading-5 text-slate-600">{step.summary}</p>
                                          ) : null}
                                          {Array.isArray(step.actions) && step.actions.length > 0 ? (
                                            <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
                                              {step.actions.slice(0, 2).map((action, actionIndex) => (
                                                <li key={`${actionIndex}-${action}`} className="flex gap-2">
                                                  <span className="text-red-400">-</span>
                                                  <span>{action}</span>
                                                </li>
                                              ))}
                                            </ul>
                                          ) : null}
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </>
                        )}
                      </MotionDiv>
                    </div>
                    )}
                    </div>
                  </div>
                )}
                  </MotionDiv>
                ) : (
              <MotionDiv
                key="code"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex bg-white "
              >
                {/* Left Sidebar - File Explorer (VS Code style) */}
                <div className="w-64 flex-shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col">
                  {/* File Tree */}
                  <div className="flex-1 overflow-y-auto bg-slate-50 custom-scrollbar">
                    {!tree || tree.length === 0 ? (
                      <div className="px-3 py-8 text-center text-[11px] text-slate-600 select-none">
                        No files found
                      </div>
                    ) : (
                      <TreeView
                        entries={tree || []}
                        selectedFile={selectedFile}
                        expandedFolders={expandedFolders}
                        folderContents={folderContents}
                        onToggleFolder={toggleFolder}
                        onSelectFile={openFile}
                        onLoadFolder={handleLoadFolder}
                        level={0}
                        parentPath=""
                        getFileIcon={getFileIcon}
                      />
                    )}
                  </div>
                </div>

                {/* Right Editor Area */}
                <div className="flex-1 flex flex-col bg-white min-w-0">
                  {selectedFile ? (
                    <>
                      {/* File Tab */}
                      <div className="flex-shrink-0 bg-slate-100 ">
                        <div className="flex items-center gap-3 bg-white px-3 py-1.5 border-t-2 border-t-blue-500 ">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="w-4 h-4 flex items-center justify-center">
                              {getFileIcon(tree.find(e => e.path === selectedFile) || { path: selectedFile, type: 'file' })}
                            </span>
                            <span className="truncate text-[13px] text-slate-700 " style={{ fontFamily: "'Segoe UI', Tahoma, sans-serif" }}>
                              {selectedFile.split('/').pop()}
                            </span>
                          </div>
                          {hasUnsavedChanges && (
                            <span className="text-[11px] text-amber-600 ">
                              • Unsaved changes
                            </span>
                          )}
                          {!hasUnsavedChanges && saveFeedback === 'success' && (
                            <span className="text-[11px] text-green-600 ">
                              Saved
                            </span>
                          )}
                          {saveFeedback === 'error' && (
                            <span
                              className="text-[11px] text-red-600 truncate max-w-[160px]"
                              title={saveError ?? 'Failed to save file'}
                            >
                              Save error
                            </span>
                          )}
                          {!hasUnsavedChanges && saveFeedback !== 'success' && isFileUpdating && (
                            <span className="text-[11px] text-green-600 ">
                              Updated
                            </span>
                          )}
                          <div className="ml-auto flex items-center gap-2">
                            <button
                              className="px-3 py-1 text-xs font-medium rounded bg-blue-500 text-white hover:bg-blue-600 disabled:bg-slate-300 disabled:text-slate-600 disabled:cursor-not-allowed "
                              onClick={handleSaveFile}
                              disabled={!hasUnsavedChanges || isSavingFile}
                              title="Save (Ctrl+S)"
                            >
                              {isSavingFile ? 'Saving…' : 'Save'}
                            </button>
                            <button
                              className="text-slate-700 hover:bg-slate-200 px-1 rounded"
                              onClick={() => {
                                if (hasUnsavedChanges) {
                                  const confirmClose =
                                    typeof window !== 'undefined'
                                      ? window.confirm('You have unsaved changes. Close without saving?')
                                      : true;
                                  if (!confirmClose) {
                                    return;
                                  }
                                }
                                setSelectedFile('');
                                setContent('');
                                setEditedContent('');
                                editedContentRef.current = '';
                                setHasUnsavedChanges(false);
                                setSaveFeedback('idle');
                                setSaveError(null);
                                setIsFileUpdating(false);
                              }}
                            >
                              ×
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Code Editor */}
                      <div className="flex-1 overflow-hidden">
                        <div className="w-full h-full flex bg-white overflow-hidden">
                          {/* Line Numbers */}
                          <div
                            ref={lineNumberRef}
                            className="bg-slate-50 px-3 py-4 select-none flex-shrink-0 overflow-y-auto overflow-x-hidden custom-scrollbar pointer-events-none"
                            aria-hidden="true"
                          >
                            <div className="text-[13px] font-mono text-slate-500 leading-[19px]">
                              {(editedContent || '').split('\n').map((_, index) => (
                                <div key={index} className="text-right pr-2">
                                  {index + 1}
                                </div>
                              ))}
                            </div>
                          </div>
                          {/* Code Content */}
                          <div className="relative flex-1">
                            <pre
                              ref={highlightRef}
                              aria-hidden="true"
                              className="absolute inset-0 m-0 p-4 overflow-hidden text-[13px] leading-[19px] font-mono text-slate-800 whitespace-pre pointer-events-none"
                              style={{ fontFamily: "'Fira Code', 'Consolas', 'Monaco', monospace" }}
                            >
                              <code className="qp-code-preview language-plaintext">{highlightedCode}</code>
                              <span className="block h-full min-h-[1px]" />
                            </pre>
                            <textarea
                              ref={editorRef}
                              value={editedContent}
                              onChange={onEditorChange}
                              onScroll={handleEditorScroll}
                              onKeyDown={handleEditorKeyDown}
                              spellCheck={false}
                              autoCorrect="off"
                              autoCapitalize="none"
                              autoComplete="off"
                              wrap="off"
                              aria-label="Code editor"
                              className="absolute inset-0 w-full h-full resize-none bg-transparent text-transparent caret-slate-800 outline-none font-mono text-[13px] leading-[19px] p-4 whitespace-pre overflow-auto custom-scrollbar"
                              style={{ fontFamily: "'Fira Code', 'Consolas', 'Monaco', monospace" }}
                            />
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    /* Welcome Screen */
                    <div className="flex-1 flex items-center justify-center bg-white ">
                      <div className="text-center">
                        <span className="w-16 h-16 mb-4 opacity-10 text-slate-400 mx-auto flex items-center justify-center"><FaCode size={64} /></span>
                        <h3 className="text-lg font-medium text-slate-700 mb-2">
                          Welcome to Code Editor
                        </h3>
                        <p className="text-sm text-slate-500 ">
                          Select a file from the explorer to start viewing code
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </MotionDiv>
                )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>
      </div>


      {/* Publish Modal */}
      {showPublishPanel && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowPublishPanel(false)} />
          <div className="relative w-full max-w-lg bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/60 ">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white bg-black border border-black/10 ">
                  <FaRocket size={14} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-900 ">Publish Project</h3>
                  <p className="text-xs text-slate-600 ">Deploy with Vercel, linked to your GitHub repo</p>
                </div>
              </div>
              <button onClick={() => setShowPublishPanel(false)} className="text-slate-400 hover:text-slate-600 ">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
              </button>
            </div>

            <div className="p-6 space-y-4">
              {deploymentStatus === 'deploying' && (
                <div className="p-4 rounded-xl border border-blue-200 bg-blue-50 ">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                    <p className="text-sm font-medium text-blue-700 ">Deployment in progress…</p>
                  </div>
                  <p className="text-xs text-blue-700/80 ">Building and deploying your project. This may take a few minutes.</p>
                </div>
              )}

              {deploymentStatus === 'ready' && publishedUrl && (
                <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50 ">
                  <p className="text-sm font-medium text-emerald-700 mb-2">Published successfully</p>
                  <div className="flex items-center gap-2">
                    <a href={publishedUrl} target="_blank" rel="noopener noreferrer" className="text-sm font-mono text-emerald-700 underline break-all flex-1">
                      {publishedUrl}
                    </a>
                    <button
                      onClick={() => navigator.clipboard?.writeText(publishedUrl)}
                      className="px-2 py-1 text-xs rounded-lg border border-emerald-300/80 text-emerald-700 hover:bg-emerald-100 "
                    >
                      Copy
                    </button>
                  </div>
                </div>
              )}

              {deploymentStatus === 'error' && (
                <div className="p-4 rounded-xl border border-red-200 bg-red-50 ">
                  <p className="text-sm font-medium text-red-700 ">Deployment failed. Please try again.</p>
                </div>
              )}

              {!githubConnected || !vercelConnected ? (
                <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 ">
                  <p className="text-sm font-medium text-slate-900 mb-2">Connect the following services:</p>
                  <div className="space-y-1 text-amber-700 text-sm">
                    {!githubConnected && (<div className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-500"/>GitHub repository not connected</div>)}
                    {!vercelConnected && (<div className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-500"/>Vercel project not connected</div>)}
                  </div>
                  <button
                    className="mt-3 w-full px-4 py-2 rounded-xl border border-slate-200 text-slate-800 hover:bg-slate-50 "
                    onClick={() => { setShowPublishPanel(false); setShowGlobalSettings(true); }}
                  >
                    Open Settings → Services
                  </button>
                </div>
              ) : null}

              <button
                disabled={publishLoading || deploymentStatus === 'deploying' || !githubConnected || !vercelConnected}
                onClick={async () => {
                  try {
                    setPublishLoading(true);
                    setDeploymentStatus('deploying');
                    // 1) Push to GitHub to ensure branch/commit exists
                    try {
                      const pushRes = await fetch(`${API_BASE}/api/projects/${projectId}/github/push`, { method: 'POST' });
                      if (!pushRes.ok) {
                        const err = await pushRes.text();
                        console.error('🚀 GitHub push failed:', err);
                        throw new Error(err);
                      }
                    } catch (e) {
                      console.error('🚀 GitHub push step failed', e);
                      throw e;
                    }
                    // Small grace period to let GitHub update default branch
                    await new Promise(r => setTimeout(r, 800));
                    // 2) Deploy to Vercel (branch auto-resolved on server)
                    const deployUrl = `${API_BASE}/api/projects/${projectId}/vercel/deploy`;
                    const vercelRes = await fetch(deployUrl, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ branch: 'main' })
                    });
                    if (vercelRes.ok) {
                      const data = await vercelRes.json();
                      setDeploymentStatus('deploying');
                      if (data.deployment_id) startDeploymentPolling(data.deployment_id);
                      if (data.ready && data.deployment_url) {
                        const url = data.deployment_url.startsWith('http') ? data.deployment_url : `https://${data.deployment_url}`;
                        setPublishedUrl(url);
                        setDeploymentStatus('ready');
                      }
                    } else {
                      const errorText = await vercelRes.text();
                      console.error('🚀 Vercel deploy failed:', vercelRes.status, errorText);
                      setDeploymentStatus('idle');
                      setPublishLoading(false);
                    }
                  } catch (e) {
                    console.error('🚀 Publish failed:', e);
                    alert('Publish failed. Check Settings and tokens.');
                    setDeploymentStatus('idle');
                    setPublishLoading(false);
                    setTimeout(() => setShowPublishPanel(false), 1000);
                  } finally {
                    loadDeployStatus();
                  }
                }}
                className={`w-full px-4 py-3 rounded-xl font-medium text-white transition ${
                  publishLoading || deploymentStatus === 'deploying' || !githubConnected || !vercelConnected
                    ? 'bg-slate-400 cursor-not-allowed'
                    : 'bg-black hover:bg-slate-900'
                }`}
              >
                {publishLoading ? 'Publishing…' : deploymentStatus === 'deploying' ? 'Deploying…' : (!githubConnected || !vercelConnected) ? 'Connect Services First' : (deploymentStatus === 'ready' && publishedUrl ? 'Update' : 'Publish')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Project Settings Modal */}
      <ProjectSettings
        isOpen={showGlobalSettings}
        onClose={() => setShowGlobalSettings(false)}
        projectId={projectId}
        projectName={projectName}
        projectDescription={projectDescription}
        initialTab="services"
        onProjectUpdated={({ name, description }) => {
          setProjectName(name);
          setProjectDescription(description ?? '');
        }}
      />
    </>
  );
}
