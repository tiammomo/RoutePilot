"""
================================================================================
Agent 工厂

负责创建和管理不同类型的 Agent 实例。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Agent 类型"""
    PLANNER = "planner"           # 规划 Agent
    MANAGER = "manager"           # 管理 Agent
    SUPERVISOR = "supervisor"     # 监督 Agent
    SPECIALIST = "specialist"      # 专家 Agent
    COORDINATOR = "coordinator"    # 协调 Agent
    GENERAL = "general"           # 通用 Agent


@dataclass
class AgentConfig:
    """Agent 配置"""
    agent_type: AgentType
    agent_id: str
    name: str
    description: str = ""
    capabilities: Set[str] = field(default_factory=set)  # 能力
    tools: List[str] = field(default_factory=list)       # 可用工具
    max_retries: int = 3                                 # 最大重试次数
    timeout: int = 30                                    # 超时时间（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentInstance:
    """Agent 实例"""
    config: AgentConfig
    agent_type: AgentType
    is_active: bool = False
    current_task: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "tasks_completed": 0,
        "tasks_failed": 0,
        "total_execution_time": 0.0
    })


class AgentFactory:
    """Agent 工厂

    负责创建、配置和管理 Agent 实例。
    """

    # 预定义的 Agent 模板
    TEMPLATES = {
        AgentType.PLANNER: {
            "name": "Planner Agent",
            "description": "负责任务分解和计划制定",
            "capabilities": {"task_decomposition", "planning", "reasoning"},
            "tools": ["llm_chat"]
        },
        AgentType.MANAGER: {
            "name": "Manager Agent",
            "description": "负责任务分发和进度跟踪",
            "capabilities": {"task_management", "progress_tracking", "coordination"},
            "tools": ["llm_chat"]
        },
        AgentType.SUPERVISOR: {
            "name": "Supervisor Agent",
            "description": "负责结果审核和质量控制",
            "capabilities": {"review", "quality_control", "validation"},
            "tools": ["llm_chat"]
        },
        AgentType.SPECIALIST: {
            "name": "Specialist Agent",
            "description": "负责领域任务执行",
            "capabilities": {"domain_expertise", "tool_execution"},
            "tools": []  # 运行时注入
        },
        AgentType.COORDINATOR: {
            "name": "Coordinator Agent",
            "description": "负责多 Agent 协调",
            "capabilities": {"coordination", "negotiation", "conflict_resolution"},
            "tools": ["llm_chat"]
        },
        AgentType.GENERAL: {
            "name": "General Agent",
            "description": "通用 Agent",
            "capabilities": {"general_reasoning"},
            "tools": []
        }
    }

    def __init__(self, llm_client: Optional[Any] = None):
        """
        Args:
            llm_client: LLM 客户端实例
        """
        self.llm_client = llm_client
        self._agents: Dict[str, AgentInstance] = {}
        self._agent_counter = 0

    def create_agent(
        self,
        agent_type: AgentType,
        agent_id: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> AgentInstance:
        """创建 Agent

        Args:
            agent_type: Agent 类型
            agent_id: 自定义 Agent ID（可选）
            custom_config: 自定义配置（可选）

        Returns:
            Agent 实例
        """
        # 生成 Agent ID
        if agent_id is None:
            agent_id = f"{agent_type.value}_{self._generate_id()}"

        # 获取模板配置
        template = self.TEMPLATES.get(agent_type, {})
        config_dict = custom_config or {}

        # 合并模板配置和自定义配置
        config = AgentConfig(
            agent_type=agent_type,
            agent_id=agent_id,
            name=config_dict.get("name", template.get("name", "Unnamed Agent")),
            description=config_dict.get("description", template.get("description", "")),
            capabilities=config_dict.get("capabilities", template.get("capabilities", set())),
            tools=config_dict.get("tools", template.get("tools", [])),
            max_retries=config_dict.get("max_retries", 3),
            timeout=config_dict.get("timeout", 30),
            metadata=config_dict.get("metadata", {})
        )

        # 创建实例
        instance = AgentInstance(
            config=config,
            agent_type=agent_type,
            is_active=False
        )

        self._agents[agent_id] = instance
        logger.info(f"Created agent {agent_id} of type {agent_type.value}")

        return instance

    def create_planner(self, agent_id: Optional[str] = None) -> AgentInstance:
        """创建 Planner Agent"""
        return self.create_agent(AgentType.PLANNER, agent_id)

    def create_manager(self, agent_id: Optional[str] = None) -> AgentInstance:
        """创建 Manager Agent"""
        return self.create_agent(AgentType.MANAGER, agent_id)

    def create_supervisor(self, agent_id: Optional[str] = None) -> AgentInstance:
        """创建 Supervisor Agent"""
        return self.create_agent(AgentType.SUPERVISOR, agent_id)

    def create_specialist(
        self,
        agent_id: Optional[str] = None,
        domain: str = "general",
        tools: Optional[List[str]] = None
    ) -> AgentInstance:
        """创建 Specialist Agent

        Args:
            agent_id: Agent ID
            domain: 专业领域
            tools: 专用工具列表
        """
        custom_config = {
            "name": f"Specialist Agent ({domain})",
            "description": f"负责 {domain} 领域的任务执行",
            "capabilities": {f"{domain}_expertise", "tool_execution"},
            "tools": tools or [],
            "metadata": {"domain": domain}
        }
        return self.create_agent(AgentType.SPECIALIST, agent_id, custom_config)

    def get_agent(self, agent_id: str) -> Optional[AgentInstance]:
        """获取 Agent"""
        return self._agents.get(agent_id)

    def list_agents(self, agent_type: Optional[AgentType] = None) -> List[AgentInstance]:
        """列出所有 Agent"""
        if agent_type:
            return [a for a in self._agents.values() if a.agent_type == agent_type]
        return list(self._agents.values())

    def remove_agent(self, agent_id: str) -> bool:
        """移除 Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Removed agent {agent_id}")
            return True
        return False

    def activate_agent(self, agent_id: str) -> bool:
        """激活 Agent"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.is_active = True
            return True
        return False

    def deactivate_agent(self, agent_id: str) -> bool:
        """停用 Agent"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.is_active = False
            agent.current_task = None
            return True
        return False

    def update_stats(self, agent_id: str, key: str, value: Any) -> bool:
        """更新统计"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.stats[key] = value
            return True
        return False

    def _generate_id(self) -> str:
        """生成唯一 ID"""
        self._agent_counter += 1
        return str(self._agent_counter).zfill(4)
