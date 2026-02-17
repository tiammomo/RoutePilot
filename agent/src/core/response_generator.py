"""
================================================================================
响应生成器模块 (Response Generator)

提供旅游助手的回答生成和格式化功能。
支持多风格响应、JSON 解析、Markdown 格式化等功能。

功能模块：
1. 风格化提示词构建
2. JSON 响应解析
3. 旅游响应格式化
4. 文本分块处理

使用示例:
```python
from core.response_generator import ResponseGenerator

generator = ResponseGenerator(llm_client, style_manager)
answer = await generator.generate_answer(history, intent)
formatted = generator.format_travel_response(data)
```

================================================================================
"""

import json
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from llm.client import LLMClient
from core.style_config import style_manager, StyleConfig
from core.intent_recognizer import IntentResult, SentimentType

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    响应生成器

    负责根据工具执行结果和用户意图生成结构化、风格化的回答。

    功能：
    1. 根据风格配置构建系统提示词
    2. 解析 LLM 返回的 JSON 响应
    3. 将结构化数据格式化为 Markdown 文本
    4. 格式化景点响应数据
    """

    def __init__(self, llm_client: LLMClient):
        """
        初始化响应生成器

        Args:
            llm_client: LLM 客户端实例
        """
        self.llm_client = llm_client

    async def generate_answer(
        self,
        history: List[Dict],
        intent: IntentResult = None
    ) -> str:
        """
        使用 LLM 生成最终回答

        根据工具执行结果和用户意图，生成结构化、风格化的回答。

        Args:
            history: 执行历史列表
            intent: 意图识别结果（可选）

        Returns:
            str: 生成的回答文本
        """
        try:
            tool_results = []
            for step in history:
                action = step.get('action', {})
                if action.get('status') == 'SUCCESS' and action.get('result'):
                    tool_results.append({
                        'tool': action.get('tool_name', ''),
                        'result': action.get('result', {})
                    })

            # 获取风格配置
            if intent:
                # 安全获取 sentiment
                sentiment_value = intent.sentiment.value if hasattr(intent.sentiment, 'value') else str(intent.sentiment) if intent.sentiment else 'neutral'
                sentiment = SentimentType(sentiment_value) if sentiment_value in [e.value for e in SentimentType] else SentimentType.NEUTRAL
                style = style_manager.get_style_for_task(intent.intent.value, sentiment)
            else:
                style = style_manager.get_style_for_task("general_chat", SentimentType.NEUTRAL)

            # 根据风格调整温度
            temperature = style.temperature

            # 构建风格化的系统提示词
            system_prompt = self._build_style_prompt(style, intent)

            user_prompt = f"""我想要规划一次旅行，这是我的查询结果：
{json.dumps(tool_results, ensure_ascii=False, indent=2)}

请只输出JSON格式的结果，不要有任何其他内容。"""

            result = self.llm_client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=temperature)

            if result.get('success'):
                content = result.get('content', '')
                # 尝试解析JSON
                data = self._parse_json_response(content)
                if data:
                    return self._format_travel_response(data)
                return content
            return '处理完成'

        except Exception as e:
            logger.error(f"生成回答失败: {e}")
            return f'生成回答失败：{str(e)}'

    def _build_style_prompt(
        self,
        style: StyleConfig,
        intent: IntentResult = None
    ) -> str:
        """
        根据风格配置构建系统提示词

        Args:
            style: 风格配置
            intent: 意图识别结果

        Returns:
            str: 系统提示词
        """
        # 根据风格选择问候语和角色设定
        role_greetings = {
            "热情活泼": "你是一个超级热情、活泼的AI旅游小伙伴！",
            "温暖亲切": "你是一个贴心、温暖的AI旅游助手！",
            "专业正式": "你是一位专业、可靠的AI旅游顾问。",
            "俏皮可爱": "你是一个可爱又热情的旅行小达人！",
            "简洁明了": "你是一个简洁高效的AI旅游助手。"
        }

        role = role_greetings.get(style.name, "你是一个AI旅游助手")

        # 根据风格选择语气关键词
        tone_keywords = {
            "热情活泼": "使用轻松活泼的语气，多用口语化表达。适当使用emoji表情符号增添趣味。用'小伙伴'、'亲'、'哇塞'等亲切称呼。",
            "温暖亲切": "使用温柔亲切的语气，像朋友一样聊天。适当表达关心和理解。让对话氛围轻松愉快。",
            "专业正式": "使用专业、清晰的语言。提供准确、有用的信息。保持礼貌和专业的态度。",
            "俏皮可爱": "使用俏皮可爱的语气，可以适当用一些有趣的网络用语。多多使用可爱的emoji。",
            "简洁明了": "使用简洁、直接的语言。不说废话，直奔主题。高效率递信息。"
        }

        tone = tone_keywords.get(style.name, "使用友好的语气")

        # 构建提示词
        prompt = f"""{role}

【任务】
根据工具查询结果，生成结构化的旅游推荐信息。

【说话风格】
- {tone}
- 适当加入旅行的氛围感描写
- 重点信息用**加粗**标记

【输出格式】
必须输出JSON格式，不要包含任何Markdown格式！JSON结构如下：
{{
    "opening": "开场白，使用轻松活泼的语气",
    "cities": [
        {{
            "name": "城市名",
            "emoji": "城市emoji",
            "days": "推荐天数",
            "budget": "预算描述",
            "season": "最佳旅行季节",
            "attractions": [
                {{"name": "景点名", "type": "景点类型", "ticket": "门票价格", "description": "简短描述"}}
            ]
        }}
    ],
    "tips": "旅行小贴士"
}}

【重要】
- 只输出JSON，不要输出任何Markdown语法
- 确保JSON格式正确，可以被json.loads()解析
- 每个城市至少推荐2-4个景点"""

        return prompt

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """
        解析 LLM 返回的 JSON 响应

        LLM 有时会在 JSON 外面包裹 markdown 代码块或添加额外文本，
        此函数负责提取纯 JSON 内容。

        Args:
            content: LLM 返回的原始内容

        Returns:
            dict: 解析后的 JSON 对象，解析失败返回 None
        """
        try:
            # 首先尝试直接解析
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 代码块
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # 尝试提取任何 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass

        return None

    def _format_travel_response(self, data: dict) -> str:
        """
        格式化旅游响应

        将 LLM 生成的 JSON 数据格式化为规范的 Markdown 文本。

        Args:
            data: 结构化数据字典

        Returns:
            str: 格式化后的 Markdown 文本
        """
        lines = []

        # 开场白
        opening = data.get('opening', '')
        if opening:
            lines.append(opening)
            lines.append('')

        # 城市推荐
        for i, city in enumerate(data.get('cities', [])):
            lines.append(f"## {city.get('emoji', '')} {city.get('name', '')}")
            lines.append('')

            # 城市基本信息
            lines.append(f"- **推荐天数**：{city.get('days', '3天')}")
            lines.append(f"- **预算**：约 **{city.get('budget', '待定')}/天**")
            lines.append(f"- **最佳旅行季节**：{city.get('season', '四季皆宜')}")
            lines.append('')

            # 必游景点
            lines.append('#### 必游景点：')
            attractions = city.get('attractions', [])
            for j, attr in enumerate(attractions, 1):
                ticket = attr.get('ticket', '免费')
                ticket_str = f"门票 **{ticket}**" if ticket not in ['免费', '0', 0] else '完全免费'
                lines.append(f"{j}. **{attr.get('name', '未知景点')}**（{attr.get('type', '景点')}）- {ticket_str}")
                desc = attr.get('description', '')
                if desc:
                    lines.append(f"   - {desc}")
                lines.append('')

            # 城市之间加空行
            if i < len(data.get('cities', [])) - 1:
                lines.append('')

        # 旅行小贴士
        tips = data.get('tips', '')
        if tips:
            lines.append('')
            lines.append('☀️ 旅行小贴士')
            lines.append('')
            lines.append(tips)

        return '\n'.join(lines)

    def _format_attractions_response(self, tool_result: Dict) -> str:
        """
        格式化景点响应数据

        将景点查询结果格式化为可读的文本。

        Args:
            tool_result: 工具返回的原始结果

        Returns:
            str: 格式化后的景点描述文本
        """
        lines = []

        # 兼容新旧两种数据格式
        if 'cities' in tool_result:
            data = tool_result['cities']
        elif 'data' in tool_result:
            data = tool_result['data']
        else:
            data = tool_result

        if not data:
            return "未找到相关景点信息"

        for city, data_item in data.items():
            region = data_item.get('region', '') if isinstance(data_item, dict) else ''
            region_str = f" (来自{region}地区)" if region else ""
            lines.append(f"\n## {city}{region_str}")
            attractions = data_item.get('attractions', []) if isinstance(data_item, dict) else []
            if attractions:
                lines.append("\n### 景点推荐：")
                for i, attr in enumerate(attractions[:10], 1):
                    name = attr.get('name', '未知景点')
                    desc = attr.get('description', '')[:100]
                    ticket = attr.get('ticket', 0)
                    lines.append(f"{i}. **{name}**")
                    if desc:
                        lines.append(f"   - {desc}")
                    if ticket > 0:
                        lines.append(f"   - 门票: ¥{ticket}")
            else:
                lines.append("  暂无景点信息")

        return '\n'.join(lines) if lines else "未找到相关景点信息"

    @staticmethod
    def split_into_chunks(text: str, chunk_size: int = 3) -> List[str]:
        """
        将文本拆分成小块用于流式输出

        当 LLM 不支持流式输出时，使用此方法进行模拟流式。
        拆分策略：
        1. 优先在标点符号处断开
        2. 控制每块最大长度
        3. 确保中英文都能正确处理

        Args:
            text: 输入文本
            chunk_size: 每个块的最大字符数（中文字符），默认3个

        Returns:
            文本块列表

        Examples:
            >>> chunks = ResponseGenerator.split_into_chunks("你好世界！再见。")
            >>> print(chunks)  # ['你好', '世界', '！', '再见', '。']
        """
        if not text:
            return []

        chunks = []
        i = 0

        while i < len(text):
            # 找到下一个断点（标点或换行）
            chunk_end = min(i + 20, len(text))  # 最大20个字符

            # 从后往前找合适的断点
            for j in range(chunk_end, i, -1):
                char = text[j - 1]
                # 中文标点作为断点
                if char in '。！？；：、\n':
                    chunk_end = j
                    break
                # 英文标点也作为断点
                if char in '.!?:;,' and j > i + 3:
                    chunk_end = j
                    break

            # 确保至少返回一个字符
            if chunk_end <= i:
                chunk_end = min(i + 1, len(text))

            chunk = text[i:chunk_end]
            chunks.append(chunk)
            i = chunk_end

        # 如果分块太大，进一步拆分
        final_chunks = []
        for chunk in chunks:
            while len(chunk) > 15:  # 如果块太大，按更小单位拆分
                final_chunks.append(chunk[:8])  # 8个字符
                chunk = chunk[8:]
            if chunk:
                final_chunks.append(chunk)

        return final_chunks if final_chunks else [text]


class ReasoningBuilder:
    """
    推理过程构建器

    负责将 ReAct 执行历史格式化为可读的推理过程描述。
    """

    @staticmethod
    def build_reasoning_text(history: List[Dict]) -> str:
        """
        构建推理过程文本

        将 ReAct 执行历史格式化为可读的推理过程描述。
        支持阶段分层展示（理解 -> 规划 -> 执行 -> 生成）。

        Args:
            history: ReAct 执行历史列表

        Returns:
            str: 格式化后的推理过程文本（Markdown 格式）
        """
        if not history:
            return "<thinking>\n[Timestamp: {timestamp}]\n\n[Intent Analysis]\nNo reasoning history available.\n\n[Context Evaluation]\nNo context available.\n\n[Response Planning]\nUnable to generate response.\n\n[Constraint Check]\nNo constraints checked.\n</thinking>".format(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        # 阶段名称映射（中文）
        phase_names = {
            'UNDERSTANDING': '阶段一：理解任务',
            'PLANNING': '阶段二：制定计划',
            'EXECUTION': '阶段三：执行工具',
            'GENERATION': '阶段四：生成回答'
        }

        # 按阶段分类
        phases_content = {phase: [] for phase in phase_names.keys()}

        # 遍历历史，按阶段分类
        for i, step in enumerate(history):
            thought = step.get('thought', {})
            action = step.get('action', {})

            thought_phase = step.get('phase', 'UNKNOWN')
            thought_type = thought.get('type', 'UNKNOWN')
            thought_content = thought.get('content', '')
            action_name = action.get('tool_name', '')
            action_status = action.get('status', 'PENDING')
            result = action.get('result', {})

            # 构建步骤内容
            step_content = f"\n【步骤 {i + 1}】"

            if thought_type == 'ANALYSIS':
                step_content += "\n任务分析"
            elif thought_type == 'PLANNING':
                step_content += "\n执行规划"
            elif thought_type == 'INFERENCE':
                step_content += "\n执行推理"
            elif thought_type == 'REFLECTION':
                step_content += "\n结果反思"
            elif thought_type == 'DECISION':
                step_content += "\n最终决策"

            if thought_content:
                # 提取有意义的摘要（去除装饰性内容）
                lines = thought_content.split('\n')
                meaningful_lines = [l for l in lines if l.strip() and not l.strip().startswith('━') and not l.strip().startswith('【阶段')]
                if meaningful_lines:
                    step_content += "\n" + "\n".join(meaningful_lines[:5])

            # 添加工具执行信息
            if action_name and action_name != 'none':
                status_str = '成功' if action_status == 'SUCCESS' else '失败' if action_status == 'FAILED' else '执行中'
                step_content += f"\n工具: {action_name} [{status_str}]"

            # 分配到对应阶段
            if thought_phase in phases_content:
                phases_content[thought_phase].append(step_content)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tools_used = ReasoningBuilder.extract_tools_used(history)

        # 构建带阶段标记的推理文本
        sections = []

        # 标题
        sections.append(f"[Timestamp: {timestamp}]")

        # 统计信息
        sections.append(f"[执行统计]")
        sections.append(f"- 总步骤数: {len(history)}")
        sections.append(f"- 使用工具: {', '.join(tools_used) if tools_used else '无'}")

        # 按阶段输出
        for phase_key, phase_name in phase_names.items():
            content = phases_content.get(phase_key, [])
            if content:
                sections.append(f"\n{'=' * 40}")
                sections.append(f"[{phase_name}]")
                sections.append(''.join(content))

        thinking_content = '\n'.join(sections)

        return f"<thinking>\n{thinking_content}\n{'=' * 40}\n</thinking>"

    @staticmethod
    def extract_tools_used(history: List[Dict]) -> List[str]:
        """
        提取使用的工具列表

        从执行历史中收集所有被调用的工具名称。

        Args:
            history: 执行历史列表

        Returns:
            List[str]: 使用的工具名称列表（去重）
        """
        tools = []
        for step in history:
            action = step.get('action', {})
            tool_name = action.get('tool_name', '')
            if tool_name and tool_name not in tools and tool_name != 'none':
                tools.append(tool_name)
        return tools
