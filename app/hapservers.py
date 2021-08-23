#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('hapservers.html')

print('Content-type: text/html\n')
funct.check_login()

try:
    user, user_id, role, token, servers, user_services = funct.get_users_params()
    services = []
except:
    pass

form = funct.form
serv = funct.is_ip_or_dns(form.getvalue('serv'))
service = form.getvalue('service')
autorefresh = 0
cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
keep_alive, stderr = funct.subprocess_execute(cmd)

if service == 'nginx':
    if funct.check_login(service=2):
        title = 'Nginx servers overview'
        servers = sql.get_dick_permit(virt=1, nginx=1)
        service = 'nginx'
        if serv:
            if funct.check_is_server_in_group(serv):
                servers = sql.select_servers(server=serv)
                autorefresh = 1
elif service == 'keepalived':
    if funct.check_login(service=3):
        title = 'Keepalived servers overview'
        servers = sql.get_dick_permit(virt=1, keepalived=1)
        service = 'keepalived'
        if serv:
            if funct.check_is_server_in_group(serv):
                servers = sql.select_servers(server=serv)
                autorefresh = 1
else:
    if funct.check_login(service=1):
        title = "HAProxy servers overview"
        service = 'haproxy'
        if serv:
            if funct.check_is_server_in_group(serv):
                servers = sql.select_servers(server=serv)
                autorefresh = 1
        else:
            servers = sql.get_dick_permit(virt=1, haproxy=1)

services_name = {'roxy-wi-checker': 'Master backends checker service',
                 'roxy-wi-keep_alive': 'Auto start service',
                 'roxy-wi-metrics': 'Master metrics service'}
for s, v in services_name.items():
    if s != 'roxy-wi-keep_alive':
        service_name = s.split('_')[0]
    else:
        service_name = s
    cmd = "rpm --query " + service_name + "-* |awk -F\"" + service_name + "\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
    service_ver, stderr = funct.subprocess_execute(cmd)
    try:
        services.append([s, service_ver[0]])
    except Exception:
        services.append([s, ''])

haproxy_sock_port = sql.get_setting('haproxy_sock_port')
servers_with_status1 = []
out1 = ''
for s in servers:
    servers_with_status = list()
    servers_with_status.append(s[0])
    servers_with_status.append(s[1])
    servers_with_status.append(s[2])
    servers_with_status.append(s[11])
    if service == 'nginx':
        h = (['', ''],)
        cmd = [
            "/usr/sbin/nginx -v 2>&1|awk '{print $3}' && systemctl status nginx |grep -e 'Active' |awk '{print $2, $9$10$11$12$13}' && ps ax |grep nginx:|grep -v grep |wc -l"]
        try:
            out = funct.ssh_command(s[2], cmd)
            h = ()
            out1 = []
            for k in out.split():
                out1.append(k)
            h = (out1,)
            servers_with_status.append(h)
            servers_with_status.append(h)
            servers_with_status.append(s[17])
        except:
            servers_with_status.append(h)
            servers_with_status.append(h)
            servers_with_status.append(s[17])
    elif service == 'keepalived':
        h = (['',''],)
        cmd = [
            "/usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}' && systemctl status keepalived |grep -e 'Active' |awk '{print $2, $9$10$11$12$13}' && ps ax |grep keepalived|grep -v grep |wc -l"]
        try:
            out = funct.ssh_command(s[2], cmd)
            out1 = []
            for k in out.split():
                out1.append(k)
            h = (out1,)
            servers_with_status.append(h)
            servers_with_status.append(h)
            servers_with_status.append(s[17])
        except:
            servers_with_status.append(h)
            servers_with_status.append(h)
            servers_with_status.append(s[17])
    else:
        cmd = 'echo "show info" |nc %s %s -w 1 |grep -e "Ver\|Uptime:\|Process_num"' % (s[2], haproxy_sock_port)
        out = funct.subprocess_execute(cmd)
        for k in out:
            if "Ncat:" not in k:
                out1 = out
            else:
                out1 = False
            servers_with_status.append(out1)

        servers_with_status.append(s[12])

    servers_with_status.append(sql.is_master(s[2]))
    servers_with_status.append(sql.select_servers(server=s[2]))

    is_keepalived = sql.select_keepalived(s[2])

    if is_keepalived:
        try:
            cmd = ['sudo kill -USR1 `cat /var/run/keepalived.pid` && sudo grep State /tmp/keepalived.data -m 1 |awk -F"=" \'{print $2}\'|tr -d \'[:space:]\' && sudo rm -f /tmp/keepalived.data' ]
            out = funct.ssh_command(s[2], cmd)
            out1 = ('1', out)
            servers_with_status.append(out1)
        except Exception:
            servers_with_status.append('')
    else:
        servers_with_status.append('')

    servers_with_status1.append(servers_with_status)

template = template.render(h2=1,
                           autorefresh=autorefresh,
                           title=title,
                           role=role,
                           user=user,
                           servers=servers_with_status1,
                           keep_alive=''.join(keep_alive),
                           serv=serv,
						   service=service,
						   services=services,
                           user_services=user_services,
						   token=token)
print(template)
