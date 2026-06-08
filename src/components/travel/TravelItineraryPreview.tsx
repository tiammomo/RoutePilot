"use client";

import { useState } from 'react';
import Image from 'next/image';

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


export type TravelItineraryData = {
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
    hotel_recommendations?: Array<Record<string, any>>;
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

export default function TravelItineraryPreview({ data }: { data: TravelItineraryData }) {
  const planning = data.planning_response ?? {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const dailyItinerary = Array.isArray(planning.daily_itinerary) ? planning.daily_itinerary : [];
  const primary = proposals[0];
  const stops = Array.isArray(primary?.pois) ? primary.pois : [];
  const naturalLanguageExplanation = String(planning.natural_language_explanation || '');
  const routePatchSummary = planning.route_patch_summary;
  const selectedReasons = Array.isArray(primary?.selection_reasons) ? primary.selection_reasons : [];
  const keptStops = Array.isArray(routePatchSummary?.kept) ? routePatchSummary.kept : [];
  const removedStops = Array.isArray(routePatchSummary?.removed) ? routePatchSummary.removed : [];
  const addedStops = Array.isArray(routePatchSummary?.added) ? routePatchSummary.added : [];
  const hasRouteDiff = keptStops.length > 0 || removedStops.length > 0 || addedStops.length > 0 || Boolean(routePatchSummary?.reordered);
  const reasonFor = (poiId?: string) =>
    selectedReasons.find((item: Record<string, any>) => item.poi_id === poiId)?.reason;
  const transferSummary = primary?.transfer_source_summary || primary?.quality_summary?.commute || {};
  const commuteEdgesUsed = Number(transferSummary.commute_edges_used || 0);
  const coordinateEstimatesUsed = Number(transferSummary.coordinate_estimates_used || 0);
  const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);
  const selectedPlan = proposals[selectedPlanIndex] || primary;
  const selectedDailyItinerary = Array.isArray(selectedPlan?.daily_itinerary) && selectedPlan.daily_itinerary.length > 0
    ? selectedPlan.daily_itinerary
    : dailyItinerary;
  const selectedStops = Array.isArray(selectedPlan?.pois) ? selectedPlan.pois : stops;
  const accommodation = selectedPlan?.accommodation || selectedDailyItinerary.find((day: Record<string, any>) => day.accommodation)?.accommodation || null;
  const hotelRecommendations = (
    Array.isArray(selectedPlan?.hotel_recommendations) && selectedPlan.hotel_recommendations.length > 0
      ? selectedPlan.hotel_recommendations
      : Array.isArray(planning.hotel_recommendations)
        ? planning.hotel_recommendations
        : []
  ).slice(0, 3);
  const dayCount = selectedDailyItinerary.length || planning.day_count || 1;
  const isMultiDay = selectedDailyItinerary.length > 1;
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
  const transferModeLabel = (stop: Record<string, any>) => {
    const mode = String(stop.transfer_mode || '').toLowerCase();
    const source = String(stop.transfer_source || '').toLowerCase();
    if (mode === 'walking' || mode === 'walking_estimate') return source === 'commute_edge' ? '步行' : '步行估算';
    if (mode === 'bike_estimate' || mode === 'cycling' || mode === 'bike') return '骑行估算';
    if (mode === 'transit' || mode === 'subway' || mode === 'bus') return '公共交通';
    if (mode === 'taxi' || mode === 'driving') return '打车/驾车';
    return source === 'commute_edge' ? '本地通勤数据' : '坐标估算';
  };
  const transferLine = (stop: Record<string, any>) =>
    `${transferModeLabel(stop)} · 约 ${stop.transfer_from_previous_minutes ?? '-'} 分钟 · ${stop.transfer_from_previous_meters ?? '-'} 米`;

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
                  <Image
                    src={coverImages[selectedPlanIndex % coverImages.length]}
                    alt=""
                    fill
                    sizes="(min-width: 1280px) calc(100vw - 432px), 100vw"
                    className="object-cover opacity-85 saturate-125"
                  />
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
                    {selectedDailyItinerary.map((day: Record<string, any>, dayIndex: number) => {
                      const dayProposal = day.proposal || {};
                      const dayStops = Array.isArray(dayProposal.pois) ? dayProposal.pois : [];
                      const dayAccommodation = day.accommodation || dayProposal.accommodation || accommodation;
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
                          {dayAccommodation ? (
                            <div className="mb-5 rounded-2xl bg-[#eef8f3] p-4 text-sm leading-6 text-[#236247]">
                              <p className="font-black">住宿锚点：{dayAccommodation.name}</p>
                              <p>
                                出发到首站约 {dayAccommodation.outbound_transfer_minutes ?? '-'} 分钟 · {dayAccommodation.outbound_transfer_meters ?? '-'} 米；
                                末站返回约 {dayAccommodation.return_transfer_minutes ?? '-'} 分钟 · {dayAccommodation.return_transfer_meters ?? '-'} 米
                              </p>
                            </div>
                          ) : null}
                          <div className="space-y-4">
                            {dayStops.map((stop: Record<string, any>, index: number) => {
                              const previousStop = dayStops[index - 1] as Record<string, any> | undefined;
                              const transferFromName = previousStop?.name || stop.transfer_from_label;
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
                                      {transferFromName ? (
                                        <p className="mt-3 rounded-2xl bg-[#eef8f3] p-3 text-sm leading-6 text-[#236247]">
                                          通勤：{transferFromName} → {stop.name}，{transferLine(stop)}
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
                            const transferFromName = previousStop?.name || stop.transfer_from_label;
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
                                      {transferFromName ? (
                                        <div className="rounded-2xl bg-[#eef8f3] p-3 text-sm leading-6 text-[#236247]">
                                          <span className="font-black">通勤</span>
                                          <p>{transferFromName} → {stop.name}</p>
                                          <p>{transferLine(stop)}</p>
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
                    <p className="text-xs font-bold text-[#236247]">通勤</p>
                    <p className="mt-1 text-xl font-black">{selectedPlan.total_transfer_minutes ?? '-'} 分钟</p>
                  </div>
                </div>
                <div className="mt-5 rounded-2xl bg-[#fff8ed] p-4 text-sm leading-6 text-[#7a4d27]">
                  {accommodation
                    ? `住宿按“${accommodation.name}”作为每日出发/返回锚点，通勤为本地数据或坐标估算。`
                    : '按你的出行要求生成当前路线，优先兼顾时间、预算、步行距离和餐饮停留。'}
                </div>
              </section>

              {accommodation ? (
                <section className="rounded-[1.75rem] border border-[#eadcc9] bg-white p-6 shadow-sm">
                  <p className="text-sm font-black text-[#c46b42]">住宿与通勤</p>
                  <h2 className="mt-1 text-2xl font-black">{accommodation.name}</h2>
                  <p className="mt-2 text-sm font-semibold text-[#667085]">{accommodation.area || accommodation.district || '北京'} · {accommodation.address || '住宿区域锚点'}</p>
                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm font-black">
                    <div className="rounded-2xl bg-[#eef8f3] p-4 text-[#236247]">
                      <p className="text-xs text-[#236247]/70">出发到首站</p>
                      <p className="mt-1 text-xl">{accommodation.outbound_transfer_minutes ?? '-'} 分钟</p>
                    </div>
                    <div className="rounded-2xl bg-[#fff8ed] p-4 text-[#7a4d27]">
                      <p className="text-xs text-[#7a4d27]/70">末站返回</p>
                      <p className="mt-1 text-xl">{accommodation.return_transfer_minutes ?? '-'} 分钟</p>
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-[#667085]">{accommodation.note || '住宿位置按区域估算，真实酒店地址和实时导航需出发前确认。'}</p>
                </section>
              ) : null}

              {hotelRecommendations.length > 0 ? (
                <section className="rounded-[1.75rem] border border-[#eadcc9] bg-white p-6 shadow-sm">
                  <p className="text-sm font-black text-[#c46b42]">住宿推荐</p>
                  <h2 className="mt-1 text-2xl font-black">可选酒店方案</h2>
                  <div className="mt-4 space-y-3">
                    {hotelRecommendations.map((hotel: Record<string, any>, index: number) => (
                      <article key={hotel.poi_id || hotel.name || index} className="rounded-2xl border border-[#eadcc9] bg-[#fffaf4] p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-base font-black text-[#101828]">{hotel.name}</p>
                            <p className="mt-1 text-xs font-semibold leading-5 text-[#667085]">
                              {hotel.area || hotel.district || '北京'} · {hotel.address || '酒店地址待确认'}
                            </p>
                          </div>
                          <span className="shrink-0 rounded-full bg-[#eef8f3] px-3 py-1 text-xs font-black text-[#236247]">
                            {index === 0 ? '首选' : `备选 ${index + 1}`}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-black text-[#344054]">
                          <div className="rounded-xl bg-white p-3">
                            <p className="text-[#98a2b3]">评分</p>
                            <p className="mt-1 text-base">{hotel.rating ?? '-'}</p>
                          </div>
                          <div className="rounded-xl bg-white p-3">
                            <p className="text-[#98a2b3]">均价</p>
                            <p className="mt-1 text-base">{hotel.avg_cost ? `${hotel.avg_cost} 元` : '-'}</p>
                          </div>
                          <div className="rounded-xl bg-[#eef8f3] p-3 text-[#236247]">
                            <p className="text-[#236247]/70">到首站</p>
                            <p className="mt-1 text-base">{hotel.estimated_outbound_minutes ?? '-'} 分钟</p>
                          </div>
                          <div className="rounded-xl bg-[#fff8ed] p-3 text-[#7a4d27]">
                            <p className="text-[#7a4d27]/70">末站返回</p>
                            <p className="mt-1 text-base">{hotel.estimated_return_minutes ?? '-'} 分钟</p>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

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
                  {isMultiDay ? selectedDailyItinerary.map((day: Record<string, any>, index: number) => {
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
