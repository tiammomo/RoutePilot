import './globals.css'
import GlobalSettingsProvider from '@/contexts/GlobalSettingsContext'
import { AuthProvider } from '@/contexts/AuthContext'
import Header from '@/components/layout/Header'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        {/* next-rspack 当前会输出缺少分号的 Tailwind CSS，这里加载稳定生成的兜底样式。 */}
        {/* eslint-disable-next-line @next/next/no-css-tags */}
        <link rel="stylesheet" href="/generated/travel-agent-tailwind.css" />
      </head>
      <body className="bg-slate-50 text-slate-900 min-h-screen" data-app="beijing-travel-agent" suppressHydrationWarning>
        <AuthProvider>
          <GlobalSettingsProvider>
            <Header />
            <main>{children}</main>
          </GlobalSettingsProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
