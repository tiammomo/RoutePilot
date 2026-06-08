"use client";
import { useState } from 'react';
import ProjectSettings from '@/components/settings/ProjectSettings';
import { usePathname } from 'next/navigation';

export default function Header() {
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const pathname = usePathname() ?? '';

  // 从路径中提取项目 ID
  const projectId = pathname.match(/^\/([^\/]+)\/(chat|page)?$/)?.[1];

  // 聊天页、首页和数据平台有自己的布局，这里隐藏通用头部
  const isChatPage = pathname.includes('/chat');
  const isMainPage = pathname === '/';
  const isCapabilitiesPage = pathname === '/data-platform' || pathname === '/capabilities';

  if (isChatPage || isMainPage || isCapabilitiesPage) {
    return null;
  }

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto py-4 px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* 返回按钮：仅项目页展示 */}
            {projectId && (
              <button
                onClick={() => {
                  window.location.href = '/';
                }}
                className="flex items-center justify-center w-8 h-8 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
                title="返回项目列表"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M19 12H5M12 19l-7-7 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}
            <div className="h-8 flex items-center">
              <span className="text-2xl font-bold text-[#DE7356] leading-none">
                北京旅游规划
              </span>
            </div>
            <nav className="flex items-center gap-3" />
          </div>
          <div className="flex items-center gap-3">
            {/* 全局设置 */}
            <button
              className="flex items-center justify-center w-10 h-10 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-all duration-200"
              onClick={() => setGlobalSettingsOpen(true)}
              title="全局设置"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Global Settings Modal */}
      <ProjectSettings
        isOpen={globalSettingsOpen}
        onClose={() => setGlobalSettingsOpen(false)}
        projectId="global-settings"
        projectName="全局设置"
        initialTab="ai-assistant"
      />
    </header>
  );
}
