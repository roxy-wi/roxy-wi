import app.modules.db.sql as sql
from app.modules.service.installation import run_ansible_thread


def generate_exporter_inv(server_ip: str, ver: str, exporter: str, options=None) -> object:
    inv = {"server": {"hosts": {}}}
    server_ips = [server_ip]
    inv['server']['hosts'][server_ip] = {
        f'{exporter}_exporter_version': ver,
        'service': f'{exporter} exporter'
    }

    if exporter == 'ha_cluster':
        from app.modules.pacemaker.exporter import inventory
        inv['server']['hosts'][server_ip] = inventory(server_ip,ver,options)

    if exporter in ('haproxy', 'nginx', 'apache'):
        inv['server']['hosts'][server_ip]['STAT_PORT'] = sql.get_setting(f'{exporter}_stats_port')
        inv['server']['hosts'][server_ip]['STATS_USER'] = sql.get_setting(f'{exporter}_stats_user')
        inv['server']['hosts'][server_ip]['STATS_PASS'] = sql.get_setting(f'{exporter}_stats_password')
        inv['server']['hosts'][server_ip]['STAT_PAGE'] = sql.get_setting(f'{exporter}_stats_page')

    if exporter == 'haproxy':
        inv['server']['hosts'][server_ip]['STAT_FILE'] = sql.get_setting('server_state_file')

    return inv, server_ips


def install_exporter(server_ip: str, ver: str, exporter: str, options=None) -> int:
    service = 'Corosync / Pacemaker exporter' if exporter == 'ha_cluster' else f'{exporter.title()} exporter'
    try:
        inv, server_ips = generate_exporter_inv(server_ip, ver, exporter, options)
    except Exception as e:
        raise Exception(f'Cannot generate {exporter} inventory: {e}')

    return run_ansible_thread(inv, server_ips, f'{exporter}_exporter', service)
