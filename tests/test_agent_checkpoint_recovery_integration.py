from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

from agent.src.graph.builder import build_travel_agent
from agent.src.graph.persistent_checkpointer import PersistentSqliteSaver
from agent.src.graph.state import TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state


class _StructuredIntentLLM:
    def __init__(self, schema):
        self._schema = schema

    def invoke(self, _messages):
        return self._schema(
            intent="general",
            confidence=1.0,
            entities={},
            requires_tools=False,
        )


class FakeLLM:
    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema, method=None):  # noqa: ARG002
        return _StructuredIntentLLM(schema)

    def invoke(self, _messages):
        return AIMessage(content="ok")


def test_persistent_checkpoint_recovers_multi_turn_session(tmp_path: Path):
    db_path = tmp_path / "langgraph_checkpoints.sqlite3"
    session_id = "recovery-session-1"

    saver_1 = PersistentSqliteSaver(str(db_path))
    agent_1 = build_travel_agent(
        llm=FakeLLM(),
        tools=[],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=saver_1,
    )
    result_1 = agent_1.invoke(
        create_initial_state(
            user_message="先给我一个周末城市建议",
            session_id=session_id,
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    assert result_1.get("answer")

    config = {"configurable": {"thread_id": session_id}}
    assert saver_1.get_tuple(config) is not None
    assert db_path.exists()

    saver_2 = PersistentSqliteSaver(str(db_path))
    assert saver_2.get_tuple(config) is not None

    agent_2 = build_travel_agent(
        llm=FakeLLM(),
        tools=[],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=saver_2,
    )
    result_2 = agent_2.invoke(
        create_initial_state(
            user_message="再给一个预算友好的选项",
            session_id=session_id,
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    assert result_2.get("answer")

    checkpoints = list(saver_2.list(config))
    assert len(checkpoints) >= 2
