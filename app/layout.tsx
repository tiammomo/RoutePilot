import './globals.css'
import GlobalSettingsProvider from '@/contexts/GlobalSettingsContext'
import { AuthProvider } from '@/contexts/AuthContext'
import Header from '@/components/layout/Header'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head />
      <body className="bg-gray-50 text-gray-900 min-h-screen">
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
