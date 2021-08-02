from peewee import *
from datetime import datetime
from funct import get_config_var

mysql_enable = get_config_var('mysql', 'enable')

if mysql_enable == '1':
    mysql_user = funct.get_config_var('mysql', 'mysql_user')
    mysql_password = funct.get_config_var('mysql', 'mysql_password')
    mysql_db = funct.get_config_var('mysql', 'mysql_db')
    mysql_host = funct.get_config_var('mysql', 'mysql_host')
    mysql_port = funct.get_config_var('mysql', 'mysql_port')
    conn = MySQLDatabase(mysql_db, user=mysql_user, password=mysql_password, host=mysql_host, port=mysql_port)
else:
    db = "roxy-wi.db"
    conn = SqliteDatabase(db)


class BaseModel(Model):
    class Meta:
        database = conn


class User(BaseModel):
    user_id = AutoField(column_name='id')
    username = TextField(constraints=[SQL('UNIQUE')])
    email = TextField(constraints=[SQL('UNIQUE')])
    password = TextField(null=True)
    role = TextField()
    groups = TextField()
    ldap_user = IntegerField(default=0)
    activeuser = IntegerField(default=1)

    class Meta:
        table_name = 'user'


class Server(BaseModel):
    server_id = AutoField(column_name='id')
    hostname = TextField()
    ip = TextField()
    groups = TextField()
    type_ip = IntegerField(default=0)
    enable = IntegerField(default=1)
    master = IntegerField(default=0)
    cred = IntegerField(default=1)
    alert = IntegerField(default=0)
    metrics = IntegerField(default=0)
    port = IntegerField(default=22)
    desc = TextField(null=True)
    active = IntegerField(default=0)
    keepalived = IntegerField(default=0)
    nginx = IntegerField(default=0)
    haproxy = IntegerField(default=0)
    pos = IntegerField(default=0)
    nginx_active = IntegerField(default=0)
    firewall_enable = IntegerField(default=0)
    nginx_alert = IntegerField(default=0)
    protected = IntegerField(default=0)

    class Meta:
        table_name = 'servers'


class Role(BaseModel):
    role_id = AutoField(column_name='id')
    name = TextField(constraints=[SQL('UNIQUE')])
    description = DateTimeField()

    class Meta:
        table_name = 'role'


class Telegram(BaseModel):
    id = AutoField()
    token = TextField()
    chanel_name = TextField()
    groups = IntegerField()

    class Meta:
        table_name = 'telegram'


class Slack(BaseModel):
    id = AutoField()
    token = TextField()
    chanel_name = TextField()
    groups = IntegerField()

    class Meta:
        table_name = 'slack'


class UUID(BaseModel):
    user_id = IntegerField()
    uuid = TextField()
    exp = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'uuid'
        primary_key = False


class Token(BaseModel):
    user_id = IntegerField()
    token = TextField()
    exp = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'token'
        primary_key = False


class ApiToken(BaseModel):
    token = TextField()
    user_name = TextField()
    user_group_id = IntegerField()
    user_role = IntegerField()
    create_date = DateTimeField(default=datetime.now)
    expire_date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'api_tokens'
        primary_key = False


class Setting(BaseModel):
    param = TextField()
    value = TextField(null=True)
    section = TextField()
    desc = TextField()
    group = IntegerField(null=True, constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'settings'
        primary_key = False
        constraints = [SQL('UNIQUE (param, `group`)')]


class Groups(BaseModel):
    group_id = AutoField(column_name='id')
    name = TextField(constraints=[SQL('UNIQUE')])
    description = TextField(null=True)

    class Meta:
        table_name = 'groups'


class UserGroups(BaseModel):
    user_id = IntegerField()
    user_group_id = IntegerField()

    class Meta:
        table_name = 'user_groups'
        primary_key = False
        constraints = [SQL('UNIQUE (user_id, user_group_id)')]


class Cred(BaseModel):
    id = AutoField()
    name = TextField()
    enable = IntegerField(constraints=[SQL('DEFAULT 1')])
    username = TextField()
    password = TextField(null=True)
    groups = IntegerField(constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'cred'
        constraints = [SQL('UNIQUE (name, groups)')]


class Backup(BaseModel):
    id = AutoField()
    server = TextField()
    rhost = TextField()
    rpath = TextField()
    backup_type = TextField(column_name='type')
    time = TextField()
    cred = IntegerField()
    description = TextField(null=True)

    class Meta:
        table_name = 'backups'


class Metrics(BaseModel):
    serv = TextField()
    curr_con = IntegerField()
    cur_ssl_con = IntegerField()
    sess_rate = IntegerField()
    max_sess_rate = IntegerField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'metrics'
        primary_key = False


class WafMetrics(BaseModel):
    serv = TextField()
    conn = IntegerField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'waf_metrics'
        primary_key = False


class Version(BaseModel):
    version = TextField()

    class Meta:
        table_name = 'version'
        primary_key = False


class Option(BaseModel):
    id = AutoField()
    options = TextField()
    groups = TextField()

    class Meta:
        table_name = 'options'


class SavedServer(BaseModel):
    id = AutoField()
    server = TextField()
    description = TextField(null=True)
    groups = TextField()

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
    serv = TextField()
    rule_name = TextField()
    rule_file = TextField()
    desc = TextField(null=True)
    en = IntegerField(constraints=[SQL('DEFAULT 1')])

    class Meta:
        table_name = 'waf_rules'
        constraints = [SQL('UNIQUE (serv, rule_name)')]


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
    serv = TextField()
    user_group_id = IntegerField()
    port = IntegerField()
    service_name = TextField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'port_scanner_ports'
        primary_key = False


class PortScannerHistory(BaseModel):
    serv = TextField()
    port = IntegerField()
    status = TextField()
    service_name = TextField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'port_scanner_history'
        primary_key = False


class ProvidersCreds(BaseModel):
    id = AutoField()
    name = TextField()
    type = TextField()
    group = TextField()
    key = TextField()
    secret = TextField(null=True)
    create_date = DateTimeField(default=datetime.now)
    edit_date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'providers_creds'


class ProvisionedServers(BaseModel):
    id = AutoField()
    region = TextField()
    instance_type = TextField()
    public_ip = IntegerField(null=True)
    floating_ip = IntegerField(null=True)
    volume_size = IntegerField(null=True)
    backup = IntegerField(null=True)
    monitoring = IntegerField(null=True)
    private_networking = IntegerField(null=True)
    ssh_key_name = TextField(null=True)
    ssh_ids = TextField(null=True)
    name = TextField()
    os = TextField()
    firewall = IntegerField()
    provider_id = IntegerField()
    type = TextField()
    status = TextField()
    group_id = IntegerField()
    date = DateTimeField(default=datetime.now)
    IP = TextField(null=True)
    last_error = TextField(null=True)
    delete_on_termination = IntegerField(null=True)
    project = TextField(null=True)
    network_name = TextField(null=True)
    volume_type = TextField(null=True)
    name_template = TextField(null=True)

    class Meta:
        table_name = 'provisioned_servers'


class MetricsHttpStatus(BaseModel):
    serv = TextField()
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
    ip = IntegerField(null=True)
    port = IntegerField(null=True)
    status = IntegerField(constraints=[SQL('DEFAULT 1')])
    en = IntegerField(constraints=[SQL('DEFAULT 1')])
    desc = TextField(null=True)
    response_time = TextField(null=True)
    time_state = IntegerField(constraints=[SQL('DEFAULT 0')])
    group = TextField(null=True)
    script = TextField(null=True)
    http = TextField(null=True)
    http_status = IntegerField(constraints=[SQL('DEFAULT 1')])
    body = TextField(null=True)
    body_status = IntegerField(constraints=[SQL('DEFAULT 1')])
    telegram_channel_id = IntegerField(null=True)
    user_group = IntegerField()

    class Meta:
        table_name = 'smon'
        constraints = [SQL('UNIQUE (ip, port, http, body)')]


class Alerts(BaseModel):
    message = TextField()
    level = TextField()
    ip = TextField()
    port = IntegerField()
    user_group = IntegerField(constraints=[SQL('DEFAULT 1')])
    service = TextField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'alerts'
        primary_key = False


class GeoipCodes(BaseModel):
    code = TextField()
    name = TextField()

    class Meta:
        table_name = 'geoip_codes'
        primary_key = False
        constraints = [SQL('UNIQUE (code, name)')]

def create_tables():
    with conn:
        conn.create_tables([User, Server, Role, Telegram, Slack, UUID, Token, ApiToken, Groups, UserGroups,
                            Setting, Cred, Backup, Metrics, WafMetrics, Version, Option, SavedServer, Waf,
                            PortScannerSettings, PortScannerPorts, PortScannerHistory, ProvidersCreds,
                            ProvisionedServers, MetricsHttpStatus, SMON, WafRules, Alerts, GeoipCodes])
