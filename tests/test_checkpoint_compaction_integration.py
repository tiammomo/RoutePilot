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


def test_checkpoint_compaction_keeps_recent_only(tmp_path: Path):
    db_path = tmp_path / "compaction.sqlite3"
    saver = PersistentSqliteSaver(
        str(db_path),
        max_checkpoints_per_thread_ns=3,
        compaction_interval=1,
    )
    session_id = "compact-session"
    agent = build_travel_agent(
        llm=FakeLLM(),
        tools=[],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        checkpointer=saver,
    )

    for idx in range(8):
        agent.invoke(
            create_initial_state(
                user_message=f"message-{idx}",
                session_id=session_id,
                system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
            )
        )

    assert saver.get_checkpoint_count(session_id) <= 3
