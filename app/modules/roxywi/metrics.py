import psutil

import modules.db.sql as sql
import modules.server.server as server_mod


def show_ram_metrics(metrics_type: str) -> dict:
    metrics = {'chartData': {}}
    rams = ''

    if metrics_type == '1':
        rams_list = psutil.virtual_memory()
        rams += str(round(rams_list.total / 1048576, 2)) + ' '
        rams += str(round(rams_list.used / 1048576, 2)) + ' '
        rams += str(round(rams_list.free / 1048576, 2)) + ' '
        rams += str(round(rams_list.shared / 1048576, 2)) + ' '
        rams += str(round(rams_list.cached / 1048576, 2)) + ' '
        rams += str(round(rams_list.available / 1048576, 2)) + ' '
    else:
        commands = ["free -m |grep Mem |awk '{print $2,$3,$4,$5,$6,$7}'"]
        metric, error = server_mod.subprocess_execute(commands[0])

        for i in metric:
            rams = i

    metrics['chartData']['rams'] = rams

    return metrics


def show_cpu_metrics(metrics_type: str) -> dict:
    metrics = {'chartData': {}}
    cpus = ''

    if metrics_type == '1':
        cpus_list = psutil.cpu_times_percent(interval=1, percpu=False)
        cpus += str(cpus_list.user) + ' '
        cpus += str(cpus_list.system) + ' '
        cpus += str(cpus_list.nice) + ' '
        cpus += str(cpus_list.idle) + ' '
        cpus += str(cpus_list.iowait) + ' '
        cpus += str(cpus_list.irq) + ' '
        cpus += str(cpus_list.softirq) + ' '
        cpus += str(cpus_list.steal) + ' '
    else:
        commands = [
            "top -b -n 1 |grep Cpu |awk -F':' '{print $2}'|awk  -F' ' 'BEGIN{ORS=\" \";} { for (i=1;i<=NF;i+=2) print $i}'"]
        metric, error = server_mod.subprocess_execute(commands[0])

        for i in metric:
            cpus = i

    metrics['chartData']['cpus'] = cpus

    return metrics


def haproxy_metrics(server_ip: str, hostname: str, time_range: str) -> dict:
    metric = sql.select_metrics(server_ip, 'haproxy', time_range=time_range)
    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''
    curr_ssl_con = ''
    sess_rate = ''
    server = ''

    for i in metric:
        label = str(i[5])
        label = label.split(' ')[1]
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
    metric = sql.select_metrics(server_ip, 'http_metrics', time_range=time_range)
    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    http_2xx = ''
    http_3xx = ''
    http_4xx = ''
    http_5xx = ''
    server = ''

    for i in metric:
        label = str(i[5])
        label = label.split(' ')[1]
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
    metric = sql.select_metrics(server_ip, service, time_range=time_range)

    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''

    for i in metric:
        label = str(i[2])
        label = label.split(' ')[1]
        labels += label + ','
        curr_con += str(i[1]) + ','

    metrics['chartData']['labels'] = labels
    metrics['chartData']['curr_con'] = curr_con
    metrics['chartData']['server'] = f'{hostname} ({server_ip})'

    return metrics
