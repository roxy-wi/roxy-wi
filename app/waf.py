#!/usr/bin/env python3
import os
import sys

import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('waf.html')

form = funct.form
manage_rules = form.getvalue('manage_rules')
waf_rule_id = form.getvalue('waf_rule_id')
service = form.getvalue('service')
serv = form.getvalue('serv')
config_file_name = ''
waf_rule_file = ''
servers_waf = ''
autorefresh = 0
config_read = ''
rules = ''
cfg = ''

print('Content-type: text/html\n')
funct.page_for_admin(level=2)

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params(haproxy=1)
except Exception:
	pass

if service == 'nginx':
	funct.check_login(service=2)
else:
	funct.check_login(service=1)

if manage_rules == '1':
	serv = funct.is_ip_or_dns(form.getvalue('serv'))
	funct.check_is_server_in_group(serv)
	title = "Manage rules - Web application firewall"
	rules = sql.select_waf_rules(serv, service)
elif waf_rule_id and form.getvalue('config') is None:
	serv = funct.is_ip_or_dns(form.getvalue('serv'))
	funct.check_is_server_in_group(serv)
	title = 'Edit a WAF rule'
	waf_rule_file = sql.select_waf_rule_by_id(waf_rule_id)
	configs_dir = sql.get_setting('tmp_config_path')
	cfg = configs_dir + serv + "-" + funct.get_data('config') + "-" + waf_rule_file
	error = funct.get_config(serv, cfg, waf=service, waf_rule_file=waf_rule_file)
	if service == 'haproxy':
		config_path = sql.get_setting('haproxy_dir')
	elif service == 'nginx':
		config_path = sql.get_setting('nginx_dir')

	config_file_name = funct.return_nice_path(config_path) + 'waf/rules/' + waf_rule_file
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

if serv is not None and form.getvalue('config') is not None:
	funct.check_is_server_in_group(serv)

	configs_dir = sql.get_setting('tmp_config_path')
	cfg = configs_dir + serv + "-" + funct.get_data('config')
	config_file_name = form.getvalue('config_file_name')
	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')

	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		print("error: Cannot read imported config file")

	stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save, waf=1, oldcfg=oldcfg, config_file_name=config_file_name)

	funct.diff_config(oldcfg, cfg)

	try:
		os.system("/bin/rm -f " + configs_dir + "*.old")
	except Exception as e:
		print('error: ' + str(e))

	if stderr:
		print(stderr)

	sys.exit()

rendered_template = template.render(
	h2=1, title=title, autorefresh=autorefresh, role=role, user=user, serv=serv, servers=servers_waf,
	servers_all=servers, manage_rules=manage_rules, rules=rules, user_services=user_services,
	waf_rule_file=waf_rule_file, waf_rule_id=waf_rule_id, config=config_read, cfg=cfg, token=token,
	config_file_name=config_file_name, service=service
)
print(rendered_template)
