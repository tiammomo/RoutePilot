from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.src.graph.builder import run_travel_agent
from agent.src.graph.persistent_checkpointer import PersistentSqliteSaver
from agent.src.llm.langchain_adapter import create_from_yaml_config
from agent.src.tools.travel_tools import get_travel_tools


def _default_checkpoint_db() -> Path:
    return Path(os.getenv("AGENT_CHECKPOINT_DB", str(ROOT / "data" / "langgraph_checkpoints.sqlite3")))


def _default_llm_config() -> Path:
    return Path(ROOT / "config" / "llm_config.yaml")


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _extract_last_user_message(messages: list[Any]) -> str:
    for msg in reversed(messages or []):
        content = _safe_text(getattr(msg, "content", ""))
        if isinstance(msg, HumanMessage) and content:
            return content
        msg_type = _safe_text(getattr(msg, "type", "")).lower()
        msg_role = _safe_text(getattr(msg, "role", "")).lower()
        if content and (msg_type in {"human", "user"} or msg_role == "user"):
            return content
    return ""


def load_checkpoint_snapshot(
    db_path: str,
    session_id: str,
    checkpoint_ns: str = "",
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    saver = PersistentSqliteSaver(db_path=db_path)
    config: dict[str, Any] = {"configurable": {"thread_id": str(session_id), "checkpoint_ns": str(checkpoint_ns)}}
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = str(checkpoint_id)

    checkpoint_tuple = saver.get_tuple(config)
    if checkpoint_tuple is None:
        raise ValueError(f"No checkpoint found for session_id={session_id}, checkpoint_ns={checkpoint_ns}")

    effective_config = checkpoint_tuple.config or {}
    effective_checkpoint_id = _safe_text((effective_config.get("configurable") or {}).get("checkpoint_id"))
    checkpoint = checkpoint_tuple.checkpoint or {}
    channel_values = checkpoint.get("channel_values", {}) or {}
    messages = list(channel_values.get("messages", []) or [])
    execution_stats = channel_values.get("execution_stats", {}) or {}
    tools_used = list(channel_values.get("tools_used", []) or [])

    return {
        "session_id": str(session_id),
        "checkpoint_ns": str(checkpoint_ns),
        "checkpoint_id": effective_checkpoint_id,
        "checkpoint_ts": _safe_text(checkpoint.get("ts")),
        "intent": _safe_text(channel_values.get("intent")),
        "plan_id": _safe_text(channel_values.get("plan_id")),
        "answer": _safe_text(channel_values.get("answer")),
        "tools_used": [str(item) for item in tools_used if _safe_text(item)],
        "execution_stats": execution_stats,
        "message_count": len(messages),
        "last_user_message": _extract_last_user_message(messages),
    }


def build_replay_report(
    snapshot: dict[str, Any],
    replay_message: str,
    replay_session_id: str,
    replay_result: dict[str, Any],
    db_path: str,
) -> dict[str, Any]:
    old_tools = set(str(item) for item in snapshot.get("tools_used", []) if _safe_text(item))
    new_tools = set(str(item) for item in replay_result.get("tools_used", []) if _safe_text(item))
    overlap = len(old_tools & new_tools)
    denominator = len(old_tools | new_tools)
    tool_overlap_rate = round(overlap / denominator, 4) if denominator else 1.0

    snapshot_answer = _safe_text(snapshot.get("answer"))
    replay_answer = _safe_text(replay_result.get("answer"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "db_path": os.path.abspath(db_path),
            "session_id": snapshot.get("session_id"),
            "checkpoint_ns": snapshot.get("checkpoint_ns"),
            "checkpoint_id": snapshot.get("checkpoint_id"),
            "checkpoint_ts": snapshot.get("checkpoint_ts"),
        },
        "checkpoint_snapshot": {
            "intent": snapshot.get("intent"),
            "plan_id": snapshot.get("plan_id"),
            "tools_used": snapshot.get("tools_used", []),
            "message_count": snapshot.get("message_count", 0),
            "has_answer": bool(snapshot_answer),
        },
        "replay_input": {
            "replay_session_id": replay_session_id,
            "message": replay_message,
        },
        "replay_output": {
            "intent": replay_result.get("intent"),
            "tools_used": replay_result.get("tools_used", []),
            "answer_length": len(replay_answer),
            "success": bool(replay_result.get("success", False)),
        },
        "comparison": {
            "intent_changed": _safe_text(snapshot.get("intent")) != _safe_text(replay_result.get("intent")),
            "answer_length_delta": len(replay_answer) - len(snapshot_answer),
            "tool_overlap_rate": tool_overlap_rate,
        },
    }


def write_report(report: dict[str, Any], output_path: str) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _replay_from_snapshot(
    snapshot: dict[str, Any],
    llm_config_path: str,
    replay_message: str,
    replay_session_id: str,
) -> dict[str, Any]:
    adapter = create_from_yaml_config(llm_config_path)
    llm = adapter.chat_model
    tools = get_travel_tools()
    return asyncio.run(
        run_travel_agent(
            user_message=replay_message,
            llm=llm,
            tools=tools,
            session_id=replay_session_id,
            run_id=f"replay-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a stored LangGraph checkpoint for a session.")
    parser.add_argument("--session-id", required=True, help="Original session_id / thread_id to replay.")
    parser.add_argument("--db", default=str(_default_checkpoint_db()), help="Path to checkpoint sqlite db.")
    parser.add_argument("--checkpoint-ns", default="", help="Checkpoint namespace.")
    parser.add_argument("--checkpoint-id", default="", help="Checkpoint id. Empty means latest.")
    parser.add_argument("--message", default="", help="Replay message override. Empty means use last user message.")
    parser.add_argument(
        "--replay-session-id",
        default="",
        help="Session id used for replay run. Default: <session-id>-replay-<timestamp>.",
    )
    parser.add_argument(
        "--llm-config",
        default=str(_default_llm_config()),
        help="Path to llm_config.yaml used for replay execution.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs" / "benchmarks" / "agent_replay_latest.json"),
        help="Replay report output path (json).",
    )
    args = parser.parse_args()

    snapshot = load_checkpoint_snapshot(
        db_path=args.db,
        session_id=args.session_id,
        checkpoint_ns=args.checkpoint_ns,
        checkpoint_id=args.checkpoint_id or None,
    )
    replay_message = _safe_text(args.message) or _safe_text(snapshot.get("last_user_message"))
    if not replay_message:
        raise ValueError("Unable to determine replay message. Provide --message explicitly.")

    replay_session_id = _safe_text(args.replay_session_id) or (
        f"{args.session_id}-replay-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    replay_result = _replay_from_snapshot(
        snapshot=snapshot,
        llm_config_path=args.llm_config,
        replay_message=replay_message,
        replay_session_id=replay_session_id,
    )
    report = build_replay_report(
        snapshot=snapshot,
        replay_message=replay_message,
        replay_session_id=replay_session_id,
        replay_result=replay_result,
        db_path=args.db,
    )
    output_path = write_report(report, args.output)
    print(f"Replay report: {output_path}")
    print(
        "Replay summary: "
        f"intent_changed={report['comparison']['intent_changed']}, "
        f"tool_overlap_rate={report['comparison']['tool_overlap_rate']}, "
        f"answer_length_delta={report['comparison']['answer_length_delta']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
