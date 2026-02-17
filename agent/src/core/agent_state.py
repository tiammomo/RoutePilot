"""
================================================================================
Agent 状态管理器 (Agent State Management)

集成框架层的 StateManager，提供 Agent 级别的状态持久化和生命周期管理。

功能：
- 检查点保存/恢复
- 会话状态管理
- Agent 生命周期控制（启动/暂停/恢复/终止）
- 状态持久化

================================================================================
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent 状态"""
    IDLE = "idle"           # 空闲
    INITIALIZING = "init"   # 初始化中
    RUNNING = "running"    # 运行中
    PAUSED = "paused"      # 已暂停
    COMPLETED = "completed" # 已完成
    FAILED = "failed"      # 失败
    TERMINATED = "terminated"  # 已终止


@dataclass
class AgentSnapshot:
    """Agent 状态快照"""
    snapshot_id: str
    session_id: str
    status: AgentStatus
    state: Dict[str, Any]
    memory_data: Dict[str, Any]
    workflow_state: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "state": self.state,
            "memory_data": self.memory_data,
            "workflow_state": self.workflow_state,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentSnapshot':
        return cls(
            snapshot_id=data["snapshot_id"],
            session_id=data["session_id"],
            status=AgentStatus(data["status"]),
            state=data["state"],
            memory_data=data.get("memory_data", {}),
            workflow_state=data.get("workflow_state"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


class AgentStateManager:
    """Agent 状态管理器

    封装 StateManager，提供 Agent 级别的状态管理功能。
    支持检查点保存、恢复和生命周期控制。
    """

    def __init__(self, enable_persistence: bool = False):
        """
        Args:
            enable_persistence: 是否启用持久化（需要配置存储后端）
        """
        self.enable_persistence = enable_persistence
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._snapshots: Dict[str, List[AgentSnapshot]] = {}
        self._active_sessions: Set[str] = set()

        # 尝试导入 StateManager
        try:
            from framework.state_manager import StateManager
            self._state_manager = StateManager()
            logger.info("StateManager integration enabled")
        except ImportError:
            self._state_manager = None
            logger.warning("StateManager not available, using basic state management")

    async def save_checkpoint(
        self,
        session_id: str,
        state: Dict[str, Any],
        memory_data: Optional[Dict[str, Any]] = None,
        workflow_state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentSnapshot:
        """
        保存检查点

        Args:
            session_id: 会话 ID
            state: Agent 状态
            memory_data: 记忆数据
            workflow_state: 工作流状态
            metadata: 额外元数据

        Returns:
            保存的快照
        """
        import uuid

        snapshot = AgentSnapshot(
            snapshot_id=str(uuid.uuid4()),
            session_id=session_id,
            status=AgentStatus.RUNNING,
            state=state,
            memory_data=memory_data or {},
            workflow_state=workflow_state,
            metadata=metadata or {}
        )

        # 存储快照
        if session_id not in self._snapshots:
            self._snapshots[session_id] = []

        self._snapshots[session_id].append(snapshot)

        # 如果启用了持久化，这里可以保存到存储后端
        if self.enable_persistence:
            await self._persist_snapshot(snapshot)

        logger.info(f"Saved checkpoint for session {session_id}: {snapshot.snapshot_id}")
        return snapshot

    async def restore_checkpoint(
        self,
        session_id: str,
        snapshot_id: Optional[str] = None
    ) -> Optional[AgentSnapshot]:
        """
        恢复检查点

        Args:
            session_id: 会话 ID
            snapshot_id: 快照 ID，如果为 None 则恢复最新的

        Returns:
            快照数据，如果不存在则返回 None
        """
        snapshots = self._snapshots.get(session_id, [])

        if not snapshots:
            # 尝试从持久化存储加载
            if self.enable_persistence:
                return await self._load_snapshot(session_id, snapshot_id)
            return None

        if snapshot_id:
            # 查找指定快照
            for snapshot in snapshots:
                if snapshot.snapshot_id == snapshot_id:
                    return snapshot
            return None
        else:
            # 返回最新的快照
            return snapshots[-1] if snapshots else None

    async def get_active_sessions(self) -> List[str]:
        """获取活跃会话列表"""
        return list(self._active_sessions)

    async def cleanup_old_sessions(self, max_age_hours: int = 24):
        """清理过期会话"""
        import time

        current_time = datetime.now()
        cleaned = []

        for session_id, session_data in list(self._sessions.items()):
            if "last_access" in session_data:
                last_access = datetime.fromisoformat(session_data["last_access"])
                age_hours = (current_time - last_access).total_seconds() / 3600

                if age_hours > max_age_hours:
                    # 清理会话
                    if session_id in self._active_sessions:
                        self._active_sessions.remove(session_id)
                    if session_id in self._snapshots:
                        del self._snapshots[session_id]
                    del self._sessions[session_id]
                    cleaned.append(session_id)

        logger.info(f"Cleaned up {len(cleaned)} old sessions")
        return cleaned

    async def _persist_snapshot(self, snapshot: AgentSnapshot):
        """持久化快照（需要实现存储后端）"""
        # TODO: 实现实际的持久化逻辑
        pass

    async def _load_snapshot(self, session_id: str, snapshot_id: Optional[str] = None) -> Optional[AgentSnapshot]:
        """从持久化存储加载快照"""
        # TODO: 实现实际的加载逻辑
        return None


class AgentLifecycle:
    """Agent 生命周期管理

    管理 Agent 的启动、暂停、恢复和终止。
    """

    def __init__(self, state_manager: Optional[AgentStateManager] = None):
        """
        Args:
            state_manager: 状态管理器实例
        """
        self.state_manager = state_manager or AgentStateManager()
        self._agents: Dict[str, AgentStatus] = {}
        self._agent_contexts: Dict[str, Dict[str, Any]] = {}

    async def start(
        self,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentStatus:
        """
        启动 Agent

        Args:
            session_id: 会话 ID
            context: 初始化上下文

        Returns:
            Agent 状态
        """
        if session_id in self._agents and self._agents[session_id] == AgentStatus.RUNNING:
            logger.warning(f"Agent {session_id} is already running")
            return self._agents[session_id]

        # 恢复检查点（如果存在）
        checkpoint = await self.state_manager.restore_checkpoint(session_id)

        if checkpoint:
            # 从检查点恢复
            self._agent_contexts[session_id] = {
                "state": checkpoint.state,
                "memory_data": checkpoint.memory_data,
                "workflow_state": checkpoint.workflow_state,
                "restored": True
            }
            status = AgentStatus.RUNNING
        else:
            # 新会话
            self._agent_contexts[session_id] = {
                "state": {},
                "memory_data": {},
                "workflow_state": {},
                "restored": False,
                "context": context or {}
            }
            status = AgentStatus.INITIALIZING

        self._agents[session_id] = status
        self._active_sessions.add(session_id)

        logger.info(f"Agent {session_id} started with status {status.value}")
        return status

    async def pause(self, session_id: str) -> AgentStatus:
        """
        暂停 Agent

        Args:
            session_id: 会话 ID

        Returns:
            Agent 状态
        """
        if session_id not in self._agents:
            raise ValueError(f"Agent {session_id} not found")

        if self._agents[session_id] != AgentStatus.RUNNING:
            raise ValueError(f"Agent {session_id} is not running")

        # 保存检查点
        context = self._agent_contexts.get(session_id, {})
        await self.state_manager.save_checkpoint(
            session_id,
            state=context.get("state", {}),
            memory_data=context.get("memory_data", {}),
            workflow_state=context.get("workflow_state", {}),
            metadata={"action": "pause"}
        )

        self._agents[session_id] = AgentStatus.PAUSED

        logger.info(f"Agent {session_id} paused")
        return AgentStatus.PAUSED

    async def resume(self, session_id: str) -> AgentStatus:
        """
        恢复 Agent

        Args:
            session_id: 会话 ID

        Returns:
            Agent 状态
        """
        if session_id not in self._agents:
            raise ValueError(f"Agent {session_id} not found")

        if self._agents[session_id] != AgentStatus.PAUSED:
            raise ValueError(f"Agent {session_id} is not paused")

        # 从检查点恢复
        checkpoint = await self.state_manager.restore_checkpoint(session_id)

        if checkpoint:
            self._agent_contexts[session_id] = {
                "state": checkpoint.state,
                "memory_data": checkpoint.memory_data,
                "workflow_state": checkpoint.workflow_state,
                "restored": True
            }

        self._agents[session_id] = AgentStatus.RUNNING

        logger.info(f"Agent {session_id} resumed")
        return AgentStatus.RUNNING

    async def terminate(self, session_id: str, save_checkpoint: bool = True) -> AgentStatus:
        """
        终止 Agent

        Args:
            session_id: 会话 ID
            save_checkpoint: 是否保存最终检查点

        Returns:
            Agent 状态
        """
        if session_id not in self._agents:
            raise ValueError(f"Agent {session_id} not found")

        # 保存最终检查点
        if save_checkpoint:
            context = self._agent_contexts.get(session_id, {})
            await self.state_manager.save_checkpoint(
                session_id,
                state=context.get("state", {}),
                memory_data=context.get("memory_data", {}),
                workflow_state=context.get("workflow_state", {}),
                metadata={"action": "terminate", "final": True}
            )

        self._agents[session_id] = AgentStatus.TERMINATED

        # 清理上下文
        if session_id in self._agent_contexts:
            del self._agent_contexts[session_id]

        if session_id in self._active_sessions:
            self._active_sessions.remove(session_id)

        logger.info(f"Agent {session_id} terminated")
        return AgentStatus.TERMINATED

    async def get_status(self, session_id: str) -> AgentStatus:
        """
        获取 Agent 状态

        Args:
            session_id: 会话 ID

        Returns:
            Agent 状态
        """
        return self._agents.get(session_id, AgentStatus.IDLE)

    async def get_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取 Agent 上下文"""
        return self._agent_contexts.get(session_id)

    async def update_context(self, session_id: str, key: str, value: Any):
        """更新 Agent 上下文"""
        if session_id not in self._agent_contexts:
            self._agent_contexts[session_id] = {}

        self._agent_contexts[session_id][key] = value

    @property
    def _active_sessions(self) -> Set[str]:
        """获取活跃会话 ID 集合"""
        return {
            sid for sid, status in self._agents.items()
            if status in (AgentStatus.RUNNING, AgentStatus.PAUSED)
        }
