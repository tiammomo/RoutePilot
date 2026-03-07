# Contributing Guide

## 提交原则

1. 保持改动最小化与可回滚
2. 文档与代码一起更新
3. 不提交运行产物（缓存、日志、构建目录）

## 命名规范

- Python: `snake_case`
- React 组件: `PascalCase`
- 文档: `kebab-case.md`

## 目录规范

- 新文档放在 `docs/` 对应分层目录
- 测试代码放在 `tests/`、`agent/tests/`、`frontend/tests/`
- 环境/密钥配置仅放在本地 `.env*` 或私有 YAML

## 提交前检查

```bash
pytest tests/ -v
cd frontend && npm run test:run
```
