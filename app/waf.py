#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('waf.html')

form = funct.form
manage_rules = form.getvalue('manage_rules')
waf_rule_id = form.getvalue('waf_rule_id')
waf_rule_file = ''
servers_waf = ''
autorefresh = 0
config_read = ''
serv = ''
rules = ''
cfg = ''

print('Content-type: text/html\n')
funct.check_login(service=1)
funct.page_for_admin(level=2)

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
except Exception:
	pass

if manage_rules == '1':
	serv = funct.is_ip_or_dns(form.getvalue('serv'))
	funct.check_is_server_in_group(serv)
	title = "Manage rules - Web application firewall"
	rules = sql.select_waf_rules(serv)
elif waf_rule_id:
	serv = funct.is_ip_or_dns(form.getvalue('serv'))
	funct.check_is_server_in_group(serv)
	title = 'Edit a WAF rule'
	waf_rule_file = sql.select_waf_rule_by_id(waf_rule_id)
	configs_dir = sql.get_setting('tmp_config_path')
	cfg = configs_dir + serv + "-" + funct.get_data('config') + "-" + waf_rule_file
	error = funct.get_config(serv, cfg, waf=1, waf_rule_file=waf_rule_file)

	try:
		conf = open(cfg, "r")
		config_read = conf.read()
		conf.close()
	except IOError:
		print('Cannot read imported config file')
else:
	title = "Web application firewall"
	servers_waf = sql.select_waf_servers_metrics(user_id.value)
	autorefresh = 1

template = template.render(h2=1, title=title,
							autorefresh=autorefresh,
							role=role,
							user=user,
							serv=serv,
							servers=servers_waf,
							servers_all=servers,
							manage_rules=manage_rules,
							rules=rules,
							user_services=user_services,
						   	waf_rule_file=waf_rule_file,
							waf_rule_id=waf_rule_id,
							config=config_read,
							cfg=cfg,
							token=token)
print(template)
