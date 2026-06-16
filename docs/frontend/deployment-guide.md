# Frontend Deployment Guide

## 本地运行

```bash
python scripts/bootstrap.py
python scripts/dev.py frontend-dev
```

默认地址: `http://localhost:33003`

## 生产构建

```bash
npm run build
npm start
```

## 必需环境变量

```bash
NEXT_PUBLIC_API_BASE=http://localhost:38083
```

## 部署前检查

1. `npm run build` 成功
2. 首页可渲染
3. Chat SSE 可连通后端
