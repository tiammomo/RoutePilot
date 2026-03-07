# Development Workflow

## 日常开发顺序

1. 激活环境: `.\.venv\Scripts\activate`
2. 启动 API: `python run_api.py`
3. 启动前端: `cd frontend && npm run dev`
4. 修改代码后执行对应测试

## 常用命令

```bash
# API 测试
python -m pytest tests/ -v

# 前端测试
cd frontend && npm run test:run

# Agent 测试
cd agent && set PYTHONPATH=src && python -m pytest tests/ -v
```

## 推荐提交前检查

1. API 能正常返回 `/api/health`
2. 聊天流接口 `/api/chat/stream` 可用
3. 前端首页可正常访问
4. 至少执行一次对应模块的测试
