'use client';

import React from 'react';
import { Button } from 'antd';
import { CompassOutlined } from '@ant-design/icons';
import { CURATED_PROMPTS } from '../../shared';

interface CuratedPromptPanelProps {
  onUsePrompt: (prompt: string) => void;
}

export const CuratedPromptPanel: React.FC<CuratedPromptPanelProps> = ({ onUsePrompt }) => (
  <div
    style={{
      borderRadius: 20,
      padding: 20,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, #f8fbff 100%)',
      border: '1px solid #dbe4ee',
      boxShadow: '0 14px 30px rgba(15, 23, 42, 0.08)',
      color: '#0f172a',
      display: 'grid',
      gap: 16,
      alignContent: 'start',
    }}
  >
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        width: 'fit-content',
        padding: '6px 10px',
        borderRadius: 999,
        border: '1px solid #dbeafe',
        background: '#eff6ff',
        color: '#1d4ed8',
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      <CompassOutlined />
      灵感起点
    </div>

    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ fontSize: 24, fontWeight: 800, lineHeight: 1.2, color: '#0f172a', maxWidth: 520 }}>
        从场景出发，找到对的城市
      </div>
    </div>

    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: 10,
      }}
    >
      {CURATED_PROMPTS.map((item) => (
        <Button
          key={item.label}
          block
          aria-label={`使用场景 ${item.label}`}
          style={{
            height: '100%',
            minHeight: 92,
            padding: '14px 16px',
            borderRadius: 16,
            border: `1px solid ${item.borderColor}`,
            background: item.background,
            color: '#0f172a',
            boxShadow: 'none',
            whiteSpace: 'normal',
          }}
          onClick={() => onUsePrompt(item.prompt)}
        >
          <div style={{ display: 'grid', gap: 6, textAlign: 'left' }}>
            <span style={{ fontSize: 16, fontWeight: 700 }}>{item.label}</span>
            <span style={{ fontSize: 12, lineHeight: 1.65, color: '#64748b', fontWeight: 500 }}>{item.hint}</span>
          </div>
        </Button>
      ))}
    </div>
  </div>
);
