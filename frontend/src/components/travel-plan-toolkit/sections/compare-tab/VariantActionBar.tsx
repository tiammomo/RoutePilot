'use client';

import React from 'react';
import { Button } from 'antd';
import type { PlanVariant } from '@/utils/travelPlan';

interface VariantActionBarProps {
  variants: PlanVariant[];
  onChooseVariant: (variant: PlanVariant) => void;
}

export const VariantActionBar: React.FC<VariantActionBarProps> = ({ variants, onChooseVariant }) => (
  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
    {variants.map((variant) => (
      <Button key={variant.id} onClick={() => onChooseVariant(variant)}>
        选中“{variant.title}”继续细化
      </Button>
    ))}
  </div>
);
