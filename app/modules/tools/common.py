import distro

import modules.db.sql as sql
import modules.roxywi.roxy as roxywi_mod
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common


def get_services_status():
    services = []
    is_in_docker = roxywi_mod.is_docker()
    services_name = {
        'roxy-wi-checker': '',
        'roxy-wi-keep_alive': '',
        'roxy-wi-metrics': '',
        'roxy-wi-portscanner': '',
        'roxy-wi-smon': '',
        'roxy-wi-socket': '',
        'roxy-wi-prometheus-exporter': 'Prometheus exporter',
        'prometheus': 'Prometheus service',
        'grafana-server': 'Grafana service',
        'fail2ban': 'Fail2ban service',
        'rabbitmq-server': 'Message broker service'
    }
    for s, v in services_name.items():
        if is_in_docker:
            cmd = f"sudo supervisorctl status {s}|awk '{{print $2}}'"
        else:
            cmd = f"systemctl is-active {s}"

        status, stderr = server_mod.subprocess_execute(cmd)

        if s != 'roxy-wi-keep_alive':
            service_name = s.split('_')[0]
            if s == 'grafana-server':
                service_name = 'grafana'
        elif s == 'roxy-wi-keep_alive' and distro.id() == 'ubuntu':
            service_name = 'roxy-wi-keep-alive'
        else:
            service_name = s

        if service_name == 'prometheus':
            cmd = "prometheus --version 2>&1 |grep prometheus|awk '{print $3}'"
        else:
            if distro.id() == 'ubuntu':
                cmd = f"apt list --installed 2>&1 |grep {service_name}|awk '{{print $2}}'|sed 's/-/./'"
            else:
                cmd = f"rpm -q {service_name}|awk -F\"{service_name}\" '{{print $2}}' |awk -F\".noa\" '{{print $1}}' |sed 's/-//1' |sed 's/-/./'"
        service_ver, stderr = server_mod.subprocess_execute(cmd)

        try:
            if service_ver[0] == 'command' or service_ver[0] == 'prometheus:':
                service_ver[0] = ''
        except Exception:
            pass

        try:
            services.append([s, status, v, service_ver[0]])
        except Exception:
            services.append([s, status, v, ''])

    return services


def update_roxy_wi(service: str) -> str:
    restart_service = ''
    services = ['roxy-wi-checker',
                'roxy-wi',
                'roxy-wi-keep_alive',
                'roxy-wi-smon',
                'roxy-wi-metrics',
                'roxy-wi-portscanner',
                'roxy-wi-socket',
                'roxy-wi-prometheus-exporter']

    if service not in services:
        raise Exception(f'error: {service} is not part of Roxy-WI')

    if distro.id() == 'ubuntu':
        try:
            if service == 'roxy-wi-keep_alive':
                service = 'roxy-wi-keep-alive'
        except Exception:
            pass

        if service != 'roxy-wi':
            restart_service = f'&& sudo systemctl restart {service}'

        cmd = f'sudo -S apt-get update && sudo apt-get install {service} {restart_service}'
    else:
        if service != 'roxy-wi':
            restart_service = f'&& sudo systemctl restart {service}'
        cmd = f'sudo -S yum -y install {service} {restart_service}'

    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        return str(stderr)
    else:
        return str(output)
