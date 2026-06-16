# moyuan-travel-agent Agent Guide

## Project Overview

moyuan-travel-agent is an AI travel assistant project built with:

- Frontend: Next.js 16 + React 19 + TypeScript + antd
- Web API: FastAPI
- Agent: LangChain + LangGraph
- LLM: mimo-v2.5-pro (MiniMax Anthropic-compatible API)

## Service Ports

- Frontend: `33003`
- Web API: `38083`

## Key Endpoints

- Frontend: `http://localhost:33003`
- API: `http://localhost:38083`
- API Docs: `http://localhost:38083/rapidoc`
- Health: `http://localhost:38083/api/health`

## Current Route Structure

```text
web/moyuan_web/routes/
├── api_docs.py
├── chat.py
├── city.py
├── errors.py
├── health.py
├── model.py
└── session.py
```

## Documentation Entry

- Root: `README.md`
- Docs index: `docs/README.md`
