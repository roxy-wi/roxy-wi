import re
from annotated_types import Gt, Le
from typing import Optional, Annotated, Union, Literal, Any, Dict, List

from shlex import quote
from pydantic_core import CoreSchema, core_schema
from pydantic import BaseModel, Base64Str, StringConstraints, IPvAnyAddress, GetCoreSchemaHandler, AnyUrl

DomainName = Annotated[str, StringConstraints(pattern=r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")]


class EscapedString(str):
    pattern = re.compile('[&;|$`]')

    @classmethod
    def validate(cls, field_value, info) -> str:
        if isinstance(field_value, str):
            if cls.pattern.search(field_value):
                return re.sub(cls.pattern, '', field_value)
            elif '..' in field_value:
                raise ValueError('nice try')
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


class IdStrResponse(BaseResponse):
    id: str


class IdDataResponse(IdResponse):
    data: str


class IdDataStrResponse(IdStrResponse):
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
    delay_loop: Optional[int] = 10
    delay_before_retry: Optional[int] = 10
    retry: Optional[int] = 3


class UserPost(BaseModel):
    username: EscapedString
    password: EscapedString
    email: EscapedString
    enabled: Optional[bool] = 1
    group_id: Optional[int] = 0
    role_id: Annotated[int, Gt(0), Le(4)] = 4


class UserPut(BaseModel):
    username: EscapedString
    password: Optional[EscapedString] = ''
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
    master: Optional[int] = 0
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
    shared: Optional[int] = 0


class CredUploadRequest(BaseModel):
    private_key: Union[Base64Str, str]
    passphrase: Optional[EscapedString] = None


class HAClusterServer(BaseModel):
    eth: EscapedString
    id: int
    master: Optional[bool] = 1


class HAClusterServersRequest(BaseModel):
    servers: List[HAClusterServer]


class HAClusterService(BaseModel):
    enabled: Optional[bool] = 0
    docker: Optional[bool] = 0


class HAClusterVIP(BaseModel):
    use_src: Optional[bool] = 1
    vip: IPvAnyAddress
    return_master: Optional[bool] = 1
    virt_server: Optional[bool] = 1
    servers: List[HAClusterServer]


class HAClusterRequest(BaseModel):
    name: EscapedString
    description: Optional[EscapedString] = None
    return_master: Optional[bool] = 1
    servers: Optional[List[HAClusterServer]] = None
    services: Dict[str, HAClusterService]
    syn_flood: Optional[bool] = 1
    use_src: Optional[bool] = 1
    vip: Optional[IPvAnyAddress] = None
    virt_server: Optional[bool] = 1
    reconfigure: Optional[bool] = 0


class ConfigFileNameQuery(BaseModel):
    file_path: Optional[str] = None
    version: Optional[str] = None


class VersionsForDelete(BaseModel):
    versions: List[str]


class ConfigRequest(BaseModel):
    action: Literal['save', 'test', 'reload', 'restart']
    file_path: Optional[str] = None
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
    id: int
    master: Optional[bool] = 0


class ServiceInstall(BaseModel):
    cluster_id: Optional[int] = None
    servers: Optional[List[ServerInstall]] = None
    services: Optional[Dict[str, HAClusterService]] = None
    checker: Optional[bool] = 0
    metrics: Optional[bool] = 0
    auto_start: Optional[bool] = 0
    syn_flood: Optional[bool] = 0
    docker: Optional[bool] = 0


class Checker(BaseModel):
    checker: Optional[bool] = 0
    metrics: Optional[bool] = 0
    auto_start: Optional[bool] = 0
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
    server_id: int
    rserver: Optional[Union[IPvAnyAddress, DomainName]] = None
    description: Optional[EscapedString] = None
    rpath: Optional[EscapedString] = None
    type: Literal['backup', 'synchronization'] = None
    time: Literal['hourly', 'daily', 'weekly', 'monthly'] = None


class S3BackupRequest(BaseModel):
    server_id: int
    s3_server: Optional[Union[IPvAnyAddress, AnyUrl]] = None
    bucket: EscapedString
    secret_key: Optional[EscapedString] = None
    access_key: Optional[EscapedString] = None
    time: Literal['hourly', 'daily', 'weekly', 'monthly'] = None
    description: Optional[EscapedString] = None


class GitBackupRequest(BaseModel):
    server_id: int
    service_id: int
    init: Optional[bool] = 0
    repo: Optional[EscapedString] = None
    branch: Optional[EscapedString] = 'main'
    time: Optional[EscapedString] = 'weekly'
    cred_id: Optional[int] = None
    description: Optional[EscapedString] = None


class PortScannerRequest(BaseModel):
    enabled: Optional[bool] = 1
    history: Optional[bool] = 1
    notify: Optional[bool] = 1


class SSLCertUploadRequest(BaseModel):
    server_ip: Union[IPvAnyAddress, DomainName]
    name: EscapedString
    cert: EscapedString


class SavedServerRequest(BaseModel):
    server: EscapedString
    description: Optional[EscapedString] = None


class HaproxyBinds(BaseModel):
    ip: Optional[str] = None
    port: Annotated[int, Gt(1), Le(65535)]


class HaproxyHeaders(BaseModel):
    path: Literal['http-request', 'http-response']
    name: str
    method: Literal['add-header', 'set-header', 'del-header', 'replace-header', 'pass-header']
    value: Optional[str] = None


class HaproxyAcls(BaseModel):
    acl_if: int
    acl_then: int
    acl_then_value: Optional[str] = None
    acl_value: str


class HaproxyBackendServer(BaseModel):
    server: Union[IPvAnyAddress, DomainName]
    port: Annotated[int, Gt(1), Le(65535)]
    port_check: Annotated[int, Gt(1), Le(65535)]
    maxconn: Optional[int] = 2000
    send_proxy: Optional[bool] = 0
    backup: Optional[bool] = 0


class HaproxyCookie(BaseModel):
    dynamic: str
    dynamicKey: str
    domain: Optional[str] = None
    name: Optional[str] = None
    nocache: Optional[str] = None
    postonly: Optional[str] = None
    prefix: Optional[str] = None
    rewrite: Optional[str] = None


class HaproxyHealthCheck(BaseModel):
    check: str
    domain: Optional[str] = None
    path: str


class HaproxySSL(BaseModel):
    cert: str
    ssl_check_backend: Optional[bool] = 1


class HaproxyServersCheck(BaseModel):
    check_enabled: Optional[bool] = 1
    fall: Optional[int] = 5
    rise: Optional[int] = 2
    inter: Optional[int] = 2000


class HaproxyCircuitBreaking(BaseModel):
    observe: Literal['layer7', 'layer4']
    error_limit: int
    on_error: Literal['mark-down', 'fastinter', 'fail-check', 'sudden-death']


class HaproxyConfigRequest(BaseModel):
    balance: Optional[Literal['roundrobin', 'source', 'leastconn', 'first', 'rdp-cookie', 'uri', 'uri whole', 'static-rr']] = None
    mode: Literal['tcp', 'http'] = 'http'
    type: Literal['listen', 'frontend', 'backend']
    name: EscapedString
    option: Optional[str] = None
    maxconn: Optional[int] = 2000
    waf: Optional[bool] = 0
    binds: List[HaproxyBinds]
    headers: List[HaproxyHeaders] = None
    acls: List[HaproxyAcls] = None
    backend_servers: List[HaproxyBackendServer] = None
    blacklist: Optional[str] = ''
    whitelist: Optional[str] = ''
    ssl: Optional[HaproxySSL] = None
    cache: Optional[bool] = 0
    compression: Optional[bool] = 0
    cookie: Optional[HaproxyCookie] = None
    health_check: Optional[HaproxyHealthCheck] = None
    servers_check: Optional[HaproxyServersCheck] = None
    ssl_offloading: Optional[bool] = 0
    redispatch: Optional[bool] = 0
    forward_for: Optional[bool] = 0
    slow_attack: Optional[bool] = 0
    ddos: Optional[bool] = 0
    antibot: Optional[bool] = 0
    backends: Optional[str] = None
    circuit_breaking: Optional[HaproxyCircuitBreaking] = None
    action: Optional[Literal['save', 'test', 'reload', 'restart']] = "save"


class HaproxyUserListUser(BaseModel):
    user: str
    password: str
    group: Optional[str] = ''


class HaproxyUserListRequest(BaseModel):
    name: EscapedString
    type: Literal['userlist']
    userlist_users: Optional[List[HaproxyUserListUser]] = ''
    userlist_groups: Optional[List[str]] = ''
    action: Optional[Literal['save', 'test', 'reload', 'restart']] = "save"


class HaproxyPeers(BaseModel):
    name: str
    ip: Union[IPvAnyAddress, DomainName]
    port: Annotated[int, Gt(1), Le(65535)]


class HaproxyPeersRequest(BaseModel):
    name: EscapedString
    type: Literal['peers']
    peers: List[HaproxyPeers]
    action: Optional[Literal['save', 'test', 'reload', 'restart']] = "save"


class GenerateConfigRequest(BaseModel):
    generate: Optional[bool] = 0


class HaproxyGlobalRequest(BaseModel):
    log: Optional[List[str]] = ['127.0.0.1 local', '127.0.0.1 local1 notice']
    chroot: Optional[str] = '/var/lib/haproxy'
    pidfile: Optional[str] = '/var/run/haproxy.pid'
    maxconn: Optional[int] = 5000
    user: Optional[str] = 'haproxy'
    group: Optional[str] = 'haproxy'
    daemon: Optional[bool] = 1
    socket: Optional[List[str]] = ['*:1999 level admin', '/var/run/haproxy.sock mode 600 level admin', '/var/lib/haproxy/stats']
    type: Optional[Literal['global']] = 'global'
    option: Optional[str] = ''
    action: Optional[Literal['save', 'test', 'reload', 'restart']] = "save"


class HaproxyDefaultsTimeout(BaseModel):
    http_request: Optional[int] = 10
    queue: Optional[int] = 60
    connect: Optional[int] = 10
    client: Optional[int] = 60
    server: Optional[int] = 60
    check: Optional[int] = 10
    http_keep_alive: Optional[int] = 10


class HaproxyDefaultsRequest(BaseModel):
    log: Optional[str] = 'global'
    retries: Optional[int] = 3
    timeout: Optional[HaproxyDefaultsTimeout] = HaproxyDefaultsTimeout().model_dump(mode='json')
    option: Optional[str] = ''
    maxconn: Optional[int] = 5000
    type: Optional[Literal['defaults']] = 'defaults'
    action: Optional[Literal['save', 'test', 'reload', 'restart']] = "save"
