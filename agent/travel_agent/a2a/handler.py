"""Official A2A SDK RequestHandler adapter for RoutePilot TaskService."""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator

from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import Event
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard,
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetExtendedAgentCardRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigsRequest,
    ListTaskPushNotificationConfigsResponse,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskPushNotificationConfig,
    TaskState,
)
from a2a.utils.errors import (
    InvalidParamsError,
    PushNotificationNotSupportedError,
    UnsupportedOperationError,
)

from .models import A2AActor
from .registry import AgentRegistry, clone_card
from .service import TERMINAL_STATES, TaskService
from .store import clone_proto


def _actor(context: ServerCallContext) -> A2AActor:
    actor = context.state.get("routepilot_actor")
    if not isinstance(actor, A2AActor):
        raise UnsupportedOperationError(message="Authenticated RoutePilot context is required")
    return actor


def _page_offset(token: str) -> int:
    if not token:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii") + b"===").decode("ascii")
        offset = int(decoded)
    except (ValueError, UnicodeError) as exc:
        raise InvalidParamsError(message="Invalid pageToken") from exc
    if offset < 0:
        raise InvalidParamsError(message="Invalid pageToken")
    return offset


def _page_token(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii").rstrip("=")


def _project_task(task: Task, *, history_length: int | None, include_artifacts: bool) -> Task:
    projected = clone_proto(task)
    if history_length is not None:
        if history_length == 0:
            del projected.history[:]
        elif len(projected.history) > history_length:
            retained = [clone_proto(item) for item in projected.history[-history_length:]]
            del projected.history[:]
            projected.history.extend(retained)
    if not include_artifacts:
        del projected.artifacts[:]
    return projected


class RoutePilotA2ARequestHandler(RequestHandler):
    """Bind one curated Agent interface to a shared tenant-safe TaskService."""

    def __init__(
        self,
        agent_interface_id: str,
        registry: AgentRegistry,
        task_service: TaskService,
    ) -> None:
        self.agent_interface_id = agent_interface_id
        self.registry = registry
        self.task_service = task_service

    async def on_get_task(
        self,
        params: GetTaskRequest,
        context: ServerCallContext,
    ) -> Task | None:
        if not params.id:
            raise InvalidParamsError(message="Task id is required")
        record = await self.task_service.get_task(
            _actor(context), self.agent_interface_id, params.tenant, params.id
        )
        history_length = params.history_length if params.HasField("history_length") else None
        if history_length is not None and not 0 <= history_length <= 100:
            raise InvalidParamsError(message="historyLength must be between 0 and 100")
        return _project_task(
            record.task,
            history_length=history_length,
            include_artifacts=True,
        )

    async def on_list_tasks(
        self,
        params: ListTasksRequest,
        context: ServerCallContext,
    ) -> ListTasksResponse:
        page_size = params.page_size or 50
        if not 1 <= page_size <= 100:
            raise InvalidParamsError(message="pageSize must be between 1 and 100")
        if params.history_length < 0 or params.history_length > 100:
            raise InvalidParamsError(message="historyLength must be between 0 and 100")
        state = params.status if params.status != TaskState.TASK_STATE_UNSPECIFIED else None
        records = await self.task_service.list_tasks(
            _actor(context),
            self.agent_interface_id,
            params.tenant,
            context_id=params.context_id or None,
            state=state,
        )
        if params.HasField("status_timestamp_after"):
            timestamp_after = params.status_timestamp_after.ToDatetime()
            records = [
                record
                for record in records
                if record.updated_at is not None and record.updated_at > timestamp_after
            ]
        offset = _page_offset(params.page_token)
        page = records[offset : offset + page_size]
        next_offset = offset + len(page)
        next_token = _page_token(next_offset) if next_offset < len(records) else ""
        history_length = params.history_length
        return ListTasksResponse(
            tasks=[
                _project_task(
                    record.task,
                    history_length=history_length,
                    include_artifacts=params.include_artifacts,
                )
                for record in page
            ],
            next_page_token=next_token,
            page_size=len(page),
            total_size=len(records),
        )

    async def on_cancel_task(
        self,
        params: CancelTaskRequest,
        context: ServerCallContext,
    ) -> Task | None:
        if not params.id:
            raise InvalidParamsError(message="Task id is required")
        return await self.task_service.cancel_task(
            _actor(context), self.agent_interface_id, params.tenant, params.id
        )

    async def on_message_send(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
    ) -> Task | Message:
        return await self.task_service.send_message(
            _actor(context),
            self.agent_interface_id,
            params,
            requested_extensions=context.requested_extensions,
        )

    async def on_message_send_stream(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
    ) -> AsyncGenerator[Event, None]:
        streaming_params = clone_proto(params)
        streaming_params.configuration.return_immediately = True
        task = await self.task_service.send_message(
            _actor(context),
            self.agent_interface_id,
            streaming_params,
            requested_extensions=context.requested_extensions,
        )
        record = await self.task_service.get_task(
            _actor(context), self.agent_interface_id, params.tenant, task.id
        )
        yield clone_proto(record.task)
        async for event in self.task_service.subscribe(record, after_version=record.version):
            yield event

    async def on_subscribe_to_task(
        self,
        params: SubscribeToTaskRequest,
        context: ServerCallContext,
    ) -> AsyncGenerator[Event, None]:
        record = await self.task_service.get_task(
            _actor(context), self.agent_interface_id, params.tenant, params.id
        )
        if record.task.status.state in TERMINAL_STATES:
            raise UnsupportedOperationError(message="Cannot subscribe to a terminal Task")
        yield clone_proto(record.task)
        async for event in self.task_service.subscribe(record, after_version=record.version):
            yield event

    async def on_create_task_push_notification_config(
        self,
        params: TaskPushNotificationConfig,
        context: ServerCallContext,
    ) -> TaskPushNotificationConfig:
        del params, context
        raise PushNotificationNotSupportedError()

    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigRequest,
        context: ServerCallContext,
    ) -> TaskPushNotificationConfig:
        del params, context
        raise PushNotificationNotSupportedError()

    async def on_list_task_push_notification_configs(
        self,
        params: ListTaskPushNotificationConfigsRequest,
        context: ServerCallContext,
    ) -> ListTaskPushNotificationConfigsResponse:
        del params, context
        raise PushNotificationNotSupportedError()

    async def on_delete_task_push_notification_config(
        self,
        params: DeleteTaskPushNotificationConfigRequest,
        context: ServerCallContext,
    ) -> None:
        del params, context
        raise PushNotificationNotSupportedError()

    async def on_get_extended_agent_card(
        self,
        params: GetExtendedAgentCardRequest,
        context: ServerCallContext,
    ) -> AgentCard:
        del params
        _actor(context)
        return clone_card(self.registry.get(self.agent_interface_id).card)


__all__ = ["RoutePilotA2ARequestHandler"]
