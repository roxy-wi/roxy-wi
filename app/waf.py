#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('waf.html')

form = funct.form
manage_rules = form.getvalue('manage_rules')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level=2)

try:
	user, user_id, role, token, servers = funct.get_users_params()
except Exception:
	pass

if manage_rules == '1':
	serv = form.getvalue('serv')
	funct.check_is_server_in_group(serv)
	title = "Manage rules - Web application firewall"
	servers_waf = ''
	autorefresh = 0
	rules = sql.select_waf_rules(serv)
else:
	title = "Web application firewall"
	servers_waf = sql.select_waf_servers_metrics(user_id.value)
	autorefresh = 1
	serv = ''
	rules = ''

template = template.render(h2=1, title=title,
							autorefresh=autorefresh,
							role=role,
							user=user,
							serv=serv,
							servers=servers_waf,
							servers_all=servers,
							manage_rules=manage_rules,
							rules=rules,
							token=token)
print(template)
