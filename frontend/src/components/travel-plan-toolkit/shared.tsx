'use client';

import React from 'react';
import { Button } from 'antd';
import type { DayPlanCard, ItineraryConflict, PracticalInfoCard, ReminderItem } from '@/utils/travelPlan';

export type BudgetMode = 'saving' | 'balanced' | 'comfort';
type PeriodType = 'morning' | 'afternoon' | 'evening';

interface TimelineItem {
  timeLabel: string | null;
  content: string;
  timeMinutes: number | null;
  originalIndex: number;
}

export interface CompareRow {
  key: string;
  metric: string;
  values: Record<string, string>;
}

export interface QuickRefineAction {
  key: string;
  label: string;
  prompt: string;
}

function normalizeTipText(tip: string): string {
  return tip
    .replace(/^\s*(?:小贴士|当日小贴士|Tips?|提示|注意事项)[:：]?\s*/i, '')
    .replace(/(?<!\d)\s*[：:]{2,}\s*(?!\d)/g, '：')
    .replace(/(?<!\d)\s*[：:]\s*(?!\d)/g, '：')
    .replace(/^[：:\-\s]+/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function compactTips(tips: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of tips) {
    const normalized = normalizeTipText(raw);
    const key = normalized.toLowerCase();
    if (!normalized || seen.has(key)) continue;
    seen.add(key);
    result.push(normalized);
  }
  return result;
}

export function sliderToMode(value: number): BudgetMode {
  if (value <= 33) return 'saving';
  if (value >= 67) return 'comfort';
  return 'balanced';
}

export function modeToSliderValue(mode: BudgetMode): number {
  if (mode === 'saving') return 10;
  if (mode === 'comfort') return 90;
  return 50;
}

function periodMeta(period: PeriodType): { title: string; color: string } {
  if (period === 'morning') return { title: '上午', color: '#0ea5e9' };
  if (period === 'afternoon') return { title: '下午', color: '#f59e0b' };
  return { title: '晚上', color: '#8b5cf6' };
}

function splitTimelineItems(rawText: string): TimelineItem[] {
  const normalized = rawText
    .replace(/\r\n?/g, '\n')
    .replace(/\s+/g, ' ')
    .replace(/[。]/g, '；')
    .replace(/\s*(?:->|→)\s*/g, '；')
    .replace(/\|/g, '；');

  return normalized
    .split(/[；;]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !/^(上午|下午|晚上)\b/.test(item))
    .map((item, index) => {
      const timeMatch = item.match(/(?:^|\s)(\d{1,2}[:：]\d{2})(?:\s|$)/);
      if (!timeMatch) {
        return { timeLabel: null, content: item, timeMinutes: null, originalIndex: index };
      }

      const normalizedTime = timeMatch[1].replace('：', ':');
      const [hourStr, minuteStr] = normalizedTime.split(':');
      const hour = Number(hourStr);
      const minute = Number(minuteStr);
      const isValid =
        Number.isFinite(hour) && Number.isFinite(minute) && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;

      return {
        timeLabel: normalizedTime,
        content: item.replace(timeMatch[1], '').replace(/^\s*[-:：]?\s*/, '').trim() || item,
        timeMinutes: isValid ? hour * 60 + minute : null,
        originalIndex: index,
      };
    })
    .sort((a, b) => {
      if (a.timeMinutes !== null && b.timeMinutes !== null) return a.timeMinutes - b.timeMinutes;
      if (a.timeMinutes !== null) return -1;
      if (b.timeMinutes !== null) return 1;
      return a.originalIndex - b.originalIndex;
    });
}

export const PeriodTimeline: React.FC<{
  period: PeriodType;
  rawText: string;
  dayKey: string;
  expandedPeriods: Record<string, boolean>;
  onToggle: (periodKey: string) => void;
}> = ({ period, rawText, dayKey, expandedPeriods, onToggle }) => {
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
                  background: meta.color,
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
          {isExpanded ? '收起' : `展开更多（${items.length - 3}）`}
        </Button>
      )}
    </div>
  );
};

export function formatDistance(distanceM: number | undefined): string {
  if (!distanceM || distanceM <= 0) return '-';
  return `${(distanceM / 1000).toFixed(1)} km`;
}

export function riskColor(severity: ItineraryConflict['severity']): string {
  if (severity === 'high') return '#dc2626';
  if (severity === 'medium') return '#d97706';
  return '#b45309';
}

export function practicalToneStyle(
  tone: PracticalInfoCard['tone']
): { background: string; border: string; color: string } {
  if (tone === 'good') return { background: '#ecfdf5', border: '#a7f3d0', color: '#065f46' };
  if (tone === 'warn') return { background: '#fff7ed', border: '#fed7aa', color: '#9a3412' };
  return { background: '#f8fafc', border: '#cbd5e1', color: '#334155' };
}

export function practicalToneLabel(tone: PracticalInfoCard['tone']): string {
  if (tone === 'good') return '建议';
  if (tone === 'warn') return '注意';
  return '常规';
}

export function reminderPhaseMeta(phase: ReminderItem['phase']): { color: string; subtitle: string } {
  if (phase === 'T-1') return { color: 'volcano', subtitle: '出发前一天' };
  if (phase === 'T-3') return { color: 'cyan', subtitle: '出发前三天' };
  return { color: 'blue', subtitle: '出发前一周' };
}

export function checklistStatusMeta(completed: boolean): {
  label: string;
  background: string;
  border: string;
  color: string;
} {
  if (completed) {
    return {
      label: '已完成',
      background: '#ecfdf5',
      border: '#86efac',
      color: '#166534',
    };
  }
  return {
    label: '待处理',
    background: '#eff6ff',
    border: '#93c5fd',
    color: '#1d4ed8',
  };
}

export function subagentLabel(name: string): string {
  if (name === 'planning') return '规划';
  if (name === 'research') return '研究';
  if (name === 'verification') return '校验';
  return name;
}

export function looksLikeItineraryContent(content: string, cards: DayPlanCard[]): boolean {
  if (cards.length >= 2) return true;
  if (/(上午|下午|晚上|预算|小贴士|tips|day\s*\d+|第.{1,4}天|方案|路线|景点)/i.test(content)) return true;
  return false;
}
