import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from flask import current_app
from peewee import SqliteDatabase

from app.modules.db.db_model import Server, HaClusterVirt, HaClusterVip, InstallationTasks, RoxyTool
from app.modules.db import service_event
from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings
from app.modules.roxywi import common as roxywi_common
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError
from app.modules.service import installation
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.server.ssh import return_ssh_keys_path
import distro

import app.modules.db.roxy as roxy_sql
import app.modules.roxywi.roxy as roxywi_mod
import app.modules.server.server as server_mod
from app.modules.common.time import as_naive_utc, utc_iso, utc_now
from app.version import get_service_version


_DISTRIBUTED_TOOLS = {
    'roxy-wi-checker': 'checker',
    'roxy-wi-metrics': 'metrics',
    'roxy-wi-portscanner': 'portscanner',
    'roxy-wi-socket': 'socket',
}

_INTERNAL_TOOLS = {
    'roxy-wi-web': 'roxy-wi-web',
    'roxy-wi-scheduler': 'roxy-wi-scheduler',
    'roxy-wi-service-events': 'roxy-wi-service-events',
    'roxy-wi-operations': 'roxy-wi-operations',
}

def _distributed_status(worker_state: dict) -> str | None:
    if not worker_state:
        return None
    if worker_state.get('active', 0):
        if (
            worker_state.get('degraded', 0)
            or worker_state.get('stale', 0)
            or worker_state.get('draining', 0)
        ):
            return 'degraded'
        return 'active'
    if worker_state.get('draining', 0):
        return 'draining'
    if worker_state.get('stale', 0):
        return 'stale'
    if worker_state.get('stopped', 0):
        return 'stopped'
    return None


def _internal_status(worker_state: dict) -> str | None:
    """Internal replicas are replaceable, so expired old identities do not
    degrade a service while at least one current replica is healthy."""
    if not worker_state:
        return None
    if worker_state.get('active', 0):
        if worker_state.get('degraded', 0) or worker_state.get('draining', 0):
            return 'degraded'
        return 'active'
    return _distributed_status(worker_state)


def tool_category(tool_name: str) -> str:
    if tool_name in _INTERNAL_TOOLS:
        return 'internal'
    if tool_name in _DISTRIBUTED_TOOLS:
        return 'distributed'
    return 'local'


def _system_service_name(tool_name: str) -> str:
    if tool_name == 'roxy-wi-web':
        return 'apache2' if distro.id() in ('debian', 'ubuntu') else 'httpd'
    return tool_name


def _management_metadata(tool_name: str, status: str, worker_state: dict) -> dict:
    category = tool_category(tool_name)
    deployment_mode = roxywi_mod.deployment_mode()
    if category == 'distributed':
        management = 'Worker deployment'
        can_lifecycle = False
    elif deployment_mode == 'package':
        management = 'systemd'
        # The currently serving Web process cannot reliably start itself after
        # it has been stopped. Keep it observable, but manage httpd externally.
        can_lifecycle = tool_name != 'roxy-wi-web'
    elif deployment_mode == 'quadlet':
        management = 'Podman Quadlet'
        can_lifecycle = False
    elif deployment_mode == 'compose':
        management = 'Docker Compose'
        can_lifecycle = False
    else:
        management = 'Kubernetes'
        can_lifecycle = False

    if category in {'internal', 'distributed'}:
        instances = int(worker_state.get('active', 0))
        if not worker_state and status in {'active', 'RUNNING'}:
            instances = 1
        stale = int(worker_state.get('stale', 0))
        if category == 'internal' and instances:
            # Deployment pod names are replaceable. Without an orchestrator's
            # desired replica count, an expired identity from a rolling update
            # must not make a healthy internal process look degraded.
            stale = 0
    else:
        instances = 1 if status in {'active', 'RUNNING'} else 0
        stale = 0

    last_heartbeat = worker_state.get('last_heartbeat')
    heartbeat_age_seconds = None
    if last_heartbeat is not None:
        heartbeat_age_seconds = max(
            0,
            int((utc_now() - as_naive_utc(last_heartbeat)).total_seconds()),
        )

    return {
        'category': category,
        'management': management,
        'can_lifecycle': can_lifecycle,
        'instances': instances,
        'stale': stale,
        'last_heartbeat': utc_iso(last_heartbeat),
        'heartbeat_age_seconds': heartbeat_age_seconds,
        'deployment_mode': deployment_mode,
    }


def get_services_status(update_cur_ver=0, worker_states: dict | None = None):
    services = []
    services_name = roxy_sql.get_all_tools()

    if update_cur_ver and roxywi_mod.deployment_mode() == 'package':
        try:
            update_cur_tool_versions()
        except Exception as e:
            raise Exception(f'error: Cannot update current versions: {e}')

    try:
        for s, v in services_name.items():
            worker_state = {}
            distributed_service = _DISTRIBUTED_TOOLS.get(s)
            internal_service = _INTERNAL_TOOLS.get(s)
            heartbeat_service = distributed_service or internal_service
            if heartbeat_service and worker_states:
                worker_state = worker_states.get(heartbeat_service, {})
            try:
                if internal_service:
                    status = _internal_status(worker_state) or is_tool_active(s)
                else:
                    status = _distributed_status(worker_state) or is_tool_active(s)
            except Exception as e:
                raise Exception(f'error: Cannot get status for tool {s}: {e}')
            try:
                version = dict(v)
                runtime_versions = worker_state.get('versions', [])
                if runtime_versions:
                    version['current_version'] = ', '.join(runtime_versions)
                elif internal_service:
                    version['current_version'] = get_service_version()
                    version['new_version'] = get_service_version()
                metadata = _management_metadata(s, status, worker_state)
                services.append([s, status, version, worker_state, metadata])
            except Exception as e:
                raise Exception(f'error: Cannot combine status for tool {s}: {e}')
    except Exception as e:
        raise Exception(f'error: Cannot get tools status: {e}')

    return services


def update_roxy_wi(service: str) -> str:
    if roxywi_mod.deployment_mode() != 'package':
        raise RuntimeError('Container images must be updated by Compose or Kubernetes')
    restart_service = ''
    services = roxy_sql.get_roxy_tools()

    if service not in services and service != 'roxy-wi':
        raise Exception(f'error: {service} is not part of Roxy-WI')

    if service != 'roxy-wi':
        restart_service = f'&& sudo systemctl restart {service}'

    if distro.id() in ('debian', 'ubuntu'):
        if service == 'roxy-wi-keep_alive':
            service = 'roxy-wi-keep-alive'

        cmd = f'sudo -S apt-get update && sudo apt-get install {service} -y {restart_service}'
    else:
        cmd = f'sudo -S yum -y install {service} {restart_service}'

    result = server_mod.subprocess_execute_with_rc(cmd)
    output = result['error'].strip() or '\n'.join(result['output'])
    if result['rc']:
        raise RoxywiValidationError(output or f'Package update exited with code {result["rc"]}')
    update_cur_tool_version(service)
    return output


def is_tool_active(tool_name: str) -> str:
    if roxywi_mod.deployment_mode() != 'package':
        return 'unknown'
    is_in_docker = roxywi_mod.is_docker()
    service_name = _system_service_name(tool_name)
    if is_in_docker:
        cmd = f"sudo supervisorctl status {service_name}|awk '{{print $2}}'"
    else:
        cmd = f"systemctl is-active {service_name}"
    status, stderr = server_mod.subprocess_execute(cmd)
    return status[0]


def update_cur_tool_versions() -> None:
    tools = roxy_sql.get_all_tools()
    for s, _v in tools.items():
        if s in _INTERNAL_TOOLS:
            roxy_sql.update_tool_cur_version(s, get_service_version())
            continue
        update_cur_tool_version(s)


def update_cur_tool_version(tool_name: str) -> None:
    if roxywi_mod.deployment_mode() != 'package':
        return
    correct_name = tool_name
    if tool_name == 'grafana-server':
        correct_name = 'grafana'
    if tool_name == 'prometheus':
        cmd = "prometheus --version 2>&1 |grep prometheus|awk '{print $3}'"
    else:
        if distro.id() in ('debian', 'ubuntu'):
            if tool_name == 'roxy-wi-keep_alive':
                correct_name = 'roxy-wi-keep-alive'
            cmd = f"apt list --installed 2>&1 |grep {correct_name}|awk '{{print $2}}'|sed 's/-/./'"
        else:
            cmd = f"rpm -q {correct_name}|awk -F\"{correct_name}\" '{{print $2}}' |awk -F\".noa\" '{{print $1}}' |sed 's/-//1' |sed 's/-/./'"

    service_ver, stderr = server_mod.subprocess_execute(cmd)

    try:
        service_ver = service_ver[0]
    except Exception:
        service_ver = 0

    if service_ver in ('command', 'prometheus:', 'not'):
        service_ver = 0

    try:
        roxy_sql.update_tool_cur_version(tool_name, service_ver)
    except Exception:
        pass


def get_cur_tool_version(tool_name: str) -> str:
    return roxy_sql.get_tool_cur_version(tool_name)


TOOL_ANSIBLE_ROLE = 'roxywi_service'
TOOL_ANSIBLE_ERROR_CODES = (
    'systemd_required', 'unsupported_os', 'keep_alive_local', 'rabbit_unreachable',
    'package_version', 'invalid_configuration', 'engine_conflict', 'podman_version',
)


def tool_container_versions():
    """Use the latest versions maintained by the existing update job."""
    versions = {}
    for name, tool in roxy_sql.get_all_tools().items():
        if name not in _DISTRIBUTED_TOOLS:
            continue
        value = tool['new_version'].strip()
        # A bootstrap value, failed version check or package description is not
        # an image tag. Do not fall back to the seeded current_version.
        valid = len(value) <= 64 and re.fullmatch(r'[0-9]+(?:\.[0-9]+)+(?:[-.][A-Za-z0-9]+)*', value)
        versions[_DISTRIBUTED_TOOLS[name]] = [value] if valid else []
    return versions


def supports_local_tool_install():
    return roxywi_mod.deployment_mode() == 'package' and os.name == 'posix'


def installation_servers():
    """Exclude virtual addresses even when a legacy cluster row lacks type_ip."""
    vips = [row.vip.split('/')[0] for row in HaClusterVip.select(HaClusterVip.vip)]
    return Server.select().where(
        (Server.enabled == 1) & (Server.type_ip == 0) &
        Server.server_id.not_in(HaClusterVirt.select(HaClusterVirt.virt_id)) & Server.ip.not_in(vips))


def tool_inventory(body, *, inspect_only=False):
    """Build Ansible variables from an existing host and saved application settings."""
    server = None
    if body.component == 'keep_alive' and (body.server_id is not None or body.engine != 'native'):
        raise RoxywiValidationError('keep_alive_local')
    if body.server_id is None:
        if not supports_local_tool_install():
            raise RoxywiValidationError('local_systemd_required')
    else:
        server = installation_servers().where(Server.server_id == body.server_id).first()
        if server is None:
            raise RoxywiValidationError('server_unavailable')
        roxywi_common.require_active_group_access(server.group_id)
        if not return_ssh_keys_path(server.ip).get('host_key'):
            raise RoxywiValidationError('ssh_unconfirmed')
    payload = dict(component=body.component, engine=body.engine,
                   stage='check' if inspect_only else 'install', detect_runtime=inspect_only,
                   application_path=GetConfigVar().get_config_var('main', 'fullpath', '/var/www/haproxy-wi'))
    if not inspect_only and body.component != 'keep_alive':
        if body.engine != 'native':
            versions = tool_container_versions().get(body.component, [])
            if not versions:
                raise RoxywiValidationError('version_unavailable')
            selected = body.version or versions[0]
            if selected not in versions:
                raise RoxywiValidationError('invalid_configuration')
            payload['image'] = f'ghcr.io/roxy-wi/roxy-wi-{body.component}:{selected}'
        rabbit = RabbitConnectionSettings.load()
        if server is not None and rabbit.host in ('localhost', '127.0.0.1', '::1'):
            raise RoxywiValidationError('rabbit_remote_host')
        prefix = body.component.upper()
        instance = f'roxywi-{body.component}-' + (f'server-{server.server_id}' if server else 'local')
        values = {
            prefix + '_USE_ROXYWI_RABBITMQ_SETTINGS': '0', prefix + '_INSTANCE_ID': instance,
            prefix + '_RABBITMQ_HOST': rabbit.host, prefix + '_RABBITMQ_PORT': str(rabbit.port),
            prefix + '_RABBITMQ_VHOST': rabbit.vhost, prefix + '_RABBITMQ_USER': rabbit.username,
            prefix + '_RABBITMQ_PASSWORD': rabbit.password,
            prefix + '_RABBITMQ_QUEUE_TYPE': os.environ.get('ROXYWI_RABBITMQ_QUEUE_TYPE', 'classic'),
        }
        if body.database_url:
            values[prefix + '_DATABASE_URL'] = body.database_url
        payload.update(environment=values, rabbit_host=rabbit.host, rabbit_port=rabbit.port,
                       worker_hosts=sorted({item['current'].hostname for item in service_event.worker_instances(body.component).values()
                                            if item['status'] in service_event.ACTIVE_WORKER_STATUSES and item['current'].hostname}))
        if body.component == 'socket':
            values.update(SOCKET_LISTEN_HOST=server.ip if server else '127.0.0.1',
                          SOCKET_LISTEN_PORT=str(body.socket_port), SOCKET_JWT_ALGORITHM=current_app.config['JWT_ALGORITHM'])
            if current_app.config['JWT_ALGORITHM'] == 'RS256':
                payload['public_key'] = current_app.config['JWT_PUBLIC_KEY']
                values['SOCKET_JWT_PUBLIC_KEY_FILE'] = '/etc/roxy-wi/socket-ux-public.pem'
            else:
                values['SOCKET_JWT_SECRET'] = current_app.config['JWT_SECRET_KEY']
        if any(ord(char) < 32 for value in values.values() for char in str(value)):
            raise RoxywiValidationError('invalid_configuration')
    variables = {'roxywi_install': payload}
    if server is None:
        variables.update(ansible_connection='local', ansible_become=True)
    return {'server': {'hosts': {server.ip if server else 'localhost': variables}}}, [server.ip] if server else []


def tool_install_error(error):
    """Expose bounded Ansible error codes instead of its private inventory."""
    if isinstance(error, RoxywiValidationError):
        return error.public_message
    codes = (*TOOL_ANSIBLE_ERROR_CODES, 'shared_database_required')
    if str(error) in codes:
        return str(error)
    return next((code for code in codes if f'roxywi_error:{code}' in str(error)), 'command_failed')


def inspect_tool(body):
    """Use one bounded read through the existing SSH connection for UI status."""
    _, addresses = tool_inventory(body, inspect_only=True)
    script = Path(current_app.root_path) / 'scripts' / 'tool_status.py'
    try:
        if addresses:
            command = shlex.join(['sudo', '-n', 'python3', '-c', script.read_text(), body.component])
            output = server_mod.ssh_command(addresses[0], command, timeout=6,
                                            connect_timeout=2, banner_timeout=2,
                                            error_context='Cannot read optional service status')
        else:
            result = subprocess.run(['sudo', '-n', 'python3', str(script), body.component],
                                    capture_output=True, text=True, timeout=7)
            output = result.stdout
        facts = json.loads(output)
        if facts.get('error_code'):
            raise RoxywiValidationError(tool_install_error(RuntimeError(facts['error_code'])))
        if (facts.get('engine') not in ('native', 'docker', 'podman')
                or type(facts.get('installed')) is not bool
                or not isinstance(facts.get('version'), str)
                or facts.get('state') not in ('active', 'inactive')):
            raise RoxywiValidationError('command_failed')
        return facts
    except RoxywiValidationError:
        raise
    except Exception as error:
        raise RoxywiValidationError('command_failed') from error


def install_tool(body):
    """Queue one Ansible operation, preventing concurrent updates of a service."""
    database = InstallationTasks._meta.database
    service = 'roxy-wi-' + body.component
    with database.atomic(*(('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ())):
        row = RoxyTool.select().where(RoxyTool.name == service)
        if (row if isinstance(database, SqliteDatabase) else row.for_update()).get_or_none() is None:
            raise RoxywiValidationError('invalid_configuration')
        if InstallationTasks.select().where(
            (InstallationTasks.service_name == service) &
            InstallationTasks.status.in_(('created', 'published', 'running'))).exists():
            raise RoxywiConflictError('busy')
        inventory, addresses = tool_inventory(body)
        return installation.run_ansible_thread(
            inventory, addresses, TOOL_ANSIBLE_ROLE, service, run_locally=not addresses)
