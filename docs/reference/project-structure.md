# Project Structure

## 顶层目录职责

```text
ShuaiTravelAgent/
├── agent/        # LangGraph Agent 逻辑
├── web/          # FastAPI 服务
├── frontend/     # Next.js 前端
├── config/       # YAML 配置
├── docs/         # 文档
├── tests/        # API 与集成测试
└── data/         # 运行时数据（默认忽略）
```

## 关键模块

### agent/src

- `graph/`: 状态图构建与节点执行
- `llm/`: 模型适配层
- `tools/`: 旅行工具定义与调用

### web/src

- `main.py`: FastAPI 应用入口
- `routes/`: API 路由
- `services/`: 业务服务
- `repositories/`: 仓储接口与实现
- `storage/`: 存储抽象与落地

### frontend/src

- `app/`: Next.js App Router 页面
- `components/`: 组件层
- `context/`: 全局上下文
- `services/`: API 访问层
- `types/`: TS 类型定义

## 结构规范

1. Python 文件统一 `snake_case.py`
2. React 组件文件使用 `PascalCase.tsx`
3. 文档文件统一 `kebab-case.md`
4. 禁止在 `docs/` 中混放运行产物
5. 临时输出与缓存必须进入 `.gitignore`
