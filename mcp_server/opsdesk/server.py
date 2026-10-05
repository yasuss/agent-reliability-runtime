"""Exactly five typed OpsDesk tools, backed only by fictional demo tables."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, Tool, ToolAnnotations
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import SQLAlchemyError

from agent_reliability_runtime.contracts.domain import Identifier
from agent_reliability_runtime.mcp.contracts import (
    INPUTS,
    Incident,
    Note,
    Notification,
    ReceiptEnvelope,
    Restart,
    Service,
)
from agent_reliability_runtime.persistence.schema import (
    demo_incident_notes as notes,
)
from agent_reliability_runtime.persistence.schema import (
    demo_incidents as incidents,
)
from agent_reliability_runtime.persistence.schema import (
    demo_notifications as notifications,
)
from agent_reliability_runtime.persistence.schema import (
    demo_services as services,
)
from mcp_server.opsdesk.effects import apply_effect, row_id


class OpsDeskServer(MCPServer[None]):
    """Validate raw arguments before SDK coercion/extra-field filtering."""

    async def list_tools(self) -> list[Tool]:
        tools = await super().list_tools()
        return [
            t.model_copy(update={"input_schema": INPUTS[t.name].model_json_schema()})
            for t in tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context[None, Any] | None = None,
    ) -> CallToolResult | InputRequiredResult:
        if name not in INPUTS:
            raise ToolError("unknown OpsDesk tool")
        try:
            INPUTS[name].model_validate(arguments)
        except ValidationError:
            invalid = True
        else:
            invalid = False
        if invalid:
            raise ToolError("invalid OpsDesk arguments")
        return await super().call_tool(name, arguments, context)


def create_server(
    engine: Engine, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> OpsDeskServer:
    server = OpsDeskServer("OpsDesk", version="0.1.0")
    reads = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    writes = ToolAnnotations(
        read_only_hint=False, idempotent_hint=False, open_world_hint=False
    )

    @server.tool(annotations=reads)
    def get_incident(incident_id: Identifier) -> Incident:
        """Read details of one fictional incident for investigation or diagnosis.

        Read-only; never changes state.
        """
        try:
            with engine.connect() as con:
                row = (
                    con.execute(
                        select(incidents).where(incidents.c.incident_id == incident_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ToolError("fictional incident not found")
                return Incident.model_validate(dict(row))
        except (SQLAlchemyError, ValidationError):
            pass
        raise ToolError("fictional incident data unavailable")

    @server.tool(annotations=reads)
    def get_service_status(service_id: Identifier) -> Service:
        """Read the current status of one fictional service.

        Use to verify service state before answering or deciding whether an
        explicitly requested remediation is supported. Read-only; never changes state.
        """
        try:
            with engine.connect() as con:
                row = (
                    con.execute(
                        select(services).where(services.c.service_id == service_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ToolError("fictional service not found")
                return Service.model_validate(dict(row))
        except (SQLAlchemyError, ValidationError):
            pass
        raise ToolError("fictional service data unavailable")

    @server.tool(annotations=writes)
    def add_incident_note(
        incident_id: Identifier,
        note: Identifier,
        idempotency_key: Identifier,
        ctx: Context[None, Any],
    ) -> ReceiptEnvelope:
        """Add a note to an incident only when the user explicitly requests
        recording or updating the incident. This is a side effect and the trusted
        runtime requires exact approval. Do not use merely to investigate, explain
        findings, or request approval.
        """
        try:
            value = Note(
                note_id=row_id("add_incident_note", idempotency_key),
                incident_id=incident_id,
                note=note,
                created_at=clock(),
            )

            def mutate(con: Connection) -> Note:
                if (
                    con.scalar(
                        select(incidents.c.incident_id).where(
                            incidents.c.incident_id == incident_id
                        )
                    )
                    is None
                ):
                    raise ToolError("fictional incident not found")
                con.execute(notes.insert(), value.model_dump())
                return value

            return apply_effect(
                engine, "add_incident_note", idempotency_key, ctx, mutate, clock()
            )
        except (SQLAlchemyError, ValidationError):
            pass
        raise ToolError("fictional note rejected or data unavailable")

    @server.tool(annotations=writes)
    def restart_service(
        service_id: Identifier,
        reason: Identifier,
        idempotency_key: Identifier,
        ctx: Context[None, Any],
    ) -> ReceiptEnvelope:
        """Restart a service only when the user explicitly requests remediation/restart
        and current evidence/status support it. This is a side effect and the trusted
        runtime requires exact approval. For investigation-only requests, explain
        the restart/approval as a next step instead of calling this tool.
        """
        try:

            def mutate(con: Connection) -> Restart:
                previous = con.scalar(
                    select(services.c.status)
                    .where(services.c.service_id == service_id)
                    .with_for_update()
                )
                if previous is None:
                    raise ToolError("fictional service not found")
                value = Restart(
                    service_id=service_id,
                    previous_status=previous,
                    status="healthy",
                    reason=reason,
                )
                con.execute(
                    services.update()
                    .where(services.c.service_id == service_id)
                    .values(status="healthy")
                )
                return value

            return apply_effect(
                engine, "restart_service", idempotency_key, ctx, mutate, clock()
            )
        except (SQLAlchemyError, ValidationError):
            pass
        raise ToolError("fictional restart data unavailable")

    @server.tool(annotations=writes)
    def send_notification(
        channel: Identifier,
        message: Identifier,
        idempotency_key: Identifier,
        ctx: Context[None, Any],
    ) -> ReceiptEnvelope:
        """Create a fictional notification only when the user explicitly requests a
        notification/message. This is a side effect and the trusted runtime requires
        exact approval. Do not use it merely to summarize an investigation or to
        request approval for another action.
        """
        try:
            value = Notification(
                notification_id=row_id("send_notification", idempotency_key),
                channel=channel,
                message=message,
                created_at=clock(),
            )

            def mutate(con: Connection) -> Notification:
                con.execute(notifications.insert(), value.model_dump())
                return value

            return apply_effect(
                engine, "send_notification", idempotency_key, ctx, mutate, clock()
            )
        except (SQLAlchemyError, ValidationError):
            pass
        raise ToolError("fictional notification rejected or data unavailable")

    return server
