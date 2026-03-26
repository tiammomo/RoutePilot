'use client';

import React from 'react';
import type { PlanVariant } from '@/utils/travelPlan';
import { CompareEmptyState } from './compare-tab/CompareEmptyState';
import { VariantActionBar } from './compare-tab/VariantActionBar';
import { VariantComparisonTable } from './compare-tab/VariantComparisonTable';

interface ToolkitCompareTabProps {
  variants: PlanVariant[];
  onChooseVariant: (variant: PlanVariant) => void;
}

export const ToolkitCompareTab: React.FC<ToolkitCompareTabProps> = ({ variants, onChooseVariant }) => {
  if (variants.length < 2) return <CompareEmptyState />;

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <VariantComparisonTable variants={variants} />
      <VariantActionBar variants={variants} onChooseVariant={onChooseVariant} />
    </div>
  );
};
