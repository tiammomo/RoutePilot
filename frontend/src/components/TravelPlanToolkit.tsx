'use client';

import React, { useMemo, useState } from 'react';
import { App, Button, Card, Checkbox, Divider, Progress, Slider, Space, Tabs, Tag, Tooltip } from 'antd';
import {
  CheckSquareOutlined,
  CompassOutlined,
  EnvironmentOutlined,
  FilePdfOutlined,
  FundOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  StarOutlined,
  StarFilled,
} from '@ant-design/icons';
import html2canvas from 'html2canvas';
import type { Message } from '@/types';
import { apiService } from '@/services/api';
import {
  buildChecklist,
  buildConfidenceSummary,
  buildReminders,
  getBudgetProjection,
  parseDayPlanCards,
  parsePlanVariants,
  reorderByDistance,
} from '@/utils/travelPlan';

interface TravelPlanToolkitProps {
  messageId: string;
  content: string;
  diagnostics?: Message['diagnostics'];
}

type BudgetMode = 'saving' | 'balanced' | 'comfort';
type PeriodType = 'morning' | 'afternoon' | 'evening';

interface PeriodTimelineProps {
  period: PeriodType;
  rawText: string;
  dayKey: string;
  expandedPeriods: Record<string, boolean>;
  onToggle: (periodKey: string) => void;
}

interface TimelineItem {
  timeLabel: string | null;
  content: string;
  timeMinutes: number | null;
  originalIndex: number;
}

function splitTimelineItems(rawText: string): TimelineItem[] {
  const normalized = rawText
    .replace(/\s+/g, ' ')
    .replace(/[，,]\s*(?=\d{1,2}[:：]\d{2})/g, '；')
    .replace(/[。]/g, '；')
    .replace(/->|→/g, '；');

  return normalized
    .split(/[；;]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .filter((item) => !/^上午|^下午|^晚上/.test(item))
    .map((item, index) => {
      const timeMatch = item.match(/(?:^|\s)(\d{1,2}[:：]\d{2})(?:\s|$)/);
      if (!timeMatch) return { timeLabel: null, content: item, timeMinutes: null, originalIndex: index };
      const timeLabel = timeMatch[1].replace('：', ':');
      const content = item.replace(timeMatch[1], '').replace(/^\s*[-:：]?\s*/, '').trim();
      const [hourStr, minuteStr] = timeLabel.split(':');
      const hour = Number(hourStr);
      const minute = Number(minuteStr);
      const isValidHour = Number.isFinite(hour) && hour >= 0 && hour <= 23;
      const isValidMinute = Number.isFinite(minute) && minute >= 0 && minute <= 59;
      const timeMinutes = isValidHour && isValidMinute ? hour * 60 + minute : null;
      return {
        timeLabel,
        content: content || item,
        timeMinutes,
        originalIndex: index,
      };
    })
    .sort((left, right) => {
      if (left.timeMinutes !== null && right.timeMinutes !== null) return left.timeMinutes - right.timeMinutes;
      if (left.timeMinutes !== null) return -1;
      if (right.timeMinutes !== null) return 1;
      return left.originalIndex - right.originalIndex;
    });
}

function periodMeta(period: PeriodType): { title: string; dotColor: string } {
  if (period === 'morning') return { title: '上午', dotColor: '#0ea5e9' };
  if (period === 'afternoon') return { title: '下午', dotColor: '#f59e0b' };
  return { title: '晚上', dotColor: '#8b5cf6' };
}

const PeriodTimeline: React.FC<PeriodTimelineProps> = ({ period, rawText, dayKey, expandedPeriods, onToggle }) => {
  const items = splitTimelineItems(rawText);
  const key = `${dayKey}-${period}`;
  const isExpanded = expandedPeriods[key] ?? false;
  const visibleItems = isExpanded ? items : items.slice(0, 3);
  const hasMore = items.length > 3;
  const meta = periodMeta(period);

  return (
    <div
      style={{
        border: '1px solid #e2e8f0',
        borderRadius: 10,
        padding: '10px 12px',
        background: '#fff',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b', marginBottom: 8 }}>{meta.title}</div>
      <div style={{ display: 'grid', gap: 8 }}>
        {visibleItems.map((item, index) => (
          <div key={`${key}-${index}`} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: 2 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: meta.dotColor,
                  display: 'inline-block',
                }}
              />
              {index < visibleItems.length - 1 && (
                <span
                  style={{
                    width: 1,
                    minHeight: 18,
                    background: '#cbd5e1',
                    marginTop: 2,
                  }}
                />
              )}
            </div>
            <div style={{ display: 'grid', gap: 4 }}>
              {item.timeLabel && (
                <span
                  style={{
                    display: 'inline-flex',
                    width: 'fit-content',
                    fontSize: 11,
                    color: '#1d4ed8',
                    background: '#dbeafe',
                    border: '1px solid #93c5fd',
                    borderRadius: 999,
                    padding: '1px 8px',
                    fontWeight: 600,
                  }}
                >
                  {item.timeLabel}
                </span>
              )}
              <div style={{ fontSize: 13, color: '#334155', lineHeight: 1.6 }}>{item.content}</div>
            </div>
          </div>
        ))}
      </div>
      {hasMore && (
        <Button size="small" type="link" style={{ padding: 0, marginTop: 6 }} onClick={() => onToggle(key)}>
          {isExpanded ? '收起' : `展开更多（+${items.length - 3}）`}
        </Button>
      )}
    </div>
  );
};

function modeToSliderValue(mode: BudgetMode): number {
  if (mode === 'saving') return 10;
  if (mode === 'comfort') return 90;
  return 50;
}

function sliderValueToMode(value: number): BudgetMode {
  if (value <= 33) return 'saving';
  if (value >= 67) return 'comfort';
  return 'balanced';
}

const TravelPlanToolkit: React.FC<TravelPlanToolkitProps> = ({ messageId, content, diagnostics }) => {
  const { message } = App.useApp();
  const dayCards = useMemo(() => parseDayPlanCards(content), [content]);
  const planVariants = useMemo(() => parsePlanVariants(content), [content]);
  const reminders = useMemo(() => buildReminders(), []);
  const checklist = useMemo(() => buildChecklist(content), [content]);
  const confidence = useMemo(() => buildConfidenceSummary(diagnostics), [diagnostics]);
  const [budgetMode, setBudgetMode] = useState<BudgetMode>('balanced');
  const [budgetSlider, setBudgetSlider] = useState<number>(50);
  const [favorite, setFavorite] = useState(false);
  const [checkedItems, setCheckedItems] = useState<string[]>([]);
  const [distanceSortedDays, setDistanceSortedDays] = useState<Record<string, boolean>>({});
  const [expandedPeriods, setExpandedPeriods] = useState<Record<string, boolean>>({});
  const [routePreviews, setRoutePreviews] = useState<
    Record<
      string,
      {
        loading: boolean;
        error?: string;
        provider?: 'amap';
        staticMapUrl?: string;
        distanceM?: number;
        durationS?: number;
        points?: Array<{ name: string; lat: number; lng: number }>;
      }
    >
  >({});

  if (dayCards.length === 0 && planVariants.length === 0) return null;

  const baseDailyBudget = Math.round(dayCards.reduce((sum, day) => sum + day.baseBudget, 0) / dayCards.length);
  const budgetProjection = getBudgetProjection(baseDailyBudget, dayCards.length || 1, budgetSlider);

  const modeLabelMap: Record<BudgetMode, string> = {
    saving: '省钱',
    balanced: '均衡',
    comfort: '舒适',
  };

  const handleReorderRoute = (dayKey: string) => {
    setDistanceSortedDays((prev) => ({ ...prev, [dayKey]: !prev[dayKey] }));
  };
  const handleTogglePeriodExpand = (periodKey: string) => {
    setExpandedPeriods((prev) => ({ ...prev, [periodKey]: !prev[periodKey] }));
  };

  const handleToggleFavorite = () => {
    setFavorite((prev) => !prev);
    message.success(favorite ? '已取消收藏此方案卡片' : '已收藏此方案卡片');
  };

  const handleExport = async () => {
    const element = document.getElementById(`travel-plan-toolkit-${messageId}`);
    if (!element) {
      message.error('未找到可导出的方案区域');
      return;
    }

    try {
      const canvas = await html2canvas(element, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff',
      });
      const dataUrl = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = dataUrl;
      link.download = `travel-plan-${messageId}.png`;
      link.click();
      message.success('长图已导出为 PNG');
    } catch (error) {
      message.error(`导出失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  };

  const handleShare = async () => {
    try {
      const share = await apiService.createShareLink({
        title: dayCards[0]?.dayLabel || '旅行方案',
        content,
      });

      if (navigator.share) {
        try {
          await navigator.share({
            title: '旅行方案分享',
            text: '我整理了一份旅行方案，点链接查看：',
            url: share.share_url,
          });
          return;
        } catch {
          // fallback to clipboard
        }
      }

      await navigator.clipboard.writeText(share.share_url);
      message.success('短链已复制，可直接发给同行人。');
    } catch (error) {
      message.error(`生成短链失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  };

  React.useEffect(() => {
    if (process.env.NODE_ENV === 'test') return;

    let cancelled = false;
    const loadRoutePreview = async () => {
      const pendingState = dayCards.reduce(
        (acc, _day, index) => ({ ...acc, [`${messageId}-day-${index}`]: { loading: true } }),
        {} as Record<string, { loading: boolean; error?: string }>
      );
      setRoutePreviews(pendingState);

      const entries = await Promise.all(
        dayCards.map(async (day, index) => {
          const key = `${messageId}-day-${index}`;
          if (!day.spots || day.spots.length < 2) return [key, { loading: false, error: '点位不足，无法规划路线' }];
          try {
            const response = await apiService.getRoutePreview({
              spots: day.spots.slice(0, 6),
              provider: 'auto',
            });
            return [
              key,
              {
                loading: false,
                provider: response.provider,
                staticMapUrl: response.static_map_url,
                distanceM: response.distance_m,
                durationS: response.duration_s,
                points: response.points,
              },
            ];
          } catch (error) {
            return [
              key,
              { loading: false, error: error instanceof Error ? error.message : '地图服务不可用' },
            ];
          }
        })
      );

      if (cancelled) return;
      setRoutePreviews(Object.fromEntries(entries));
    };

    loadRoutePreview();
    return () => {
      cancelled = true;
    };
  }, [dayCards, messageId]);

  const getSortedPoints = (dayKey: string) => {
    const routeInfo = routePreviews[dayKey];
    const points = routeInfo?.points || [];
    if (!distanceSortedDays[dayKey]) return points;
    return reorderByDistance(points);
  };

  const tabItems = [
    {
      key: 'cards',
      label: (
        <span>
          <CompassOutlined /> 每日卡片
        </span>
      ),
      children: (
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {dayCards.map((day, index) => {
            const dayKey = `${messageId}-day-${index}`;
            const routeInfo = routePreviews[dayKey];
            const routePoints = getSortedPoints(dayKey);
            const distanceKm = routeInfo?.distanceM ? (routeInfo.distanceM / 1000).toFixed(1) : '--';
            const durationMinutes = routeInfo?.durationS ? Math.round(routeInfo.durationS / 60) : '--';

            return (
              <Card
                key={dayKey}
                size="small"
                title={day.dayLabel}
                extra={
                  <Button size="small" icon={<ReloadOutlined />} onClick={() => handleReorderRoute(dayKey)}>
                    按距离重排
                  </Button>
                }
              >
                <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
                  <PeriodTimeline
                    period="morning"
                    rawText={day.morning}
                    dayKey={dayKey}
                    expandedPeriods={expandedPeriods}
                    onToggle={handleTogglePeriodExpand}
                  />
                  <PeriodTimeline
                    period="afternoon"
                    rawText={day.afternoon}
                    dayKey={dayKey}
                    expandedPeriods={expandedPeriods}
                    onToggle={handleTogglePeriodExpand}
                  />
                  <PeriodTimeline
                    period="evening"
                    rawText={day.evening}
                    dayKey={dayKey}
                    expandedPeriods={expandedPeriods}
                    onToggle={handleTogglePeriodExpand}
                  />
                  <Tag color="gold">预算参考：￥{day.baseBudget}/天</Tag>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {day.tips.map((tip) => (
                      <Tag key={`${dayKey}-${tip}`} color="cyan">
                        小贴士：{tip}
                      </Tag>
                    ))}
                  </div>
                </div>

                {routePoints.length > 0 && (
                  <>
                    <Divider style={{ margin: '10px 0' }} />
                    <div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>
                      <EnvironmentOutlined style={{ marginRight: 4 }} />
                      点位与路线预览（真实距离）
                    </div>
                    <div style={{ fontSize: 12, color: '#334155', marginBottom: 6 }}>
                      服务商：{routeInfo?.provider || '--'} | 全程约 {distanceKm} km | 预计 {durationMinutes} 分钟
                    </div>
                    {routeInfo?.staticMapUrl && (
                      <img
                        src={routeInfo.staticMapUrl}
                        alt={`${day.dayLabel} 路线地图`}
                        style={{
                          width: '100%',
                          borderRadius: 10,
                          border: '1px solid #dbeafe',
                          marginBottom: 8,
                        }}
                      />
                    )}
                    {routeInfo?.loading && <div style={{ fontSize: 12, color: '#64748b' }}>地图加载中...</div>}
                    {routeInfo?.error && <div style={{ fontSize: 12, color: '#dc2626' }}>{routeInfo.error}</div>}
                    <div style={{ display: 'grid', gap: 4 }}>
                      {routePoints.map((point, pointIndex) => (
                        <div key={`${dayKey}-${point.name}`} style={{ fontSize: 12, color: '#334155' }}>
                          {pointIndex + 1}. {point.name} ({point.lat}, {point.lng})
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </Card>
            );
          })}
        </Space>
      ),
    },
    {
      key: 'budget',
      label: (
        <span>
          <FundOutlined /> 预算滑杆
        </span>
      ),
      children: (
        <Card size="small">
          <Space orientation="vertical" style={{ width: '100%' }} size={12}>
            <div style={{ fontSize: 13, color: '#334155' }}>
              当前预算模式：
              <Tag color={budgetMode === 'saving' ? 'green' : budgetMode === 'comfort' ? 'orange' : 'blue'}>
                {modeLabelMap[budgetMode]}
              </Tag>
            </div>

            <Slider
              value={budgetSlider}
              marks={{ 0: '省钱', 50: '均衡', 100: '舒适' }}
              onChange={(value) => {
                const nextValue = Number(value);
                setBudgetSlider(nextValue);
                setBudgetMode(sliderValueToMode(nextValue));
              }}
            />

            <div style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              <div>总预算：￥{budgetProjection.totalBudget}</div>
              <div>日均预算：￥{budgetProjection.perDayBudget}</div>
              <div>
                住宿/餐饮/交通占比：{Math.round(budgetProjection.hotelShare * 100)}% /
                {Math.round(budgetProjection.foodShare * 100)}% / {Math.round(budgetProjection.trafficShare * 100)}%
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                size="small"
                onClick={() => {
                  const value = modeToSliderValue('saving');
                  setBudgetSlider(value);
                  setBudgetMode('saving');
                }}
              >
                省钱版
              </Button>
              <Button
                size="small"
                onClick={() => {
                  const value = modeToSliderValue('balanced');
                  setBudgetSlider(value);
                  setBudgetMode('balanced');
                }}
              >
                均衡版
              </Button>
              <Button
                size="small"
                onClick={() => {
                  const value = modeToSliderValue('comfort');
                  setBudgetSlider(value);
                  setBudgetMode('comfort');
                }}
              >
                舒适版
              </Button>
            </div>
          </Space>
        </Card>
      ),
    },
    {
      key: 'compare',
      label: '比较模式',
      children: (
        <Card size="small">
          {planVariants.length >= 2 ? (
            <Tabs
              size="small"
              items={planVariants.map((variant) => ({
                key: variant.id,
                label: variant.title,
                children: <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{variant.content}</div>,
              }))}
            />
          ) : (
            <div style={{ fontSize: 13, color: '#64748b' }}>
              当前回答仅识别到 1 套方案。可在输入时开启“比较模式”，一次生成 2-3 套方案直接对比。
            </div>
          )}
        </Card>
      ),
    },
    {
      key: 'checklist',
      label: (
        <span>
          <CheckSquareOutlined /> 执行清单
        </span>
      ),
      children: (
        <Card size="small">
          <Space orientation="vertical" style={{ width: '100%' }} size={8}>
            <Checkbox.Group
              value={checkedItems}
              onChange={(values) => setCheckedItems(values as string[])}
              style={{ display: 'grid', gap: 8 }}
            >
              {checklist.map((item) => (
                <Checkbox value={item.id} key={item.id}>
                  {item.label}
                </Checkbox>
              ))}
            </Checkbox.Group>
            <div style={{ fontSize: 12, color: '#64748b' }}>
              进度：{checkedItems.length}/{checklist.length}
            </div>
          </Space>
        </Card>
      ),
    },
    {
      key: 'timeline',
      label: '时间线提醒',
      children: (
        <Card size="small">
          <Space orientation="vertical" style={{ width: '100%' }} size={8}>
            {reminders.map((item) => (
              <div
                key={item.id}
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  padding: '8px 10px',
                  fontSize: 13,
                }}
              >
                <Tag color="blue">{item.phase}</Tag>
                <strong>{item.title}</strong>
                <div style={{ marginTop: 4, color: '#64748b' }}>{item.detail}</div>
              </div>
            ))}
          </Space>
        </Card>
      ),
    },
  ];

  return (
    <div style={{ marginTop: 12 }} id={`travel-plan-toolkit-${messageId}`}>
      <Card
        size="small"
        title="行程增强工具"
        extra={
          <Space>
            <Tooltip title={favorite ? '取消收藏' : '收藏方案'}>
              <Button
                size="small"
                icon={favorite ? <StarFilled style={{ color: '#f59e0b' }} /> : <StarOutlined />}
                onClick={handleToggleFavorite}
              />
            </Tooltip>
            <Tooltip title="导出 PDF">
              <Button size="small" icon={<FilePdfOutlined />} onClick={handleExport} />
            </Tooltip>
            <Tooltip title="分享方案">
              <Button size="small" icon={<ShareAltOutlined />} onClick={handleShare} />
            </Tooltip>
          </Space>
        }
      >
        <div style={{ marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, color: '#334155' }}>结果可信度</span>
            <Tag color={confidence.level === '高' ? 'green' : confidence.level === '中' ? 'gold' : 'red'}>
              {confidence.level}
            </Tag>
          </div>
          <Progress percent={confidence.score} size="small" />
          <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>
            {confidence.risks.map((risk, index) => (
              <div key={`${messageId}-risk-${index}`} style={{ fontSize: 12, color: '#92400e' }}>
                风险提示：{risk}
              </div>
            ))}
          </div>
        </div>
        <Tabs size="small" items={tabItems} />
      </Card>
    </div>
  );
};

export default TravelPlanToolkit;
