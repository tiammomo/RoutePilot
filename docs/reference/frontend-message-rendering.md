# Frontend Message Rendering Guide

本文档说明聊天页中“流式输出 -> Markdown 清洗 -> `<think>` 折叠 -> 卡片渲染”的完整链路，方便后续维护和扩展。

## 1. 关键文件

1. `frontend/src/components/ChatArea.tsx`
2. `frontend/src/components/chat-area/useChatRuntime.ts`
3. `frontend/src/components/MessageList.tsx`
4. `frontend/src/components/message-list/markdownRenderer.tsx`
5. `frontend/src/services/api/chatClient.ts`
6. `frontend/src/services/api/chatStreamParser.ts`
7. `frontend/src/types/index.ts`

其中要特别注意：`ChatArea.tsx` 和 `MessageList.tsx` 现在都已经是薄入口，真实的运行时状态、SSE 解析和 Markdown 渲染逻辑分别下沉到了 `chat-area/`、`message-list/` 和 `services/api/`。

## 2. 流式数据进入 UI 的路径

1. `ChatArea.tsx` 负责 chat workspace 装配，并委托 `useChatRuntime.ts` 维护运行时状态。
2. `useChatRuntime.ts` 调用 `chatClient.fetchStreamChat(...)` 发起流式请求。
3. `chatClient.ts` 负责连接状态、超时、中断、重连与 reader 循环。
4. `chatStreamParser.ts` 逐行解析 SSE，把 `chunk / reasoning / stage / tool / metadata / artifact` 事件分发到独立回调。
5. `useChatRuntime.ts` 把原始内容先写入 `fullResponseRef/fullReasoningRef`，同时把增量文本推入 `streamQueueRef`（`answer/reasoning`）。
6. `flushStreamingQueue` 按固定 tick 抽取少量字符更新 UI。
7. `onComplete` 时把队列剩余内容 `drain` 到 ref 并落盘为正式消息。

这样做的目的是：

1. 避免每个 token 都触发 React 重渲染。
2. 保证停止流式时不会丢失尾部字符。
3. 保持“思考”与“答案”两个通道的节奏可控。

## 3. Markdown 清洗链路

`MessageList.tsx` 现在主要做列表装配，Markdown 清洗与表格归一化已经下沉到 `message-list/markdownRenderer.tsx`。这条链路主要通过 `prepareMarkdownContent` 处理内容，步骤如下：

1. `cleanContent`：统一换行、空格、HTML `<br>`。
2. `normalizePseudoSeparators`：修正常见 `||` 与全角竖线问题。
3. `normalizePipeTableBlocks`：把伪表格整理成合法 markdown 表格。
4. `normalizeEvidenceBlocks`：确保证据来源块有稳定换行。
5. `transformOutsideCodeFences`：只处理代码块外内容，避免破坏 fenced code。

## 4. `<think>` 折叠机制

`extractThinkBlocks` 现在位于 `message-list/messageSections.tsx`，它会把正文与思考拆分：

1. `<think> ... </think>` 内容进入 `thinkBlocks`。
2. 非 think 内容进入 `visibleContent`。
3. 若 `</think>` 缺失，标记 `hasUnclosedThink=true`，以便流式中提示“仍在思考”。

渲染策略：

1. `ReasoningBlock`: 展示后端 `reasoning` 字段（可展开）。
2. `ThinkBlock`: 展示正文中的 `<think>` 段落（可展开）。
3. 正文为空时显示提示“已折叠思考过程，正文内容为空”。

## 5. 表格转卡片策略

`MarkdownTableAsCards` 将 markdown table 转成卡片/列表视图，主要原因：

1. 原始表格在移动端可读性差。
2. 模型输出经常是“伪表格”，直接渲染会错位。
3. 卡片布局更适合行程信息（时间段、预算、点位）展示。

规则摘要：

1. 两列表格渲染为 key-value 卡片。
2. 多列表格渲染为字段卡片网格。
3. 缺失列自动补 `-`，避免 UI 断裂。

## 6. 常见问题排查

### 6.1 看到重复 key 警告

检查 `MessageList` 中 `messageId` 与 `key` 是否包含 `index` 或其它稳定去重因子。

### 6.2 “思考内容泄漏到正文”

检查：

1. 输出是否包含合法闭合的 `</think>`。
2. `extractThinkBlocks` 是否处理了大小写/换行。

### 6.3 表格渲染成纯文本

检查：

1. 是否被 fenced code 包裹（代码块内不会转表格）。
2. 行内分隔符是否至少满足表格识别规则。

## 7. 改动建议

当你修改这条链路时，请同步更新：

1. `docs/reference/api-reference.md`（如果 SSE 字段变化）
2. `docs/reference/project-structure.md`（如果模块职责变化）
3. `docs/teaching/02-chat-mainline-and-frontend.md`（如果主链阅读入口变化）
4. 本文档（渲染规则变化）
