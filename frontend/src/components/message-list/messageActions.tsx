'use client';

import React, { useState } from 'react';
import { App } from 'antd';
import { CheckOutlined, CopyOutlined, FileImageOutlined } from '@ant-design/icons';
import html2canvas from 'html2canvas';
import { prepareMarkdownContent } from './markdownRenderer';

export function deriveExportTitle(content: string): string {
  const firstMeaningfulLine = prepareMarkdownContent(content)
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith('|') && !line.startsWith('-') && !line.startsWith('>'));

  if (!firstMeaningfulLine) return '旅行方案分享';
  const normalized = firstMeaningfulLine.replace(/^#+\s*/, '').slice(0, 28).trim();
  return normalized || '旅行方案分享';
}

export function formatSubagentLabel(name: string): string {
  if (name === 'planning') return '规划';
  if (name === 'research') return '研究';
  if (name === 'budget') return '预算';
  if (name === 'verification') return '校验';
  return name;
}

export const CopyButton: React.FC<{ content: string }> = ({ content }) => {
  const [copied, setCopied] = useState(false);
  const { message } = App.useApp();

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      message.success('已复制到剪贴板');
      setTimeout(() => setCopied(false), 1500);
    } catch {
      message.error('复制失败，请手动复制');
    }
  }

  return (
    <button
      onClick={handleCopy}
      title={copied ? '已复制' : '复制'}
      style={{
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        padding: '4px 8px',
        borderRadius: '4px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: copied ? '#52c41a' : 'inherit',
        transition: 'all 0.2s ease',
      }}
    >
      {copied ? <CheckOutlined style={{ fontSize: '14px' }} /> : <CopyOutlined style={{ fontSize: '14px' }} />}
    </button>
  );
};

export const ExportImageButton: React.FC<{
  targetRef: React.RefObject<HTMLDivElement | null>;
  filename: string;
  title: string;
  exportedAt: string;
}> = ({ targetRef, filename, title, exportedAt }) => {
  const [exporting, setExporting] = useState(false);
  const { message } = App.useApp();

  async function handleExport() {
    if (!targetRef.current || exporting) return;

    let exportShell: HTMLDivElement | null = null;

    try {
      setExporting(true);
      exportShell = document.createElement('div');
      exportShell.style.position = 'fixed';
      exportShell.style.left = '-10000px';
      exportShell.style.top = '0';
      exportShell.style.width = '920px';
      exportShell.style.padding = '28px';
      exportShell.style.background = 'linear-gradient(180deg, #f8fbff 0%, #ffffff 28%, #f8fafc 100%)';
      exportShell.style.boxSizing = 'border-box';

      const header = document.createElement('div');
      header.style.display = 'flex';
      header.style.justifyContent = 'space-between';
      header.style.alignItems = 'center';
      header.style.gap = '16px';
      header.style.padding = '18px 20px';
      header.style.marginBottom = '18px';
      header.style.borderRadius = '20px';
      header.style.background = 'linear-gradient(135deg, #082f49 0%, #0f766e 100%)';
      header.style.color = '#ffffff';

      const brand = document.createElement('div');
      brand.style.display = 'flex';
      brand.style.alignItems = 'center';
      brand.style.gap = '12px';

      const logo = document.createElement('div');
      logo.textContent = 'ST';
      logo.style.width = '42px';
      logo.style.height = '42px';
      logo.style.display = 'flex';
      logo.style.alignItems = 'center';
      logo.style.justifyContent = 'center';
      logo.style.borderRadius = '12px';
      logo.style.background = 'rgba(255,255,255,0.16)';
      logo.style.fontWeight = '700';
      logo.style.fontSize = '16px';

      const brandText = document.createElement('div');
      const brandTitle = document.createElement('div');
      brandTitle.textContent = 'Moyuan Travel Agent';
      brandTitle.style.fontSize = '16px';
      brandTitle.style.fontWeight = '700';
      const brandSubtitle = document.createElement('div');
      brandSubtitle.textContent = 'AI 旅行方案分享卡';
      brandSubtitle.style.fontSize = '12px';
      brandSubtitle.style.opacity = '0.82';
      brandText.appendChild(brandTitle);
      brandText.appendChild(brandSubtitle);

      brand.appendChild(logo);
      brand.appendChild(brandText);

      const meta = document.createElement('div');
      meta.style.textAlign = 'right';
      const metaTitle = document.createElement('div');
      metaTitle.textContent = title;
      metaTitle.style.fontSize = '18px';
      metaTitle.style.fontWeight = '700';
      const metaTime = document.createElement('div');
      metaTime.textContent = `导出时间 ${exportedAt}`;
      metaTime.style.fontSize = '12px';
      metaTime.style.opacity = '0.82';
      meta.appendChild(metaTitle);
      meta.appendChild(metaTime);

      header.appendChild(brand);
      header.appendChild(meta);

      const clonedCard = targetRef.current.cloneNode(true) as HTMLDivElement;
      clonedCard.style.maxWidth = '100%';

      exportShell.appendChild(header);
      exportShell.appendChild(clonedCard);
      document.body.appendChild(exportShell);

      const canvas = await html2canvas(exportShell, {
        scale: 2,
        backgroundColor: '#f8fbff',
        useCORS: true,
      });
      const link = document.createElement('a');
      link.href = canvas.toDataURL('image/png');
      link.download = `${filename}.png`;
      link.click();
      message.success('回答已导出为图片');
    } catch {
      message.error('导出图片失败，请重试');
    } finally {
      if (exportShell?.parentNode) exportShell.parentNode.removeChild(exportShell);
      setExporting(false);
    }
  }

  return (
    <button
      onClick={handleExport}
      title={exporting ? '导出中' : '导出图片'}
      style={{
        background: 'transparent',
        border: 'none',
        cursor: exporting ? 'wait' : 'pointer',
        padding: '4px 8px',
        borderRadius: '4px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: exporting ? '#2563eb' : 'inherit',
        transition: 'all 0.2s ease',
      }}
      disabled={exporting}
    >
      <FileImageOutlined style={{ fontSize: '14px' }} />
    </button>
  );
};
