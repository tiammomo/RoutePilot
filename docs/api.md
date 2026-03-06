# API 接口文档

## 概述

本项目提供 RESTful API 接口，采用 HTTP + SSE (Server-Sent Events) 实现流式响应。所有接口均以 `/api/` 为前缀，基础 URL 为 `http://localhost:38000`。

---

## 目录

- [健康检查](#健康检查)
- [流式聊天](#流式聊天)
- [会话管理](#会话管理)
- [模型管理](#模型管理)
- [城市信息](#城市信息)
- [SSE 事件类型](#sse-事件类型)

---

## 健康检查

### 健康检查

获取服务健康状态。

**请求**

```
GET /api/health
```

**响应 (200 OK)**

```json
{
  "status": "healthy",
  "version": "3.2.0",
  "timestamp": "2024-01-01T00:00:00",
  "services": {
    "api": "healthy",
    "llm": "initialized",
    "sessions": "healthy"
  }
}
```

### 就绪检查

检查服务是否就绪。

**请求**

```
GET /api/ready
```

**响应 (200 OK)**

```json
{
  "status": "ready"
}
```

### 存活检查

简单的存活检测。

**请求**

```
GET /api/live
```

**响应 (200 OK)**

```json
{
  "status": "alive"
}
```

### LLM 健康检查

检查 LLM 服务状态。

**请求**

```
GET /api/health/llm
```

**响应 (200 OK)**

```json
{
  "status": "ok",
  "llm_adapter": true,
  "tools_count": 5,
  "sessions_count": 2
}
```

---

## 流式聊天

### SSE 流式聊天

发送消息并接收流式响应。这是核心接口，使用 SSE 实现实时流式输出。

**请求**

```
POST /api/chat/stream
Content-Type: application/json

{
  "message": "云南丽江旅游攻略",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "mode": "react"
}
```

**请求参数**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| message | string | 是 | 用户消息内容 |
| session_id | string | 否 | 会话ID，不传则创建新会话 |
| mode | string | 否 | 对话模式：`direct`/`react`/`plan`，默认 `react` |

**响应 (SSE Stream)**

```
data: {"type": "session_id", "session_id": "550e8400-e29b-41d4-a716-446655440000"}

data: {"type": "reasoning_start"}

data: {"type": "reasoning_chunk", "content": "[已思考 0.5秒]\n\n分析用户需求..."}

data: {"type": "reasoning_end"}

data: {"type": "answer_start"}

data: {"type": "chunk", "content": "云南"}

data: {"type": "chunk", "content": "丽江"}

data: {"type": "chunk", "content": "是"}

...

data: {"type": "done", "stats": {"tokens": 482, "duration": 17.087}}
```

**响应说明**

响应为 SSE 格式，每行以 `data: ` 开头。详见 [SSE 事件类型](#sse-事件类型)。

---

## 会话管理

### 创建新会话

创建一个新的聊天会话。

**请求**

```
POST /api/session/new
Content-Type: application/json

{
  "name": "我的旅行计划"
}
```

**请求参数**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| name | string | 否 | 会话名称，默认"新会话" |

**响应 (200 OK)**

```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "我的旅行计划"
}
```

### 获取会话列表

列出所有会话。

**请求**

```
GET /api/sessions?include_empty=false
```

**查询参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| include_empty | boolean | 是否包含空会话，默认 false |

**响应 (200 OK)**

```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "云南旅游攻略",
      "message_count": 5,
      "last_active": "2024-01-15T10:30:00Z",
      "model_id": "minimax-m2-5"
    }
  ],
  "total": 1
}
```

### 删除会话

删除指定会话。

**请求**

```
DELETE /api/session/{session_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| session_id | string | 要删除的会话ID |

**响应 (200 OK)**

```json
{
  "success": true
}
```

### 更新会话名称

更新会话的名称。

**请求**

```
PUT /api/session/{session_id}/name
Content-Type: application/json

{
  "name": "新的会话名称"
}
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| session_id | string | 要更新的会话ID |

**请求Body**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| name | string | 是 | 新的会话名称 |

**响应 (200 OK)**

```json
{
  "success": true,
  "name": "新的会话名称"
}
```

### 设置会话模型

设置会话使用的 LLM 模型。

**请求**

```
PUT /api/session/{session_id}/model
Content-Type: application/json

{
  "model_id": "minimax-m2-5"
}
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| session_id | string | 要设置的会话ID |

**请求Body**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| model_id | string | 是 | 模型ID |

**响应 (200 OK)**

```json
{
  "success": true,
  "model_id": "minimax-m2-5"
}
```

### 获取会话模型

获取会话当前使用的模型。

**请求**

```
GET /api/session/{session_id}/model
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| session_id | string | 会话ID |

**响应 (200 OK)**

```json
{
  "success": true,
  "model_id": "minimax-m2-5"
}
```

### 清除聊天记录

清空会话的聊天记录。

**请求**

```
POST /api/clear/{session_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| session_id | string | 要清空的会话ID |

**响应 (200 OK)**

```json
{
  "success": true
}
```

---

## 模型管理

### 获取可用模型列表

获取所有可用的 LLM 模型。

**请求**

```
GET /api/models
```

**响应 (200 OK)**

```json
{
  "success": true,
  "models": [
    {
      "model_id": "minimax-m2-5",
      "name": "MiniMax M2.5",
      "provider": "anthropic",
      "model": "MiniMax-M2.5"
    },
    {
      "model_id": "gpt-4o-mini",
      "name": "GPT-4o Mini",
      "provider": "openai",
      "model": "gpt-4o-mini"
    }
  ]
}
```

### 获取模型详情

获取指定模型的详细信息。

**请求**

```
GET /api/models/{model_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| model_id | string | 模型ID |

**响应 (200 OK)**

```json
{
  "success": true,
  "model": {
    "model_id": "minimax-m2-5",
    "name": "MiniMax M2.5",
    "provider": "anthropic",
    "model": "MiniMax-M2.5",
    "status": "available"
  }
}
```

---

## 城市信息

### 获取城市列表

获取支持的城市列表，支持过滤。

**请求**

```
GET /api/cities?region=华东&has_attractions=true
```

**查询参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| region | string | 地区过滤（华东/华北/华南/西南/西北/东北） |
| has_attractions | boolean | 只返回有景点的城市 |
| search | string | 搜索关键词 |

**响应 (200 OK)**

```json
{
  "success": true,
  "cities": [
    {
      "city_id": "lijiang",
      "name": "丽江",
      "region": "西南",
      "description": "丽江是一个充满民族风情的古城..."
    }
  ],
  "total": 1
}
```

### 获取城市详情

获取指定城市的详细信息。

**请求**

```
GET /api/cities/{city_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| city_id | string | 城市ID |

**响应 (200 OK)**

```json
{
  "success": true,
  "city": {
    "city_id": "lijiang",
    "name": "丽江",
    "region": "西南",
    "description": "丽江是一个充满民族风情的古城...",
    "highlights": ["丽江古城", "玉龙雪山", "束河古镇"],
    "best_season": "春秋两季",
    "avg_cost": "2000-3000元/天"
  }
}
```

### 获取城市景点

获取指定城市的景点列表。

**请求**

```
GET /api/cities/{city_id}/attractions
```

**路径参数**

| 参数 | 类型 | 说明 |
|-----|------|------|
| city_id | string | 城市ID |

**响应 (200 OK)**

```json
{
  "success": true,
  "attractions": [
    {
      "attraction_id": "lijiang-ancient-town",
      "name": "丽江古城",
      "category": "历史文化",
      "rating": 4.8,
      "address": "云南省丽江市古城区",
      "description": "世界文化遗产，纳西族文化中心..."
    }
  ],
  "total": 1
}
```

### 获取地区列表

获取所有可选的地区。

**请求**

```
GET /api/regions
```

**响应 (200 OK)**

```json
{
  "success": true,
  "regions": ["华东", "华北", "华南", "西南", "西北", "东北"]
}
```

### 获取标签列表

获取所有可用的城市/景点标签。

**请求**

```
GET /api/tags
```

**响应 (200 OK)**

```json
{
  "success": true,
  "tags": [
    {"id": "history", "name": "历史文化"},
    {"id": "nature", "name": "自然风光"},
    {"id": "food", "name": "美食"},
    {"id": "photography", "name": "摄影圣地"}
  ]
}
```

---

## SSE 事件类型

### 事件类型汇总

| 事件类型 | 说明 | 数据结构 |
|----------|------|----------|
| `session_id` | 会话标识 | `{"type": "session_id", "session_id": "..."}` |
| `thinking` | 思考过程 | `{"type": "thinking", "thought": "...", "step": 1}` |
| `reasoning_start` | 思考过程开始 | `{"type": "reasoning_start"}` |
| `reasoning_chunk` | 思考内容片段 | `{"type": "reasoning_chunk", "content": "..."}` |
| `reasoning_end` | 思考过程结束 | `{"type": "reasoning_end"}` |
| `tool_call` | 工具调用 | `{"type": "tool_call", "tool": "...", "parameters": {...}}` |
| `tool_result` | 工具结果 | `{"type": "tool_result", "tool": "...", "result": {...}}` |
| `answer_start` | 答案开始生成 | `{"type": "answer_start"}` |
| `chunk` | 答案内容片段 | `{"type": "chunk", "content": "..."}` |
| `error` | 错误信息 | `{"type": "error", "content": "...", "code": "..."}` |
| `heartbeat` | 心跳保活 | `{"type": "heartbeat", "timestamp": "..."}` |
| `done` | 传输完成 | `{"type": "done", "stats": {...}}` |

### 事件详情

#### session_id

新会话创建或确认会话ID时发送。

```json
{
  "type": "session_id",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### reasoning_start

AI 开始思考时发送。

```json
{
  "type": "reasoning_start"
}
```

#### reasoning_chunk

AI 思考内容的片段。包含可折叠展示的思考过程。

```json
{
  "type": "reasoning_chunk",
  "content": "[已思考 0.5秒]\n\n分析用户需求：\n用户想要了解云南丽江的旅游攻略，这是一个典型的城市旅游咨询问题。\n\n制定计划：\n1. 调用城市信息API获取丽江基本介绍\n2. 查询丽江热门景点\n3. 获取景点详细信息\n4. 生成完整攻略"
}
```

#### thinking

AI 思考过程事件，包含推理步骤。

```json
{
  "type": "thinking",
  "thought": "分析用户需求，确定下一步行动",
  "step": 1
}
```

#### tool_call

Agent 调用工具时发送。

```json
{
  "type": "tool_call",
  "tool": "get_city_attractions",
  "parameters": {
    "city_id": "lijiang"
  }
}
```

#### tool_result

工具执行结果。

```json
{
  "type": "tool_result",
  "tool": "get_city_attractions",
  "result": {
    "success": true,
    "data": [
      {
        "id": "attr_001",
        "name": "丽江古城",
        "rating": 4.8
      }
    ]
  }
}
```

#### reasoning_end

思考过程结束时发送。

```json
{
  "type": "reasoning_end"
}
```

#### answer_start

开始生成最终回答时发送。

```json
{
  "type": "answer_start"
}
```

#### chunk

回答内容的片段。实时输出的每个 token 或词组。

```json
{
  "type": "chunk",
  "content": "云南"
}
```

```json
{
  "type": "chunk",
  "content": "丽江"
}
```

#### error

发生错误时发送。

```json
{
  "type": "error",
  "content": "抱歉，处理您的请求时出现了问题，请稍后重试。"
}
```

#### heartbeat

心跳保活，每30秒发送一次。

```json
{
  "type": "heartbeat",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### done

流式传输完成时发送，包含统计信息。

```json
{
  "type": "done",
  "stats": {
    "tokens": 482,
    "duration": 17.087,
    "reasoning_tokens": 156,
    "answer_tokens": 326
  }
}
```

---

## 错误响应

所有接口的错误响应格式如下：

```json
{
  "success": false,
  "error": "错误描述信息"
}
```

### 常见错误码

| HTTP状态码 | 错误信息 | 说明 |
|-----------|---------|------|
| 400 | Bad Request | 请求参数错误 |
| 404 | Not Found | 资源不存在 |
| 500 | Internal Server Error | 服务器内部错误 |
| 503 | Service Unavailable | 服务不可用 |

---

## WebSocket SSE 示例

### 前端集成示例

```typescript
import { useState, useCallback } from 'react';

interface SSEEvent {
  type: string;
  content?: string;
  session_id?: string;
  stats?: {
    tokens: number;
    duration: number;
  };
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [reasoning, setReasoning] = useState('');

  const sendMessage = useCallback(async (message: string, sessionId?: string) => {
    setIsStreaming(true);
    setReasoning('');

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) return;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event: SSEEvent = JSON.parse(line.slice(6));

            switch (event.type) {
              case 'session_id':
                console.log('会话ID:', event.session_id);
                break;

              case 'reasoning_start':
                setReasoning('🧠 思考中...\n');
                break;

              case 'reasoning_chunk':
                setReasoning(prev => prev + event.content!);
                break;

              case 'reasoning_end':
                console.log('思考完成');
                break;

              case 'answer_start':
                setReasoning(prev => prev + '\n✨ 回答：\n');
                break;

              case 'chunk':
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  if (last?.role === 'assistant') {
                    return [...prev.slice(0, -1), {
                      ...last,
                      content: last.content + (event.content || '')
                    }];
                  }
                  return [...prev, { role: 'assistant', content: event.content || '' }];
                });
                break;

              case 'done':
                setIsStreaming(false);
                console.log('完成:', event.stats);
                break;

              case 'error':
                setIsStreaming(false);
                console.error('错误:', event.content);
                break;
            }
          } catch (e) {
            // 忽略解析错误
          }
        }
      }
    }
  }, []);

  return { sendMessage, isStreaming, messages, reasoning };
}
```

---

## 认证

当前版本未实现认证机制，所有接口公开可访问。

未来版本计划添加：
- API Key 认证
- JWT Token 认证
- OAuth 2.0 认证

---

## 速率限制

当前版本未实现速率限制。

未来版本计划：
- 每 IP 每分钟 60 次请求
- 流式接口每分钟 30 次请求
