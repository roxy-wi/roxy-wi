"""Versioned, credential-free Keepalived probe contract shared with Checker."""
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ProbeModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class VrrpInstance(ProbeModel):
    name: str = Field(min_length=1, max_length=255, pattern=r'^[^\x00-\x1f\x7f]+$')
    state: Literal['MASTER', 'BACKUP', 'FAULT', 'INIT']


class KeepalivedSnapshot(ProbeModel):
    service: Literal['UP', 'DOWN']
    instances: list[VrrpInstance] = Field(max_length=1024)

    @model_validator(mode='after')
    def consistent_instances(self) -> 'KeepalivedSnapshot':
        names = [instance.name for instance in self.instances]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate VRRP instance')
        if (self.service == 'UP') != bool(self.instances):
            raise ValueError('Running Keepalived must report its VRRP instances')
        return self


class KeepalivedProbeRequest(ProbeModel):
    type: Literal['keepalived.probe.request'] = 'keepalived.probe.request'
    schema_version: Literal[1] = 1
    source: Literal['checker'] = 'checker'
    request_id: UUID
    assignment_id: str = Field(pattern=r'^keepalived:server-[1-9][0-9]*$', max_length=255)
    revision: int = Field(ge=1)
    lease_epoch: int = Field(ge=1)
    group_id: int = Field(ge=1)
    expires_at: AwareDatetime


class KeepalivedProbeResult(ProbeModel):
    type: Literal['keepalived.probe.result'] = 'keepalived.probe.result'
    schema_version: Literal[1] = 1
    source: Literal['roxy-wi'] = 'roxy-wi'
    request_id: UUID
    assignment_id: str = Field(max_length=255)
    revision: int = Field(ge=1)
    lease_epoch: int = Field(ge=1)
    snapshot: KeepalivedSnapshot | None = None
    error: Literal['expired', 'assignment_unavailable', 'probe_failed'] | None = None

    @model_validator(mode='after')
    def result_or_error(self) -> 'KeepalivedProbeResult':
        if (self.snapshot is None) == (self.error is None):
            raise ValueError('Expected either a snapshot or a probe error')
        return self
