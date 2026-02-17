"""
================================================================================
状态管理器 (State Manager)

提供 Agent 工作流的统一状态管理，支持状态持久化、恢复和追踪。

功能特点:
- 工作流状态追踪
- 状态持久化/恢复
- 状态变更监听
- 时间旅行（历史回溯）
- 快照管理

使用示例:
```python
state_manager = StateManager()
state_manager.set_state("input", user_query)
state = state_manager.get_state()
state_manager.save_snapshot()
```

================================================================================
"""

import json
import logging
import uuid
import copy
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """工作流状态"""
    IDLE = "idle"           # 空闲
    INITIALIZING = "init"   # 初始化
    RUNNING = "running"     # 运行中
    WAITING = "waiting"     # 等待中
    COMPLETED = "completed"  # 完成
    FAILED = "failed"       # 失败
    CANCELLED = "cancelled"  # 取消


@dataclass
class StateSnapshot:
    """状态快照"""
    snapshot_id: str
    state: Dict[str, Any]
    timestamp: str
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "state": self.state,
            "timestamp": self.timestamp,
            "label": self.label,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateSnapshot':
        return cls(
            snapshot_id=data['snapshot_id'],
            state=data['state'],
            timestamp=data['timestamp'],
            label=data.get('label', ''),
            metadata=data.get('metadata', {})
        )


@dataclass
class StateTransition:
    """状态转移记录"""
    from_state: Dict[str, Any]
    to_state: Dict[str, Any]
    key: str
    old_value: Any
    new_value: Any
    timestamp: str
    node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp,
            "node_id": self.node_id
        }


class StateManager:
    """
    统一状态管理器

    管理 Agent 工作流的完整状态，包括：
    - 输入状态
    - 节点状态
    - 中间结果
    - 最终输出

    特性：
    - 支持嵌套状态
    - 自动快照
    - 变更追踪
    - 状态恢复
    """

    def __init__(
        self,
        max_history: int = 100,
        enable_snapshot: bool = True,
        snapshot_interval: int = 10
    ):
        """
        初始化状态管理器

        Args:
            max_history: 最大历史记录数
            enable_snapshot: 是否启用快照
            snapshot_interval: 快照间隔（操作次数）
        """
        self.workflow_id = str(uuid.uuid4())[:8]
        self.status = WorkflowStatus.IDLE

        # 主状态字典
        self._state: Dict[str, Any] = {}

        # 状态历史（用于撤销）
        self._history: deque = deque(maxlen=max_history)

        # 快照管理
        self._snapshots: Dict[str, StateSnapshot] = {}
        self._snapshot_order: List[str] = []
        self._enable_snapshot = enable_snapshot
        self._snapshot_interval = snapshot_interval
        self._operation_count = 0

        # 变更监听器
        self._listeners: Dict[str, List[Callable]] = {}

        # 执行追踪
        self._execution_trace: List[Dict[str, Any]] = []

        # 节点状态
        self._node_states: Dict[str, Dict[str, Any]] = {}

        logger.info(f"[StateManager] 初始化完成，workflow_id={self.workflow_id}")

    @property
    def state(self) -> Dict[str, Any]:
        """获取当前状态（只读）"""
        return copy.deepcopy(self._state)

    def get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any, node_id: Optional[str] = None) -> None:
        """
        设置状态值

        Args:
            key: 状态键，支持点分隔的嵌套键，如 "node.result.output"
            value: 状态值
            node_id: 设置状态的节点ID
        """
        # 记录旧值用于历史
        old_value = self._get_nested(self._state, key)

        # 设置新值
        self._set_nested(self._state, key, value)

        # 记录转移
        self._history.append(StateTransition(
            from_state=copy.deepcopy(self._state),
            to_state=copy.deepcopy(self._state),
            key=key,
            old_value=old_value,
            new_value=value,
            timestamp=datetime.now().isoformat(),
            node_id=node_id
        ))

        # 触发监听器
        self._notify_listeners(key, old_value, value)

        # 自动快照
        self._operation_count += 1
        if self._enable_snapshot and self._operation_count % self._snapshot_interval == 0:
            self.auto_snapshot()

        logger.debug(f"[StateManager] 状态更新: {key} = {value}")

    def _get_nested(self, d: Dict, key: str) -> Any:
        """获取嵌套值"""
        keys = key.split('.')
        value = d
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        return value

    def _set_nested(self, d: Dict, key: str, value: Any) -> None:
        """设置嵌套值"""
        keys = key.split('.')
        current = d
        for i, k in enumerate(keys[:-1]):
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    def add_listener(self, key: str, callback: Callable) -> None:
        """添加状态变更监听器"""
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(callback)

    def _notify_listeners(self, key: str, old_value: Any, new_value: Any) -> None:
        """通知监听器"""
        # 精确匹配
        if key in self._listeners:
            for callback in self._listeners[key]:
                callback(key, old_value, new_value)

        # 通配符匹配
        if '*' in self._listeners:
            for callback in self._listeners['*']:
                callback(key, old_value, new_value)

        # 前缀匹配
        parts = key.split('.')
        for i in range(len(parts) - 1, 0, -1):
            prefix = '.'.join(parts[:i])
            if prefix in self._listeners:
                for callback in self._listeners[prefix]:
                    callback(key, old_value, new_value)

    def has_state(self, key: str) -> bool:
        """检查状态是否存在"""
        return self._get_nested(self._state, key) is not None

    def delete_state(self, key: str) -> bool:
        """删除状态"""
        if not self.has_state(key):
            return False

        keys = key.split('.')
        current = self._state
        for k in keys[:-1]:
            if k not in current:
                return False
            current = current[k]

        if keys[-1] in current:
            del current[keys[-1]]
            return True
        return False

    def clear(self, keep_keys: Optional[List[str]] = None) -> None:
        """
        清空状态

        Args:
            keep_keys: 保留的键列表
        """
        if keep_keys:
            preserved = {}
            for key in keep_keys:
                if self.has_state(key):
                    preserved[key] = self.get_state(key)
            self._state = preserved
        else:
            self._state = {}
        self._history.clear()

    def snapshot(self, label: str = "", metadata: Optional[Dict] = None) -> str:
        """
        创建快照

        Args:
            label: 快照标签
            metadata: 额外元数据

        Returns:
            str: 快照ID
        """
        snapshot_id = str(uuid.uuid4())[:8]
        snapshot = StateSnapshot(
            snapshot_id=snapshot_id,
            state=copy.deepcopy(self._state),
            timestamp=datetime.now().isoformat(),
            label=label,
            metadata=metadata or {}
        )

        self._snapshots[snapshot_id] = snapshot
        self._snapshot_order.append(snapshot_id)

        logger.info(f"[StateManager] 创建快照: {snapshot_id} ({label})")
        return snapshot_id

    def auto_snapshot(self, label: Optional[str] = None) -> str:
        """自动快照"""
        return self.snapshot(
            label=label or f"auto_{self._operation_count}",
            metadata={'auto': True, 'operation_count': self._operation_count}
        )

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        恢复快照

        Args:
            snapshot_id: 快照ID

        Returns:
            bool: 是否成功
        """
        if snapshot_id not in self._snapshots:
            logger.warning(f"[StateManager] 快照不存在: {snapshot_id}")
            return False

        snapshot = self._snapshots[snapshot_id]
        self._state = copy.deepcopy(snapshot.state)
        logger.info(f"[StateManager] 恢复快照: {snapshot_id}")
        return True

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """获取快照"""
        return self._snapshots.get(snapshot_id)

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有快照"""
        return [self._snapshots[sid].to_dict() for sid in self._snapshot_order]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照"""
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
            if snapshot_id in self._snapshot_order:
                self._snapshot_order.remove(snapshot_id)
            return True
        return False

    def undo(self, steps: int = 1) -> bool:
        """
        撤销操作

        Args:
            steps: 撤销步数

        Returns:
            bool: 是否成功
        """
        if len(self._history) < steps:
            return False

        for _ in range(steps):
            if self._history:
                self._history.pop()

        # 从最近的快照恢复
        if self._snapshots and self._snapshot_order:
            last_snapshot = self._snapshots[self._snapshot_order[-1]]
            self._state = copy.deepcopy(last_snapshot.state)

        return True

    def get_history(self) -> List[Dict[str, Any]]:
        """获取历史记录"""
        return [t.to_dict() for t in self._history]

    # ==================== 节点状态管理 ====================

    def set_node_state(self, node_id: str, state: Dict[str, Any]) -> None:
        """设置节点状态"""
        self._node_states[node_id] = {
            **state,
            'updated_at': datetime.now().isoformat()
        }

    def get_node_state(self, node_id: str) -> Optional[Dict[str, Any]]:
        """获取节点状态"""
        return self._node_states.get(node_id)

    def get_all_node_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有节点状态"""
        return copy.deepcopy(self._node_states)

    # ==================== 执行追踪 ====================

    def trace_execution(
        self,
        node_id: str,
        event: str,
        data: Optional[Dict] = None
    ) -> None:
        """记录执行轨迹"""
        trace_entry = {
            'timestamp': datetime.now().isoformat(),
            'node_id': node_id,
            'event': event,
            'data': data or {},
            'workflow_id': self.workflow_id
        }
        self._execution_trace.append(trace_entry)

    def get_execution_trace(self) -> List[Dict[str, Any]]:
        """获取执行轨迹"""
        return copy.deepcopy(self._execution_trace)

    def clear_execution_trace(self) -> None:
        """清空执行轨迹"""
        self._execution_trace.clear()

    # ==================== 统计信息 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'workflow_id': self.workflow_id,
            'status': self.status.value,
            'state_keys': len(self._state),
            'history_count': len(self._history),
            'snapshot_count': len(self._snapshots),
            'node_count': len(self._node_states),
            'trace_count': len(self._execution_trace)
        }

    def export_state(self) -> Dict[str, Any]:
        """导出完整状态"""
        return {
            'workflow_id': self.workflow_id,
            'status': self.status.value,
            'state': self._state,
            'snapshots': {k: v.to_dict() for k, v in self._snapshots.items()},
            'node_states': self._node_states,
            'execution_trace': self._execution_trace
        }

    def import_state(self, data: Dict[str, Any]) -> None:
        """导入状态"""
        self.workflow_id = data.get('workflow_id', self.workflow_id)
        self._state = data.get('state', {})
        self._node_states = data.get('node_states', {})
        self._execution_trace = data.get('execution_trace', [])

        # 恢复快照
        snapshots = data.get('snapshots', {})
        self._snapshots = {k: StateSnapshot.from_dict(v) for k, v in snapshots.items()}
        self._snapshot_order = list(self._snapshots.keys())
