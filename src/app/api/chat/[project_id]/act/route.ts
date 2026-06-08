/**
 * Travel-only chat action endpoint.
 *
 * The route never falls back to the legacy QuantPilot/CLI generation flow.
 * Database writes are best-effort so local demos still work when Postgres is
 * not running.
 */

import fs from 'fs/promises';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { createMessage } from '@/lib/services/message';
import { getProjectById, updateProjectActivity } from '@/lib/services/project';
import { streamManager } from '@/lib/services/stream';
import { markUserRequestAsCompleted, upsertUserRequest } from '@/lib/services/user-requests';
import { serializeMessage } from '@/lib/serializers/chat';
import { generateProjectId } from '@/lib/utils';
import type { ChatActRequest } from '@/types/backend';
import { warmTravelData } from '@/lib/travel/planner';
import { executeTravelPlanningSession, type TravelPlanningSessionState } from '@/lib/travel/orchestration';

interface RouteContext {
  params: Promise<{ project_id: string }>;
}

type TravelProgressStage =
  | 'received'
  | 'parsing'
  | 'retrieving_poi'
  | 'planning'
  | 'writing_artifacts'
  | 'rendering'
  | 'completed';

const TRAVEL_PROGRESS_LABELS: Record<TravelProgressStage, string> = {
  received: '旅游规划任务已收到，正在启动北京路线规划链路。',
  parsing: '已识别本轮游玩目标和约束。',
  retrieving_poi: '正在读取本地北京 POI/UGC 数据并筛选候选点。',
  planning: '正在生成或调整可执行路线方案。',
  writing_artifacts: '正在写入 itinerary-data.json 和证据文件。',
  rendering: '已更新右侧“北京智能路线方案”。',
  completed: '北京旅游路线规划完成。',
};

const TRAVEL_CAPABILITY_IDS = new Set([
  'culture_route',
  'mixed_food_route',
  'family_low_queue',
  'budget_route',
  'efficient_route',
  'replan_compare',
]);

const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(process.cwd(), PROJECTS_DIR);

function coerceString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function resolveProjectRoot(projectId: string, repoPath?: string | null): string {
  if (repoPath) {
    return path.isAbsolute(repoPath) ? repoPath : path.resolve(process.cwd(), repoPath);
  }
  return path.join(PROJECTS_DIR_ABSOLUTE, projectId);
}

function resolveTravelCapabilityId(value?: string | null): string {
  return value && TRAVEL_CAPABILITY_IDS.has(value) ? value : 'mixed_food_route';
}

function normalizeTravelInstruction(value: string): string {
  return value
    .trim()
    .replace(/^[/\\]+\s*/, '')
    .replace(/^(travel|route|replan|plan)\s*[:：]\s*/i, '')
    .trim();
}

function isTravelAdjustmentText(value: string): boolean {
  const normalized = normalizeTravelInstruction(value);
  if (/(预算降到|重新规划|保留|不去|别去|不要去|去掉|排除|避开|取消|删除|替换|换一个|换成|改成|调整|仍然|控制在|添加|加一个|增加|再加|顺路|其他地方不变|午餐不变|午餐地点|吃饭地点|还想|也想|想去|有点想去|能不能.*(?:安排|加|放|去)|顺便.*(?:去|看|逛)|补一个|加上|放进去|排进去)/.test(normalized)) return true;
  if (/(重新做|重新来|新路线|换个区域|不要之前|不保留原路线)/.test(normalized)) return false;
  return normalized.length <= 24 && /(长城|八达岭|慕田峪|故宫|天坛|颐和园|圆明园|环球影城|北海|景山|雍和宫|国博|国家博物馆|恭王府|鸟巢|水立方|798|三里屯|南锣鼓巷|什刹海|后海|前门|王府井|博物馆|美术馆|展馆|公园|景区|景点|胡同|寺|庙|宫|园|城)/.test(normalized);
}

function publishTravelProgress(params: {
  projectId: string;
  requestId: string;
  stage: TravelProgressStage;
  startedAt: number;
  conversationId?: string | null;
  final?: boolean;
}) {
  const message = TRAVEL_PROGRESS_LABELS[params.stage];
  const elapsedMs = Math.max(0, Math.round(performance.now() - params.startedAt));
  streamManager.publish(params.projectId, {
    type: 'travel_progress',
    data: { requestId: params.requestId, stage: params.stage, message, elapsed_ms: elapsedMs },
  });
  streamManager.publish(params.projectId, {
    type: 'message',
    data: {
      id: `${params.requestId}-travel-progress-${params.stage}`,
      projectId: params.projectId,
      role: 'assistant',
      messageType: 'chat',
      content: message,
      conversationId: params.conversationId ?? null,
      cliSource: 'local-travel-planner',
      requestId: `${params.requestId}-travel-progress-${params.stage}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      isStreaming: !params.final,
      isFinal: Boolean(params.final),
      isOptimistic: true,
      metadata: { type: 'travel_progress', stage: params.stage, elapsed_ms: elapsedMs, localOnly: true },
    },
  });
}

function buildTravelAssistantMessage(result: Record<string, any>): string {
  const planning = result.planning_response || {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const dailyItinerary = Array.isArray(planning.daily_itinerary) ? planning.daily_itinerary : [];
  const routePatchSummary = planning.replan_metadata?.adjustment_text || planning.replan_metadata?.route_patch_summary
    ? planning.route_patch_summary || planning.replan_metadata?.route_patch_summary
    : null;
  const sla = planning.generation_metrics?.sla || {};
  const acceleration = planning.acceleration || {};
  const knowledgeGuidance = planning.knowledge_guidance || {};
  const lines = ['# 北京旅行规划已生成', '', `目的地：${planning.resolved_area || result.parsed_request?.area || '北京'}`, ''];

  lines.push(
    '## 生成状态',
    `- 响应 SLA：${sla.within_10s === false ? '超过 10 秒' : '10 秒内完成'}${sla.elapsed_ms !== undefined ? `（${sla.elapsed_ms}ms）` : ''}`,
    `- 规划路径：${sla.fast_path || (planning.route_corpus_match?.used ? 'route_corpus' : 'local_planner')}`,
    `- 加速层：${Array.isArray(acceleration.cache_layers_hit) && acceleration.cache_layers_hit.length ? acceleration.cache_layers_hit.join('、') : 'memory_data'}`,
    `- 常见语义加速：${acceleration.layers?.common_semantic_fast_path ? '已命中' : '未命中'}`,
    `- 知识库引导：${knowledgeGuidance.enabled ? `已启用（${knowledgeGuidance.knowledge_base?.hit_count ?? 0} 条命中）` : '未阻塞主链路'}`,
    `- LLM 阻塞主链路：${sla.llm_blocking ? '是' : '否'}`,
    '',
  );

  if (routePatchSummary) {
    const kept = Array.isArray(routePatchSummary.preserved_poi_ids) ? routePatchSummary.preserved_poi_ids.length : Array.isArray(routePatchSummary.kept) ? routePatchSummary.kept.length : 0;
    const removed = Array.isArray(routePatchSummary.removed_poi_ids) ? routePatchSummary.removed_poi_ids.length : Array.isArray(routePatchSummary.removed) ? routePatchSummary.removed.length : 0;
    const added = Array.isArray(routePatchSummary.added_poi_ids) ? routePatchSummary.added_poi_ids.length : Array.isArray(routePatchSummary.added) ? routePatchSummary.added.length : 0;
    const beforeNames = Array.isArray(routePatchSummary.before_route_names) ? routePatchSummary.before_route_names.join(' -> ') : '';
    const afterNames = Array.isArray(routePatchSummary.after_route_names) ? routePatchSummary.after_route_names.join(' -> ') : '';
    lines.push('## 本次调整');
    lines.push(`- 变化状态：${routePatchSummary.changed || routePatchSummary.reordered || removed > 0 || added > 0 ? '路线已局部更新' : '路线保持稳定'}`);
    lines.push(`- 保留/删除/新增：${kept}/${removed}/${added}`);
    if (beforeNames) lines.push(`- 调整前：${beforeNames}`);
    if (afterNames) lines.push(`- 调整后：${afterNames}`);
    lines.push('');
  }

  if (planning.natural_language_explanation) {
    lines.push('## 路线说明', String(planning.natural_language_explanation), '');
  }

  if (planning.llm_rerank) {
    lines.push(
      '## 规划依据',
      `- 主推方案：${planning.final_selected_proposal_id ?? planning.llm_rerank.primary_proposal_id ?? '-'}`,
      `- 选择依据：${planning.llm_rerank.rerank_source === 'wiki_local' ? '本地旅行知识与地点证据' : planning.llm_rerank.llm_used ? '你的偏好与路线可执行性' : '本地规划规则'}`,
      planning.llm_rerank.fallback_reason ? `- 注意事项：${planning.llm_rerank.fallback_reason}` : '- 注意事项：暂无硬性风险',
      '',
    );
  }

  if (planning.wiki_retrieval) {
    const hits = Array.isArray(planning.wiki_retrieval.hits) ? planning.wiki_retrieval.hits.slice(0, 5) : [];
    lines.push(
      '## 参考地点',
      ...hits.map((hit: Record<string, any>) => `- ${hit.title || '-'}`),
      '',
    );
  }

  if (dailyItinerary.length > 1) {
    lines.push('## 多日行程安排');
    dailyItinerary.forEach((day: Record<string, any>, index: number) => {
      const proposal = day.proposal || {};
      const names = Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.join(' -> ') : '暂无候选 POI';
      const checks = proposal.constraint_report?.checks || {};
      lines.push(
        `### ${day.title || `第 ${index + 1} 天`}：${day.area || planning.resolved_area || '北京'}`,
        `- 主题：${day.theme || proposal.display_title || proposal.title || '日程方案'}`,
        `- 预计时长：${proposal.total_route_duration_min ?? '-'} 分钟，预算 ${proposal.total_budget_estimate ?? '-'} 元`,
        `- 覆盖：${checks.poi_count?.actual ?? proposal.ordered_poi_names?.length ?? '-'} 个 POI，餐饮 ${checks.category_coverage?.food_count ?? '-'} 个，文化/娱乐 ${checks.category_coverage?.culture_or_entertainment_count ?? '-'} 个`,
        `- 路线：${names}`,
        '',
      );
    });
  }

  proposals.forEach((proposal: Record<string, any>, index: number) => {
    const names = Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.join(' -> ') : '暂无候选 POI';
    const risks = Array.isArray(proposal.risks) && proposal.risks.length > 0 ? proposal.risks.slice(0, 2).join('；') : '未发现硬约束风险';
    const transferSummary = proposal.transfer_source_summary || proposal.quality_summary?.commute || {};
    const commuteEdgesUsed = Number(transferSummary.commute_edges_used || 0);
    const coordinateEstimatesUsed = Number(transferSummary.coordinate_estimates_used || 0);
    const report = proposal.constraint_report || {};
    const checks = report.checks || {};
    const resolution = proposal.constraint_resolution || {};
    const readiness = proposal.quality_summary?.competition_readiness_score;
    lines.push(
      `## 方案 ${index + 1}：${proposal.display_title || proposal.title || proposal.strategy || '路线方案'}`,
      `- 预计总时长：${proposal.total_route_duration_min ?? '-'} 分钟`,
      `- 预计预算：${proposal.total_budget_estimate ?? '-'} 元`,
      `- 预计转移/步行：${proposal.total_transfer_minutes ?? '-'} 分钟，${proposal.total_walking_distance_m ?? '-'} 米`,
      `- 命题覆盖：${checks.poi_count?.actual ?? proposal.ordered_poi_names?.length ?? '-'} 个 POI，餐饮 ${checks.category_coverage?.food_count ?? '-'} 个，文化/娱乐 ${checks.category_coverage?.culture_or_entertainment_count ?? '-'} 个`,
      `- 约束满足：预算 ${checks.budget?.satisfied === false ? '需取舍' : '满足'}，时长 ${checks.duration?.satisfied === false ? '需取舍' : '满足'}，少排队 ${checks.queue?.satisfied === false ? '需取舍' : '满足'}，营业时间 ${checks.opening_hours?.satisfied === false ? '需取舍' : '可执行'}`,
      readiness !== undefined ? `- 可用性评分：${Math.round(Number(readiness) * 100)}%` : '- 可用性评分：-',
      `- 冲突处理：${resolution.user_visible_summary || '核心约束已完成校验'}`,
      `- 转移估算：${commuteEdgesUsed} 段有本地通勤数据，${coordinateEstimatesUsed} 段按距离估算`,
      `- 路线：${names}`,
      `- 风险：${risks}`,
      '',
    );
  });

  lines.push(
    `数据来源：${planning.generation_metrics?.database_recall_used ? '已使用本地北京旅行数据库' : '已使用本地旅行规划数据'}`,
    '说明：转移时间和排队热度是规划参考，出发前仍建议核对实时交通与景区开放信息。',
  );
  return lines.join('\n');
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderTravelDashboardHtml(result: Record<string, any>): string {
  const planning = result.planning_response || {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const dailyItinerary = Array.isArray(planning.daily_itinerary) ? planning.daily_itinerary : [];
  const primary = proposals[0] || {};
  const checks = primary.constraint_report?.checks || {};
  const sla = planning.generation_metrics?.sla || {};
  const acceleration = planning.acceleration || {};
  const knowledgeGuidance = planning.knowledge_guidance || {};
  const patch = planning.replan_metadata?.adjustment_text || planning.replan_metadata?.route_patch_summary
    ? planning.route_patch_summary || planning.replan_metadata?.route_patch_summary
    : null;
  const proposalCards = proposals.map((proposal: Record<string, any>) => {
    const report = proposal.constraint_report?.checks || {};
    return `
      <article class="proposal">
        <h3>${escapeHtml(proposal.display_title || proposal.title || proposal.strategy || '路线方案')}</h3>
        <p>${escapeHtml(Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.join(' -> ') : '-')}</p>
        <dl>
          <div><dt>时长</dt><dd>${escapeHtml(proposal.total_route_duration_min ?? '-')} 分钟</dd></div>
          <div><dt>预算</dt><dd>${escapeHtml(proposal.total_budget_estimate ?? '-')} 元</dd></div>
          <div><dt>覆盖</dt><dd>${escapeHtml(report.category_coverage?.food_count ?? 0)} 餐饮 / ${escapeHtml(report.category_coverage?.culture_or_entertainment_count ?? 0)} 文化</dd></div>
          <div><dt>冲突</dt><dd>${escapeHtml(proposal.constraint_resolution?.relaxed_constraints?.length ?? 0)} 项</dd></div>
        </dl>
      </article>`;
  }).join('');
  const timeline = (Array.isArray(primary.pois) ? primary.pois : []).map((poi: Record<string, any>) => `
    <li>
      <div class="time">${escapeHtml(poi.arrival_time || '--:--')}<small>${escapeHtml(poi.departure_time || '--:--')}</small></div>
      <div>
        <h3>${escapeHtml(poi.name)}</h3>
        <p>${escapeHtml(poi.poi_type === 'food' ? '餐饮' : '文化/娱乐')} · 停留 ${escapeHtml(poi.stay_minutes ?? '-')} 分钟 · 预算 ${escapeHtml(poi.estimated_cost ?? 0)} 元</p>
        <p>${escapeHtml(poi.recommendation_reason || '本地 POI 与 UGC 信号推荐')}</p>
      </div>
    </li>`).join('');
  const dailyTimeline = dailyItinerary.length > 1 ? dailyItinerary.map((day: Record<string, any>, dayIndex: number) => {
    const proposal = day.proposal || {};
    const dayStops = Array.isArray(proposal.pois) ? proposal.pois : [];
    const stopItems = dayStops.map((poi: Record<string, any>) => `
      <li>
        <div class="time">${escapeHtml(poi.arrival_time || '--:--')}<small>${escapeHtml(poi.departure_time || '--:--')}</small></div>
        <div>
          <h3>${escapeHtml(poi.name)}</h3>
          <p>${escapeHtml(poi.poi_type === 'food' ? '餐饮' : '文化/娱乐')} · 停留 ${escapeHtml(poi.stay_minutes ?? '-')} 分钟 · 预算 ${escapeHtml(poi.estimated_cost ?? 0)} 元</p>
          <p>${escapeHtml(poi.recommendation_reason || '本地 POI 与 UGC 信号推荐')}</p>
        </div>
      </li>`).join('');
    return `
      <article class="day-card">
        <div class="panel-heading">
          <div><h2>${escapeHtml(day.title || `第 ${dayIndex + 1} 天`)}</h2><p>${escapeHtml(day.area || planning.resolved_area || '北京')} · ${escapeHtml(day.theme || proposal.display_title || '日程方案')}</p></div>
          <span>${escapeHtml(proposal.total_route_duration_min ?? '-')} 分钟</span>
        </div>
        <ol class="timeline">${stopItems}</ol>
      </article>`;
  }).join('') : '';
  const patchBlock = patch ? `
    <section class="panel">
      <div class="panel-heading"><h2>自然语言调整结果</h2><span>${patch.changed || patch.reordered ? '已更新' : '无变化'}</span></div>
      <div class="patch-grid">
        <p><b>调整前</b>${escapeHtml(Array.isArray(patch.before_route_names) ? patch.before_route_names.join(' -> ') : Array.isArray(patch.kept) ? patch.kept.join(' -> ') : '-')}</p>
        <p><b>调整后</b>${escapeHtml(Array.isArray(patch.after_route_names) ? patch.after_route_names.join(' -> ') : '-')}</p>
        <p><b>保留/删除/新增</b>${escapeHtml(patch.preserved_poi_ids?.length ?? patch.kept?.length ?? 0)}/${escapeHtml(patch.removed_poi_ids?.length ?? patch.removed?.length ?? 0)}/${escapeHtml(patch.added_poi_ids?.length ?? patch.added?.length ?? 0)}</p>
      </div>
    </section>` : '';
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>北京路线规划看板</title>
  <style>
    :root{color-scheme:light;--bg:#f6f7f4;--ink:#18201c;--muted:#647067;--panel:#fff;--soft:#eef3ef;--line:#d8ded8;--accent:#2f7d68}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,Helvetica,sans-serif}.shell{width:min(1180px,100%);margin:0 auto;padding:28px}.topbar{display:flex;justify-content:space-between;gap:20px;padding-bottom:20px}.eyebrow{margin:0 0 8px;color:var(--accent);font-size:12px;font-weight:700;text-transform:uppercase}h1{margin:0;font-size:34px;line-height:1.15}h2{margin:0;font-size:18px}h3{margin:0 0 8px;font-size:15px}p{color:var(--muted);font-size:14px;line-height:1.65}.status-pill,.panel,.summary-grid article,.proposal,.day-card{border:1px solid var(--line);border-radius:8px;background:var(--panel)}.status-pill{display:grid;gap:4px;min-width:150px;padding:10px 14px}.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:12px}.summary-grid article{min-height:112px;padding:16px}.summary-grid span,.status-pill span,.panel-heading span,.checks span,dt{color:var(--muted);font-size:12px}.summary-grid strong,.status-pill strong{display:block;font-size:20px}.layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(320px,.8fr);gap:12px;margin:12px 0}.panel,.day-card{padding:18px}.day-grid{display:grid;gap:12px;margin:12px 0}.panel-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.panel-heading span{padding:5px 8px;border-radius:6px;background:var(--soft);color:var(--accent);font-weight:700}.timeline{display:grid;gap:10px;margin:0;padding:0;list-style:none}.timeline li{display:grid;grid-template-columns:88px minmax(0,1fr);gap:14px;padding:12px;border:1px solid var(--line);border-radius:8px;background:#fbfcfb}.time{color:var(--accent);font-weight:800}.time small{display:block;margin-top:4px;color:var(--muted);font-weight:500}.checks{display:grid;gap:10px}.checks div{display:grid;grid-template-columns:74px 72px minmax(0,1fr);gap:8px;align-items:center;padding:10px;border-radius:8px;background:var(--soft)}.checks b{color:var(--accent);font-size:14px}.checks small{text-align:right;color:var(--muted)}.resolution{margin:14px 0 0;padding-top:14px;border-top:1px solid var(--line)}.patch-grid{display:grid;gap:8px}.patch-grid p{margin:0;padding:10px;border-radius:8px;background:var(--soft)}.patch-grid b{display:block;margin-bottom:4px;color:var(--ink)}.proposal-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.proposal{padding:14px}.proposal p{min-height:68px;margin-bottom:12px}dl{display:grid;gap:8px;margin:0}dl div{display:flex;justify-content:space-between;gap:10px;border-top:1px solid var(--line);padding-top:8px}dd{margin:0;text-align:right;font-weight:700}@media(max-width:900px){.topbar{display:grid}.layout{grid-template-columns:1fr}.summary-grid,.proposal-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.shell{padding:18px}h1{font-size:28px}.summary-grid,.proposal-grid,.timeline li{grid-template-columns:1fr}.checks div{grid-template-columns:1fr}.checks small{text-align:left}}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div><p class="eyebrow">Local intelligent route planner</p><h1>${escapeHtml(planning.resolved_area || '北京')}路线规划看板</h1></div>
      <div class="status-pill"><span>10 秒响应</span><strong>${sla.within_10s === false ? '超时' : '达标'}</strong></div>
    </header>
    <section class="summary-grid">
      <article><span>生成耗时</span><strong>${escapeHtml(sla.elapsed_ms ?? planning.generation_metrics?.elapsed_ms ?? '-')}ms</strong><p>${escapeHtml(sla.fast_path || 'local_planner')}</p></article>
      <article><span>${dailyItinerary.length > 1 ? '多日天数' : 'POI 串联'}</span><strong>${escapeHtml(dailyItinerary.length > 1 ? dailyItinerary.length : checks.poi_count?.actual ?? primary.ordered_poi_names?.length ?? '-')}</strong><p>${dailyItinerary.length > 1 ? '每天独立日程' : '至少 3 个 POI'}</p></article>
      <article><span>类型覆盖</span><strong>${escapeHtml(checks.category_coverage?.food_count ?? 0)} + ${escapeHtml(checks.category_coverage?.culture_or_entertainment_count ?? 0)}</strong><p>餐饮 + 文化/娱乐</p></article>
      <article><span>可用性评分</span><strong>${primary.quality_summary?.competition_readiness_score ? Math.round(Number(primary.quality_summary.competition_readiness_score) * 100) : '-'}%</strong><p>时间轴、证据、转场综合</p></article>
    </section>
    <section class="panel"><div class="panel-heading"><h2>加速与知识库</h2><span>${knowledgeGuidance.enabled ? '知识库引导' : '快路径优先'}</span></div><div class="checks">
      <div><span>语义加速</span><b>${acceleration.layers?.common_semantic_fast_path ? '命中' : '未命中'}</b><small>${escapeHtml(acceleration.parser || '-')}</small></div>
      <div><span>缓存层</span><b>${escapeHtml(Array.isArray(acceleration.cache_layers_hit) ? acceleration.cache_layers_hit.length : 0)} 层</b><small>${escapeHtml(Array.isArray(acceleration.cache_layers_hit) ? acceleration.cache_layers_hit.join(' / ') : '-')}</small></div>
      <div><span>知识库</span><b>${knowledgeGuidance.enabled ? '启用' : '未阻塞'}</b><small>${escapeHtml(knowledgeGuidance.knowledge_base?.hit_count ?? 0)} 条命中</small></div>
    </div><p class="resolution">${escapeHtml(knowledgeGuidance.user_visible_summary || '加速层优先保障 10 秒内返回。')}</p></section>
    ${patchBlock}
    ${dailyTimeline ? `<section class="day-grid">${dailyTimeline}</section>` : ''}
    <section class="layout">
      <div class="panel"><div class="panel-heading"><h2>主推路线</h2><span>${escapeHtml(primary.display_title || primary.title || primary.strategy || '方案')}</span></div><ol class="timeline">${timeline}</ol></div>
      <aside class="panel">
        <div class="panel-heading"><h2>约束报告</h2><span>${primary.constraint_report?.overall_satisfied ? '全部满足' : '显式取舍'}</span></div>
        <div class="checks">
          <div><span>预算</span><b>${checks.budget?.satisfied === false ? '需取舍' : '满足'}</b><small>${escapeHtml(checks.budget?.estimated_budget ?? primary.total_budget_estimate ?? '-')} 元</small></div>
          <div><span>时长</span><b>${checks.duration?.satisfied === false ? '需取舍' : '满足'}</b><small>${escapeHtml(checks.duration?.estimated_duration_min ?? primary.total_route_duration_min ?? '-')} 分钟</small></div>
          <div><span>少排队</span><b>${checks.queue?.satisfied === false ? '需取舍' : '满足'}</b><small>${escapeHtml(checks.queue?.high_queue_stop_names?.length ?? 0)} 个风险点</small></div>
          <div><span>少走路</span><b>${checks.distance?.satisfied === false ? '需取舍' : '满足'}</b><small>${escapeHtml(checks.distance?.estimated_transfer_distance_m ?? primary.total_walking_distance_m ?? '-')} 米</small></div>
          <div><span>营业时间</span><b>${checks.opening_hours?.satisfied === false ? '需复核' : '可执行'}</b><small>${escapeHtml(checks.opening_hours?.unknown_count ?? 0)} 个未知</small></div>
        </div>
        <p class="resolution">${escapeHtml(primary.constraint_resolution?.user_visible_summary || '路线已完成多约束校验。')}</p>
      </aside>
    </section>
    <section class="panel"><div class="panel-heading"><h2>多方案对比</h2><span>${proposals.length} 套方案</span></div><div class="proposal-grid">${proposalCards}</div></section>
  </main>
</body>
</html>`;
}

async function writeTravelPlanArtifacts(params: {
  projectPath: string;
  requestId: string;
  capabilityId: string;
  instruction: string;
  result: Record<string, any>;
  agentTrace?: Array<Record<string, any>>;
  sessionState?: TravelPlanningSessionState | null;
}) {
  const travelDir = path.join(params.projectPath, '.travelpilot');
  const finalDir = path.join(params.projectPath, 'data_file', 'final');
  const evidenceDir = path.join(params.projectPath, 'evidence');
  const dashboardDir = path.join(params.projectPath, 'dashboard');
  await Promise.all([
    fs.mkdir(travelDir, { recursive: true }),
    fs.mkdir(finalDir, { recursive: true }),
    fs.mkdir(evidenceDir, { recursive: true }),
    fs.mkdir(dashboardDir, { recursive: true }),
  ]);

  const now = new Date().toISOString();
  const planning = params.result.planning_response || {};
  const primaryProposal = Array.isArray(planning.proposals) ? planning.proposals[0] : null;
  await Promise.all([
    fs.writeFile(
      path.join(travelDir, 'run_plan.json'),
      `${JSON.stringify(
        {
          schemaVersion: 2,
          product: 'beijing-travel-agent',
          requestId: params.requestId,
          capabilityId: params.capabilityId,
          status: 'completed',
          instruction: params.instruction,
          artifactPaths: {
            itinerary: 'data_file/final/itinerary-data.json',
            sources: 'evidence/sources.json',
            dataQuality: 'evidence/data_quality.json',
            diagnostics: '.travelpilot/session-state.json',
          },
          createdAt: now,
          updatedAt: now,
        },
        null,
        2,
      )}\n`,
      'utf8',
    ),
    fs.writeFile(path.join(finalDir, 'itinerary-data.json'), `${JSON.stringify(params.result, null, 2)}\n`, 'utf8'),
    fs.writeFile(path.join(dashboardDir, 'index.html'), renderTravelDashboardHtml(params.result), 'utf8'),
    fs.writeFile(path.join(travelDir, 'agent-trace.json'), `${JSON.stringify(params.agentTrace || [], null, 2)}\n`, 'utf8'),
    fs.writeFile(path.join(travelDir, 'session-state.json'), `${JSON.stringify(params.sessionState || {}, null, 2)}\n`, 'utf8'),
    fs.writeFile(
      path.join(evidenceDir, 'sources.json'),
      `${JSON.stringify(
        {
          generatedAt: now,
          dataSource: 'travel-data/processed',
          evidence: planning.evidence || params.result.evidence || [],
          dataFiles: [
            'beijing_planner_entities.json',
            'beijing_mixed_category_pois.json',
            'beijing_culture_pois.json',
            'beijing_poi_feature_aggregates.json',
            'beijing_review_records.json',
          ],
        },
        null,
        2,
      )}\n`,
      'utf8',
    ),
    fs.writeFile(
      path.join(evidenceDir, 'data_quality.json'),
      `${JSON.stringify(
        {
          generatedAt: now,
          dataSource: 'travel-data/processed',
          realtimeData: false,
          proposalCount: Array.isArray(planning.proposals) ? planning.proposals.length : 0,
          generationMetrics: planning.generation_metrics || null,
          sla: planning.generation_metrics?.sla || null,
          constraintReport: primaryProposal?.constraint_report || null,
          constraintResolution: primaryProposal?.constraint_resolution || null,
          routePatchSummary: planning.route_patch_summary || planning.replan_metadata?.route_patch_summary || null,
          limitations: [
            '未接入实时地图、实时排队或外部点评 API。',
            '转移时间优先来自 travel_commute_edges 通勤库，缺失路段回退坐标估算；排队风险为本地静态信号。',
          ],
        },
        null,
        2,
      )}\n`,
      'utf8',
    ),
  ]);
}

async function readExistingTravelItinerary(projectPath: string): Promise<Record<string, any> | null> {
  try {
    const raw = await fs.readFile(path.join(projectPath, 'data_file', 'final', 'itinerary-data.json'), 'utf8');
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

async function saveTravelMessages(params: {
  projectId: string;
  requestId: string;
  conversationId?: string | null;
  userContent: string;
  assistantContent: string;
  assistantMetadata?: Record<string, unknown>;
}): Promise<{ userMessageId: string; assistantMessageId: string; persisted: boolean }> {
  try {
    const userMessage = await createMessage({
      projectId: params.projectId,
      role: 'user',
      messageType: 'chat',
      content: params.userContent,
      conversationId: params.conversationId ?? undefined,
      cliSource: 'local-travel-planner',
      requestId: params.requestId,
    });
    const assistantMessage = await createMessage({
      projectId: params.projectId,
      role: 'assistant',
      messageType: 'chat',
      content: params.assistantContent,
      conversationId: params.conversationId ?? undefined,
      cliSource: 'local-travel-planner',
      metadata: params.assistantMetadata,
      requestId: params.requestId,
    });
    streamManager.publish(params.projectId, { type: 'message', data: serializeMessage(userMessage, { requestId: params.requestId }) });
    streamManager.publish(params.projectId, { type: 'message', data: serializeMessage(assistantMessage, { requestId: params.requestId }) });
    return { userMessageId: userMessage.id, assistantMessageId: assistantMessage.id, persisted: true };
  } catch (error) {
    console.warn('[TravelChat] Database unavailable; streaming local-only messages instead.', error);
  }

  const now = new Date().toISOString();
  const userMessageId = `${params.requestId}-user-local`;
  const assistantMessageId = `${params.requestId}-assistant-local`;
  streamManager.publish(params.projectId, {
    type: 'message',
    data: {
      id: userMessageId,
      projectId: params.projectId,
      role: 'user',
      messageType: 'chat',
      content: params.userContent,
      conversationId: params.conversationId ?? null,
      cliSource: 'local-travel-planner',
      requestId: params.requestId,
      createdAt: now,
      updatedAt: now,
      metadata: { localOnly: true },
    },
  });
  streamManager.publish(params.projectId, {
    type: 'message',
    data: {
      id: assistantMessageId,
      projectId: params.projectId,
      role: 'assistant',
      messageType: 'chat',
      content: params.assistantContent,
      conversationId: params.conversationId ?? null,
      cliSource: 'local-travel-planner',
      requestId: params.requestId,
      createdAt: now,
      updatedAt: now,
      metadata: { ...params.assistantMetadata, localOnly: true },
    },
  });
  return { userMessageId, assistantMessageId, persisted: false };
}

function buildImagePreferenceText(images: unknown[]): string {
  if (images.length === 0) return '';
  return `\n\n用户上传了 ${images.length} 张图片附件；当前旅游规划会把图片作为出行偏好、目的地或风格线索。`;
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  try {
    const { project_id } = await params;
    const rawBody = await request.json().catch(() => ({}));
    const body = (rawBody && typeof rawBody === 'object' ? rawBody : {}) as ChatActRequest & Record<string, unknown>;

    const project = await getProjectById(project_id);
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 });

    const legacyBody = body as Record<string, unknown>;
    const projectPath = resolveProjectRoot(project_id, project.repoPath);
    const rawInstruction = typeof body.instruction === 'string' ? body.instruction : '';
    const displayInstruction = coerceString(body.displayInstruction) ?? coerceString(legacyBody.display_instruction) ?? rawInstruction;
    const conversationId = coerceString(body.conversationId) ?? coerceString(legacyBody.conversation_id);
    const requestId = coerceString(body.requestId) ?? coerceString(legacyBody.request_id) ?? generateProjectId();
    const rawImages = Array.isArray(body.images) ? body.images : [];

    const finalInstruction = `${normalizeTravelInstruction(displayInstruction || rawInstruction)}${buildImagePreferenceText(rawImages)}`.trim();
    if (!finalInstruction) return NextResponse.json({ success: false, error: 'instruction is required' }, { status: 400 });

    await upsertUserRequest({ id: requestId, projectId: project_id, instruction: finalInstruction, cliPreference: 'local-travel-planner' }).catch(() => {});
    await updateProjectActivity(project_id).catch(() => {});

    const legacyCapabilityId = coerceString(body.quantCapabilityId) ?? coerceString(legacyBody.quant_capability_id) ?? coerceString(body.capabilityId) ?? coerceString(legacyBody.capability_id);
    const selectedTravelCapabilityId = resolveTravelCapabilityId(coerceString(body.travelCapabilityId) ?? legacyCapabilityId);
    const existingItinerary = await readExistingTravelItinerary(projectPath);
    const shouldReplan = Boolean(existingItinerary) && isTravelAdjustmentText(finalInstruction);

    const startedAt = performance.now();
    publishTravelProgress({ projectId: project_id, requestId, stage: 'received', startedAt, conversationId });
    publishTravelProgress({ projectId: project_id, requestId, stage: 'parsing', startedAt, conversationId });
    publishTravelProgress({ projectId: project_id, requestId, stage: 'retrieving_poi', startedAt, conversationId });
    await warmTravelData();
    publishTravelProgress({ projectId: project_id, requestId, stage: 'planning', startedAt, conversationId });

    const orchestration = await executeTravelPlanningSession({
      text: finalInstruction,
      requestId,
      existingItinerary: shouldReplan ? existingItinerary : null,
    });

    if (orchestration.status === 'travel_clarification_required') {
      const messages = await saveTravelMessages({
        projectId: project_id,
        requestId,
        conversationId,
        userContent: finalInstruction,
        assistantContent: orchestration.clarification?.message || '需要补充信息后再继续规划。',
        assistantMetadata: {
          type: 'travel_clarification_required',
          reason: orchestration.clarification?.reason,
          sessionStateSummary: orchestration.sessionStateSummary,
          clarificationPayload: orchestration.clarificationPayload,
        },
      });
      await markUserRequestAsCompleted(requestId).catch(() => {});
      streamManager.publish(project_id, {
        type: 'status',
        data: {
          status: 'travel_clarification_required',
          message: orchestration.clarification?.message || '需要补充信息后再继续规划。',
          requestId,
          metadata: {
            reason: orchestration.clarification?.reason,
            sessionStateSummary: orchestration.sessionStateSummary,
            clarificationPayload: orchestration.clarificationPayload,
          },
        },
      });
      return NextResponse.json({
        success: true,
        status: 'travel_clarification_required',
        requestId,
        userMessageId: messages.userMessageId,
        assistantMessageId: messages.assistantMessageId,
        persistedMessages: messages.persisted,
        conversationId: conversationId ?? null,
        message: orchestration.clarification?.message || '需要补充信息后再继续规划。',
        needsClarification: true,
        sessionStateSummary: orchestration.sessionStateSummary,
        clarificationPayload: orchestration.clarificationPayload,
        agentTrace: orchestration.agentTrace,
      });
    }

    const travelResult = {
      parsed_request: orchestration.parsed_request || {},
      parser_confidence: orchestration.parser_confidence ?? 0.86,
      parser_notes: orchestration.parser_notes || [],
      parser_correction_hints: orchestration.parser_correction_hints || [],
      planning_response: orchestration.planning_response || {},
      agent_trace: orchestration.agentTrace,
      session_state_summary: orchestration.sessionStateSummary,
    };
    const planningResponse = travelResult.planning_response as Record<string, any>;

    publishTravelProgress({ projectId: project_id, requestId, stage: 'writing_artifacts', startedAt, conversationId });
    await writeTravelPlanArtifacts({
      projectPath,
      requestId,
      capabilityId: selectedTravelCapabilityId,
      instruction: finalInstruction,
      result: travelResult as Record<string, any>,
      agentTrace: orchestration.agentTrace,
      sessionState: orchestration.sessionState,
    });
    publishTravelProgress({ projectId: project_id, requestId, stage: 'rendering', startedAt, conversationId });

    const status = orchestration.status;
    const messages = await saveTravelMessages({
      projectId: project_id,
      requestId,
      conversationId,
      userContent: finalInstruction,
      assistantContent: buildTravelAssistantMessage(travelResult as Record<string, any>),
      assistantMetadata: {
        type: status,
        capabilityId: selectedTravelCapabilityId,
        itineraryPath: 'data_file/final/itinerary-data.json',
        evidencePath: 'evidence/sources.json',
        runPlanPath: '.travelpilot/run_plan.json',
        generationMetrics: planningResponse.generation_metrics,
        replanMetadata: planningResponse.replan_metadata,
        sessionStateSummary: orchestration.sessionStateSummary,
      },
    });
    await markUserRequestAsCompleted(requestId).catch(() => {});

    streamManager.publish(project_id, {
      type: 'status',
      data: {
        status,
        message: status === 'travel_replan_completed' ? '北京旅游路线已基于上一轮结果完成动态重规划。' : '北京旅游路线已基于本地 POI/UGC 数据完成规划。',
        requestId,
        metadata: {
          capabilityId: selectedTravelCapabilityId,
          itineraryPath: 'data_file/final/itinerary-data.json',
          proposalCount: Array.isArray(planningResponse.proposals) ? planningResponse.proposals.length : 0,
          sessionStateSummary: orchestration.sessionStateSummary,
        },
      },
    });
    publishTravelProgress({ projectId: project_id, requestId, stage: 'completed', startedAt, conversationId, final: true });

    return NextResponse.json({
      success: true,
      status,
      requestId,
      userMessageId: messages.userMessageId,
      assistantMessageId: messages.assistantMessageId,
      persistedMessages: messages.persisted,
      conversationId: conversationId ?? null,
      itineraryPath: 'data_file/final/itinerary-data.json',
      proposalCount: Array.isArray(planningResponse.proposals) ? planningResponse.proposals.length : 0,
      travelItinerary: travelResult,
      agentTrace: orchestration.agentTrace,
      sessionStateSummary: orchestration.sessionStateSummary,
      clarificationPayload: orchestration.clarificationPayload ?? null,
    });
  } catch (error) {
    console.error('[TravelChat] Failed to execute travel planning:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to execute travel planning', message: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 },
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
