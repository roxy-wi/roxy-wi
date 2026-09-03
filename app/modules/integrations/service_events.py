from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import app.modules.db.service_event as event_sql
from app.modules.db.db_model import ServiceAssignment


SUPPORTED_WORKER_SERVICES = frozenset({
    'checker', 'metrics', 'keep_alive', 'portscanner', 'smon', 'socket', 'automation'
})
SERVICE_IDS = {
    'haproxy': 1,
    'nginx': 2,
    'keepalived': 3,
    'apache': 4,
    'udp': 6,
}


class UnsupportedServiceEvent(ValueError):
    pass


class _EventBase(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: UUID
    type: str = Field(min_length=3, max_length=128)
    schema_version: Literal[1] = 1
    source: str = Field(min_length=1, max_length=64)


class WorkerHeartbeat(_EventBase):
    worker_id: str = Field(min_length=1, max_length=128)
    service: str = Field(min_length=1, max_length=64)
    instance_id: str | None = Field(default=None, max_length=128)
    status: Literal['starting', 'running', 'degraded', 'draining', 'stopped'] = 'running'
    hostname: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=64)
    started_at: datetime | None = None
    heartbeat_at: datetime
    ttl_seconds: int = Field(default=30, ge=10, le=300)
    active_assignments: int = Field(default=0, ge=0)
    capacity: int | None = Field(default=None, ge=1)
    group_ids: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator('service')
    @classmethod
    def supported_service(cls, value: str) -> str:
        if value not in SUPPORTED_WORKER_SERVICES:
            raise ValueError(f'unsupported worker service: {value}')
        return value

    @field_validator('group_ids')
    @classmethod
    def positive_unique_groups(cls, value: list[int]) -> list[int]:
        if any(group_id < 1 for group_id in value):
            raise ValueError('group_ids must contain positive integers')
        return sorted(set(value))


class CheckerStatusChanged(_EventBase):
    assignment_id: str = Field(min_length=1, max_length=255)
    assignment_revision: int = Field(ge=0)
    lease_epoch: int = Field(ge=0)
    sequence: int = Field(ge=0)
    group_id: int = Field(ge=1)
    server_id: int | None = Field(default=None, ge=1)
    server_address: str = Field(min_length=1, max_length=255)
    port: int = Field(default=0, ge=0, le=65535)
    service: Literal['haproxy', 'nginx', 'keepalived', 'apache', 'udp']
    object_type: str = Field(min_length=1, max_length=64)
    object_name: str | None = Field(default=None, max_length=255)
    previous_status: str | None = Field(default=None, max_length=64)
    current_status: str = Field(min_length=1, max_length=64)
    level: Literal['info', 'warning', 'critical', 'error']
    message: str = Field(min_length=1, max_length=4096)
    alert_type: Literal['service', 'backend', 'maxconn']
    observed_at: datetime
    notify: bool = True


class MetricsSampleCollected(_EventBase):
    assignment_id: str = Field(min_length=1, max_length=255)
    assignment_revision: int = Field(ge=1)
    lease_epoch: int = Field(ge=0)
    sequence: int = Field(ge=1)
    group_id: int = Field(ge=1)
    server_id: int = Field(ge=1)
    server_address: str = Field(min_length=1, max_length=255)
    service: Literal['haproxy', 'nginx', 'apache', 'waf']
    observed_at: datetime
    values: dict[str, int]

    @model_validator(mode='after')
    def validate_values(self):
        expected = {
            'haproxy': {
                'curr_con', 'cur_ssl_con', 'sess_rate', 'max_sess_rate',
                'http_2xx', 'http_3xx', 'http_4xx', 'http_5xx',
            },
            'nginx': {'conn'},
            'apache': {'conn'},
            'waf': {'conn'},
        }[self.service]
        if set(self.values) != expected:
            raise ValueError(f'{self.service} metric fields must be {sorted(expected)}')
        if any(isinstance(value, bool) or value < 0 for value in self.values.values()):
            raise ValueError('metric values must be non-negative integers')
        return self


class PortScannerPort(BaseModel):
    model_config = ConfigDict(extra='forbid')

    port: int = Field(ge=1, le=65535)
    protocol: Literal['tcp'] = 'tcp'
    service_name: str = Field(default='unknown', min_length=1, max_length=255)


class PortScannerScanCompleted(_EventBase):
    assignment_id: str = Field(min_length=1, max_length=255)
    assignment_revision: int = Field(ge=1)
    lease_epoch: int = Field(ge=0)
    sequence: int = Field(ge=1)
    group_id: int = Field(ge=1)
    server_id: int = Field(ge=1)
    server_address: str = Field(min_length=1, max_length=255)
    service: Literal['portscanner']
    observed_at: datetime
    duration_seconds: float = Field(ge=0, le=3600)
    ports: list[PortScannerPort] = Field(max_length=65535)

    @field_validator('ports')
    @classmethod
    def unique_ports(cls, value: list[PortScannerPort]) -> list[PortScannerPort]:
        identities = [(port.protocol, port.port) for port in value]
        if len(identities) != len(set(identities)):
            raise ValueError('port snapshot contains duplicate ports')
        return sorted(value, key=lambda port: (port.port, port.protocol))


@dataclass(frozen=True)
class ProcessResult:
    kind: Literal['worker_heartbeat', 'status_changed', 'metric_sample', 'port_snapshot']
    created: bool


def _mapping(payload: bytes | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError('service event payload must be a JSON object')
    return parsed


def _model_data(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump()
    data['event_id'] = str(data['event_id'])
    return data


def process_event(payload: bytes | str | Mapping[str, Any]) -> ProcessResult:
    raw = _mapping(payload)
    event_type = raw.get('type')
    if isinstance(event_type, str) and event_type.endswith('.worker.heartbeat'):
        heartbeat = WorkerHeartbeat.model_validate(raw)
        expected_source = event_type.split('.', 1)[0]
        if heartbeat.service != expected_source or heartbeat.source != expected_source:
            raise ValueError('worker heartbeat source, service and routing type must match')
        data = _model_data(heartbeat)
        data['expires_at'] = heartbeat.heartbeat_at + timedelta(seconds=heartbeat.ttl_seconds)
        event_sql.record_worker_heartbeat(data)
        return ProcessResult(kind='worker_heartbeat', created=True)

    if event_type == 'checker.status.changed':
        event = CheckerStatusChanged.model_validate(raw)
        if event.source != 'checker':
            raise ValueError('checker.status.changed must have source=checker')
        assignment = ServiceAssignment.get_or_none(
            ServiceAssignment.assignment_id == event.assignment_id
        )
        if assignment is not None:
            if event.assignment_revision < assignment.revision:
                return ProcessResult(kind='status_changed', created=False)
            if event.assignment_revision > assignment.revision:
                raise ValueError('checker event revision is newer than desired state')
            desired_payload = json.loads(assignment.payload)
            target = desired_payload.get('target', {})
            expected = (
                int(assignment.user_group),
                assignment.server_id,
                assignment.service,
                target.get('address'),
            )
            actual = (
                event.group_id,
                event.server_id,
                event.service,
                event.server_address,
            )
            if actual != expected:
                raise ValueError('checker event target does not match its desired assignment')
        data = _model_data(event)
        data['history_service'] = 'Checker'
        return ProcessResult(kind='status_changed', created=event_sql.store_status_event(data))

    if event_type == 'metrics.sample.collected':
        event = MetricsSampleCollected.model_validate(raw)
        if event.source != 'metrics':
            raise ValueError('metrics.sample.collected must have source=metrics')
        assignment = ServiceAssignment.get_or_none(
            ServiceAssignment.assignment_id == event.assignment_id
        )
        if assignment is None or assignment.target_service != 'metrics':
            raise ValueError('unknown Metrics assignment')
        if event.assignment_revision < assignment.revision:
            return ProcessResult(kind='metric_sample', created=False)
        if event.assignment_revision > assignment.revision:
            raise ValueError('Metrics event revision is newer than desired state')
        desired_payload = json.loads(assignment.payload)
        target = desired_payload.get('target', {})
        expected = (
            int(assignment.user_group), assignment.server_id, assignment.service, target.get('address')
        )
        actual = (event.group_id, event.server_id, event.service, event.server_address)
        if actual != expected:
            raise ValueError('Metrics event target does not match its desired assignment')
        data = _model_data(event)
        return ProcessResult(kind='metric_sample', created=event_sql.store_metric_sample(data))

    if event_type == 'portscanner.scan.completed':
        event = PortScannerScanCompleted.model_validate(raw)
        if event.source != 'portscanner':
            raise ValueError('portscanner.scan.completed must have source=portscanner')
        assignment = ServiceAssignment.get_or_none(
            ServiceAssignment.assignment_id == event.assignment_id
        )
        if assignment is None or assignment.target_service != 'portscanner':
            raise ValueError('unknown Port Scanner assignment')
        if event.assignment_revision < assignment.revision:
            return ProcessResult(kind='port_snapshot', created=False)
        if event.assignment_revision > assignment.revision:
            raise ValueError('Port Scanner event revision is newer than desired state')
        desired_payload = json.loads(assignment.payload)
        target = desired_payload.get('target', {})
        expected = (
            int(assignment.user_group),
            assignment.server_id,
            assignment.service,
            target.get('address'),
        )
        actual = (event.group_id, event.server_id, event.service, event.server_address)
        if actual != expected:
            raise ValueError('Port Scanner event target does not match its desired assignment')
        settings = desired_payload.get('settings', {})
        data = _model_data(event)
        data['notify'] = bool(settings.get('notify', False))
        data['history'] = bool(settings.get('history', False))
        return ProcessResult(
            kind='port_snapshot', created=event_sql.store_portscanner_snapshot(data)
        )

    raise UnsupportedServiceEvent(f'unsupported service event type: {event_type!r}')


def deliver_pending_notifications(limit: int = 100) -> int:
    """Deliver persisted notifications; failures remain in the outbox for retry."""
    from app.modules.tools import alerting

    delivered = 0
    for delivery in event_sql.claim_pending_deliveries(limit=limit):
        event = delivery.event_id
        payload = json.loads(event.payload)
        try:
            if payload['service'] == 'portscanner':
                alerting.portscanner_alert_routing(
                    payload['server_address'],
                    payload['group_id'],
                    payload['level'],
                    payload['message'],
                )
            else:
                alerting.alert_routing(
                    payload['server_address'],
                    SERVICE_IDS[payload['service']],
                    payload['group_id'],
                    payload['level'],
                    payload['message'],
                    payload['alert_type'],
                )
        except Exception as exc:
            event_sql.mark_delivery_failed(delivery.id, str(exc))
        else:
            event_sql.mark_delivery_succeeded(delivery.id)
            delivered += 1
    return delivered
