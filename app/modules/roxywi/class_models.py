import re
from annotated_types import Gt, Le
from typing import Optional, Annotated, Union, Literal, Any, Dict, List

from shlex import quote
from pydantic_core import CoreSchema, core_schema
from pydantic import BaseModel, field_validator, StringConstraints, IPvAnyAddress, AnyUrl, root_validator, GetCoreSchemaHandler

DomainName = Annotated[str, StringConstraints(pattern=r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")]


class EscapedString(str):
    pattern = re.compile('[&;|$`]')

    @classmethod
    def validate(cls, field_value, info) -> str:
        if isinstance(field_value, str):
            if cls.pattern.search(field_value):
                return re.sub(cls.pattern, '', field_value)
            elif field_value == '':
                return field_value
            else:
                return quote(field_value.rstrip())

    @classmethod
    def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:

        return core_schema.chain_schema(
            [
                core_schema.with_info_plain_validator_function(
                    function=cls.validate,
                )
            ]
        )


class BaseResponse(BaseModel):
    status: str = 'Ok'


class IdResponse(BaseResponse):
    id: int


class IdDataResponse(IdResponse):
    data: str


class DataResponse(BaseModel):
    data: Union[list, dict]


class DataStrResponse(BaseModel):
    data: str


class ErrorResponse(BaseModel):
    status: str = 'failed'
    error: Union[str, list]


class UdpBackendConfig(BaseModel):
    backend_ip: Union[IPvAnyAddress, DomainName]
    port: Annotated[int, Gt(1), Le(65535)]
    weight: Annotated[int, Gt(0), Le(51)]


class UdpListenerRequest(BaseModel):
    name: EscapedString
    cluster_id: Optional[int] = None
    server_id: Optional[int] = None
    vip: Optional[str] = None
    port: Annotated[int, Gt(1), Le(65535)]
    group_id: int
    config: List[UdpBackendConfig]
    description: Optional[EscapedString] = None
    lb_algo: Literal['rr', 'wrr', 'lc', 'wlc', 'sh', 'dh', 'wlc', 'lblc']
    check_enabled: Optional[bool] = 1
    reconfigure: Optional[bool] = 0


class UserPost(BaseModel):
    username: EscapedString
    password: str
    email: EscapedString
    enabled: Optional[bool] = 1
    user_group: int
    role: Annotated[int, Gt(0), Le(4)] = 4


class UserPut(BaseModel):
    username: EscapedString
    email: EscapedString
    enabled: Optional[bool] = 1


class AddUserToGroup(BaseModel):
    role_id: Annotated[int, Gt(0), Le(4)]


class ServerRequest(BaseModel):
    hostname: EscapedString
    ip: Union[IPvAnyAddress, DomainName]
    enabled: Optional[bool] = 1
    type_ip: Optional[bool] = 0
    cred_id: int
    description: Optional[EscapedString] = None
    group_id: Optional[int] = None
    protected: Optional[bool] = 0
    master: Optional[int] = None
    port: Annotated[int, Gt(1), Le(65535)] = 22
    haproxy: Optional[bool] = 0
    nginx: Optional[bool] = 0
    apache: Optional[bool] = 0
    firewall_enable: Optional[bool] = 0
    scan_server: Optional[bool] = 1


class GroupQuery(BaseModel):
    group_id: Optional[int] = None


class GroupRequest(BaseModel):
    name: EscapedString
    description: Optional[EscapedString] = None


class CredRequest(BaseModel):
    name: EscapedString
    username: EscapedString
    password: Optional[EscapedString] = None
    key_enabled: Optional[bool] = 1
    group_id: Optional[int] = None


class CredUploadRequest(BaseModel):
    private_key: str
    passphrase: Optional[EscapedString] = None


class HAClusterServer(BaseModel):
    eth: EscapedString
    id: int
    ip: Union[IPvAnyAddress, DomainName]
    name: EscapedString
    master: Optional[bool] = 1


class HAClusterService(BaseModel):
    enabled: Optional[bool] = 0
    docker: Optional[bool] = 0


class HAClusterVIP(BaseModel):
    name: EscapedString
    use_src: Optional[bool] = 1
    vip: IPvAnyAddress
    return_master: Optional[bool] = 1
    virt_server: Optional[bool] = 1
    router_id: Optional[int] = None
    servers: Dict[int, HAClusterServer]


class HAClusterRequest(BaseModel):
    name: EscapedString
    description: Optional[EscapedString] = None
    return_master: Optional[bool] = 1
    servers: List[HAClusterServer]
    services: Dict[str, HAClusterService]
    syn_flood: Optional[bool] = 1
    use_src: Optional[bool] = 1
    vip: IPvAnyAddress
    virt_server: Optional[bool] = 1


class ConfigFileNameQuery(BaseModel):
    file_name: Optional[str] = None
    version: Optional[str] = None


class ConfigRequest(BaseModel):
    action: Literal['save', 'test', 'reload', 'restart']
    file_name: Optional[str] = None
    config_local_path: Optional[str] = None
    config: str


class LoginRequest(BaseModel):
    login: EscapedString
    password: EscapedString


class ChannelRequest(BaseModel):
    token: EscapedString
    channel: EscapedString
    group_id: Optional[int] = None


class ServerInstall(BaseModel):
    ip: Union[IPvAnyAddress, DomainName]
    master: Optional[bool] = 0
    name: EscapedString


class ServiceInstall(BaseModel):
    cluster_id: Optional[int] = None
    servers: List[ServerInstall]
    services: Dict[str, HAClusterService]
    checker: Optional[bool] = 0
    metrics: Optional[bool] = 0
    auto_start: Optional[bool] = 0
    syn_flood: Optional[bool] = 0


class Checker(BaseModel):
    server_id: int
    checker: Optional[bool] = 0
    metrics: Optional[bool] = 0
    auto_start: Optional[bool] = 0
    service: Optional[bool] = 1
    telegram_id: Optional[int] = 0
    slack_id: Optional[int] = 0
    pd_id: Optional[int] = 0
    mm_id: Optional[int] = 0
    email: Optional[int] = 1
    service_alert: Optional[int] = 1
    backend_alert: Optional[int] = 1
    maxconn_alert: Optional[int] = 1


class SettingsRequest(BaseModel):
    param: EscapedString
    value: EscapedString


class BackupRequest(BaseModel):
    cred_id: int
    server: Union[IPvAnyAddress, DomainName]
    rserver: Optional[Union[IPvAnyAddress, DomainName]] = None
    description: Optional[EscapedString] = None
    rpath: Optional[EscapedString] = None
    type: Optional[EscapedString] = None
    time: Optional[EscapedString] = None


class S3BackupRequest(BaseModel):
    server: Union[IPvAnyAddress, DomainName]
    s3_server: Optional[Union[IPvAnyAddress, DomainName]] = None
    bucket: EscapedString
    secret_key: Optional[EscapedString] = None
    access_key: Optional[EscapedString] = None
    time: Optional[EscapedString] = None
    description: Optional[EscapedString] = None
