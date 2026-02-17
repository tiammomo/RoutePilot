"""
================================================================================
基础设施层 - Prompt 模板管理 (Prompt Manager)

提供 Prompt 模板的集中管理、版本控制、变量替换和动态生成功能。

功能特点:
- 模板集中管理
- 变量替换支持
- 模板版本控制
- 模板继承和组合
- 动态 Prompt 生成

使用示例:
```python
from infrastructure.prompt_manager import PromptManager, PromptTemplate

manager = PromptManager()
manager.load_from_dict("travel_agent", {...})
prompt = manager.render("travel_agent", {"city": "北京"})
```

================================================================================
"""

import re
import json
import hashlib
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptType(Enum):
    """Prompt 类型"""
    SYSTEM = "system"       # 系统提示词
    USER = "user"          # 用户提示词
    ASSISTANT = "assistant" # 助手提示词
    FEWSHOT = "fewshot"    # 示例提示词


@dataclass
class PromptTemplate:
    """Prompt 模板"""
    name: str
    template: str
    type: PromptType = PromptType.USER
    version: str = "1.0.0"
    description: str = ""
    variables: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def render(self, variables: Dict[str, Any] = None) -> str:
        """
        渲染模板

        Args:
            variables: 变量映射

        Returns:
            str: 渲染后的 Prompt
        """
        if not variables:
            variables = {}

        result = self.template

        # 替换变量 {{variable}}
        pattern = r'\{\{(\w+)\}\}'

        def replace(match):
            var_name = match.group(1)
            # 先检查传入的变量
            if var_name in variables:
                value = variables[var_name]
                # 如果是列表或字典，转为 JSON
                if isinstance(value, (list, dict)):
                    return json.dumps(value, ensure_ascii=False)
                return str(value)
            # 检查模板定义的默认值
            if var_name in self.variables:
                return self.variables[var_name]
            # 保留原样
            return match.group(0)

        result = re.sub(pattern, replace, result)

        # 清理多余空白
        result = self._clean_whitespace(result)

        return result

    def _clean_whitespace(self, text: str) -> str:
        """清理空白"""
        # 合并多行空白
        lines = [line.strip() for line in text.split('\n')]
        # 过滤空行
        lines = [line for line in lines if line]
        return '\n'.join(lines)

    def get_hash(self) -> str:
        """获取模板哈希"""
        content = f"{self.name}:{self.template}:{self.version}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "template": self.template,
            "type": self.type.value,
            "version": self.version,
            "description": self.description,
            "variables": self.variables,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PromptTemplate':
        """从字典创建"""
        return cls(
            name=data['name'],
            template=data['template'],
            type=PromptType(data.get('type', 'user')),
            version=data.get('version', '1.0.0'),
            description=data.get('description', ''),
            variables=data.get('variables', {}),
            metadata=data.get('metadata', {}),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat())
        )


@dataclass
class PromptChain:
    """Prompt 链"""
    name: str
    templates: List[PromptTemplate]
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, variables: Dict[str, Any] = None) -> List[Dict[str, str]]:
        """
        渲染整个链

        Args:
            variables: 全局变量

        Returns:
            List[Dict]: 消息列表
        """
        if variables is None:
            variables = {}

        messages = []
        for template in self.templates:
            # 合并全局变量和模板局部变量
            merged_vars = {**variables, **(template.metadata.get('local_vars', {}))}
            content = template.render(merged_vars)
            messages.append({
                "role": template.type.value,
                "content": content
            })
        return messages

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "templates": [t.to_dict() for t in self.templates],
            "description": self.description,
            "metadata": self.metadata
        }


class PromptManager:
    """
    Prompt 模板管理器

    提供模板的加载、存储、渲染和版本管理功能。
    """

    def __init__(self):
        """初始化管理器"""
        self._templates: Dict[str, PromptTemplate] = {}
        self._chains: Dict[str, PromptChain] = {}
        self._template_groups: Dict[str, List[str]] = {}  # 组名 -> 模板名列表
        self._custom_functions: Dict[str, Callable] = {}

        # 加载内置模板
        self._load_builtin_templates()

        logger.info("[PromptManager] 初始化完成")

    def _load_builtin_templates(self) -> None:
        """加载内置模板"""
        # 旅游 Agent 系统提示词
        self.add(PromptTemplate(
            name="travel_agent_system",
            type=PromptType.SYSTEM,
            template="""你是一个专业的旅游助手，帮助用户规划旅行、推荐景点、计算预算。

你的主要职责:
1. 根据用户需求推荐合适的目的地
2. 提供详细的景点信息和旅行建议
3. 计算旅行预算和时间安排
4. 生成实用的旅行攻略

请始终用友好、专业的方式回答用户问题。""",
            description="旅游 Agent 系统提示词"
        ))

        # 思考提示词
        self.add(PromptTemplate(
            name="travel_thought",
            type=PromptType.SYSTEM,
            template="""请分析用户需求，确定下一步行动。

用户输入: {{query}}
历史上下文: {{history}}

请输出JSON格式:
{
    "thought": "你的思考过程",
    "next_action": "决定调用的工具名称，不需要则返回null",
    "parameters": {"tool_name": {"参数": "值"}}
}""",
            description="思考提示词"
        ))

        # 城市推荐提示词
        self.add(PromptTemplate(
            name="city_recommendation",
            type=PromptType.USER,
            template="""用户需求: {{user_query}}
可选城市: {{available_cities}}
用户偏好: {{preferences}}

请根据用户需求推荐最合适的城市，只返回JSON:
{
    "cities": ["推荐的城市名"],
    "reasons": ["推荐理由"]
}""",
            description="城市推荐提示词"
        ))

        # 路线规划提示词
        self.add(PromptTemplate(
            name="route_planning",
            type=PromptType.USER,
            template="""目的地: {{city}}
天数: {{days}}
偏好: {{preferences}}
可用景点: {{attractions}}

请生成详细的每日行程安排，返回JSON:
{
    "daily_plan": [
        {
            "day": 1,
            "morning": "上午活动",
            "afternoon": "下午活动",
            "evening": "晚上活动"
        }
    ],
    "tips": ["实用建议"]
}""",
            description="路线规划提示词"
        ))

        # 预算计算提示词
        self.add(PromptTemplate(
            name="budget_calculation",
            type=PromptType.USER,
            template="""城市: {{city}}
天数: {{days}}
人数: {{travelers}}
预算范围: {{budget_range}}

请计算预计花费，返回JSON:
{
    "total_budget": 总金额,
    "breakdown": {
        "accommodation": 住宿费,
        "food": 餐饮费,
        "transportation": 交通费,
        "tickets": 门票费,
        "other": 其他费用
    },
    "tips": ["省钱建议"]
}""",
            description="预算计算提示词"
        ))

    def add(self, template: PromptTemplate) -> None:
        """
        添加模板

        Args:
            template: Prompt 模板
        """
        self._templates[template.name] = template

    def get(self, name: str) -> Optional[PromptTemplate]:
        """
        获取模板

        Args:
            name: 模板名称

        Returns:
            PromptTemplate: 模板，不存在返回 None
        """
        return self._templates.get(name)

    def render(
        self,
        name: str,
        variables: Dict[str, Any] = None
    ) -> str:
        """
        渲染模板

        Args:
            name: 模板名称
            variables: 变量映射

        Returns:
            str: 渲染后的 Prompt

        Raises:
            KeyError: 模板不存在
        """
        template = self.get(name)
        if template is None:
            raise KeyError(f"模板不存在: {name}")
        return template.render(variables)

    def render_chain(
        self,
        chain_name: str,
        variables: Dict[str, Any] = None
    ) -> List[Dict[str, str]]:
        """
        渲染 Prompt 链

        Args:
            chain_name: 链名称
            variables: 变量映射

        Returns:
            List[Dict]: 消息列表
        """
        chain = self._chains.get(chain_name)
        if chain is None:
            raise KeyError(f"Prompt 链不存在: {chain_name}")
        return chain.render(variables)

    def add_chain(self, chain: PromptChain) -> None:
        """
        添加 Prompt 链

        Args:
            chain: Prompt 链
        """
        self._chains[chain.name] = chain

    def load_from_dict(self, group_name: str, templates: Dict[str, Any]) -> None:
        """
        从字典加载模板

        Args:
            group_name: 组名称
            templates: 模板字典
        """
        if group_name not in self._template_groups:
            self._template_groups[group_name] = []

        for name, data in templates.items():
            if isinstance(data, str):
                # 简化格式: name -> template
                template = PromptTemplate(
                    name=name,
                    template=data
                )
            else:
                # 完整格式
                template = PromptTemplate.from_dict(data)

            self.add(template)
            self._template_groups[group_name].append(name)

        logger.info(f"[PromptManager] 加载模板组 {group_name}: {len(templates)} 个模板")

    def load_from_file(self, file_path: str) -> None:
        """
        从文件加载模板

        Args:
            file_path: 文件路径
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"模板文件不存在: {file_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        group_name = path.stem
        self.load_from_dict(group_name, data)

    def list_templates(self, group: Optional[str] = None) -> List[str]:
        """
        列出模板

        Args:
            group: 可选的组名称

        Returns:
            List[str]: 模板名称列表
        """
        if group:
            return self._template_groups.get(group, [])
        return list(self._templates.keys())

    def list_groups(self) -> List[str]:
        """列出所有组"""
        return list(self._template_groups.keys())

    def remove(self, name: str) -> bool:
        """
        删除模板

        Args:
            name: 模板名称

        Returns:
            bool: 是否成功删除
        """
        if name in self._templates:
            del self._templates[name]
            # 从组中移除
            for group, templates in self._template_groups.items():
                if name in templates:
                    templates.remove(name)
            return True
        return False

    def clear(self, group: Optional[str] = None) -> int:
        """
        清空模板

        Args:
            group: 可选的组名称，None 则清空所有

        Returns:
            int: 删除的模板数量
        """
        if group:
            names = self._template_groups.get(group, [])
            for name in names:
                if name in self._templates:
                    del self._templates[name]
            del self._template_groups[group]
            return len(names)
        else:
            count = len(self._templates)
            self._templates.clear()
            self._chains.clear()
            self._template_groups.clear()
            return count

    def export(self, group: Optional[str] = None) -> Dict[str, Any]:
        """
        导出模板

        Args:
            group: 可选的组名称

        Returns:
            Dict: 模板字典
        """
        if group:
            names = self._template_groups.get(group, [])
            return {name: self._templates[name].to_dict() for name in names}
        return {name: template.to_dict() for name, template in self._templates.items()}

    def register_function(self, name: str, func: Callable) -> None:
        """
        注册自定义函数

        Args:
            name: 函数名称
            func: 函数对象
        """
        self._custom_functions[name] = func

    def get_registered_functions(self) -> Dict[str, Callable]:
        """获取已注册的函数"""
        return self._custom_functions.copy()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "template_count": len(self._templates),
            "chain_count": len(self._chains),
            "group_count": len(self._template_groups),
            "custom_functions": len(self._custom_functions)
        }


class DynamicPrompt:
    """
    动态 Prompt 生成器

    根据上下文动态调整 Prompt 内容。
    """

    def __init__(self, prompt_manager: PromptManager = None):
        """
        初始化

        Args:
            prompt_manager: Prompt 管理器
        """
        self.prompt_manager = prompt_manager or PromptManager()

    def adapt_for_sentiment(
        self,
        base_template: str,
        sentiment: str,
        **variables
    ) -> str:
        """
        根据情感调整 Prompt

        Args:
            base_template: 基础模板名
            sentiment: 情感 (positive/negative/neutral)
            **variables: 变量

        Returns:
            str: 调整后的 Prompt
        """
        # 获取基础模板
        template = self.prompt_manager.get(base_template)
        if template is None:
            return base_template

        # 根据情感添加前缀
        sentiment_prefixes = {
            "positive": "用户很期待这次旅行，请用热情的语气回答。\n\n",
            "negative": "用户可能有些顾虑，请耐心解答。\n\n",
            "neutral": "请客观、专业地回答用户问题。\n\n"
        }

        prefix = sentiment_prefixes.get(sentiment, "")
        base_content = template.render(variables)

        return prefix + base_content

    def adapt_for_complexity(
        self,
        base_template: str,
        complexity: str,
        **variables
    ) -> str:
        """
        根据问题复杂度调整 Prompt

        Args:
            base_template: 基础模板名
            complexity: 复杂度 (simple/moderate/complex)
            **variables: 变量

        Returns:
            str: 调整后的 Prompt
        """
        template = self.prompt_manager.get(base_template)
        if template is None:
            return base_template

        base_content = template.render(variables)

        # 根据复杂度添加指令
        complexity_instructions = {
            "simple": "请简洁明了地回答。",
            "moderate": "请提供适度的详细信息。",
            "complex": "请提供详细的解释和分析。"
        }

        instruction = complexity_instructions.get(complexity, "")
        if instruction:
            base_content += f"\n\n{instruction}"

        return base_content

    def merge_contexts(
        self,
        templates: List[str],
        variables: Dict[str, Any] = None,
        separator: str = "\n\n"
    ) -> str:
        """
        合并多个模板上下文

        Args:
            templates: 模板名列表
            variables: 变量
            separator: 分隔符

        Returns:
            str: 合并后的内容
        """
        if not templates:
            return ""

        contents = []
        for name in templates:
            template = self.prompt_manager.get(name)
            if template:
                contents.append(template.render(variables or {}))

        return separator.join(contents)


# 全局 Prompt 管理器实例
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """获取全局 Prompt 管理器"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def create_prompt_manager(
    templates: Dict[str, Any] = None,
    template_file: str = None
) -> PromptManager:
    """
    创建 Prompt 管理器

    Args:
        templates: 模板字典
        template_file: 模板文件路径

    Returns:
        PromptManager: 管理器实例
    """
    manager = PromptManager()

    if templates:
        manager.load_from_dict("custom", templates)

    if template_file:
        manager.load_from_file(template_file)

    return manager
