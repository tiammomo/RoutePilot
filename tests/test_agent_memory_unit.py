"""Automated tests for test agent memory unit.

The module validates behavior, regressions, and integration contracts.
"""

import pytest
import json
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from agent.travel_agent.graph.memory_integration import AgentMemoryManager


@pytest.mark.asyncio
async def test_memory_cleanup_expired_sessions():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=1,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "hello")
    await manager.add_message("s2", "user", "world")

    # Force s1 to be expired.
    manager._sessions["s1"]["messages"][-1].timestamp = "2000-01-01T00:00:00"

    # Any async API call triggers cleanup.
    await manager.get_summary("s2")

    assert "s1" not in manager._sessions
    assert "s2" in manager._sessions


@pytest.mark.asyncio
async def test_memory_capacity_evicts_old_sessions():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=2,
    )

    await manager.add_message("s1", "user", "first")
    await manager.add_message("s2", "user", "second")

    # Make s1 oldest.
    now = datetime.now()
    manager._sessions["s1"]["messages"][-1].timestamp = (now - timedelta(seconds=10)).isoformat()
    manager._sessions["s2"]["messages"][-1].timestamp = (now - timedelta(seconds=5)).isoformat()

    await manager.add_message("s3", "user", "third")

    assert len(manager._sessions) == 2
    assert "s1" not in manager._sessions
    assert "s2" in manager._sessions
    assert "s3" in manager._sessions


@pytest.mark.asyncio
async def test_memory_profile_extraction_from_user_messages():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "两个人，预算5000元，玩4天，偏好美食和历史，避免人多")
    profile = await manager.get_profile("s1")

    assert profile.get("people_hint") == 2
    assert profile.get("days_hint") == 4
    assert profile.get("budget_hint") in {"5000元", "5000人民币"}
    assert "美食" in profile.get("interests", [])
    assert "历史" in profile.get("interests", [])
    assert "人多" in profile.get("avoid_preferences", [])
    assert profile.get("schema_version") == 2
    assert "_meta" in profile


@pytest.mark.asyncio
async def test_memory_preference_synonym_merge_and_dedupe():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "我想遛娃，看展览和拍照，不想人挤人也不想久等")
    profile = await manager.get_profile("s1")

    interests = profile.get("interests", [])
    avoids = profile.get("avoid_preferences", [])
    assert "亲子" in interests
    assert "博物馆" in interests
    assert "摄影" in interests
    assert "人多" in avoids
    assert "排队" in avoids


@pytest.mark.asyncio
async def test_memory_attr_normalization_avoids_false_budget_conflict():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算5000人民币")
    await manager.add_message("s1", "user", "预算5000元")
    profile = await manager.get_profile("s1")

    assert profile.get("budget_hint") == "5000元"
    pending = profile.get("pending_clarifications", [])
    assert not any(isinstance(item, dict) and item.get("key") == "budget_hint" for item in pending)


@pytest.mark.asyncio
async def test_memory_cleanup_prunes_stale_low_confidence_entries():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算5000元，玩3天")
    profile = manager._sessions["s1"]["profile"]
    profile["attributes"]["legacy_hint"] = {
        "value": "old",
        "source": "inferred",
        "confidence": 0.05,
        "updated_at": "2020-01-01T00:00:00",
    }
    profile["pending_clarifications"].append(
        {
            "key": "legacy_hint",
            "type": "legacy_conflict",
            "old_value": "a",
            "new_value": "b",
            "severity": "low",
            "prompt": "legacy",
            "created_at": "2020-01-01T00:00:00",
            "state": "pending",
            "retry_count": 1,
            "asked_at": "2020-01-02T00:00:00",
            "resolved_at": None,
            "resolution_source": None,
            "last_asked_fingerprint": "old",
        }
    )

    manager._cleanup_stale_profile_entries(profile)
    assert "legacy_hint" not in profile["attributes"]
    assert not any(item.get("key") == "legacy_hint" for item in profile.get("pending_clarifications", []))


@pytest.mark.asyncio
async def test_memory_clear_and_delete_session():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=2,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )
    await manager.add_message("s1", "user", "预算3000元，玩2天")
    await manager.add_message("s1", "assistant", "world")

    cleared = await manager.clear_session_messages("s1")
    assert cleared is True
    assert await manager.get_recent_messages("s1") == []
    assert await manager.get_summary("s1") == ""
    cleared_profile = await manager.get_profile("s1")
    assert cleared_profile.get("schema_version") == 2
    assert cleared_profile.get("interests") == []

    deleted = await manager.delete_session("s1")
    assert deleted is True
    assert await manager.get_recent_messages("s1") == []


@pytest.mark.asyncio
async def test_memory_context_clipping_prefers_relevant_messages():
    manager = AgentMemoryManager(
        max_history=4,
        summary_threshold=10,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "我在上海出差，住在陆家嘴")
    await manager.add_message("s1", "assistant", "好的，记录上海行程")
    await manager.add_message("s1", "user", "我也在关注北京景点")
    await manager.add_message("s1", "assistant", "北京故宫和颐和园值得去")

    context = manager.build_context_messages_for_query("s1", "北京三日游怎么玩", max_messages=2)
    user_context = [m for m in context if isinstance(m, HumanMessage)]
    assert any("北京" in m.content for m in user_context)


@pytest.mark.asyncio
async def test_memory_cross_session_hints_injected_for_sparse_session():
    manager = AgentMemoryManager(
        max_history=6,
        summary_threshold=10,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s_anchor", "user", "预算6000元，两个人，偏好亲子和博物馆，避免排队")
    context = manager.build_context_messages_for_query("s_new", "北京亲子三日游", max_messages=2)

    cross_hints = [
        msg.content
        for msg in context
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("跨会话稳定偏好候选")
    ]
    assert cross_hints
    payload = json.loads(cross_hints[0].split(":\n", 1)[1])
    assert "core_slots" in payload
    assert payload["core_slots"].get("budget_hint") == "6000元"


@pytest.mark.asyncio
async def test_memory_cross_session_hints_skip_existing_current_slots():
    manager = AgentMemoryManager(
        max_history=6,
        summary_threshold=10,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s_anchor", "user", "预算9000元，偏好摄影")
    await manager.add_message("s_current", "user", "预算5000元，三天")
    context = manager.build_context_messages_for_query("s_current", "北京摄影路线", max_messages=2)

    cross_hints = [
        msg.content
        for msg in context
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("跨会话稳定偏好候选")
    ]
    if cross_hints:
        payload = json.loads(cross_hints[0].split(":\n", 1)[1])
        assert "budget_hint" not in payload.get("core_slots", {})


@pytest.mark.asyncio
async def test_memory_cross_session_hints_skipped_for_rich_profile():
    manager = AgentMemoryManager(
        max_history=8,
        summary_threshold=10,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s_anchor", "user", "预算9000元，偏好摄影和美食，避免排队")
    await manager.add_message("s_rich", "user", "预算5000元，3天，2人，亲子博物馆行程，避免排队")

    context = manager.build_context_messages_for_query("s_rich", "北京亲子3日游预算和路线", max_messages=4)
    cross_hints = [
        msg.content
        for msg in context
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("跨会话稳定偏好候选")
    ]
    assert cross_hints == []


@pytest.mark.asyncio
async def test_memory_diagnostics_session_stats_updates():
    manager = AgentMemoryManager(
        max_history=6,
        summary_threshold=10,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算3000元，两个人")
    await manager.add_message("s1", "user", "这次预算10000元")
    manager.build_context_messages_for_query("s1", "帮我规划行程", max_messages=2)
    await manager.add_message("s1", "user", "按这次预算10000元为准")

    diagnostics = manager.get_memory_diagnostics_sync("s1")
    assert diagnostics.get("exists") is True
    stats = diagnostics.get("stats", {})
    assert stats.get("clarification_asked", 0) >= 1
    assert stats.get("conflict_resolved", 0) >= 1


@pytest.mark.asyncio
async def test_memory_diagnostics_global_aggregation_contains_cross_session_stat():
    manager = AgentMemoryManager(
        max_history=6,
        summary_threshold=10,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s_anchor", "user", "预算6000元，偏好亲子和博物馆，避免排队")
    await manager.add_message("s_new", "user", "先记录一个新会话")
    manager.build_context_messages_for_query("s_new", "北京亲子三天", max_messages=2)

    diagnostics = manager.get_memory_diagnostics_sync()
    assert diagnostics.get("session_count", 0) >= 1
    assert "cross_session_hint_injected_total" in diagnostics
    assert diagnostics.get("cross_session_hint_injected_total", 0) >= 1


@pytest.mark.asyncio
async def test_memory_conflict_detection_adds_pending_clarification():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算3000元，两个人")
    await manager.add_message("s1", "user", "这次预算10000元")
    profile = await manager.get_profile("s1")
    pending = profile.get("pending_clarifications", [])
    assert isinstance(pending, list)
    assert pending
    assert "预算偏好" in str(pending[0].get("prompt", ""))
    assert str(profile.get("budget_hint", "")).startswith("3000")


@pytest.mark.asyncio
async def test_memory_profile_time_decay_filters_old_attributes():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600 * 24 * 365,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算5000元，3天")
    attrs = manager._sessions["s1"]["profile"]["attributes"]
    for item in attrs.values():
        item["updated_at"] = "2020-01-01T00:00:00"

    profile = await manager.get_profile("s1")
    assert "budget_hint" not in profile
    meta = profile.get("_meta", {})
    # P2 cleanup strategy now prunes stale low-confidence attributes from storage and prompt meta.
    assert "budget_hint" not in meta


@pytest.mark.asyncio
async def test_memory_atomic_persist_recover_from_backup(tmp_path):
    persist_path = tmp_path / "agent_memory.json"
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=str(persist_path),
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算5000元，玩3天")
    backup_path = tmp_path / f"agent_memory.json{manager.PERSIST_BACKUP_SUFFIX}"
    assert persist_path.exists()
    assert backup_path.exists()

    primary_snapshot = json.loads(persist_path.read_text(encoding="utf-8"))
    assert "s1" in primary_snapshot

    # Simulate primary snapshot corruption and verify backup-based recovery on next startup.
    persist_path.write_text("{broken-json", encoding="utf-8")
    recovered = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=str(persist_path),
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    profile = recovered.get_profile_sync("s1")
    assert str(profile.get("budget_hint", "")).startswith("5000")
    restored_snapshot = json.loads(persist_path.read_text(encoding="utf-8"))
    assert "s1" in restored_snapshot


@pytest.mark.asyncio
async def test_memory_profile_top_k_slot_injection_reduces_prompt_bloat():
    manager = AgentMemoryManager(
        max_history=6,
        summary_threshold=6,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算5000元，两个人，玩4天，夏天，偏好美食和历史")
    profile = manager._sessions["s1"]["profile"]
    for i in range(10):
        manager._merge_profile_attr(
            profile,
            key=f"custom_slot_{i}",
            value=f"value_{i}",
            source="inferred",
            confidence=0.7,
        )

    context = manager.build_context_messages_for_query("s1", "预算和天数优先", max_messages=2)
    profile_messages = [
        msg.content
        for msg in context
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("用户长期偏好(Top-K 槽位):")
    ]
    assert profile_messages
    payload = json.loads(profile_messages[0].split(":\n", 1)[1])
    core_slots = payload.get("core_slots", {})
    assert len(core_slots) <= manager.PROFILE_SLOT_TOP_K
    assert "budget_hint" in core_slots
    assert "_meta" not in profile_messages[0]


@pytest.mark.asyncio
async def test_memory_conflict_auto_clarification_hint_injected():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算3000元，两个人")
    await manager.add_message("s1", "user", "这次预算10000元")

    context = manager.build_context_messages_for_query("s1", "帮我规划3天行程", max_messages=2)
    clarify_messages = [
        msg.content
        for msg in context
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("偏好冲突自动澄清:")
    ]
    assert clarify_messages
    assert "预算偏好" in clarify_messages[0]
    assert "请先用 1 句确认冲突偏好" in clarify_messages[0]


@pytest.mark.asyncio
async def test_memory_conflict_pending_entry_has_retry_state_fields():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算3000元，两个人")
    await manager.add_message("s1", "user", "这次预算10000元")

    internal_profile = manager._sessions["s1"]["profile"]
    pending = internal_profile.get("pending_clarifications", [])
    assert pending
    entry = pending[0]
    assert entry.get("state") == "pending"
    assert entry.get("retry_count") == 0
    assert entry.get("asked_at") is None
    assert entry.get("resolved_at") is None
    assert entry.get("resolution_source") is None


@pytest.mark.asyncio
async def test_memory_clarification_retry_cap_and_same_turn_dedup():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算3000元，两个人")
    await manager.add_message("s1", "user", "这次预算10000元")

    context_turn_1 = manager.build_context_messages_for_query("s1", "帮我规划3天行程", max_messages=2)
    hints_turn_1 = [
        msg.content
        for msg in context_turn_1
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("偏好冲突自动澄清:")
    ]
    assert hints_turn_1

    # Same user turn fingerprint should not consume extra retry quota and still keeps clarification visible.
    context_same_turn = manager.build_context_messages_for_query("s1", "帮我规划3天行程", max_messages=2)
    hints_same_turn = [
        msg.content
        for msg in context_same_turn
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("偏好冲突自动澄清:")
    ]
    assert hints_same_turn

    context_next_turn = manager.build_context_messages_for_query("s1", "请直接给我路线，不需要再问预算", max_messages=2)
    hints_next_turn = [
        msg.content
        for msg in context_next_turn
        if isinstance(msg, SystemMessage) and str(msg.content).startswith("偏好冲突自动澄清:")
    ]
    assert hints_next_turn == []


@pytest.mark.asyncio
async def test_memory_conflict_resolution_phrase_overrides_and_clears_pending():
    manager = AgentMemoryManager(
        max_history=5,
        summary_threshold=5,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    await manager.add_message("s1", "user", "预算3000元，两个人")
    await manager.add_message("s1", "user", "这次预算10000元")
    profile_before = await manager.get_profile("s1")
    assert str(profile_before.get("budget_hint", "")).startswith("3000")
    assert profile_before.get("pending_clarifications")

    # Explicit "按这次...为准" should close the conflict loop and adopt the new value.
    await manager.add_message("s1", "user", "按这次预算10000元为准")
    profile_after = await manager.get_profile("s1")

    assert str(profile_after.get("budget_hint", "")).startswith("10000")
    pending = profile_after.get("pending_clarifications", [])
    assert not any(isinstance(item, dict) and item.get("key") == "budget_hint" for item in pending)
    raw_profile = manager._sessions["s1"]["profile"]
    conflict_log = raw_profile.get("conflict_log", [])
    assert any(
        isinstance(item, dict)
        and item.get("type") == "conflict_resolved"
        and str(item.get("resolution_source", "")).startswith("explicit_")
        for item in conflict_log
    )


@pytest.mark.asyncio
async def test_memory_context_respects_budget_guardrail():
    manager = AgentMemoryManager(
        max_history=12,
        summary_threshold=4,
        persist_path=None,
        session_ttl_seconds=3600,
        max_sessions=10,
    )

    long_user = "我想规划北京亲子旅行，预算5000元，偏好历史和美食，避免排队，" * 8
    long_assistant = "建议上午博物馆下午公园晚上休息，并准备雨天备选方案，注意交通高峰，" * 8
    for _ in range(6):
        await manager.add_message("s1", "user", long_user)
        await manager.add_message("s1", "assistant", long_assistant)

    context = manager.build_context_messages_for_query("s1", "北京3天亲子预算路线", max_messages=8)
    total_tokens = sum(manager._estimate_token_cost(str(msg.content)) for msg in context)
    soft_upper_bound = (
        manager.MEMORY_PROMPT_TOKEN_BUDGET
        + manager.MEMORY_PER_MESSAGE_TOKEN_BUDGET * manager.MEMORY_MIN_CONTEXT_MESSAGES
        + 40
    )
    assert total_tokens <= soft_upper_bound
