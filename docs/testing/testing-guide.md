# Testing Guide

## 测试目录

- `tests/`: API 与集成测试
- `agent/tests/`: Agent 单元/模块测试
- `frontend/tests/`: 前端单元测试

## 运行命令

### API / 集成

```bash
pytest tests/ -v
```

### Agent

```bash
cd agent
set PYTHONPATH=src
python -m pytest tests/ -v
```

### Frontend

```bash
cd frontend
npm run test:run
```

## 常见问题

1. `Connection refused`: 先启动 `python run_api.py`
2. `ModuleNotFoundError`: 检查 Python 环境与依赖
3. SSE 测试失败: 先确认 `/api/chat/stream` 可访问
