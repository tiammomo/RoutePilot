"""
多协议大模型调用模块 (Multi-Protocol LLM Client)

本模块提供统一的LLM客户端接口，支持多种协议和模型提供商。
采用适配器模式设计，通过不同的协议适配器来适配OpenAI、Anthropic、Google、Ollama等协议。

主要组件:
- LLMProtocolAdapter: 协议适配器抽象基类，定义了统一的接口
- OpenAIAdapter: OpenAI API协议适配器
- AnthropicAdapter: Anthropic Claude API协议适配器
- GoogleAdapter: Google Gemini API协议适配器
- OllamaAdapter: Ollama本地模型适配器
- LLMClient: 统一的LLM客户端封装
- LLMClientFactory: LLM客户端工厂类

功能特点:
- 支持同步和流式两种调用方式
- 自动重试机制，网络错误时指数退避
- 统一的响应格式，包含成功状态、内容、token使用量等信息
- 专门针对旅游场景的推荐和路线规划方法

使用示例:
    from llm.client import LLMClientFactory

    # 通过配置创建客户端
    config = {"provider": "openai", "model": "gpt-4", "api_key": "..."}
    client = LLMClientFactory.create_adapter(config)

    # 同步调用
    response = client.chat([{"role": "user", "content": "你好"}])

    # 流式调用
    for chunk in client.chat_stream([{"role": "user", "content": "你好"}]):
        print(chunk, end="", flush=True)
"""

import json
import time
import logging
from abc import ABC, abstractmethod  # 抽象基类用于定义接口协议
from typing import Dict, Any, List, Optional, Iterator

logger = logging.getLogger(__name__)
import urllib.request
import urllib.error
from enum import Enum


class ProtocolType(Enum):
    """
    支持的LLM协议类型枚举

    定义了系统支持的所有大模型协议类型，每种类型对应不同的API接口规范。
    - OPENAI: OpenAI官方API协议
    - ANTHROPIC: Anthropic Claude API协议
    - GOOGLE: Google Gemini API协议
    - OLLAMA: Ollama本地模型协议
    - OPENAI_COMPATIBLE: 兼容OpenAI API协议的通用接口
    """
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai-compatible"


class LLMProtocolAdapter(ABC):
    """LLM协议适配器抽象基类"""

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', '')
        self.api_base = config.get('api_base', '')
        self.temperature = config.get('temperature', 0.7)
        self.max_tokens = config.get('max_tokens', 2000)
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('max_retries', 3)
        self.top_p = config.get('top_p', 1.0)
        self.frequency_penalty = config.get('frequency_penalty', 0.0)
        self.presence_penalty = config.get('presence_penalty', 0.0)
        # Embedding 配置
        self.embedding_dim = config.get('embedding_dim', 1536)
        self._init_protocol_specific(config)

    @abstractmethod
    def _init_protocol_specific(self, config: Dict[str, Any]):
        pass

    @abstractmethod
    def _build_request_payload(self, messages: List[Dict[str, str]],
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None,
                               stream: bool = False) -> Dict[str, Any]:
        pass

    @abstractmethod
    def _build_request_headers(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def _get_chat_endpoint(self) -> str:
        pass

    @abstractmethod
    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        pass

    @abstractmethod
    def _parse_response(self, response_data: Dict[str, Any]) -> str:
        pass

    def chat_stream(self, messages: List[Dict[str, str]],
                    temperature: Optional[float] = None,
                    max_tokens: Optional[int] = None) -> Iterator[str]:
        payload = self._build_request_payload(messages, temperature, max_tokens, stream=True)
        headers = self._build_request_headers()
        endpoint = self._get_chat_endpoint()

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    content = self._parse_stream_chunk(line)
                    if content:
                        yield content

        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8')
            yield f"\n\n[错误: HTTP {e.code} - {error_msg}]\n"
        except urllib.error.URLError as e:
            yield f"\n\n[错误: 网络连接失败 - {str(e.reason)}]\n"
        except Exception as e:
            yield f"\n\n[错误: {str(e)}]\n"

    def chat(self, messages: List[Dict[str, str]],
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None) -> Dict[str, Any]:
        # 验证消息列表
        if not messages or len(messages) == 0:
            logger.error("消息列表为空")
            return {"success": False, "error": "消息列表不能为空"}

        # 过滤掉空消息
        valid_messages = []
        for msg in messages:
            content = msg.get('content', '')
            if content and isinstance(content, str) and content.strip():
                valid_messages.append(msg)
            elif msg.get('role') == 'system':
                # system 消息即使为空也保留
                valid_messages.append(msg)

        if not valid_messages:
            logger.error("没有有效的消息内容")
            return {"success": False, "error": "消息内容不能为空"}

        payload = self._build_request_payload(valid_messages, temperature, max_tokens, stream=False)
        headers = self._build_request_headers()
        endpoint = self._get_chat_endpoint()

        for attempt in range(self.max_retries):
            try:
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')

                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                    content = self._parse_response(response_data)

                    return {
                        "success": True,
                        "content": content,
                        "usage": response_data.get('usage', {}),
                        "model": response_data.get('model', self.model)
                    }

            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')
                logger.warning(f"HTTP error (attempt {attempt + 1}/{self.max_retries}): {e.code} - {error_body}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return {"success": False, "error": f"HTTP {e.code}: {error_body}"}

            except urllib.error.URLError as e:
                logger.warning(f"Network error (attempt {attempt + 1}/{self.max_retries}): {str(e.reason)}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return {"success": False, "error": f"网络错误: {str(e.reason)}"}

            except Exception as e:
                logger.warning(f"Unknown error (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return {"success": False, "error": f"未知错误: {str(e)}"}

        return {"success": False, "error": "超过最大重试次数"}

    def embed(self, text: str) -> List[float]:
        """
        生成文本嵌入向量

        默认实现使用 OpenAI 兼容的 embedding API。
        子类可以重写此方法以支持其他 embedding 服务。

        Args:
            text: 输入文本

        Returns:
            List[float]: 嵌入向量
        """
        import numpy as np

        # 检查是否是 embedding 模型
        if hasattr(self, 'embedding_dim'):
            embedding_dim = getattr(self, 'embedding_dim', 1536)
        else:
            embedding_dim = 1536

        # 调用 embedding API
        try:
            payload = {
                "input": text,
                "model": self.model
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            endpoint = f"{self.api_base.rstrip('/')}/embeddings"

            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['embedding']
        except Exception as e:
            logger.warning(f"Embedding API 调用失败: {e}")

        # 如果失败，返回零向量
        return [0.0] * embedding_dim

    async def async_embed(self, text: str) -> List[float]:
        """
        异步生成文本嵌入向量

        Args:
            text: 输入文本

        Returns:
            List[float]: 嵌入向量
        """
        return self.embed(text)


class OpenAIAdapter(LLMProtocolAdapter):
    """OpenAI API协议适配器"""

    def _init_protocol_specific(self, config: Dict[str, Any]):
        if not self.api_base:
            self.api_base = "https://api.openai.com/v1"

    def _build_request_payload(self, messages: List[Dict[str, str]],
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None,
                               stream: bool = False) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": stream
        }

    def _build_request_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def _get_chat_endpoint(self) -> str:
        return f"{self.api_base.rstrip('/')}/chat/completions"

    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        if not line.startswith('data: '):
            return None
        data_str = line[6:].strip()
        if data_str == '[DONE]':
            return None
        try:
            chunk = json.loads(data_str)
            delta = chunk.get('choices', [{}])[0].get('delta', {})
            content = delta.get('content', '')
            return content if content else None
        except json.JSONDecodeError:
            return None

    def _parse_response(self, response_data: Dict[str, Any]) -> str:
        return response_data['choices'][0]['message']['content']


class AnthropicAdapter(LLMProtocolAdapter):
    """Anthropic Claude API协议适配器"""

    def _init_protocol_specific(self, config: Dict[str, Any]):
        if not self.api_base:
            self.api_base = "https://api.anthropic.com/v1"
        # MiniMax API 使用较新的 API 版本
        self.api_version = config.get('api_version', '2024-01-04')

    def _build_request_payload(self, messages: List[Dict[str, str]],
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None,
                               stream: bool = False) -> Dict[str, Any]:
        system_message = None
        other_messages = []
        for msg in messages:
            if msg.get('role') == 'system':
                system_message = msg.get('content', '')
            else:
                other_messages.append(msg)

        payload = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": other_messages,
            "stream": stream
        }
        if system_message:
            payload["system"] = system_message
        return payload

    def _build_request_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version
        }

    def _get_chat_endpoint(self) -> str:
        return f"{self.api_base.rstrip('/')}/messages"

    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        # SSE 格式: event: <type> 和 data: <json> 分开
        if not line.startswith('data: '):
            return None
        data_str = line[6:].strip()
        try:
            chunk = json.loads(data_str)
            event_type = chunk.get('type', '')

            # 处理 text_delta
            if event_type == 'content_block_delta':
                delta = chunk.get('delta', {})
                if delta.get('type') == 'text_delta':
                    return delta.get('text', '')

            # 处理 thinking_delta
            if event_type == 'content_block_delta':
                delta = chunk.get('delta', {})
                if delta.get('type') == 'thinking_delta':
                    return delta.get('thinking', '')
        except json.JSONDecodeError:
            pass
        return None

    def chat_stream(self, messages: List[Dict[str, str]],
                    temperature: Optional[float] = None,
                    max_tokens: Optional[int] = None) -> Iterator[str]:
        """流式聊天 - 支持 SSE 格式"""
        payload = self._build_request_payload(messages, temperature, max_tokens, stream=True)
        headers = self._build_request_headers()
        endpoint = self._get_chat_endpoint()

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                current_event_data = ""

                for line in response:
                    line = line.decode('utf-8').strip()

                    # 空行分隔事件
                    if not line:
                        if current_event_data:
                            content = self._parse_stream_chunk(current_event_data)
                            if content:
                                yield content
                            current_event_data = ""
                        continue

                    # SSE 格式解析
                    if line.startswith('data: '):
                        current_event_data = line
                    elif line.startswith('event: '):
                        # 如果有之前的事件数据，先处理它
                        if current_event_data:
                            content = self._parse_stream_chunk(current_event_data)
                            if content:
                                yield content
                            current_event_data = ""
                        # 开始新的事件
                        current_event_data = line  # 保留 event 行用于调试

        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8')
            yield f"\n\n[错误: HTTP {e.code} - {error_msg}]\n"
        except urllib.error.URLError as e:
            yield f"\n\n[错误: 网络连接失败 - {str(e.reason)}]\n"
        except Exception as e:
            yield f"\n\n[错误: {str(e)}]\n"

    def _parse_response(self, response_data: Dict[str, Any]) -> str:
        # 记录原始响应用于调试
        logger.debug(f"AnthropicAdapter 原始响应: {response_data}")

        # 获取 content blocks
        content_blocks = response_data.get('content', [])
        if not content_blocks:
            # 尝试从其他字段获取内容
            if 'text' in response_data:
                return response_data.get('text', '')
            if 'message' in response_data:
                return response_data.get('message', {}).get('content', '')
            logger.warning("响应中没有 content 字段")
            return ''

        result_parts = []

        for block in content_blocks:
            if not isinstance(block, dict):
                continue

            block_type = block.get('type', '')
            if block_type == 'text':
                text_content = block.get('text', '')
                if text_content:
                    result_parts.append(text_content)
            elif block_type == 'thinking':
                # 包含 thinking 内容
                thinking = block.get('thinking', '')
                if thinking:
                    result_parts.append(f"[思考: {thinking}]")

        result = ''.join(result_parts)

        if not result:
            logger.warning(f"解析后的内容为空，原始响应: {response_data}")

        return result


class GoogleAdapter(LLMProtocolAdapter):
    """Google Gemini API协议适配器"""

    def _init_protocol_specific(self, config: Dict[str, Any]):
        if not self.api_base:
            self.api_base = "https://generativelanguage.googleapis.com/v1beta/openai"

    def _build_request_payload(self, messages: List[Dict[str, str]],
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None,
                               stream: bool = False) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "top_p": self.top_p,
            "stream": stream
        }

    def _build_request_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def _get_chat_endpoint(self) -> str:
        return f"{self.api_base.rstrip('/')}/chat/completions"

    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        if not line.startswith('data: '):
            return None
        data_str = line[6:].strip()
        if data_str == '[DONE]':
            return None
        try:
            chunk = json.loads(data_str)
            delta = chunk.get('choices', [{}])[0].get('delta', {})
            content = delta.get('content', '')
            return content if content else None
        except json.JSONDecodeError:
            return None

    def _parse_response(self, response_data: Dict[str, Any]) -> str:
        return response_data['choices'][0]['message']['content']


class OpenAICompatibleAdapter(LLMProtocolAdapter):
    """通用OpenAI兼容协议适配器"""

    def _init_protocol_specific(self, config: Dict[str, Any]):
        if not self.api_base:
            raise ValueError("OpenAI兼容协议必须提供api_base参数")

    def _build_request_payload(self, messages: List[Dict[str, str]],
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None,
                               stream: bool = False) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "top_p": self.top_p,
            "stream": stream
        }

    def _build_request_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_chat_endpoint(self) -> str:
        return f"{self.api_base.rstrip('/')}/chat/completions"

    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        if not line.startswith('data: '):
            return None
        data_str = line[6:].strip()
        if data_str == '[DONE]':
            return None
        try:
            chunk = json.loads(data_str)
            delta = chunk.get('choices', [{}])[0].get('delta', {})
            content = delta.get('content', '')
            return content if content else None
        except json.JSONDecodeError:
            return None

    def _parse_response(self, response_data: Dict[str, Any]) -> str:
        return response_data['choices'][0]['message']['content']


class OllamaAdapter(OpenAICompatibleAdapter):
    """Ollama 本地模型适配器"""

    def _init_protocol_specific(self, config: Dict[str, Any]):
        if not self.api_base:
            self.api_base = "http://localhost:11434/v1"
        # Ollama 不需要 API Key
        self.api_key = ""


class LLMClientFactory:
    """LLM客户端工厂"""

    _ADAPTERS = {
        ProtocolType.OPENAI.value: OpenAIAdapter,
        ProtocolType.ANTHROPIC.value: AnthropicAdapter,
        ProtocolType.GOOGLE.value: GoogleAdapter,
        ProtocolType.OLLAMA.value: OllamaAdapter,
        ProtocolType.OPENAI_COMPATIBLE.value: OpenAICompatibleAdapter,
    }

    # 协议类型别名映射
    _PROVIDER_ALIASES = {
        "openai-compatible": "openai-compatible",
        "compatible": "openai-compatible",
        "local": "openai-compatible",
    }

    @staticmethod
    def create_adapter(config: Dict[str, Any]) -> LLMProtocolAdapter:
        # 支持 'provider'（YAML配置）和 'provider_type' 两种配置键
        provider_type = config.get('provider', config.get('provider_type', ProtocolType.OPENAI.value))
        provider_type = provider_type.lower()

        # 处理协议类型别名
        if provider_type in LLMClientFactory._PROVIDER_ALIASES:
            provider_type = LLMClientFactory._PROVIDER_ALIASES[provider_type]

        if provider_type not in LLMClientFactory._ADAPTERS:
            raise ValueError(
                f"不支持的协议类型: {provider_type}\n"
                f"支持的类型: {', '.join(LLMClientFactory._ADAPTERS.keys())}"
            )

        adapter_class = LLMClientFactory._ADAPTERS[provider_type]
        return adapter_class(config)

    @staticmethod
    def get_supported_protocols() -> List[str]:
        return list(LLMClientFactory._ADAPTERS.keys())

    @staticmethod
    def create_from_config_manager(config_manager) -> 'LLMClient':
        """从 ConfigManager 创建 LLMClient（使用默认模型）"""
        model_config = config_manager.get_default_model_config()
        return LLMClient(model_config)

    @staticmethod
    def create_by_model_id(config_manager, model_id: str) -> 'LLMClient':
        """从 ConfigManager 创建指定模型的 LLMClient"""
        model_config = config_manager.get_model_config(model_id)
        return LLMClient(model_config)


class LLMClient:
    """统一的LLM客户端"""

    def __init__(self, config: Dict[str, Any]):
        self.adapter = LLMClientFactory.create_adapter(config)
        self.config = config

    def chat_stream(self, messages: List[Dict[str, str]],
                    temperature: Optional[float] = None,
                    max_tokens: Optional[int] = None) -> Iterator[str]:
        return self.adapter.chat_stream(messages, temperature, max_tokens)

    def chat(self, messages: List[Dict[str, str]],
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None) -> Dict[str, Any]:
        return self.adapter.chat(messages, temperature, max_tokens)

    def generate_travel_recommendation(self, user_query: str,
                                       context: str,
                                       available_cities: List[str]) -> Dict[str, Any]:
        """生成旅游推荐"""
        system_prompt = f"""你是一个专业的旅游助手，负责根据用户需求推荐合适的旅游城市。

可推荐城市列表：{', '.join(available_cities)}

当前用户偏好：
{context}

请基于用户需求，从可推荐城市中选择3-5个最合适的城市，并以JSON格式返回：
{{
    "recommendations": [
        {{
            "city": "城市名",
            "reason": "推荐理由（50字以内）",
            "match_score": 90
        }}
    ],
    "explanation": "整体推荐说明（100字以内）"
}}

注意：
1. 只推荐列表中存在的城市
2. match_score为匹配度评分（0-100）
3. 推荐理由需结合用户偏好和城市特色
4. 按匹配度从高到低排序"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]

        response = self.chat(messages, temperature=0.7)

        if not response['success']:
            return response

        try:
            content = response['content']
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            recommendations = json.loads(content)
            response['recommendations'] = recommendations
            return response
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON解析失败: {str(e)}",
                "raw_content": response['content']
            }

    def generate_route_plan(self, city: str,
                           days: int,
                           attractions: List[Dict[str, Any]],
                           user_preference: str) -> Dict[str, Any]:
        """生成旅游路线规划"""
        attractions_info = "\n".join([
            f"- {a['name']}：{a['type']}，建议游玩{a['duration']}小时，门票{a['ticket']}元"
            for a in attractions
        ])

        system_prompt = f"""你是一个专业的旅游规划师，负责为用户制定详细的旅游路线。

目标城市：{city}
旅行天数：{days}天
可选景点：
{attractions_info}

用户偏好：
{user_preference}

请制定一个{days}天的详细旅游路线，以JSON格式返回：
{{
    "route_plan": [
        {{
            "day": 1,
            "attractions": ["景点1", "景点2"],
            "schedule": "上午游览景点1（3小时），下午游览景点2（4小时）",
            "tips": "建议事项"
        }}
    ],
    "total_cost_estimate": {{
        "tickets": 500,
        "meals": 300,
        "transportation": 200,
        "total": 1000
    }},
    "travel_tips": ["tip1", "tip2", "tip3"]
}}

注意：
1. 合理安排每天行程，避免过于紧凑
2. 考虑景点间的地理位置和交通时间
3. 提供实用的旅行建议
4. 估算各项费用"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"帮我规划{city}{days}天的旅游路线"}
        ]

        response = self.chat(messages, temperature=0.6)

        if not response['success']:
            return response

        try:
            content = response['content']
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            route_plan = json.loads(content)
            response['route_plan'] = route_plan
            return response
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON解析失败: {str(e)}",
                "raw_content": response['content']
            }
