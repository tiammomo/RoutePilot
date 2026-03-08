from __future__ import annotations

from typing import Optional

INTENT_GUIDANCE: dict[str, str] = {
    "recommend": "先给出候选目的地对比（适合人群、季节、预算区间），再给出推荐结论。",
    "attractions": "先给出景点清单、开放时间与建议游玩时长，再给动线建议。",
    "itinerary": "先给按天行程（上午/下午/晚上），再给交通与备选方案。",
    "budget": "先给分项预算（交通/住宿/门票/餐饮），再给总预算区间与可降本项。",
    "tips": "先给风险提醒和准备清单，再给可执行注意事项。",
    "general": "直接回答；信息不足时只补充 1-2 个澄清问题。",
    "unclear": "先用一句话确认需求，再给可选方向。",
}

INTENT_REACT_PROMPTS: dict[str, str] = {
    "recommend": "你是目的地推荐策略助手。只在缺少事实时调用工具。",
    "attractions": "你是景点查询策略助手。优先返回可验证的开放时间和票务信息。",
    "itinerary": "你是行程规划策略助手。先收集景点和天气，再生成日程。",
    "budget": "你是预算测算策略助手。涉及价格必须先工具验证再作答。",
    "tips": "你是旅行建议策略助手。优先给风险规避与操作清单。",
    "general": "你是通用问答策略助手。无需工具时保持简洁。",
    "unclear": "你是澄清策略助手。优先补齐关键信息。",
}

REACT_CONSTRAINTS = """
ReAct 约束：
1. 严格按 Thought -> Action -> Observation 的顺序执行。
2. 若 Observation 已能支撑结论，不再继续调用工具。
3. 不得重复调用同一工具同一参数。
4. 涉及价格、政策、签证、退改等高风险结论时，必须先有工具验证结果。
""".strip()


def build_system_prompt(base_prompt: str, intent: Optional[str]) -> str:
    intent_key = (intent or "general").lower()
    guidance = INTENT_GUIDANCE.get(intent_key, INTENT_GUIDANCE["general"])
    react_prompt = INTENT_REACT_PROMPTS.get(intent_key, INTENT_REACT_PROMPTS["general"])
    return f"{base_prompt}\n\n任务策略:\n{react_prompt}\n\n回答要求:\n{guidance}\n\n{REACT_CONSTRAINTS}"


def build_answer_prompt(
    user_question: str,
    context: str,
    tools_used: list[str],
    intent: Optional[str],
) -> str:
    guidance = INTENT_GUIDANCE.get((intent or "general").lower(), INTENT_GUIDANCE["general"])
    if tools_used:
        return (
            f"用户问题: {user_question}\n\n"
            f"{context}\n\n"
            f"任务类型: {intent or 'general'}\n"
            f"回答要求: {guidance}\n"
            "请基于工具结果回答，优先引用 source/fetched_at；涉及时效信息时明确日期。"
        )
    return (
        f"用户问题: {user_question}\n\n"
        f"任务类型: {intent or 'general'}\n"
        f"回答要求: {guidance}\n"
        "请直接给出可执行建议。"
    )


def build_direct_prompt(user_question: str, intent: Optional[str]) -> str:
    guidance = INTENT_GUIDANCE.get((intent or "general").lower(), INTENT_GUIDANCE["general"])
    return (
        f"用户问题: {user_question}\n\n"
        f"任务类型: {intent or 'general'}\n"
        f"回答要求: {guidance}\n"
        "若关键条件不足，请在结尾给出最多 2 个澄清问题。"
    )
