# Contributing Guide

## 提交原则

1. 保持改动最小化与可回滚
2. 文档与代码一起更新
3. 不提交运行产物（缓存、日志、构建目录）
4. 复杂逻辑优先补“职责清晰”的注释，不保留模板化说明

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
python scripts/docstring_audit.py --strict
cd frontend && npm run test:run
```

## 文档同步清单（建议）

发生以下变更时，建议同步更新对应文档：

1. 新增/修改接口字段：`docs/reference/api-reference.md`
2. 模块职责或目录变化：`docs/reference/project-structure.md`
3. 聊天渲染/`<think>` 行为变化：`docs/reference/frontend-message-rendering.md`
4. 后端流程或排障策略变化：`docs/reference/backend-maintainer-playbook.md`
