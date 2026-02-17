# Agent 编排架构演进方案

## 1. 当前架构分析

### 1.1 现有组件

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ReActTravelAgent                             │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  ReActAgent  │  │  Memory v2.2 │  │     Tools (6个)           │ │
│  │              │  │              │  │                          │ │
│  │ - Reasoning  │  │ - Orchestrator│ │ - search_cities         │ │
│  │ - Acting     │  │ - Attention   │ │ - query_attractions     │ │
│  │ - Observing  │  │ - Reflection  │ │ - generate_route        │ │
│  │ - Evaluating │  │ - Eviction    │ │ - calculate_budget       │ │
│  └──────────────┘  │ - Vectorizer  │ │ - get_city_info         │ │
│                    │ - Recirculation│ │ - llm_chat              │ │
│                    │ - Retrieval    │ │ - generate_recommendation│ │
│                    └──────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 现有能力

| 能力 | 状态 | 说明 |
|------|------|------|
| ReAct 推理循环 | ✅ 完整 | Think → Act → Observe → Evaluate |
| Memory v2.2 | ✅ 完整 | 注意力、反思、淘汰、向量化、回流、检索 |
| 工具调用 | ✅ 基础 | 6 个旅游相关工具 |
| 多模式对话 | ✅ | Direct / ReAct / Plan |
| 意图识别 | ✅ | 17+ 细粒度意图类型 |
| 动态风格 | ✅ | 5 种回复风格 |
| 依赖注入 | ✅ | DI 容器 |
| 基础设施 | ⚠️ 丰富但分散 | HTTP池/缓存/限流/向量库等 |

### 1.3 存在的问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **单 Agent 架构** | 只有一个 ReActTravelAgent，无法处理复杂任务 | 复杂场景处理能力有限 |
| **工具单一** | 仅 6 个工具，无动态工具学习 | 扩展性差 |
| **无工作流引擎** | PLAN 模式未真正实现 | 多步骤任务执行弱 |
| **无 Agent 通信** | 缺乏 Agent 间协作机制 | 无法多 Agent 协同 |
| **状态管理割裂** | StateManager 存在但未集成 | 状态持久化困难 |
| **评估体系缺失** | 无 Agent 性能评估 | 优化无量化指标 |
| **生命周期管理** | 无 Agent 启动/暂停/恢复 | 可控性差 |

---

## 2. 演进路线图

### 阶段一：Agent 基础设施强化 (v2.3.0)

**目标**: 夯实基础，完善单 Agent 能力

#### 1.1 完善 PLAN 模式

```
用户请求 ──► 任务分解 ──► 子任务队列 ──► 顺序/并行执行 ──► 结果聚合
                    │
                    ▼
              生成执行计划
              (步骤1: 搜索城市 → 步骤2: 查询景点 → 步骤3: 生成路线)
```

**核心组件**:
- `WorkflowEngine`: 工作流引擎
- `TaskDecomposer`: 任务分解器
- `TaskQueue`: 任务队列管理
- `ResultAggregator`: 结果聚合器

**文件**: `agent/src/core/workflow_engine.py`

```python
class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, agent: ReActTravelAgent):
        self.agent = agent
        self.task_queue = TaskQueue()
        self.decomposer = TaskDecomposer()
        self.aggregator = ResultAggregator()

    async def execute_plan(self, user_request: str) -> WorkflowResult:
        # 1. 任务分解
        subtasks = await self.decomposer.decompose(user_request)

        # 2. 添加到任务队列
        for task in subtasks:
            await self.task_queue.enqueue(task)

        # 3. 按依赖顺序执行
        results = []
        while not self.task_queue.is_empty():
            task = await self.task_queue.dequeue()
            result = await self._execute_task(task)
            results.append(result)

        # 4. 聚合结果
        return await self.aggregator.aggregate(results)
```

#### 1.2 扩展工具系统

**现有工具** → **工具生态系统**

| 类别 | 现有工具 | 新增工具 |
|------|---------|---------|
| 搜索 | search_cities | search_hotels, search_flights, search_restaurants |
| 查询 | query_attractions, get_city_info | query_weather, query_traffic, query_events |
| 规划 | generate_route, generate_route_plan | generate_itinerary, optimize_route |
| 计算 | calculate_budget | compare_prices, estimate_time |
| 推荐 | generate_recommendation | recommend_season, recommend_activities |

**工具注册增强**:
- 动态工具发现
- 工具版本管理
- 工具依赖声明
- 工具使用统计

**文件**: `agent/src/tools/tool_registry.py`

```python
class ToolRegistry:
    """工具注册表 - 增强版"""

    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._dependencies: Dict[str, List[str]] = {}

    def register(self, tool: ToolInfo, executor: Callable):
        """注册工具"""
        self._tools[tool.name] = tool

    def discover_tools(self, module_path: str):
        """自动发现工具"""
        # 从指定模块自动发现工具类
        pass

    def get_execution_plan(self, required_tools: List[str]) -> List[List[str]]:
        """计算工具执行计划（考虑依赖）"""
        # 拓扑排序
        pass
```

#### 1.3 增强状态管理

**目标**: 集成现有 StateManager，实现 Agent 状态持久化

```python
class AgentStateManager:
    """Agent 状态管理器"""

    async def save_checkpoint(self, session_id: str, state: AgentSnapshot):
        """保存检查点"""

    async def restore_checkpoint(self, session_id: str) -> Optional[AgentSnapshot]:
        """恢复检查点"""

    async def get_active_sessions(self) -> List[str]:
        """获取活跃会话"""

    async def cleanup_old_sessions(self, max_age_hours: int):
        """清理过期会话"""
```

#### 1.4 Agent 生命周期管理

```python
class AgentLifecycle:
    """Agent 生命周期管理"""

    async def start(self, session_id: str):
        """启动 Agent"""

    async def pause(self, session_id: str):
        """暂停 Agent"""

    async def resume(self, session_id: str):
        """恢复 Agent"""

    async def terminate(self, session_id: str):
        """终止 Agent"""

    async def get_status(self, session_id: str) -> AgentStatus:
        """获取状态"""
```

---

### 阶段二：多 Agent 编排框架 (v2.4.0) ✅ 已完成

**目标**: 支持多 Agent 协作，处理复杂任务

**实现状态**:
- ✅ `agent/src/multiagent/` 模块完整实现
- ✅ 56 个单元测试全部通过

#### 2.1 多 Agent 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Orchestrator                            │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │   Planner   │  │   Manager   │  │  Supervisor │               │
│  │   Agent     │  │   Agent     │  │    Agent    │               │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘               │
│         │                │                │                        │
│         └────────────────┼────────────────┘                        │
│                          ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Task Distribution                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│    ┌─────────────────────┼─────────────────────┐                  │
│    ▼                     ▼                     ▼                   │
│ ┌──────────┐       ┌──────────┐       ┌──────────┐              │
│ │ Specialist│       │ Specialist│       │ Specialist│              │
│ │  Agent   │       │  Agent   │       │  Agent   │              │
│ │ (Search) │       │ (Planning)│       │ (Review) │              │
│ └──────────┘       └──────────┘       └──────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.2 Agent 类型定义

| Agent 类型 | 职责 | 工具权限 |
|-----------|------|---------|
| Planner Agent | 任务分解、计划制定 | 全部只读 |
| Manager Agent | 任务分发、进度跟踪 | 任务管理 |
| Specialist Agent | 领域任务执行 | 领域工具 |
| Supervisor Agent | 结果审核、质量控制 | 审查工具 |
| Coordinator Agent | 多 Agent 协调 | 通信+管理 |

#### 2.3 Agent 通信协议

```python
class AgentMessage:
    """Agent 间消息"""

    sender: str           # 发送者 ID
    receiver: str         # 接收者 ID
    message_type: MessageType  # 消息类型
    content: Any          # 消息内容
    correlation_id: str   # 关联 ID
    timestamp: datetime   # 时间戳


class MessageType(Enum):
    REQUEST = "request"           # 请求
    RESPONSE = "response"         # 响应
    TASK_ASSIGN = "task_assign"   # 任务分配
    TASK_COMPLETE = "task_complete" # 任务完成
    PROGRESS = "progress"         # 进度更新
    ERROR = "error"               # 错误通知
    APPROVAL = "approval"         # 审批请求
```

#### 2.4 核心组件

**文件**: `agent/src/multiagent/__init__.py`

```
agent/src/multiagent/
├── __init__.py
├── orchestrator.py       # 多 Agent 协调器
├── agent_factory.py      # Agent 工厂
├── message_bus.py        # 消息总线
├── protocols/
│   ├── __init__.py
│   ├── communication.py  # 通信协议
│   └── negotiation.py    # 协商协议
├── roles/
│   ├── __init__.py
│   ├── planner.py        # 规划 Agent
│   ├── specialist.py     # 专家 Agent
│   └── supervisor.py     # 监督 Agent
└── collaboration/
    ├── __init__.py
    ├── task_distributor.py  # 任务分发
    └── result_merger.py     # 结果合并
```

```python
class MultiAgentOrchestrator:
    """多 Agent 协调器"""

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.agent_factory = AgentFactory()
        self.message_bus = MessageBus()
        self.task_distributor = TaskDistributor()
        self.result_merger = ResultMerger()

    async def process(self, user_request: str) -> MultiAgentResult:
        # 1.  Planner Agent 分解任务
        plan = await self._planning(user_request)

        # 2. 分发给 Specialist Agents
        tasks = self.task_distributor.distribute(plan)

        # 3. 并行执行
        results = await asyncio.gather(*[
            self._execute_specialist(task)
            for task in tasks
        ])

        # 4. Supervisor Agent 审核
        reviewed = await self._supervise(results)

        # 5. 合并结果
        return await self.result_merger.merge(reviewed)
```

---

### 阶段三：智能编排增强 (v2.5.0) ✅ 已完成

**目标**: 引入 AI 驱动的智能编排

**实现状态**:
- ✅ `agent/src/agent_enhanced/` 模块完整实现
- ✅ 自适应工作流 (AdaptiveWorkflow)
- ✅ Agent 性能评估器 (AgentEvaluator)
- ✅ 反馈学习循环 (FeedbackLoop)
- ✅ 23 个单元测试全部通过

#### 3.1 自适应工作流

```python
class AdaptiveWorkflow:
    """自适应工作流 - 根据任务动态选择执行策略"""

    async def execute(self, task: Task) -> ExecutionResult:
        # 1. 任务复杂度评估
        complexity = await self._assess_complexity(task)

        # 2. 选择执行策略
        if complexity == TaskComplexity.SIMPLE:
            return await self._simple_execute(task)
        elif complexity == TaskComplexity.MEDIUM:
            return await self._workflow_execute(task)
        else:
            return await self._multiagent_execute(task)
```

#### 3.2 Agent 性能评估

```python
class AgentEvaluator:
    """Agent 性能评估器"""

    async def evaluate(self, session_id: str) -> EvaluationResult:
        metrics = {
            "response_time": self._measure_response_time(),
            "tool_usage_efficiency": self._measure_tool_efficiency(),
            "user_satisfaction": await self._survey_user(),
            "task_completion_rate": self._measure_completion(),
            "reasoning_quality": await self._assess_reasoning(),
        }

        return EvaluationResult(
            score=self._calculate_score(metrics),
            metrics=metrics,
            suggestions=self._generate_suggestions(metrics)
        )
```

#### 3.3 反馈学习循环

```
用户反馈 ──► 评估分析 ──► 策略调整 ──► 执行优化
                │              │
                ▼              ▼
           收集案例库      更新提示词模板
```

---

### 阶段四：生产级增强 (v2.6.0)

**目标**: 稳定性、安全性、可观测性

#### 4.1 安全沙箱

```python
class AgentSandbox:
    """Agent 执行沙箱"""

    def __init__(self):
        self.resource_limits = ResourceLimits(
            max_execution_time=30,  # 秒
            max_memory_mb=512,
            max_network_calls=10,
            allowed_domains=["api.example.com"]
        )
```

#### 4.2 完整可观测性

```
Metrics ──► Prometheus ──► Grafana
Logs    ──► ELK Stack
Traces  ──► Jaeger
```

#### 4.3 限流与熔断

```python
class AgentCircuitBreaker:
    """Agent 熔断器"""

    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.state = CircuitState.CLOSED

    async def call(self, agent, *args):
        if self.state == CircuitState.OPEN:
            raise CircuitOpenException()

        try:
            result = await agent(*args)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

---

## 3. 实施优先级

| 优先级 | 功能 | 预估工作量 | 价值 |
|--------|------|----------|------|
| P0 | 完善 PLAN 模式 | 2 周 | 高 |
| P0 | 扩展工具系统 | 2 周 | 高 |
| P1 | 状态管理集成 | 1 周 | 中 |
| P1 | 生命周期管理 | 1 周 | 中 |
| P2 | 多 Agent 框架 | 4 周 | 高 |
| P2 | 自适应工作流 | 3 周 | 高 |
| P3 | 性能评估 | 2 周 | 中 |
| P3 | 安全沙箱 | 2 周 | 中 |

---

## 4. 文件变更清单

### 新增文件

| 文件路径 | 说明 |
|---------|------|
| `agent/src/core/workflow_engine.py` | 工作流引擎 |
| `agent/src/core/task_decomposer.py` | 任务分解器 |
| `agent/src/tools/tool_registry.py` | 增强工具注册表 |
| `agent/src/multiagent/__init__.py` | 多 Agent 模块入口 |
| `agent/src/multiagent/orchestrator.py` | 多 Agent 协调器 |
| `agent/src/multiagent/message_bus.py` | 消息总线 |
| `agent/src/multiagent/agent_factory.py` | Agent 工厂 |
| `agent/src/multiagent/roles/planner.py` | 规划 Agent |
| `agent/src/multiagent/roles/specialist.py` | 专家 Agent |
| `agent/src/multiagent/roles/supervisor.py` | 监督 Agent |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `agent/src/core/travel_agent.py` | 集成工作流引擎 |
| `agent/src/core/react_agent.py` | 支持检查点恢复 |
| `agent/src/core/travel_tools.py` | 扩展工具集 |
| `agent/src/tools/__init__.py` | 导出新工具类 |

---

## 5. 兼容性说明

- **向后兼容**: 所有变更保持现有 API 兼容
- **渐进式**: 每个阶段可独立部署
- **配置驱动**: 新功能可通过配置开启/关闭
