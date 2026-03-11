"""Persistent checkpoint saver backed by SQLite (incremental mode)."""

from __future__ import annotations

import os
import pickle
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, Tuple

from langgraph.checkpoint.memory import InMemorySaver

Key3 = Tuple[str, str, str]
Key4 = Tuple[str, str, str, str]
WriteKey = Tuple[str, int]


class PersistentSqliteSaver(InMemorySaver):
    """Durable saver with incremental writes and periodic compaction.

    Data model:
    - `checkpoints`: one row per (thread_id, checkpoint_ns, checkpoint_id)
    - `blobs`: one row per changed blob version
    - `writes`: one row per write record
    """

    def __init__(
        self,
        db_path: str,
        *,
        max_checkpoints_per_thread_ns: int = 200,
        compaction_interval: int = 50,
    ):
        """Initialize PersistentSqliteSaver and prepare runtime dependencies.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            db_path: Filesystem/resource path for `db_path` resolution.
            max_checkpoints_per_thread_ns: Numeric control parameter `max_checkpoints_per_thread_ns` used for bounds or pagination.
            compaction_interval: Time-related setting `compaction_interval` used by scheduling/retry windows.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        self._db_path = os.path.abspath(db_path)
        self._persist_lock = threading.RLock()
        self._max_checkpoints = max(1, int(max_checkpoints_per_thread_ns))
        self._compaction_interval = max(10, int(compaction_interval))
        self._write_counter = 0
        super().__init__()
        self._init_db()
        self._load_from_db()

    def put(self, config, checkpoint, metadata, new_versions):
        """Persist checkpoint and blobs after synchronous save.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config: Configuration payload used to initialize runtime behavior.
            checkpoint: Serialized checkpoint payload persisted for graph recovery.
            metadata: Checkpoint metadata persisted alongside the state snapshot.
            new_versions: Collection `new_versions` iterated or aggregated by this routine.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        next_config = super().put(config, checkpoint, metadata, new_versions)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(next_config)
        self._persist_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
        self._persist_blobs(thread_id, checkpoint_ns, new_versions)
        self._on_mutation(thread_id, checkpoint_ns)
        return next_config

    async def aput(self, config, checkpoint, metadata, new_versions):
        """Persist checkpoint and blobs after asynchronous save.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config: Configuration payload used to initialize runtime behavior.
            checkpoint: Serialized checkpoint payload persisted for graph recovery.
            metadata: Checkpoint metadata persisted alongside the state snapshot.
            new_versions: Collection `new_versions` iterated or aggregated by this routine.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        next_config = await super().aput(config, checkpoint, metadata, new_versions)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(next_config)
        self._persist_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
        self._persist_blobs(thread_id, checkpoint_ns, new_versions)
        self._on_mutation(thread_id, checkpoint_ns)
        return next_config

    def put_writes(self, config, writes, task_id, task_path=""):
        """Persist incremental channel writes for a checkpoint.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config: Configuration payload used to initialize runtime behavior.
            writes: Collection `writes` iterated or aggregated by this routine.
            task_id: Unique identifier for `task_id` used in lookup/tracing logic.
            task_path: Filesystem/resource path for `task_path` resolution.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        super().put_writes(config, writes, task_id, task_path=task_path)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(config)
        self._persist_writes(thread_id, checkpoint_ns, checkpoint_id)
        self._on_mutation(thread_id, checkpoint_ns)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        """Persist incremental channel writes asynchronously.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config: Configuration payload used to initialize runtime behavior.
            writes: Collection `writes` iterated or aggregated by this routine.
            task_id: Unique identifier for `task_id` used in lookup/tracing logic.
            task_path: Filesystem/resource path for `task_path` resolution.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        await super().aput_writes(config, writes, task_id, task_path=task_path)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(config)
        self._persist_writes(thread_id, checkpoint_ns, checkpoint_id)
        self._on_mutation(thread_id, checkpoint_ns)

    def get_checkpoint_count(self, thread_id: str, checkpoint_ns: str = "") -> int:
        """Get checkpoint count from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
        
        Returns:
            int: Numeric value used by quotas, counts, or status aggregation.
        """
        self._compact_thread(thread_id, checkpoint_ns)
        with self._persist_lock:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ?
                    """,
                    (thread_id, checkpoint_ns),
                ).fetchone()
                return int(row[0] if row else 0)

    def _resolve_checkpoint_key(self, config) -> Key3:
        """Resolve checkpoint key using config defaults and overrides.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config: Configuration payload used to initialize runtime behavior.
        
        Returns:
            Key3: Computed value returned to the caller.
        """
        configurable = (config or {}).get("configurable", {})
        thread_id = str(configurable.get("thread_id") or "default")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        checkpoint_id = str(configurable.get("checkpoint_id") or "")
        return thread_id, checkpoint_ns, checkpoint_id

    def _init_db(self) -> None:
        """Initialize SQLite schema and indexes for checkpoint storage.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blobs (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    version TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    write_idx INTEGER NOT NULL,
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _load_from_db(self) -> None:
        """Load from db from persistence source.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        with self._persist_lock:
            with sqlite3.connect(self._db_path) as conn:
                checkpoint_rows = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, checkpoint_id, payload
                    FROM checkpoints
                    ORDER BY created_at ASC
                    """
                ).fetchall()
                blob_rows = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, channel, version, payload
                    FROM blobs
                    ORDER BY created_at ASC
                    """
                ).fetchall()
                write_rows = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx, payload
                    FROM writes
                    ORDER BY created_at ASC
                    """
                ).fetchall()

        self.storage = defaultdict(lambda: defaultdict(dict))
        for thread_id, checkpoint_ns, checkpoint_id, payload in checkpoint_rows:
            value = self._safe_load(payload)
            if value is None:
                continue
            self.storage[str(thread_id)][str(checkpoint_ns)][str(checkpoint_id)] = value

        self.blobs = defaultdict()
        for thread_id, checkpoint_ns, channel, version, payload in blob_rows:
            value = self._safe_load(payload)
            if value is None:
                continue
            key = (str(thread_id), str(checkpoint_ns), str(channel), str(version))
            self.blobs[key] = value

        self.writes = defaultdict(dict)
        for thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx, payload in write_rows:
            value = self._safe_load(payload)
            if value is None:
                continue
            outer_key = (str(thread_id), str(checkpoint_ns), str(checkpoint_id))
            inner_key = (str(task_id), int(write_idx))
            self.writes[outer_key][inner_key] = value

    @staticmethod
    def _safe_load(payload: bytes) -> Any:
        """Safely deserialize JSON value with fallback on malformed input.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            payload: Structured payload used by API/service boundary.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        try:
            return pickle.loads(payload)
        except Exception:
            return None

    def _persist_checkpoint(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> None:
        """Write one checkpoint snapshot into SQLite storage.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
            checkpoint_id: Unique identifier for `checkpoint_id` used in lookup/tracing logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if not checkpoint_id:
            return

        stored = self.storage.get(thread_id, {}).get(checkpoint_ns, {}).get(checkpoint_id)
        if stored is None:
            return

        payload = pickle.dumps(stored, protocol=pickle.HIGHEST_PROTOCOL)
        now = datetime.now().isoformat()
        with self._persist_lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id, payload, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(thread_id, checkpoint_ns, checkpoint_id)
                    DO UPDATE SET payload = excluded.payload
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id, payload, now),
                )
                conn.commit()

    def _persist_blobs(self, thread_id: str, checkpoint_ns: str, new_versions: Dict[str, Any]) -> None:
        """Write channel-version blobs linked to a checkpoint.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
            new_versions: Collection `new_versions` iterated or aggregated by this routine.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if not new_versions:
            return

        rows = []
        now = datetime.now().isoformat()
        for channel, version in new_versions.items():
            key = (thread_id, checkpoint_ns, str(channel), str(version))
            value = self.blobs.get(key)
            if value is None:
                continue
            rows.append((thread_id, checkpoint_ns, str(channel), str(version), pickle.dumps(value), now))

        if not rows:
            return

        with self._persist_lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.executemany(
                    """
                    INSERT INTO blobs(thread_id, checkpoint_ns, channel, version, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(thread_id, checkpoint_ns, channel, version)
                    DO UPDATE SET payload = excluded.payload
                    """,
                    rows,
                )
                conn.commit()

    def _persist_writes(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> None:
        """Write task-level writes for resumable execution.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
            checkpoint_id: Unique identifier for `checkpoint_id` used in lookup/tracing logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        outer_key: Key3 = (thread_id, checkpoint_ns, checkpoint_id)
        write_map = self.writes.get(outer_key, {})
        if not write_map:
            return

        now = datetime.now().isoformat()
        rows = []
        for (task_id, write_idx), value in write_map.items():
            rows.append(
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    str(task_id),
                    int(write_idx),
                    pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL),
                    now,
                )
            )

        with self._persist_lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.executemany(
                    """
                    INSERT INTO writes(
                        thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx, payload, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                    DO UPDATE SET payload = excluded.payload
                    """,
                    rows,
                )
                conn.commit()

    def _on_mutation(self, thread_id: str, checkpoint_ns: str) -> None:
        """Run post-mutation housekeeping and compaction checks.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        self._write_counter += 1
        if self._write_counter % self._compaction_interval != 0:
            return
        self._compact_thread(thread_id, checkpoint_ns)

    def _compact_thread(self, thread_id: str, checkpoint_ns: str) -> None:
        """Compact old checkpoint rows for one thread namespace.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        with self._persist_lock:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT checkpoint_id FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ?
                    ORDER BY created_at DESC
                    """,
                    (thread_id, checkpoint_ns),
                ).fetchall()
                checkpoint_ids = [str(r[0]) for r in rows]
                if len(checkpoint_ids) <= self._max_checkpoints:
                    return

                keep = set(checkpoint_ids[: self._max_checkpoints])
                delete_ids = [cid for cid in checkpoint_ids[self._max_checkpoints :] if cid]
                if not delete_ids:
                    return

                placeholders = ",".join("?" for _ in delete_ids)
                params = [thread_id, checkpoint_ns, *delete_ids]
                conn.execute(
                    f"""
                    DELETE FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id IN ({placeholders})
                    """,
                    params,
                )
                conn.execute(
                    f"""
                    DELETE FROM writes
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id IN ({placeholders})
                    """,
                    params,
                )
                conn.commit()

        self._compact_memory(thread_id, checkpoint_ns, keep)

    def _compact_memory(self, thread_id: str, checkpoint_ns: str, keep: Iterable[str]) -> None:
        """Compact in-memory structures maintained by checkpointer.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            thread_id: Thread/checkpoint identifier used by langgraph persistence.
            checkpoint_ns: Checkpoint namespace that partitions persisted state records.
            keep: Number of newest checkpoints preserved during compaction.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        keep_set = set(keep)
        ns_storage = self.storage.get(thread_id, {}).get(checkpoint_ns, {})
        for checkpoint_id in list(ns_storage.keys()):
            if checkpoint_id not in keep_set:
                ns_storage.pop(checkpoint_id, None)

        for outer_key in list(self.writes.keys()):
            t_id, ns, checkpoint_id = outer_key
            if t_id == thread_id and ns == checkpoint_ns and checkpoint_id not in keep_set:
                self.writes.pop(outer_key, None)
