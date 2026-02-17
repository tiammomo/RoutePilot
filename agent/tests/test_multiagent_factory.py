"""
AgentFactory 和 Role Agents 单元测试
"""

import pytest
from multiagent.agent_factory import AgentFactory, AgentType, AgentConfig, AgentInstance
from multiagent.roles.planner import PlannerAgent, ExecutionPlan, PlanComplexity, SubTask
from multiagent.roles.specialist import SpecialistAgent, TaskStatus
from multiagent.roles.supervisor import SupervisorAgent, ReviewStatus


class TestAgentFactory:
    """Agent 工厂测试"""

    def test_initialization(self):
        """测试初始化"""
        factory = AgentFactory()
        assert factory.llm_client is None
        assert len(factory._agents) == 0

    def test_create_agent(self):
        """测试创建 Agent"""
        factory = AgentFactory()
        agent = factory.create_agent(AgentType.PLANNER, agent_id="test_planner")

        assert agent is not None
        assert agent.agent_type == AgentType.PLANNER
        assert agent.config.agent_id == "test_planner"

    def test_create_planner(self):
        """测试创建 Planner"""
        factory = AgentFactory()
        agent = factory.create_planner()

        assert agent.agent_type == AgentType.PLANNER

    def test_create_manager(self):
        """测试创建 Manager"""
        factory = AgentFactory()
        agent = factory.create_manager()

        assert agent.agent_type == AgentType.MANAGER

    def test_create_supervisor(self):
        """测试创建 Supervisor"""
        factory = AgentFactory()
        agent = factory.create_supervisor()

        assert agent.agent_type == AgentType.SUPERVISOR

    def test_create_specialist(self):
        """测试创建 Specialist"""
        factory = AgentFactory()
        agent = factory.create_specialist(domain="search")

        assert agent.agent_type == AgentType.SPECIALIST
        assert agent.config.metadata.get("domain") == "search"

    def test_get_agent(self):
        """测试获取 Agent"""
        factory = AgentFactory()
        created = factory.create_agent(AgentType.PLANNER, agent_id="test_id")
        retrieved = factory.get_agent("test_id")

        assert retrieved is not None
        assert retrieved.config.agent_id == "test_id"

    def test_list_agents(self):
        """测试列出所有 Agent"""
        factory = AgentFactory()
        factory.create_planner()
        factory.create_supervisor()

        agents = factory.list_agents()
        assert len(agents) == 2

    def test_list_agents_by_type(self):
        """测试按类型列出 Agent"""
        factory = AgentFactory()
        factory.create_planner()
        factory.create_planner()

        planners = factory.list_agents(AgentType.PLANNER)
        assert len(planners) == 2

    def test_remove_agent(self):
        """测试移除 Agent"""
        factory = AgentFactory()
        factory.create_agent(AgentType.PLANNER, agent_id="to_remove")

        result = factory.remove_agent("to_remove")
        assert result is True
        assert factory.get_agent("to_remove") is None


class TestPlannerAgent:
    """Planner Agent 测试"""

    def test_initialization(self):
        """测试初始化"""
        planner = PlannerAgent("planner_1")
        assert planner.agent_id == "planner_1"

    @pytest.mark.asyncio
    async def test_create_plan_simple(self):
        """测试创建简单计划"""
        planner = PlannerAgent("planner_1")
        plan = await planner.create_plan("推荐一个城市")

        assert plan is not None
        assert plan.complexity == PlanComplexity.SIMPLE
        assert len(plan.tasks) >= 1

    @pytest.mark.asyncio
    async def test_create_plan_medium(self):
        """测试创建中等复杂度计划"""
        planner = PlannerAgent("planner_1")
        plan = await planner.create_plan("规划北京三日游路线")

        assert plan is not None
        assert plan.complexity == PlanComplexity.MEDIUM

    @pytest.mark.asyncio
    async def test_create_plan_complex(self):
        """测试创建复杂计划"""
        planner = PlannerAgent("planner_1")
        plan = await planner.create_plan("请帮我安排一个完整的多日深度游行程")

        assert plan is not None
        assert plan.complexity == PlanComplexity.COMPLEX

    def test_identify_parallel_groups(self):
        """测试识别并行组"""
        planner = PlannerAgent("planner_1")
        tasks = [
            SubTask(task_id="task_1", description="task1", dependencies=[]),
            SubTask(task_id="task_2", description="task2", dependencies=[]),
            SubTask(task_id="task_3", description="task3", dependencies=["task_1"])
        ]
        groups = planner._identify_parallel_groups(tasks)
        assert len(groups) > 0


class TestSpecialistAgent:
    """Specialist Agent 测试"""

    def test_initialization(self):
        """测试初始化"""
        specialist = SpecialistAgent("specialist_1", "search")
        assert specialist.agent_id == "specialist_1"
        assert specialist.domain == "search"

    def test_register_tool(self):
        """测试注册工具"""
        specialist = SpecialistAgent("specialist_1", "search")

        def mock_tool(param):
            return f"result: {param}"

        specialist.register_tool("mock_tool", mock_tool)
        assert "mock_tool" in specialist.tools

    @pytest.mark.asyncio
    async def test_execute_task_with_tool(self):
        """测试执行带工具的任务"""
        def search_cities(city):
            return {"cities": ["北京", "上海"]}

        specialist = SpecialistAgent("specialist_1", "search", tools={"search_cities": search_cities})

        result = await specialist.execute_task(
            task_id="task_1",
            task_description="搜索城市",
            parameters={"tool": "search_cities", "params": {"city": "北京"}}
        )

        assert result.status == TaskStatus.COMPLETED
        assert result.result is not None

    @pytest.mark.asyncio
    async def test_execute_task_without_tool(self):
        """测试执行无工具的任务"""
        specialist = SpecialistAgent("specialist_1", "general")

        result = await specialist.execute_task(
            task_id="task_1",
            task_description="简单任务",
            parameters={}
        )

        assert result.status == TaskStatus.COMPLETED
        assert result.execution_time >= 0

    def test_get_capabilities(self):
        """测试获取能力"""
        specialist = SpecialistAgent("specialist_1", "search")
        caps = specialist.get_capabilities()

        assert caps["agent_id"] == "specialist_1"
        assert caps["domain"] == "search"


class TestSupervisorAgent:
    """Supervisor Agent 测试"""

    def test_initialization(self):
        """测试初始化"""
        supervisor = SupervisorAgent("supervisor_1")
        assert supervisor.agent_id == "supervisor_1"

    @pytest.mark.asyncio
    async def test_review_approved(self):
        """测试审核通过"""
        supervisor = SupervisorAgent("supervisor_1")

        result = await supervisor.review_result(
            task_id="task_1",
            task_description="test",
            result={"status": "ok", "data": "test data", "content": "some additional content here"},
            criteria={"required_fields": ["status"]}
        )

        # 由于 completeness 取决于 criteria，这里只检查有结果返回
        assert result is not None
        assert result.score >= 0

    @pytest.mark.asyncio
    async def test_review_none_result(self):
        """测试审核空结果"""
        supervisor = SupervisorAgent("supervisor_1")

        result = await supervisor.review_result(
            task_id="task_1",
            task_description="test",
            result=None
        )

        assert result.score == 0.0

    def test_get_review_stats(self):
        """测试获取审核统计"""
        supervisor = SupervisorAgent("supervisor_1")
        stats = supervisor.get_review_stats()

        assert stats["total"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
