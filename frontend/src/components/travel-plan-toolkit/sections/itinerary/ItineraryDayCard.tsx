'use client';

import React from 'react';
import { Button, Card, Tag } from 'antd';
import {
  CompassOutlined,
  EnvironmentOutlined,
  HeartFilled,
  HeartOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { RoutePreviewResponse } from '@/types';
import type { DayPlanCard, ItineraryConflict, SpotDecisionInfo } from '@/utils/travelPlan';
import { buildSpotDecisionInfos } from '@/utils/travelPlan';
import { compactTips, formatDistance, PeriodTimeline, riskColor } from '../../shared';

interface ItineraryDayCardProps {
  day: DayPlanCard;
  dayIndex: number;
  dayKey: string;
  expandedPeriods: Record<string, boolean>;
  expandedTips: Record<string, boolean>;
  favoriteSpots: Record<string, SpotDecisionInfo>;
  onFetchRoute: (dayKey: string, day: DayPlanCard) => void;
  onOneClickFix: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
  onReorderByDistance: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
  onToggleFavoriteSpot: (spot: SpotDecisionInfo) => void;
  onTogglePeriod: (periodKey: string) => void;
  onToggleTips: (dayKey: string) => void;
  conflicts: ItineraryConflict[];
  route?: RoutePreviewResponse;
  routeLoadingDay: string | null;
}

export const ItineraryDayCard: React.FC<ItineraryDayCardProps> = ({
  day,
  dayIndex,
  dayKey,
  expandedPeriods,
  expandedTips,
  favoriteSpots,
  onFetchRoute,
  onOneClickFix,
  onReorderByDistance,
  onToggleFavoriteSpot,
  onTogglePeriod,
  onToggleTips,
  conflicts,
  route,
  routeLoadingDay,
}) => {
  const decisionInfos = buildSpotDecisionInfos(day.spots);
  const compactedTips = compactTips(day.tips);
  const tipsExpanded = expandedTips[dayKey] ?? false;
  const visibleTips = tipsExpanded ? compactedTips : compactedTips.slice(0, 2);
  const hiddenTipCount = compactedTips.length - visibleTips.length;

  return (
    <Card size="small" title={day.dayLabel}>
      <div style={{ display: 'grid', gap: 10 }}>
        {conflicts.length > 0 && (
          <div
            style={{
              display: 'grid',
              gap: 8,
              background: 'linear-gradient(135deg, #fff7ed 0%, #fffbeb 100%)',
              border: '1px solid #fed7aa',
              borderRadius: 12,
              padding: 10,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700, color: '#9a3412' }}>本日风险提醒</div>
            {conflicts.slice(0, 2).map((conflict) => (
              <div key={`${dayKey}-risk-${conflict.id}`} style={{ fontSize: 12, color: riskColor(conflict.severity) }}>
                {conflict.title}：{conflict.suggestion}
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'grid', gap: 8 }}>
          <PeriodTimeline period="morning" rawText={day.morning} dayKey={dayKey} expandedPeriods={expandedPeriods} onToggle={onTogglePeriod} />
          <PeriodTimeline
            period="afternoon"
            rawText={day.afternoon}
            dayKey={dayKey}
            expandedPeriods={expandedPeriods}
            onToggle={onTogglePeriod}
          />
          <PeriodTimeline period="evening" rawText={day.evening} dayKey={dayKey} expandedPeriods={expandedPeriods} onToggle={onTogglePeriod} />
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Tag color="blue">当日预算：¥{day.baseBudget}</Tag>
          <Tag color="processing">景点数：{day.spots.length}</Tag>
          <Tag color="purple">路线距离：{formatDistance(route?.distance_m)}</Tag>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Button size="small" icon={<EnvironmentOutlined />} loading={routeLoadingDay === dayKey} onClick={() => onFetchRoute(dayKey, day)}>
            真实路线
          </Button>
          <Button size="small" icon={<CompassOutlined />} onClick={() => onReorderByDistance(dayKey, dayIndex, day)}>
            按距离重排
          </Button>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => onOneClickFix(dayKey, dayIndex, day)}>
            一键修复冲突
          </Button>
        </div>

        {route?.static_map_url && (
          <img src={route.static_map_url} alt={`${day.dayLabel} route`} style={{ width: '100%', borderRadius: 10, border: '1px solid #e2e8f0' }} />
        )}

        {decisionInfos.length > 0 && (
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#1f2937' }}>景点决策卡</div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 10,
              }}
            >
              {decisionInfos.map((spot) => {
                const active = Boolean(favoriteSpots[spot.name]);
                return (
                  <div
                    key={`${dayKey}-${spot.name}`}
                    style={{
                      border: '1px solid #dbe4ee',
                      borderRadius: 12,
                      padding: 12,
                      background: active ? 'linear-gradient(135deg, #fff7ed 0%, #ffffff 100%)' : '#ffffff',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                      <div style={{ fontWeight: 700, color: '#1f2937' }}>{spot.name}</div>
                      <Button
                        type="text"
                        size="small"
                        icon={active ? <HeartFilled style={{ color: '#f97316' }} /> : <HeartOutlined />}
                        onClick={() => onToggleFavoriteSpot(spot)}
                      />
                    </div>
                    <div style={{ display: 'grid', gap: 4, fontSize: 12, color: '#475569' }}>
                      <div>停留：{spot.stayDuration}</div>
                      <div>最佳到达：{spot.bestArrival}</div>
                      <div>适合：{spot.audience}</div>
                      <div>花费感知：{spot.costHint}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {conflicts.length > 0 && (
          <div style={{ display: 'grid', gap: 6 }}>
            {conflicts.map((conflict) => (
              <div
                key={`${dayKey}-${conflict.id}`}
                style={{
                  fontSize: 12,
                  color: '#7c2d12',
                  background: '#fff7ed',
                  border: '1px solid #fed7aa',
                  borderRadius: 8,
                  padding: '6px 8px',
                }}
              >
                <div style={{ fontWeight: 600 }}>{conflict.title}</div>
                <div>{conflict.description}</div>
                <div>建议：{conflict.suggestion}</div>
              </div>
            ))}
          </div>
        )}

        {compactedTips.length > 0 && (
          <div style={{ display: 'grid', gap: 4 }}>
            {visibleTips.map((tip, index) => (
              <div key={`${dayKey}-tip-${index}`} style={{ fontSize: 12, color: '#0f766e' }}>
                小贴士：{tip}
              </div>
            ))}
            {hiddenTipCount > 0 && (
              <Button type="link" size="small" style={{ width: 'fit-content', padding: 0 }} onClick={() => onToggleTips(dayKey)}>
                {tipsExpanded ? '收起' : `展开更多（+${hiddenTipCount}）`}
              </Button>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};
