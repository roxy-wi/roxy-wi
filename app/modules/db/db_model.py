from peewee import *
from playhouse.migrate import *
from datetime import datetime

import modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()
mysql_enable = get_config.get_config_var('mysql', 'enable')

if mysql_enable == '1':
    mysql_user = get_config.get_config_var('mysql', 'mysql_user')
    mysql_password = get_config.get_config_var('mysql', 'mysql_password')
    mysql_db = get_config.get_config_var('mysql', 'mysql_db')
    mysql_host = get_config.get_config_var('mysql', 'mysql_host')
    mysql_port = get_config.get_config_var('mysql', 'mysql_port')
    conn = MySQLDatabase(mysql_db, user=mysql_user, password=mysql_password, host=mysql_host, port=int(mysql_port))
    migrator = MySQLMigrator(conn)
else:
    db = "/var/lib/roxy-wi/roxy-wi.db"
    conn = SqliteDatabase(db, pragmas={'timeout': 1000, 'foreign_keys': 1})
    migrator = SqliteMigrator(conn)


class BaseModel(Model):
    class Meta:
        database = conn


class User(BaseModel):
    user_id = AutoField(column_name='id')
    username = CharField(constraints=[SQL('UNIQUE')])
    email = CharField(constraints=[SQL('UNIQUE')])
    password = CharField(null=True)
    role = CharField()
    groups = CharField()
    ldap_user = IntegerField(constraints=[SQL('DEFAULT "0"')])
    activeuser = IntegerField(constraints=[SQL('DEFAULT "1"')])
    user_services = CharField(constraints=[SQL('DEFAULT "1 2 3 4"')])
    last_login_date = DateTimeField(constraints=[SQL('DEFAULT "0000-00-00 00:00:00"')])
    last_login_ip = CharField(null=True)

    class Meta:
        table_name = 'user'


class Server(BaseModel):
    server_id = AutoField(column_name='id')
    hostname = CharField()
    ip = CharField(constraints=[SQL('UNIQUE')])
    groups = CharField()
    type_ip = IntegerField(constraints=[SQL('DEFAULT 0')])
    enable = IntegerField(constraints=[SQL('DEFAULT 1')])
    master = IntegerField(constraints=[SQL('DEFAULT 0')])
    cred = IntegerField(constraints=[SQL('DEFAULT 1')])
    alert = IntegerField(constraints=[SQL('DEFAULT 0')])
    metrics = IntegerField(constraints=[SQL('DEFAULT 0')])
    port = IntegerField(constraints=[SQL('DEFAULT 22')])
    desc = CharField(null=True)
    active = IntegerField(constraints=[SQL('DEFAULT 0')])
    keepalived = IntegerField(constraints=[SQL('DEFAULT 0')])
    nginx = IntegerField(constraints=[SQL('DEFAULT 0')])
    haproxy = IntegerField(constraints=[SQL('DEFAULT 0')])
    pos = IntegerField(constraints=[SQL('DEFAULT 0')])
    nginx_active = IntegerField(constraints=[SQL('DEFAULT 0')])
    firewall_enable = IntegerField(constraints=[SQL('DEFAULT 0')])
    nginx_alert = IntegerField(constraints=[SQL('DEFAULT 0')])
    protected = IntegerField(constraints=[SQL('DEFAULT 0')])
    nginx_metrics = IntegerField(constraints=[SQL('DEFAULT 0')])
    keepalived_active = IntegerField(constraints=[SQL('DEFAULT 0')])
    keepalived_alert = IntegerField(constraints=[SQL('DEFAULT 0')])
    apache = IntegerField(constraints=[SQL('DEFAULT 0')])
    apache_active = IntegerField(constraints=[SQL('DEFAULT 0')])
    apache_alert = IntegerField(constraints=[SQL('DEFAULT 0')])
    apache_metrics = IntegerField(constraints=[SQL('DEFAULT 0')])

    class Meta:
        table_name = 'servers'


class Role(BaseModel):
    role_id = AutoField(column_name='id')
    name = CharField(constraints=[SQL('UNIQUE')])
    description = CharField()

    class Meta:
        table_name = 'role'


class Telegram(BaseModel):
    id = AutoField()
    token = CharField()
    chanel_name = CharField()
    groups = IntegerField()

    class Meta:
        table_name = 'telegram'


class Slack(BaseModel):
    id = AutoField()
    token = CharField()
    chanel_name = CharField()
    groups = IntegerField()

    class Meta:
        table_name = 'slack'


class PD(BaseModel):
    id = AutoField()
    token = CharField()
    chanel_name = CharField()
    groups = IntegerField()

    class Meta:
        table_name = 'pd'


class UUID(BaseModel):
    user_id = IntegerField()
    uuid = CharField()
    exp = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'uuid'
        primary_key = False


class Token(BaseModel):
    user_id = IntegerField()
    token = CharField()
    exp = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'token'
        primary_key = False


class ApiToken(BaseModel):
    token = CharField()
    user_name = CharField()
    user_group_id = IntegerField()
    user_role = IntegerField()
    create_date = DateTimeField(default=datetime.now)
    expire_date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'api_tokens'
        primary_key = False


class Setting(BaseModel):
    param = CharField()
    value = CharField(null=True)
    section = CharField()
    desc = CharField()
    group = IntegerField(null=True, constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'settings'
        primary_key = False
        constraints = [SQL('UNIQUE (param, `group`)')]


class Groups(BaseModel):
    group_id = AutoField(column_name='id')
    name = CharField(constraints=[SQL('UNIQUE')])
    description = CharField(null=True)

    class Meta:
        table_name = 'groups'


class UserGroups(BaseModel):
    user_id = IntegerField()
    user_group_id = IntegerField()
    user_role_id = IntegerField()

    class Meta:
        table_name = 'user_groups'
        primary_key = False
        constraints = [SQL('UNIQUE (user_id, user_group_id)')]


class Cred(BaseModel):
    id = AutoField()
    name = CharField()
    enable = IntegerField(constraints=[SQL('DEFAULT 1')])
    username = CharField()
    password = CharField(null=True)
    groups = IntegerField(constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'cred'
        constraints = [SQL('UNIQUE (name, `groups`)')]


class Backup(BaseModel):
    id = AutoField()
    server = CharField()
    rhost = CharField()
    rpath = CharField()
    backup_type = CharField(column_name='type')
    time = CharField()
    cred = IntegerField()
    description = CharField(null=True)

    class Meta:
        table_name = 'backups'


class S3Backup(BaseModel):
    id = AutoField()
    server = CharField()
    s3_server = CharField()
    bucket = CharField()
    secret_key = CharField()
    access_key = CharField()
    time = CharField()
    description = CharField(null=True)

    class Meta:
        table_name = 's3_backups'


class Metrics(BaseModel):
    serv = CharField()
    curr_con = IntegerField()
    cur_ssl_con = IntegerField()
    sess_rate = IntegerField()
    max_sess_rate = IntegerField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'metrics'
        primary_key = False


class WafMetrics(BaseModel):
    serv = CharField()
    conn = IntegerField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'waf_metrics'
        primary_key = False


class NginxMetrics(BaseModel):
    serv = CharField()
    conn = IntegerField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'nginx_metrics'
        primary_key = False


class ApacheMetrics(BaseModel):
    serv = CharField()
    conn = IntegerField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'apache_metrics'
        primary_key = False


class Version(BaseModel):
    version = CharField()

    class Meta:
        table_name = 'version'
        primary_key = False


class Option(BaseModel):
    id = AutoField()
    options = CharField()
    groups = CharField()

    class Meta:
        table_name = 'options'


class SavedServer(BaseModel):
    id = AutoField()
    server = CharField()
    description = CharField(null=True)
    groups = CharField()

    class Meta:
        table_name = 'saved_servers'


class Waf(BaseModel):
    server_id = IntegerField()
    metrics = IntegerField()

    class Meta:
        table_name = 'waf'
        primary_key = False
        constraints = [SQL('UNIQUE (server_id)')]


class WafRules(BaseModel):
    id = AutoField()
    serv = CharField()
    rule_name = CharField()
    rule_file = CharField()
    desc = TextField(null=True)
    en = IntegerField(constraints=[SQL('DEFAULT 1')])
    service = CharField(constraints=[SQL('DEFAULT "haproxy"')])

    class Meta:
        table_name = 'waf_rules'
        constraints = [SQL('UNIQUE (serv, rule_name, service)')]


class PortScannerSettings(BaseModel):
    server_id = IntegerField()
    user_group_id = IntegerField()
    enabled = IntegerField()
    notify = IntegerField()
    history = IntegerField()

    class Meta:
        table_name = 'port_scanner_settings'
        primary_key = False
        constraints = [SQL('UNIQUE (server_id)')]


class PortScannerPorts(BaseModel):
    serv = CharField()
    user_group_id = IntegerField()
    port = IntegerField()
    service_name = CharField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'port_scanner_ports'
        primary_key = False


class PortScannerHistory(BaseModel):
    serv = CharField()
    port = IntegerField()
    status = CharField()
    service_name = CharField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'port_scanner_history'
        primary_key = False


class ProvidersCreds(BaseModel):
    id = AutoField()
    name = CharField()
    type = CharField()
    group = CharField()
    key = CharField()
    secret = CharField(null=True)
    create_date = DateTimeField(default=datetime.now)
    edit_date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'providers_creds'


class ProvisionParam(BaseModel):
    id = AutoField()
    param = CharField()
    name = CharField()
    optgroup = CharField()
    section = CharField()
    provider = CharField()
    image = CharField(null=True)

    class Meta:
        table_name = 'provision_param'
        constraints = [SQL('UNIQUE (param, section, provider)')]


class ProvisionedServers(BaseModel):
    id = AutoField()
    region = CharField()
    instance_type = CharField()
    public_ip = IntegerField(null=True)
    floating_ip = IntegerField(null=True)
    volume_size = IntegerField(null=True)
    backup = IntegerField(null=True)
    monitoring = IntegerField(null=True)
    private_networking = IntegerField(null=True)
    ssh_key_name = CharField(null=True)
    ssh_ids = CharField(null=True)
    name = CharField()
    os = CharField()
    firewall = IntegerField()
    provider_id = IntegerField()
    type = CharField()
    status = CharField()
    group_id = IntegerField()
    date = DateTimeField(default=datetime.now)
    IP = CharField(null=True)
    last_error = CharField(null=True)
    delete_on_termination = IntegerField(null=True)
    project = CharField(null=True)
    network_name = CharField(null=True)
    volume_type = CharField(null=True)
    name_template = CharField(null=True)

    class Meta:
        table_name = 'provisioned_servers'


class MetricsHttpStatus(BaseModel):
    serv = CharField()
    ok_ans = IntegerField(column_name='2xx')
    redir_ans = IntegerField(column_name='3xx')
    not_found_ans = IntegerField(column_name='4xx')
    err_ans = IntegerField(column_name='5xx')
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'metrics_http_status'
        primary_key = False


class SMON(BaseModel):
    id = AutoField()
    name = CharField(null=True)
    port = IntegerField(null=True)
    status = IntegerField(constraints=[SQL('DEFAULT 1')])
    en = IntegerField(constraints=[SQL('DEFAULT 1')])
    desc = CharField(null=True)
    response_time = CharField(null=True)
    time_state = DateTimeField(constraints=[SQL('DEFAULT "0000-00-00 00:00:00"')])
    group = CharField(null=True)
    http = CharField(null=True)
    body = CharField(null=True)
    body_status = IntegerField(constraints=[SQL('DEFAULT 1')])
    telegram_channel_id = IntegerField(null=True)
    user_group = IntegerField()
    slack_channel_id = IntegerField(null=True)
    ssl_expire_warning_alert = IntegerField(constraints=[SQL('DEFAULT 0')])
    ssl_expire_critical_alert = IntegerField(constraints=[SQL('DEFAULT 0')])
    ssl_expire_date = CharField(null=True)
    pd_channel_id = IntegerField(null=True)
    check_type = CharField(constraints=[SQL('DEFAULT "tcp"')])

    class Meta:
        table_name = 'smon'
        constraints = [SQL('UNIQUE (name, port, http, body)')]


class Alerts(BaseModel):
    message = CharField()
    level = CharField()
    ip = CharField()
    port = IntegerField()
    user_group = IntegerField(constraints=[SQL('DEFAULT 1')])
    service = CharField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'alerts'
        primary_key = False


class GeoipCodes(BaseModel):
    code = CharField()
    name = CharField()

    class Meta:
        table_name = 'geoip_codes'
        primary_key = False
        constraints = [SQL('UNIQUE (code, name)')]


class ServiceSetting(BaseModel):
    server_id = IntegerField()
    service = CharField()
    setting = CharField()
    value = CharField()

    class Meta:
        table_name = 'service_settings'
        primary_key = False
        constraints = [SQL('UNIQUE (server_id, service, setting)')]


class ActionHistory(BaseModel):
    service = CharField(null=True)
    server_id = IntegerField(null=True)
    user_id = IntegerField(null=True)
    action = CharField(null=True)
    ip = CharField(null=True)
    date = DateTimeField(default=datetime.now)
    server_ip = CharField(null=True)
    hostname = CharField(null=True)

    class Meta:
        table_name = 'action_history'
        primary_key = False


class ConfigVersion(BaseModel):
    id = AutoField()
    server_id = IntegerField()
    user_id = IntegerField()
    service = CharField()
    local_path = CharField()
    remote_path = CharField()
    diff = TextField()
    message = CharField(null=True)
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'config_versions'


class SystemInfo(BaseModel):
    id = AutoField()
    server_id = IntegerField()
    os_info = CharField()
    sys_info = CharField()
    cpu = CharField()
    ram = CharField()
    disks = CharField()
    network = TextField()

    class Meta:
        table_name = 'system_info'


class Services(BaseModel):
    service_id = IntegerField(null=True)
    service = CharField(null=True)
    slug = CharField(null=True)

    class Meta:
        table_name = 'services'
        primary_key = False
        constraints = [SQL('UNIQUE (service_id, service)')]


class UserName(BaseModel):
    UserName = CharField(null=True)
    Status = IntegerField(constraints=[SQL('DEFAULT 0')])
    Plan = CharField(null=True)
    Method = CharField(null=True)

    class Meta:
        table_name = 'user_name'
        primary_key = False


class GitSetting(BaseModel):
    id = AutoField()
    server_id = ForeignKeyField(Server, on_delete='Cascade')
    service_id = IntegerField()
    period = CharField()
    repo = CharField(null=True)
    branch = CharField(null=True)
    cred_id = IntegerField()
    description = CharField(null=True)

    class Meta:
        table_name = 'git_setting'
        constraints = [SQL('UNIQUE (server_id, service_id)')]


class CheckerSetting(BaseModel):
    id = AutoField()
    server_id = ForeignKeyField(Server, on_delete='Cascade')
    service_id = IntegerField()
    email = IntegerField(constraints=[SQL('DEFAULT 1')])
    telegram_id = IntegerField(constraints=[SQL('DEFAULT 0')])
    slack_id = IntegerField(constraints=[SQL('DEFAULT 0')])
    service_alert = IntegerField(constraints=[SQL('DEFAULT 1')])
    backend_alert = IntegerField(constraints=[SQL('DEFAULT 1')])
    maxconn_alert = IntegerField(constraints=[SQL('DEFAULT 1')])
    pd_id = IntegerField(constraints=[SQL('DEFAULT 0')])

    class Meta:
        table_name = 'checker_setting'
        constraints = [SQL('UNIQUE (server_id, service_id)')]


class WafNginx(BaseModel):
    id = AutoField()
    server_id = ForeignKeyField(Server, on_delete='Cascade')

    class Meta:
        table_name = 'waf_nginx'
        constraints = [SQL('UNIQUE (server_id)')]


class ServiceStatus(BaseModel):
    server_id = ForeignKeyField(Server, on_delete='Cascade')
    service_id = IntegerField()
    service_check = CharField()
    status = IntegerField(constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'services_statuses'
        constraints = [SQL('UNIQUE (server_id, service_id, service_check)')]


class KeepaliveRestart(BaseModel):
    server_id = ForeignKeyField(Server, on_delete='Cascade')
    service = CharField()
    restarted = IntegerField(constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'keepaplive_restarted'
        constraints = [SQL('UNIQUE (server_id, service)')]


class SmonHistory(BaseModel):
    smon_id = ForeignKeyField(SMON, on_delete='Cascade')
    check_id = IntegerField()
    response_time = FloatField()
    status = IntegerField()
    mes = CharField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'smon_history'
        primary_key = False


class SmonTcpCheck(BaseModel):
    smon_id = ForeignKeyField(SMON, on_delete='Cascade', unique=True)
    ip = CharField()
    port = IntegerField()

    class Meta:
        table_name = 'smon_tcp_check'
        primary_key = False


class SmonHttpCheck(BaseModel):
    smon_id = ForeignKeyField(SMON, on_delete='Cascade', unique=True)
    url = CharField()
    method = CharField(constraints=[SQL('DEFAULT "get"')])
    accepted_status_codes = CharField(constraints=[SQL('DEFAULT "200"')])
    body = CharField(null=True)

    class Meta:
        table_name = 'smon_http_check'
        primary_key = False


class SmonPingCheck(BaseModel):
    smon_id = ForeignKeyField(SMON, on_delete='Cascade', unique=True)
    ip = CharField()
    packet_size = IntegerField(constraints=[SQL('DEFAULT 56')])

    class Meta:
        table_name = 'smon_ping_check'
        primary_key = False


class SmonDnsCheck(BaseModel):
    smon_id = ForeignKeyField(SMON, on_delete='Cascade', unique=True)
    ip = CharField()
    port = IntegerField(constraints=[SQL('DEFAULT 53')])
    resolver = CharField()
    record_type = CharField()

    class Meta:
        table_name = 'smon_dns_check'
        primary_key = False


def create_tables():
    with conn:
        conn.create_tables([User, Server, Role, Telegram, Slack, UUID, Token, ApiToken, Groups, UserGroups, ConfigVersion,
                            Setting, Cred, Backup, Metrics, WafMetrics, Version, Option, SavedServer, Waf, ActionHistory,
                            PortScannerSettings, PortScannerPorts, PortScannerHistory, ProvidersCreds, ServiceSetting,
                            ProvisionedServers, MetricsHttpStatus, SMON, WafRules, Alerts, GeoipCodes, NginxMetrics,
                            SystemInfo, Services, UserName, GitSetting, CheckerSetting, ApacheMetrics, ProvisionParam,
                            WafNginx, ServiceStatus, KeepaliveRestart, PD, SmonHistory, SmonTcpCheck, SmonHttpCheck,
                            SmonPingCheck, SmonDnsCheck, S3Backup])
