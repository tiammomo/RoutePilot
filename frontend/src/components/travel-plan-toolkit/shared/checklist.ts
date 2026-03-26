'use client';

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
