# Documentation Index

这套文档按“先上手、再理解、再查表”的顺序组织，方便不同读者快速找到入口。

## 建议阅读顺序

### 如果你是第一次接触项目

1. [../README.md](../README.md): 先看项目概览、能力范围和界面截图
2. [getting-started/quick-start.md](getting-started/quick-start.md): 按步骤启动前后端
3. [getting-started/ai-travel-agent-zero-to-one.md](getting-started/ai-travel-agent-zero-to-one.md): 用一条完整链路理解 AI 旅游 Agent 的设计
4. [reference/project-structure.md](reference/project-structure.md): 了解目录职责

### 如果你要继续开发或排查问题

1. [architecture/system-architecture.md](architecture/system-architecture.md): 理解前端、API、Agent 调用链
2. [getting-started/ai-travel-agent-zero-to-one.md](getting-started/ai-travel-agent-zero-to-one.md): 先建立 Agent 心智模型，再深入代码
3. [reference/api-reference.md](reference/api-reference.md): 查看接口与 SSE 事件协议
4. [testing/testing-guide.md](testing/testing-guide.md): 跑测试、benchmark 和 replay
5. [reference/configuration-reference.md](reference/configuration-reference.md): 查配置与环境变量

## 文档分区

### Getting Started

- [getting-started/quick-start.md](getting-started/quick-start.md): 本地启动、配置、访问地址
- [getting-started/ai-travel-agent-zero-to-one.md](getting-started/ai-travel-agent-zero-to-one.md): 面向新人的 AI 旅游 Agent 从 0 到 1 教程
- [getting-started/development-workflow.md](getting-started/development-workflow.md): 日常开发流程与提交前检查

### Product

- [product/product-requirements.md](product/product-requirements.md): 产品目标、用户价值、当前功能范围
- [agent-optimization-roadmap.md](agent-optimization-roadmap.md): Agent 优化方向与路线图

### Architecture

- [architecture/system-architecture.md](architecture/system-architecture.md): 整体系统架构与链路说明
- [architecture/data-storage.md](architecture/data-storage.md): 数据落盘与持久化策略
- [architecture/agent-p0-hardening-roadmap.md](architecture/agent-p0-hardening-roadmap.md): Agent 稳定性治理路线图
- [architecture/agent-dialogue-4-week-execution-plan.md](architecture/agent-dialogue-4-week-execution-plan.md): 对话链路迭代排期

### Reference

- [reference/api-reference.md](reference/api-reference.md): REST / SSE / 城市探索 / 分享接口
- [reference/configuration-reference.md](reference/configuration-reference.md): 配置文件与环境变量
- [reference/project-structure.md](reference/project-structure.md): 目录结构与关键模块职责
- [reference/naming-conventions.md](reference/naming-conventions.md): 命名约定
- [reference/backend-maintainer-playbook.md](reference/backend-maintainer-playbook.md): 后端维护与排障手册
- [reference/frontend-message-rendering.md](reference/frontend-message-rendering.md): 前端消息渲染与 `<think>` 折叠机制

### Testing & Quality

- [testing/testing-guide.md](testing/testing-guide.md): 单测、集成测试、benchmark、回放
- [benchmarks/agent_benchmark_latest.md](benchmarks/agent_benchmark_latest.md): 最新 benchmark 报告
- [benchmarks/agent_benchmark_trend_latest.md](benchmarks/agent_benchmark_trend_latest.md): benchmark 趋势报告
- [benchmarks/agent_golden_eval_latest.json](benchmarks/agent_golden_eval_latest.json): golden eval 原始结果

## 文档维护建议

- 面向外部读者的信息优先放在 `README.md`
- 面向开发实现的细节放在 `docs/` 子目录
- benchmark、golden eval、replay 等运行产物只放在 `docs/benchmarks/`
- 每次大功能上线后，至少同步更新这 4 份文档：
  - `README.md`
  - `docs/README.md`
  - `docs/reference/api-reference.md`
  - `docs/product/product-requirements.md`
