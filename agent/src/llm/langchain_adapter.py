"""
================================================================================
LangChain LLM 适配器
================================================================================

将现有的 LLM 配置适配到 LangChain 框架。

支持的 Provider:
- openai: OpenAI API
- openai-compatible: 兼容 OpenAI 的 API（如硅基流动、zhiercourse 等）
- anthropic: Anthropic Claude API
- anthropic-compatible: 兼容 Anthropic 的 API（如 MiniMax）

使用示例:
```python
from llm.langchain_adapter import create_langchain_llm

# 从现有配置创建
llm = create_langchain_llm({
    "provider": "openai-compatible",
    "model": "gpt-4o-mini",
    "api_base": "https://api.zhiercourse.com/v1",
    "api_key": "sk-..."
})

# 同步调用
response = llm.invoke([HumanMessage(content="你好")])

# 流式调用
for chunk in llm.stream([HumanMessage(content="你好")]):
    print(chunk.content)
```

================================================================================
"""

import os
from typing import Optional, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

# LangChain 0.3+ imports
try:
    from langchain.chat_models.base import BaseChatModel
except ImportError:
    from langchain_core.chat_models import BaseChatModel

from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun

# LangChain 模型
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None


class LangChainLLMAdapter:
    """
    LangChain LLM 适配器

    将现有配置转换为 LangChain 的 ChatModel。
    支持多种 provider，保留现有的配置结构。
    """

    def __init__(self, config: dict):
        """
        初始化适配器

        Args:
            config: LLM 配置字典，应包含:
                - provider: 提供商类型
                - model: 模型名称
                - api_key: API 密钥
                - api_base: API 基础 URL
                - temperature: 温度参数
                - max_tokens: 最大 token 数
                - timeout: 超时时间
        """
        self.config = config
        self._chat_model = self._create_chat_model()

    def _create_chat_model(self) -> BaseChatModel:
        """根据配置创建 ChatModel 实例"""
        provider = self.config.get('provider', 'openai-compatible')
        model = self.config.get('model', 'gpt-4o-mini')
        api_key = self.config.get('api_key', '')
        api_base = self.config.get('api_base', '')
        temperature = self.config.get('temperature', 0.7)
        max_tokens = self.config.get('max_tokens', 2000)
        timeout = self.config.get('timeout', 60)

        # 构建通用参数
        common_kwargs = {
            'model': model,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'timeout': timeout,
        }

        # 添加 API 密钥（如果提供）
        if api_key:
            common_kwargs['api_key'] = api_key

        if provider == 'openai':
            # 标准 OpenAI
            if ChatOpenAI is None:
                raise ImportError("langchain-openai not installed")
            return ChatOpenAI(**common_kwargs)

        elif provider == 'openai-compatible':
            # 兼容 OpenAI 的 API（如硅基流动、zhiercourse 等）
            if ChatOpenAI is None:
                raise ImportError("langchain-openai not installed")
            if api_base:
                common_kwargs['base_url'] = api_base
            return ChatOpenAI(**common_kwargs)

        elif provider == 'anthropic':
            # Anthropic Claude
            if ChatAnthropic is None:
                raise ImportError("langchain-anthropic not installed")
            # Anthropic 使用不同的参数名
            anthropic_kwargs = {
                'model': model.replace('claude-', 'claude-'),
                'anthropic_api_key': api_key,
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            if api_base:
                anthropic_kwargs['base_url'] = api_base
            return ChatAnthropic(**anthropic_kwargs)

        elif provider == 'anthropic-compatible':
            # 兼容 Anthropic 的 API（如 MiniMax）
            if ChatAnthropic is None:
                raise ImportError("langchain-anthropic not installed")
            anthropic_kwargs = {
                'model': model,
                'anthropic_api_key': api_key,
                'base_url': api_base,
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            return ChatAnthropic(**anthropic_kwargs)

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    @property
    def chat_model(self) -> BaseChatModel:
        """获取 ChatModel 实例"""
        return self._chat_model

    def invoke(self, messages: list[BaseMessage], **kwargs) -> BaseMessage:
        """
        同步调用 LLM

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            AI 响应消息
        """
        return self._chat_model.invoke(messages, **kwargs)

    def stream(self, messages: list[BaseMessage], **kwargs):
        """
        流式调用 LLM

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Yields:
            响应块
        """
        return self._chat_model.stream(messages, **kwargs)

    async def ainvoke(self, messages: list[BaseMessage], **kwargs) -> BaseMessage:
        """
        异步调用 LLM

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            AI 响应消息
        """
        return await self._chat_model.ainvoke(messages, **kwargs)

    async def astream(self, messages: list[BaseMessage], **kwargs):
        """
        异步流式调用 LLM

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Yields:
            响应块
        """
        async for chunk in self._chat_model.astream(messages, **kwargs):
            yield chunk


def create_langchain_llm(config: dict) -> LangChainLLMAdapter:
    """
    工厂函数：创建 LangChain LLM 适配器

    Args:
        config: LLM 配置

    Returns:
        LangChainLLMAdapter 实例
    """
    return LangChainLLMAdapter(config)


def create_from_yaml_config(config_path: str) -> LangChainLLMAdapter:
    """
    从 YAML 配置文件创建适配器

    Args:
        config_path: 配置文件路径

    Returns:
        LangChainLLMAdapter 实例
    """
    import yaml
    from pathlib import Path

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)

    # 获取默认模型配置
    default_model = config_data.get('default_model', 'gpt-4o-mini')
    model_config = config_data.get('models', {}).get(default_model, {})

    if not model_config:
        raise ValueError(f"Model config not found for: {default_model}")

    return create_langchain_llm(model_config)
