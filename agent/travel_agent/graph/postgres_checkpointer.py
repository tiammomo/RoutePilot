"""SQL-backed checkpoint saver used by the optional postgres runtime backend."""

from __future__ import annotations

import pickle
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import Engine, delete, func, insert, select

from moyuan_web.persistence import build_sync_engine

from .checkpoint_sql_tables import (
    agent_checkpoint_blobs_table,
    agent_checkpoint_writes_table,
    agent_checkpoints_table,
    ensure_checkpoint_schema,
)

Key3 = tuple[str, str, str]


class PersistentPostgresSaver(InMemorySaver):
    """Durable saver backed by SQL tables that mirror the SQLite checkpoint semantics."""

    def __init__(
        self,
        database_url: str,
        *,
        pool_min: int = 1,
        pool_max: int = 5,
        max_checkpoints_per_thread_ns: int = 200,
        compaction_interval: int = 50,
        ensure_schema_ready: bool = True,
        engine: Engine | None = None,
    ) -> None:
        """Initialize the SQL engine, schema, in-memory cache, and compaction policy."""

        self._engine = engine or build_sync_engine(database_url, pool_min=pool_min, pool_max=pool_max)
        self._persist_lock = threading.RLock()
        self._max_checkpoints = max(1, int(max_checkpoints_per_thread_ns))
        self._compaction_interval = max(10, int(compaction_interval))
        self._write_counter = 0
        if ensure_schema_ready:
            ensure_checkpoint_schema(self._engine)
        super().__init__()
        self._load_from_db()

    def put(self, config, checkpoint, metadata, new_versions):
        """Persist a synchronous checkpoint mutation after the in-memory saver accepts it."""

        next_config = super().put(config, checkpoint, metadata, new_versions)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(next_config)
        self._persist_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
        self._persist_blobs(thread_id, checkpoint_ns, new_versions)
        self._on_mutation(thread_id, checkpoint_ns)
        return next_config

    async def aput(self, config, checkpoint, metadata, new_versions):
        """Persist an asynchronous checkpoint mutation after the base saver accepts it."""

        next_config = await super().aput(config, checkpoint, metadata, new_versions)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(next_config)
        self._persist_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
        self._persist_blobs(thread_id, checkpoint_ns, new_versions)
        self._on_mutation(thread_id, checkpoint_ns)
        return next_config

    def put_writes(self, config, writes, task_id, task_path=""):
        """Persist synchronous checkpoint writes for one task."""

        super().put_writes(config, writes, task_id, task_path=task_path)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(config)
        self._persist_writes(thread_id, checkpoint_ns, checkpoint_id)
        self._on_mutation(thread_id, checkpoint_ns)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        """Persist asynchronous checkpoint writes for one task."""

        await super().aput_writes(config, writes, task_id, task_path=task_path)
        thread_id, checkpoint_ns, checkpoint_id = self._resolve_checkpoint_key(config)
        self._persist_writes(thread_id, checkpoint_ns, checkpoint_id)
        self._on_mutation(thread_id, checkpoint_ns)

    def get_checkpoint_count(self, thread_id: str, checkpoint_ns: str = "") -> int:
        """Return the durable checkpoint count for one thread namespace."""

        self._compact_thread(thread_id, checkpoint_ns)
        with self._persist_lock:
            with self._engine.begin() as connection:
                count = connection.execute(
                    select(func.count())
                    .select_from(agent_checkpoints_table)
                    .where(
                        agent_checkpoints_table.c.thread_id == thread_id,
                        agent_checkpoints_table.c.checkpoint_ns == checkpoint_ns,
                    )
                ).scalar_one()
        return int(count or 0)

    def _resolve_checkpoint_key(self, config) -> Key3:
        """Extract the thread, namespace, and checkpoint identifiers from config."""

        configurable = (config or {}).get("configurable", {})
        thread_id = str(configurable.get("thread_id") or "default")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        checkpoint_id = str(configurable.get("checkpoint_id") or "")
        return thread_id, checkpoint_ns, checkpoint_id

    def _load_from_db(self) -> None:
        """Hydrate the in-memory saver state from durable SQL tables."""

        with self._persist_lock:
            with self._engine.begin() as connection:
                checkpoint_rows = connection.execute(
                    select(
                        agent_checkpoints_table.c.thread_id,
                        agent_checkpoints_table.c.checkpoint_ns,
                        agent_checkpoints_table.c.checkpoint_id,
                        agent_checkpoints_table.c.payload,
                    ).order_by(agent_checkpoints_table.c.created_at.asc())
                ).all()
                blob_rows = connection.execute(
                    select(
                        agent_checkpoint_blobs_table.c.thread_id,
                        agent_checkpoint_blobs_table.c.checkpoint_ns,
                        agent_checkpoint_blobs_table.c.channel,
                        agent_checkpoint_blobs_table.c.version,
                        agent_checkpoint_blobs_table.c.payload,
                    ).order_by(agent_checkpoint_blobs_table.c.created_at.asc())
                ).all()
                write_rows = connection.execute(
                    select(
                        agent_checkpoint_writes_table.c.thread_id,
                        agent_checkpoint_writes_table.c.checkpoint_ns,
                        agent_checkpoint_writes_table.c.checkpoint_id,
                        agent_checkpoint_writes_table.c.task_id,
                        agent_checkpoint_writes_table.c.write_idx,
                        agent_checkpoint_writes_table.c.payload,
                    ).order_by(agent_checkpoint_writes_table.c.created_at.asc())
                ).all()

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
            self.blobs[(str(thread_id), str(checkpoint_ns), str(channel), str(version))] = value

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
        """Deserialize a persisted payload, returning None for corrupt rows."""

        try:
            return pickle.loads(payload)
        except Exception:
            return None

    def _persist_checkpoint(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> None:
        """Upsert one checkpoint payload into the durable checkpoint table."""

        if not checkpoint_id:
            return

        stored = self.storage.get(thread_id, {}).get(checkpoint_ns, {}).get(checkpoint_id)
        if stored is None:
            return

        payload = pickle.dumps(stored, protocol=pickle.HIGHEST_PROTOCOL)
        now = datetime.now().isoformat()
        with self._persist_lock:
            with self._engine.begin() as connection:
                connection.execute(
                    delete(agent_checkpoints_table).where(
                        agent_checkpoints_table.c.thread_id == thread_id,
                        agent_checkpoints_table.c.checkpoint_ns == checkpoint_ns,
                        agent_checkpoints_table.c.checkpoint_id == checkpoint_id,
                    )
                )
                connection.execute(
                    insert(agent_checkpoints_table).values(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=checkpoint_id,
                        payload=payload,
                        created_at=now,
                    )
                )

    def _persist_blobs(self, thread_id: str, checkpoint_ns: str, new_versions: dict[str, Any]) -> None:
        """Upsert channel blob payloads touched by one checkpoint mutation."""

        if not new_versions:
            return

        now = datetime.now().isoformat()
        with self._persist_lock:
            with self._engine.begin() as connection:
                for channel, version in new_versions.items():
                    key = (thread_id, checkpoint_ns, str(channel), str(version))
                    value = self.blobs.get(key)
                    if value is None:
                        continue
                    connection.execute(
                        delete(agent_checkpoint_blobs_table).where(
                            agent_checkpoint_blobs_table.c.thread_id == thread_id,
                            agent_checkpoint_blobs_table.c.checkpoint_ns == checkpoint_ns,
                            agent_checkpoint_blobs_table.c.channel == str(channel),
                            agent_checkpoint_blobs_table.c.version == str(version),
                        )
                    )
                    connection.execute(
                        insert(agent_checkpoint_blobs_table).values(
                            thread_id=thread_id,
                            checkpoint_ns=checkpoint_ns,
                            channel=str(channel),
                            version=str(version),
                            payload=pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL),
                            created_at=now,
                        )
                    )

    def _persist_writes(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> None:
        """Upsert write payloads associated with one checkpoint key."""

        outer_key: Key3 = (thread_id, checkpoint_ns, checkpoint_id)
        write_map = self.writes.get(outer_key, {})
        if not write_map:
            return

        now = datetime.now().isoformat()
        with self._persist_lock:
            with self._engine.begin() as connection:
                for (task_id, write_idx), value in write_map.items():
                    connection.execute(
                        delete(agent_checkpoint_writes_table).where(
                            agent_checkpoint_writes_table.c.thread_id == thread_id,
                            agent_checkpoint_writes_table.c.checkpoint_ns == checkpoint_ns,
                            agent_checkpoint_writes_table.c.checkpoint_id == checkpoint_id,
                            agent_checkpoint_writes_table.c.task_id == str(task_id),
                            agent_checkpoint_writes_table.c.write_idx == int(write_idx),
                        )
                    )
                    connection.execute(
                        insert(agent_checkpoint_writes_table).values(
                            thread_id=thread_id,
                            checkpoint_ns=checkpoint_ns,
                            checkpoint_id=checkpoint_id,
                            task_id=str(task_id),
                            write_idx=int(write_idx),
                            payload=pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL),
                            created_at=now,
                        )
                    )

    def _on_mutation(self, thread_id: str, checkpoint_ns: str) -> None:
        """Run periodic compaction after durable mutations."""

        self._write_counter += 1
        if self._write_counter % self._compaction_interval != 0:
            return
        self._compact_thread(thread_id, checkpoint_ns)

    def _compact_thread(self, thread_id: str, checkpoint_ns: str) -> None:
        """Delete old durable checkpoints beyond the configured retention limit."""

        with self._persist_lock:
            with self._engine.begin() as connection:
                rows = connection.execute(
                    select(agent_checkpoints_table.c.checkpoint_id)
                    .where(
                        agent_checkpoints_table.c.thread_id == thread_id,
                        agent_checkpoints_table.c.checkpoint_ns == checkpoint_ns,
                    )
                    .order_by(agent_checkpoints_table.c.created_at.desc())
                ).all()
                checkpoint_ids = [str(row[0]) for row in rows]
                if len(checkpoint_ids) <= self._max_checkpoints:
                    return

                keep = set(checkpoint_ids[: self._max_checkpoints])
                delete_ids = [checkpoint_id for checkpoint_id in checkpoint_ids[self._max_checkpoints :] if checkpoint_id]
                if not delete_ids:
                    return

                connection.execute(
                    delete(agent_checkpoints_table).where(
                        agent_checkpoints_table.c.thread_id == thread_id,
                        agent_checkpoints_table.c.checkpoint_ns == checkpoint_ns,
                        agent_checkpoints_table.c.checkpoint_id.in_(delete_ids),
                    )
                )
                connection.execute(
                    delete(agent_checkpoint_writes_table).where(
                        agent_checkpoint_writes_table.c.thread_id == thread_id,
                        agent_checkpoint_writes_table.c.checkpoint_ns == checkpoint_ns,
                        agent_checkpoint_writes_table.c.checkpoint_id.in_(delete_ids),
                    )
                )

        self._compact_memory(thread_id, checkpoint_ns, keep)

    def _compact_memory(self, thread_id: str, checkpoint_ns: str, keep: Iterable[str]) -> None:
        """Mirror durable checkpoint compaction in the in-memory cache."""

        keep_set = set(keep)
        ns_storage = self.storage.get(thread_id, {}).get(checkpoint_ns, {})
        for checkpoint_id in list(ns_storage.keys()):
            if checkpoint_id not in keep_set:
                ns_storage.pop(checkpoint_id, None)

        for outer_key in list(self.writes.keys()):
            t_id, ns, checkpoint_id = outer_key
            if t_id == thread_id and ns == checkpoint_ns and checkpoint_id not in keep_set:
                self.writes.pop(outer_key, None)
