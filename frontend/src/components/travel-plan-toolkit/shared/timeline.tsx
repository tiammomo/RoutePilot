'use client';

import React from 'react';
import { Button } from 'antd';

type PeriodType = 'morning' | 'afternoon' | 'evening';

interface TimelineItem {
  timeLabel: string | null;
  content: string;
  timeMinutes: number | null;
  originalIndex: number;
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
