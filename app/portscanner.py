#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('portscanner.html')
form = funct.form
serv = form.getvalue('history')

print('Content-type: text/html\n')
funct.check_login()

try:
    user, user_id, role, token, servers, user_services = funct.get_users_params(virt=1)
except Exception as e:
    print(str(e))

if serv:
    title = 'Port scanner history for ' + serv
    port_scanner_settings = sql.select_port_scanner_history(serv)
    history = '1'
    port_scanner = ''
    port_scanner_stderr = ''
    count_ports = ''
else:
    history = ''
    title = 'Port scanner dashboard'
    user_group = funct.get_user_group(id=1)
    port_scanner_settings = sql.select_port_scanner_settings(user_group)
    if not port_scanner_settings:
        port_scanner_settings = ''
        count_ports = ''
    else:
        count_ports = list()
        for s in servers:
            count_ports_from_sql = sql.select_count_opened_ports(s[2])
            i = (s[2], count_ports_from_sql)
            count_ports.append(i)

    cmd = "systemctl is-active roxy-wi-portscanner"
    port_scanner, port_scanner_stderr = funct.subprocess_execute(cmd)

try:
    user_status, user_plan = funct.return_user_status()
except Exception as e:
    user_status, user_plan = 0, 0
    funct.logging('localhost', 'Cannot get a user plan: ' + str(e), haproxywi=1)


output_from_parsed_template = template.render(h2=1, autorefresh=0,
                                                title=title,
                                                role=role,
                                                user=user,
                                                servers=servers,
                                                port_scanner_settings=port_scanner_settings,
                                                count_ports=count_ports,
                                                history=history,
                                                port_scanner=''.join(port_scanner),
                                                port_scanner_stderr=port_scanner_stderr,
                                                user_services=user_services,
                                                user_status=user_status,
                                                user_plan=user_plan,
                                                token=token)
print(output_from_parsed_template)
