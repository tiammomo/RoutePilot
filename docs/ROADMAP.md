# 项目演进路线图 (v2.8.0 - v3.0+)

## 当前状态 (v2.7.4)

### 已完成功能

| 模块 | 特性 |
|------|------|
| **Memory v2.2** | 注意力窗口、反思机制、智能淘汰、向量化、回流、检索 |
| **MultiAgent v2.4** | 协调器、工厂、消息总线、角色Agent |
| **AgentEnhanced v2.5** | 自适应工作流、评估器、反馈循环 |
| **Production v2.6** | 沙箱、熔断器、监控 |
| **Infrastructure** | Redis、Milvus、Nacos、限流、缓存、推送 |

---

## 演进规划

### v2.8.0 - 工具生态扩展

**目标**: 扩展工具能力，支持更多场景

#### 新增模块

| 模块 | 功能 | 文件位置 |
|------|------|----------|
| **ToolRegistry** | 动态工具注册、发现、版本管理 | `tools/registry.py` |
| **ToolLearning** | 从用户反馈学习工具使用偏好 | `tools/learning.py` |
| **PluginSystem** | 插件化工具扩展机制 | `tools/plugin.py` |

#### 工具扩展

```
新增工具类型:
- WeatherTool - 天气预报、气候查询
- HotelTool - 酒店搜索、预订(仅信息)
- FlightTool - 航班查询
- RestaurantTool - 餐厅推荐、预订
- TransportTool - 交通指南、票务
- EventTool - 活动、演出、赛事查询
- PhotoSpotTool - 摄影点位推荐
- BudgetTool - 预算智能分配
```

#### 用户体验提升

- 工具自动推荐：根据上下文推荐最可能使用的工具
- 工具使用提示：引导用户发现更多功能
- 工具组合：多个工具组合使用场景

---

### v2.9.0 - 对话增强

**目标**: 提升对话质量和用户体验

#### 新增模块

| 模块 | 功能 | 文件位置 |
|------|------|----------|
| **DialoguePolicy** | 对话策略管理 | `core/dialogue_policy.py` |
| **ContextTracker** | 上下文追踪和恢复 | `memory/context_tracker.py` |
| **EntityLinker** | 实体链接和消歧 | `reasoner/entity_linker.py` |

#### 对话增强

```
增强功能:
- 多轮上下文理解：跨轮次实体追踪
- 对话状态机：清晰的状态转换
- 意图澄清：模糊意图的主动询问
- 会话续接：支持会话中断恢复
- 对话风格适配：根据用户调整回复风格
```

#### 用户体验提升

- 更自然的多轮对话
- 主动询问澄清需求
- 记住用户偏好和历史

---

### v3.0.0 - Agent 生态系统

**目标**: 构建完整的 Agent 生态

#### 新增模块

| 模块 | 功能 | 文件位置 |
|------|------|----------|
| **AgentHub** | Agent 市场、共享、发现 | `agent_hub/__init__.py` |
| **SkillStore** | 技能库管理 | `skills/store.py` |
| **AgentTemplate** | Agent 模板系统 | `templates/base.py` |
| **CollaborationProtocol** | Agent 协作协议 | `multiagent/collab_protocol.py` |

#### Agent 生态功能

```
核心功能:
- Agent 模板：预定义 Agent 类型
- 技能市场：可共享的 Agent 技能
- Agent 组合：多个 Agent 协同工作
- 技能编排：按场景组合技能
- 评估基准：Agent 性能评测
```

#### 用户体验提升

- 一键创建专业领域 Agent
- 社区共享优秀 Agent
- 复杂任务自动分解执行

---

## 演进路线图

```
v2.7.4 (当前)
    │
    ├─→ v2.8.0 (工具生态)
    │       ├─ ToolRegistry
    │       ├─ ToolLearning
    │       └─ PluginSystem
    │
    ├─→ v2.9.0 (对话增强)
    │       ├─ DialoguePolicy
    │       ├─ ContextTracker
    │       └─ EntityLinker
    │
    └─→ v3.0.0 (Agent 生态)
            ├─ AgentHub
            ├─ SkillStore
            └─ AgentTemplate
```

---

## 各版本详细规划

### v2.8.0 详细规划

#### ToolRegistry

```python
class ToolRegistry:
    """工具注册中心"""

    def register(self, tool: BaseTool) -> str:
        """注册工具"""

    def unregister(self, tool_id: str) -> bool:
        """注销工具"""

    def discover(self, query: str) -> List[BaseTool]:
        """发现工具"""

    def get_tool(self, tool_id: str) -> BaseTool:
        """获取工具"""

    def list_tools(self, category: str = None) -> List[ToolInfo]:
        """列出工具"""
```

#### ToolLearning

```python
class ToolLearning:
    """工具学习器"""

    def record_usage(self, tool_id: str, context: Dict, success: bool):
        """记录工具使用"""

    def recommend_tools(self, context: Dict, top_k: int = 3) -> List[str]:
        """推荐工具"""

    def infer_preferences(self, user_id: str) -> UserToolPreferences:
        """推断用户偏好"""
```

#### PluginSystem

```python
class PluginManager:
    """插件管理器"""

    def load_plugin(self, plugin_path: str) -> Plugin:
        """加载插件"""

    def unload_plugin(self, plugin_id: str):
        """卸载插件"""

    def list_plugins(self) -> List[PluginInfo]:
        """列出插件"""
```

---

### v2.9.0 详细规划

#### DialoguePolicy

```python
class DialoguePolicy:
    """对话策略"""

    def select_action(self, state: DialogueState) -> DialogueAction:
        """选择动作"""

    def should_clarify(self, intent: Intent) -> bool:
        """判断是否需要澄清"""

    def should_chitchat(self, context: Dict) -> bool:
        """判断是否闲聊"""
```

#### ContextTracker

```python
class ContextTracker:
    """上下文追踪"""

    def track_entity(self, entity: Entity, turn_id: int):
        """追踪实体"""

    def resolve_reference(self, reference: str) -> Entity:
        """消歧引用"""

    def get_active_entities(self) -> List[Entity]:
        """获取活跃实体"""
```

---

### v3.0.0 详细规划

#### AgentHub

```python
class AgentHub:
    """Agent 市场"""

    def publish_agent(self, agent: BaseAgent, metadata: AgentMetadata):
        """发布 Agent"""

    def discover_agents(self, query: str) -> List[AgentInfo]:
        """发现 Agent"""

    def rate_agent(self, agent_id: str, rating: int, review: str):
        """评价 Agent"""

    def download_agent(self, agent_id: str) -> BaseAgent:
        """下载 Agent"""
```

---

## 功能优先级

| 优先级 | 功能 | 预期工作量 | 用户价值 |
|--------|------|----------|---------|
| P0 | ToolRegistry | 中 | 高 |
| P0 | 工具扩展 (天气/酒店) | 中 | 高 |
| P1 | ContextTracker | 中 | 高 |
| P1 | DialoguePolicy | 小 | 中 |
| P1 | PluginSystem | 大 | 中 |
| P2 | AgentHub | 大 | 中 |
| P2 | SkillStore | 大 | 中 |

---

## 技术债务

| 债务 | 描述 | 建议 |
|------|------|------|
| TravelAgent 集成 | 部分模块未被充分集成 | v2.8 重点整合 |
| 测试覆盖 | 集成测试不足 | 持续补充 |
| 文档 | API 文档待完善 | 自动化生成 |
| 错误处理 | 部分边界情况未覆盖 | 逐步完善 |

---

## 总结

项目已具备完善的基础架构，下一步演进重点:

1. **工具生态** (v2.8): 扩展工具能力，支持更多场景
2. **对话增强** (v2.9): 提升多轮对话质量
3. **Agent 生态** (v3.0): 构建可复用的 Agent 生态

整体思路是从**功能扩展**到**质量提升**再到**生态构建**，逐步打造完整的智能旅游助手系统。
