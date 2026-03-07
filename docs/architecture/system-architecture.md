# System Architecture

## 三层结构

1. Frontend (`frontend`)
2. Web API (`web`)
3. Agent (`agent`)

## 调用链路

```text
Browser -> FastAPI (/api/chat/stream) -> ChatService -> LangGraph Agent -> Tools/LLM
```

## 关键设计点

- Chat 采用 SSE 实时流式输出
- Session 与模型切换通过 Web 层统一管理
- Agent 通过 `graph` + `tools` 解耦推理与外部数据访问

## 当前端口

- Frontend: `33001`
- Web API: `38000`
