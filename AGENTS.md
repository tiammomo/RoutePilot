# ShuaiTravelAgent Agent Guide

## Project Overview

ShuaiTravelAgent is an AI travel assistant project built with:

- Frontend: Next.js 16 + React 19 + TypeScript + antd
- Web API: FastAPI
- Agent: LangChain + LangGraph
- LLM: MiniMax M2.5 (Anthropic-compatible API)

## Service Ports

- Frontend: `33001`
- Web API: `38000`

## Key Endpoints

- Frontend: `http://localhost:33001`
- API: `http://localhost:38000`
- API Docs: `http://localhost:38000/rapidoc`
- Health: `http://localhost:38000/api/health`

## Current Route Structure

```text
web/src/routes/
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
