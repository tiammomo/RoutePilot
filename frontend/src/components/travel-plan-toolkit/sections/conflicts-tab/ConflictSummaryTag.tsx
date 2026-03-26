'use client';

import React from 'react';
import { Tag } from 'antd';

interface ConflictSummaryTagProps {
  totalConflicts: number;
}

export const ConflictSummaryTag: React.FC<ConflictSummaryTagProps> = ({ totalConflicts }) => (
  <Tag color={totalConflicts > 0 ? 'orange' : 'green'}>
    {totalConflicts > 0 ? `检测到 ${totalConflicts} 个冲突风险` : '未检测到明显冲突'}
  </Tag>
);
