'use client';

import { Layout } from 'antd';
import ChatArea from '@/components/ChatArea';
import Sidebar from '@/components/Sidebar';

export default function Home() {
  // 侧边栏始终显示，只是空会话时不显示内容
  return (
    <Layout style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)'
    }}>
      <Layout.Sider
        width={280}
        theme="light"
        style={{
          borderRight: '1px solid rgba(0, 0, 0, 0.06)',
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 100,
          background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
          boxShadow: '2px 0 12px rgba(0, 0, 0, 0.05)',
        }}
      >
        <Sidebar />
      </Layout.Sider>
      <Layout style={{
        marginLeft: 280,
        transition: 'margin-left 0.3s ease',
        background: 'transparent'
      }}>
        <Layout.Content style={{
          margin: 0,
          minHeight: '100vh',
          background: 'transparent'
        }}>
          <ChatArea />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
