import hashlib
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory

import app.modules.db.sql as sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.common as service_common
import app.modules.service.nginx as nginx
import app.modules.server.ssh as mod_ssh
from app.modules.config import candidate, waf_state
from app.modules.roxywi import logger
from app.modules.server.command import build_remote_command


def common_action(server_ip: str, action: str, service: str) -> None:
    action_functions = {
        'haproxy': service_action,
        'nginx': service_action,
        'keepalived': service_action,
        'apache': service_action,
        'waf_haproxy': action_haproxy_waf,
        'waf_nginx': action_nginx_waf
    }

    if service in ('waf_haproxy','waf_nginx'):
        from app.modules.pacemaker.autostart import assert_unmanaged
        assert_unmanaged(server_sql.get_server_by_ip(server_ip).server_id,service.removeprefix('waf_'))
    action_functions[service](server_ip, action, service)


def service_action(server_ip: str, action: str, service: str) -> None:
    """
    :param server_ip: The IP address of the server on which the action will be performed.
    :param action: The action to be performed on the service (e.g., "start", "stop").
    :param service: The name of the service on which the action will be performed.
    :return: A string indicating the success or failure of the action.
    """
    service_common.is_protected(server_ip, action)
    server_id = server_sql.get_server_by_ip(server_ip).server_id
    from app.modules.pacemaker.autostart import assert_unmanaged
    assert_unmanaged(server_id, service)

    if service_common.is_not_allowed_to_restart(server_id, service, action):
        raise Exception('This server is not allowed to be restarted')

    try:
        if service != 'keepalived':
            service_common.check_service_config(server_ip, server_id, service)
    except Exception as e:
        raise Exception(f'Cannot check config: {e}')

    command = get_action_command(service, action, server_id)
    server_mod.ssh_command(server_ip, command)
    roxywi_common.logging(server_ip, f'Service {service.title()} has been {action}ed', keep_history=1, service=service)


def get_action_command(service: str, action: str, server_id: int) -> str:
    """
    :param service: The name of the service for which the action command is needed.
    :param action: The action to be performed on the service (e.g. start, stop, restart).
    :param server_id: The ID of the server.

    :return: A list containing the action command that needs to be executed.
    """
    if action not in ('start', 'stop', 'reload', 'restart'):
        raise ValueError('Unsupported service action')
    if service == 'waf' and action == 'reload':
        raise ValueError('The HAProxy WAF agent requires restart to apply rules')
    is_docker = service_sql.select_service_setting(server_id, service, 'dockerized')
    if is_docker == '1':
        container_name = sql.get_setting(f'{service}_container_name')
        arguments = ['kill', '-s', 'HUP'] if action == 'reload' else [action]
        commands = build_remote_command('docker', [*arguments, container_name], sudo=True) + ' > /dev/null'
    else:
        service_name = service_common.get_correct_service_name(service, server_id)
        commands = build_remote_command('systemctl', [action, service_name], sudo=True)

    return commands


def action_haproxy_waf(server_ip: str, action: str, service: str) -> None:
    service_common.is_protected(server_ip, action)
    roxywi_common.logging(
        server_ip, f'HAProxy WAF service has been {action}ed', keep_history=1, service='haproxy'
    )
    command = get_action_command('waf', action, server_sql.get_server_by_ip(server_ip).server_id)
    server_mod.ssh_command(server_ip, command)


def action_nginx_waf(server_ip: str, action: str, service: str) -> None:
    if action not in ('start', 'stop'):
        raise ValueError('NGINX WAF supports start and stop only')
    service_common.is_protected(server_ip, action)
    server_id = server_sql.get_server_by_ip(server_ip).server_id
    runtime = service_common.waf_runtime_settings('nginx', server_id)
    root = common.get_waf_directory('nginx')
    temporary = str(PurePosixPath(sql.get_setting('tmp_config_path')) / 'roxywi-nginx-waf-')
    if not temporary.startswith('/') or any(char in temporary for char in ('\x00', '\r', '\n')):
        raise ValueError('Invalid remote temporary configuration directory')
    with waf_state.operation_lock(server_ip, 'nginx'), TemporaryDirectory(prefix='roxywi-nginx-waf-') as directory:
        local = Path(directory) / 'nginx.conf'
        with mod_ssh.ssh_connect(server_ip) as ssh:
            ssh.get_sftp(runtime['main'], str(local))
        original = local.read_bytes()
        local.write_bytes(nginx.waf_configuration_candidate(original.decode('utf-8'), action == 'start').encode('utf-8'))
        remote = ''
        try:
            remote = server_mod.ssh_command(server_ip, build_remote_command('mktemp', [temporary + 'XXXXXX']),
                                            rc=1, error_context='Cannot prepare the NGINX WAF candidate').strip()
            if not re.fullmatch(re.escape(temporary) + r'[A-Za-z0-9]{6,}', remote):
                remote = ''
                raise RuntimeError('Unconfirmed remote temporary file path')
            with mod_ssh.ssh_connect(server_ip) as ssh:
                ssh.put_sftp(str(local), remote)
            command = candidate.candidate_command(
                'nginx', runtime['main'], remote, 'reload', root=root, **runtime,
                action_command=get_action_command('nginx', 'reload', server_id),
                expected_sha256=hashlib.sha256(original).hexdigest())
            with waf_state.track_changes(server_id, 'nginx', applying=True):
                output = server_mod.ssh_command(server_ip, command, rc=1, timeout=candidate.REMOTE_TIMEOUT,
                                                error_context='Cannot apply the NGINX WAF state')
                candidate.check_result(output)
        finally:
            if remote:
                try:
                    server_mod.ssh_command(server_ip, build_remote_command('rm', ['-f', '--', remote], sudo=True),
                                           rc=1, error_context='Cannot remove the NGINX WAF candidate')
                except Exception as exc:
                    logger.warning('Cannot remove the NGINX WAF candidate', server_ip=server_ip, cause=type(exc).__name__)
    roxywi_common.logging(server_ip, f'NGINX WAF {action} applied', keep_history=1, service='nginx')
