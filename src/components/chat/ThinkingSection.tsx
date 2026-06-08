'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Maximize2, X } from 'lucide-react';

interface ThinkingSectionProps {
  content: string;
  isExpanded?: boolean;
}

export default function ThinkingSection({ 
  content, 
  isExpanded: initialExpanded = true
}: ThinkingSectionProps) {
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const [isModalOpen, setIsModalOpen] = useState(false);
  
  // 第一行作为过程摘要标题，其余内容保留给展开和弹窗查看。
  const lines = content.split('\n').filter(line => line.trim());
  const firstLine = lines[0] || content.substring(0, 100);
  const restContent = lines.slice(1).join('\n');
  const hasMoreContent = lines.length > 1;
  
  const formatThinkingContent = (text: string) => {
    const parts = text.split(/\*\*(.*?)\*\*/g);
    
    return parts.map((part, index) => {
      if (index % 2 === 1) {
        return (
          <span key={index} className="font-medium text-slate-700">
            {part}
          </span>
        );
      }
      
      return part.split('\n').map((line, lineIndex) => (
        <React.Fragment key={`${index}-${lineIndex}`}>
          {lineIndex > 0 && <br />}
          {line}
        </React.Fragment>
      ));
    });
  };

  return (
    <div className="my-2 text-sm text-slate-600">
      <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2">
        <div className="flex items-start justify-between gap-3">
          <button
            type="button"
            onClick={() => hasMoreContent && setIsExpanded(!isExpanded)}
            className={`min-w-0 flex-1 text-left transition-colors ${
              hasMoreContent ? 'cursor-pointer hover:text-slate-800' : 'cursor-default'
            }`}
            aria-expanded={isExpanded}
          >
            <span className="inline-flex items-center gap-1.5 font-medium text-slate-700">
              <Brain className="h-3.5 w-3.5" />
              过程叙述
            </span>
            <span className="ml-2 italic text-slate-600">
              {formatThinkingContent(firstLine.replace(/^\*\*/, '').replace(/\*\*$/, ''))}
            </span>
          </button>

          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setIsModalOpen(true);
            }}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-600 shadow-sm transition-colors hover:bg-slate-100 hover:text-slate-900"
            title="弹出查看完整过程叙述"
          >
            <Maximize2 className="h-3.5 w-3.5" />
            弹出
          </button>
        </div>

        {hasMoreContent && (
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.18 }}
                style={{ marginTop: '0.5rem', overflow: 'hidden' }}
              >
                <div className="whitespace-pre-wrap border-t border-slate-200 pt-2 leading-relaxed text-slate-600">
                  {formatThinkingContent(restContent)}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </div>

      <AnimatePresence>
        {isModalOpen && (
          <motion.div
            className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsModalOpen(false)}
          >
            <motion.div
              className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              transition={{ duration: 0.16 }}
              onClick={(event: React.MouseEvent<HTMLDivElement>) => event.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                <div className="flex items-center gap-2">
                  <Brain className="h-4 w-4 text-slate-700" />
                  <h2 className="text-base font-semibold text-slate-900">过程叙述</h2>
                </div>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
                  aria-label="关闭过程叙述弹窗"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="overflow-y-auto px-5 py-4">
                <div className="whitespace-pre-wrap text-sm leading-7 text-slate-700">
                  {formatThinkingContent(content)}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
