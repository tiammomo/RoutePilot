"""RoutePilot's strict profile constants for the A2A 1.0 boundary."""

from __future__ import annotations

A2A_PROTOCOL_VERSION = "1.0"
TRAVEL_ARTIFACT_EXTENSION_URI = "urn:routepilot:a2a:extensions:travel-artifact:v1"

MAX_A2A_HTTP_BODY_BYTES = 256 * 1024
MAX_STRUCTURED_INPUT_BYTES = 192 * 1024
MAX_GOAL_CHARACTERS = 4_000
MAX_ARTIFACTS_PER_MESSAGE = 8
MAX_REFERENCE_TASKS = 10
DEFAULT_TASK_TIMEOUT_SECONDS = 60.0
MAX_TASK_TIMEOUT_SECONDS = 30 * 60.0

# Durable-store bounds are deliberately independent from the HTTP body bound:
# completed Tasks may contain several validated output Artifacts, while a
# corrupt/hostile database row must never make a worker allocate unbounded
# protobuf or JSON payloads during recovery.
MAX_PERSISTED_TASK_PROTO_BYTES = 2 * 1024 * 1024
MAX_PERSISTED_EVENT_PROTO_BYTES = 1024 * 1024
MAX_PERSISTED_INVOCATION_JSON_BYTES = MAX_STRUCTURED_INPUT_BYTES
MAX_PERSISTED_TASK_EVENTS = 512

INPUT_REQUEST_SCHEMA_URI = "urn:routepilot:a2a:input-request:v1"
INPUT_RESPONSE_SCHEMA_URI = "urn:routepilot:a2a:input-response:v1"
PUBLIC_ERROR_SCHEMA_URI = "urn:routepilot:a2a:public-error:v1"


def invocation_schema_uri(agent_interface_id: str) -> str:
    """Return the stable structured-input schema URI for one interface."""

    return f"urn:routepilot:a2a:input:{agent_interface_id}:v1"


def artifact_schema_uri(contract: str) -> str:
    """Return the stable schema URI for a versioned RoutePilot contract."""

    name, _, version = contract.partition("@")
    return f"urn:routepilot:schema:artifact:{name}:v{version}"
