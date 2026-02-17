import { http, HttpResponse } from 'msw';
import type { SessionInfo, ModelInfo } from '@/types';

const mockSessions: SessionInfo[] = [
  {
    session_id: 'test-session-1',
    message_count: 5,
    last_active: new Date().toISOString(),
    name: '测试会话 1',
    model_id: 'gpt-4o-mini',
  },
];

const mockModels: ModelInfo[] = [
  {
    model_id: 'gpt-4o-mini',
    name: 'OpenAI GPT-4o Mini',
    provider: 'openai',
    model: 'gpt-4o-mini',
  },
];

export const handlers = [
  // 健康检查
  http.get('/api/health', () => {
    return HttpResponse.json({
      status: 'healthy',
      agent: 'ReActTravelAgent',
      version: '3.0.0',
    });
  }),

  // 创建会话
  http.post('/api/session/new', () => {
    const newSession: SessionInfo = {
      session_id: `session-${Date.now()}`,
      message_count: 0,
      last_active: new Date().toISOString(),
      name: undefined,
      model_id: 'gpt-4o-mini',
    };
    mockSessions.unshift(newSession);
    return HttpResponse.json({ success: true, session_id: newSession.session_id });
  }),

  // 获取会话列表
  http.get('/api/sessions', () => {
    return HttpResponse.json({ success: true, sessions: mockSessions });
  }),

  // 获取可用模型
  http.get('/api/models', () => {
    return HttpResponse.json({ success: true, models: mockModels });
  }),

  // 删除会话
  http.delete('/api/session/:sessionId', ({ params }) => {
    const { sessionId } = params;
    const index = mockSessions.findIndex((s) => s.session_id === sessionId);
    if (index !== -1) {
      mockSessions.splice(index, 1);
    }
    return HttpResponse.json({ success: true, message: '会话已删除' });
  }),

  // 清空会话聊天
  http.post('/api/clear/:sessionId', () => {
    return HttpResponse.json({ success: true, message: '聊天已清空' });
  }),

  // 更新会话名称
  http.put('/api/session/:sessionId/name', ({ params }) => {
    const { sessionId } = params;
    const session = mockSessions.find((s) => s.session_id === sessionId);
    if (session) {
      session.name = '新名称';
    }
    return HttpResponse.json({ success: true, message: '名称已更新' });
  }),

  // 设置会话模型
  http.put('/api/session/:sessionId/model', ({ params }) => {
    return HttpResponse.json({ success: true, message: '模型已设置' });
  }),

  // 流式聊天
  http.post('/api/chat/stream', async ({ request }) => {
    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        // 发送 session_id
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'session_id', session_id: 'test-session' })}\n\n`)
        );

        // 发送 reasoning_start
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'reasoning_start' })}\n\n`)
        );

        // 发送思考内容
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'reasoning_chunk', content: '思考中...' })}\n\n`)
        );

        // 发送 reasoning_end
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'reasoning_end' })}\n\n`)
        );

        // 发送回答
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'answer_start' })}\n\n`)
        );
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'chunk', content: '您好！' })}\n\n`)
        );

        // 发送完成
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`)
        );

        controller.close();
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    });
  }),

  // 获取城市列表
  http.get('/api/cities', () => {
    return HttpResponse.json({
      success: true,
      cities: [
        { city: '北京', region: '华北', tags: ['历史文化', '现代都市'] },
        { city: '上海', region: '华东', tags: ['现代都市', '美食'] },
      ],
    });
  }),
];
