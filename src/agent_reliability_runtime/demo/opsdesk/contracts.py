"""Project-owned argument/result shapes and field ownership, never authorization."""

from agent_reliability_runtime.core.contracts.domain import (
    Identifier,
    Record,
    Timestamp,
)
from agent_reliability_runtime.core.effects import ReceiptEnvelope

RUN_META = "agent-reliability-runtime/run-id"
DIGEST_META = "agent-reliability-runtime/action-digest"


class IncidentArgs(Record):
    incident_id: Identifier


class ServiceArgs(Record):
    service_id: Identifier


class NoteArgs(IncidentArgs):
    note: Identifier
    idempotency_key: Identifier


class RestartArgs(ServiceArgs):
    reason: Identifier
    idempotency_key: Identifier


class NotificationArgs(Record):
    channel: Identifier
    message: Identifier
    idempotency_key: Identifier


class Incident(IncidentArgs):
    service_id: Identifier
    summary: Identifier
    status: Identifier


class Service(ServiceArgs):
    status: Identifier


class Note(IncidentArgs):
    note_id: Identifier
    note: Identifier
    created_at: Timestamp


class Restart(Service):
    previous_status: Identifier
    reason: Identifier


class Notification(Record):
    notification_id: Identifier
    channel: Identifier
    message: Identifier
    created_at: Timestamp


INPUTS: dict[str, type[Record]] = {
    "get_incident": IncidentArgs,
    "get_service_status": ServiceArgs,
    "add_incident_note": NoteArgs,
    "restart_service": RestartArgs,
    "send_notification": NotificationArgs,
}
OUTPUTS: dict[str, type[Record]] = {
    "get_incident": Incident,
    "get_service_status": Service,
    "add_incident_note": ReceiptEnvelope,
    "restart_service": ReceiptEnvelope,
    "send_notification": ReceiptEnvelope,
}
RUNTIME_FIELDS = {
    "add_incident_note": {"idempotency_key"},
    "restart_service": {"idempotency_key"},
    "send_notification": {"idempotency_key"},
}


class DemoService(Record):
    service_id: Identifier
    status: Identifier


class DemoIncident(Record):
    incident_id: Identifier
    service_id: Identifier
    summary: Identifier
    status: Identifier


class DemoNotification(Record):
    notification_id: Identifier
    channel: Identifier
    message: Identifier
    created_at: Timestamp


class DemoIncidentNote(Record):
    note_id: Identifier
    incident_id: Identifier
    note: Identifier
    created_at: Timestamp


class DemoSeed(Record):
    incidents: list[DemoIncident]
    services: list[DemoService]
