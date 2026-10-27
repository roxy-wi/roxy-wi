from typing import Literal
from ipaddress import ip_address

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AGENT_PATTERN = r'^(ocf:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+|systemd:[A-Za-z0-9_.@-]+|stonith:[A-Za-z0-9_.-]+)$'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Member(StrictModel):
    server_id: int = Field(gt=0)
    name: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_.-]{0,62}$')
    address: str
    nodeid: int = Field(gt=0, le=2147483647)

    @field_validator('address')
    @classmethod
    def valid_address(cls, value):
        import re
        try:
            return str(ip_address(value))
        except ValueError:
            if re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.?', value):
                return value
            raise ValueError('Expected an IP address or DNS host name')


class ClusterCreate(StrictModel):
    name: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,62}$')
    description: str = Field(default='', max_length=2000)
    members: list[Member] = Field(min_length=2, max_length=32)

    @model_validator(mode='after')
    def unique_members(self):
        for attr in ('server_id', 'name', 'address', 'nodeid'):
            values = [getattr(member, attr) for member in self.members]
            if len(set(values)) != len(values):
                raise ValueError(f'Duplicate member {attr}')
        return self


class Candidate(StrictModel):
    xml: str = Field(min_length=1, max_length=1024 * 1024)
    base_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class Action(StrictModel):
    action: Literal['standby', 'online', 'maintenance-on', 'maintenance-off',
                    'move', 'clear', 'cleanup', 'enable', 'disable', 'restart']
    target: str = Field(default='', pattern=r'^[A-Za-z0-9_.:-]{0,128}$')
    node: str = Field(default='', pattern=r'^[A-Za-z0-9_.-]{0,63}$')


class Bootstrap(StrictModel):
    confirm: str
    syn_flood: bool = Field(default=False, strict=True)
    fence_pve: bool = Field(default=False, strict=True)


class Discovery(StrictModel):
    server_id: int = Field(gt=0)


class WitnessInstall(Discovery):
    docker: bool = Field(default=False, strict=True)


class WitnessMigration(StrictModel):
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm: str


class WitnessRecovery(StrictModel):
    token: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirm: str


class Adoption(ClusterCreate):
    seed_server_id: int = Field(gt=0)
    base_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    topology_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class CorosyncCandidate(ClusterCreate):
    token: int = Field(default=1000, ge=1000, le=30000)
    qdevice_server_id: int | None = Field(default=None, gt=0)


class WitnessTrust(WitnessMigration):
    target_id: int = Field(gt=0)
    rotate_ca: bool = Field(default=False,strict=True)


class TransportMigration(WitnessMigration):
    token: int = Field(default=1500,ge=1000,le=30000)


class ClusterConfirmation(StrictModel):
    confirm: str
