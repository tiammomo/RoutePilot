"""SQLAlchemy Core schema for durable, tenant-scoped A2A Tasks."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


metadata = MetaData()
json_type = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")
nullable_json_type = JSON(none_as_null=True).with_variant(
    JSONB(astext_type=Text(), none_as_null=True),
    "postgresql",
)

agent_tasks_table = Table(
    "v1_agent_tasks",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("agent_interface_id", String(128), nullable=False),
    Column("task_id", String(96), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("run_id", String(160), nullable=False),
    Column("dispatch_id", String(36), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("context_id", String(96), nullable=False),
    Column("task_state", Integer, nullable=False),
    Column("task_proto", LargeBinary, nullable=False),
    Column("invocation", json_type, nullable=False),
    Column("deadline", DateTime(timezone=True), nullable=False),
    Column("reference_task_ids", json_type, nullable=False),
    Column("version", BigInteger, nullable=False),
    Column("event_count", Integer, nullable=False),
    Column("pending_input_request_id", String(128), nullable=True),
    Column("execution_input", nullable_json_type, nullable=True),
    Column("execution_lease_owner", String(128), nullable=True),
    Column("execution_lease_until", DateTime(timezone=True), nullable=True),
    Column("execution_attempt", BigInteger, nullable=False, default=0),
    Column("message_fingerprints", json_type, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "tenant_id",
        "agent_interface_id",
        "task_id",
        name="pk_v1_agent_tasks",
    ),
    UniqueConstraint(
        "tenant_id",
        "agent_interface_id",
        "dispatch_id",
        name="uq_v1_agent_tasks_dispatch",
    ),
)

Index(
    "ix_v1_agent_tasks_tenant_interface_context",
    agent_tasks_table.c.tenant_id,
    agent_tasks_table.c.agent_interface_id,
    agent_tasks_table.c.context_id,
    agent_tasks_table.c.created_at,
)
Index(
    "ix_v1_agent_tasks_tenant_run",
    agent_tasks_table.c.tenant_id,
    agent_tasks_table.c.run_id,
    agent_tasks_table.c.created_at,
)
Index(
    "ix_v1_agent_tasks_state_deadline",
    agent_tasks_table.c.tenant_id,
    agent_tasks_table.c.agent_interface_id,
    agent_tasks_table.c.task_state,
    agent_tasks_table.c.deadline,
)
Index(
    "ix_v1_agent_tasks_recoverable_execution",
    agent_tasks_table.c.tenant_id,
    agent_tasks_table.c.task_state,
    agent_tasks_table.c.execution_lease_until,
)

agent_dispatch_inbox_table = Table(
    "v1_agent_dispatch_inbox",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("agent_interface_id", String(128), nullable=False),
    Column("dispatch_id", String(36), nullable=False),
    Column("task_id", String(96), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "tenant_id",
        "agent_interface_id",
        "dispatch_id",
        name="pk_v1_agent_dispatch_inbox",
    ),
    ForeignKeyConstraint(
        ["tenant_id", "agent_interface_id", "task_id"],
        [
            "v1_agent_tasks.tenant_id",
            "v1_agent_tasks.agent_interface_id",
            "v1_agent_tasks.task_id",
        ],
        name="fk_v1_agent_dispatch_task",
        ondelete="CASCADE",
    ),
)

Index(
    "ix_v1_agent_dispatch_inbox_task",
    agent_dispatch_inbox_table.c.tenant_id,
    agent_dispatch_inbox_table.c.agent_interface_id,
    agent_dispatch_inbox_table.c.task_id,
)

agent_task_events_table = Table(
    "v1_agent_task_events",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("agent_interface_id", String(128), nullable=False),
    Column("task_id", String(96), nullable=False),
    Column("event_seq", BigInteger, nullable=False),
    Column("task_version", BigInteger, nullable=False),
    Column("event_kind", String(64), nullable=False),
    Column("event_proto", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "tenant_id",
        "agent_interface_id",
        "task_id",
        "event_seq",
        name="pk_v1_agent_task_events",
    ),
    ForeignKeyConstraint(
        ["tenant_id", "agent_interface_id", "task_id"],
        [
            "v1_agent_tasks.tenant_id",
            "v1_agent_tasks.agent_interface_id",
            "v1_agent_tasks.task_id",
        ],
        name="fk_v1_agent_task_events_task",
        ondelete="CASCADE",
    ),
)

Index(
    "ix_v1_agent_task_events_replay",
    agent_task_events_table.c.tenant_id,
    agent_task_events_table.c.agent_interface_id,
    agent_task_events_table.c.task_id,
    agent_task_events_table.c.task_version,
    agent_task_events_table.c.event_seq,
)

__all__ = [
    "agent_dispatch_inbox_table",
    "agent_task_events_table",
    "agent_tasks_table",
    "metadata",
]
