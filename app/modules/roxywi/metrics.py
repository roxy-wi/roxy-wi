import psutil

import app.modules.db.metric as metric_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod


def show_ram_metrics(server_ip: str) -> dict:
    metrics = {'chartData': {}}
    rams = ''

    if str(server_ip) == '127.0.0.1':
        rams_list = psutil.virtual_memory()
        for i in (rams_list.used, rams_list.free, rams_list.shared, rams_list.cached, rams_list.available, rams_list.total):
            rams += str(round(i / 1048576, 2)) + ' '
    else:
        commands = "sudo free -m |grep Mem |awk '{print $3,$4,$5,$6,$7,$2}'"
        rams = server_mod.ssh_command(server_ip, commands).replace('\r', '').replace('\n', '')

    metrics['chartData']['rams'] = rams

    return metrics


def show_cpu_metrics(server_ip: str) -> dict:
    metrics = {'chartData': {}}
    cpus = ''
    if str(server_ip) == '127.0.0.1':
        total = psutil.cpu_percent(0.5)
        cpus_list = psutil.cpu_times_percent(interval=0.5, percpu=False)
        for i in (cpus_list.user, cpus_list.system, cpus_list.nice, cpus_list.idle, cpus_list.iowait, cpus_list.irq, cpus_list.softirq, cpus_list.steal):
            cpus += str(round(i, 2)) + ' '
        cpus += str(total) + ' '
    else:
        cmd = "top -d 0.5 -b -n2 | grep 'Cpu(s)'|tail -n 1 | awk '{print $2 + $4}'"
        total = server_mod.ssh_command(server_ip, cmd).replace('\r', '').replace('\n', '')
        cmd = "sudo top -b -n 1 |grep Cpu |awk -F':' '{print $2}'|awk -F' ' 'BEGIN{ORS=\" \";} { for (i=1;i<=NF;i+=2) print $i}'"
        cpus = server_mod.ssh_command(server_ip, cmd)
        cpus += total

    metrics['chartData']['cpus'] = cpus

    return metrics


def haproxy_metrics(server_ip: str, hostname: str, time_range: str) -> dict:
    metric = metric_sql.select_metrics(server_ip, 'haproxy', time_range=time_range)
    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''
    curr_ssl_con = ''
    sess_rate = ''
    server = ''

    for i in metric:
        label = i[5]
        metric_time = common.get_time_zoned_date(label, '%H:%M:%S')
        label = metric_time
        labels += label + ','
        curr_con += str(i[1]) + ','
        curr_ssl_con += str(i[2]) + ','
        sess_rate += str(i[3]) + ','
        server = str(i[0])

    metrics['chartData']['labels'] = labels
    metrics['chartData']['curr_con'] = curr_con
    metrics['chartData']['curr_ssl_con'] = curr_ssl_con
    metrics['chartData']['sess_rate'] = sess_rate
    metrics['chartData']['server'] = hostname + ' (' + server + ')'

    return metrics


def haproxy_http_metrics(server_ip: str, hostname: str, time_range: str) -> dict:
    metric = metric_sql.select_metrics(server_ip, 'http_metrics', time_range=time_range)
    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    http_2xx = ''
    http_3xx = ''
    http_4xx = ''
    http_5xx = ''
    server = ''

    for i in metric:
        label = i[5]
        metric_time = common.get_time_zoned_date(label, '%H:%M:%S')
        label = metric_time
        labels += label + ','
        http_2xx += str(i[1]) + ','
        http_3xx += str(i[2]) + ','
        http_4xx += str(i[3]) + ','
        http_5xx += str(i[4]) + ','
        server = str(i[0])

    metrics['chartData']['labels'] = labels
    metrics['chartData']['http_2xx'] = http_2xx
    metrics['chartData']['http_3xx'] = http_3xx
    metrics['chartData']['http_4xx'] = http_4xx
    metrics['chartData']['http_5xx'] = http_5xx
    metrics['chartData']['server'] = f'{hostname} ({server})'

    return metrics


def service_metrics(server_ip: str, hostname: str, service: str, time_range: str) -> dict:
    metric = metric_sql.select_metrics(server_ip, service, time_range=time_range)

    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''

    for i in metric:
        label = i[2]
        metric_time = common.get_time_zoned_date(label, '%H:%M:%S')
        label = metric_time
        labels += label + ','
        curr_con += str(i[1]) + ','

    metrics['chartData']['labels'] = labels
    metrics['chartData']['curr_con'] = curr_con
    metrics['chartData']['server'] = f'{hostname} ({server_ip})'

    return metrics
