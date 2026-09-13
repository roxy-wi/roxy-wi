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
        return 'apache2' if distro.id() == 'ubuntu' else 'httpd'
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

    if distro.id() == 'ubuntu':
        if service == 'roxy-wi-keep_alive':
            service = 'roxy-wi-keep-alive'

        cmd = f'sudo -S apt-get update && sudo apt-get install {service} -y {restart_service}'
    else:
        cmd = f'sudo -S yum -y install {service} {restart_service}'

    output, stderr = server_mod.subprocess_execute(cmd)
    update_cur_tool_version(service)

    if stderr != '':
        return str(stderr)
    else:
        return str(output)


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
        if distro.id() == 'ubuntu':
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
