#!/usr/bin/env python3
import os
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.config.config as config_mod
import modules.roxy_wi_tools as roxy_wi_tools

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('waf.html')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(haproxy=1)

form = common.form
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


roxywi_auth.page_for_admin(level=2)

if service == 'nginx':
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=2)
	servers = roxywi_common.get_dick_permit(nginx=1)
else:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)
	servers = user_params['servers']

if manage_rules == '1':
	serv = common.is_ip_or_dns(form.getvalue('serv'))
	roxywi_common.check_is_server_in_group(serv)
	title = "Manage rules - Web application firewall"
	rules = sql.select_waf_rules(serv, service)
elif waf_rule_id and form.getvalue('config') is None:
	serv = common.is_ip_or_dns(form.getvalue('serv'))
	roxywi_common.check_is_server_in_group(serv)
	title = 'Edit a WAF rule'
	waf_rule_file = sql.select_waf_rule_by_id(waf_rule_id)
	configs_dir = sql.get_setting('tmp_config_path')
	cfg = configs_dir + serv + "-" + get_date.return_date('config') + "-" + waf_rule_file
	error = config_mod.get_config(serv, cfg, waf=service, waf_rule_file=waf_rule_file)
	if service == 'haproxy':
		config_path = sql.get_setting('haproxy_dir')
	elif service == 'nginx':
		config_path = sql.get_setting('nginx_dir')

	config_file_name = common.return_nice_path(config_path) + 'waf/rules/' + waf_rule_file
	try:
		conf = open(cfg, "r")
		config_read = conf.read()
		conf.close()
	except IOError:
		print('Cannot read imported config file')
else:
	title = "Web application firewall"
	servers_waf = sql.select_waf_servers_metrics(user_params['user_uuid'].value)
	autorefresh = 1

if serv is not None and form.getvalue('config') is not None:
	roxywi_common.check_is_server_in_group(serv)

	configs_dir = sql.get_setting('tmp_config_path')
	cfg = configs_dir + serv + "-" + get_date.return_date('config')
	config_file_name = form.getvalue('config_file_name')
	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')

	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		print("error: Cannot read imported config file")

	stderr = config_mod.master_slave_upload_and_restart(serv, cfg, just_save=save, waf=1, oldcfg=oldcfg, config_file_name=config_file_name)

	config_mod.diff_config(oldcfg, cfg)

	try:
		os.system("/bin/rm -f " + configs_dir + "*.old")
	except Exception as e:
		print('error: ' + str(e))

	if stderr:
		print(stderr)

	sys.exit()

rendered_template = template.render(
	h2=1, title=title, autorefresh=autorefresh, role=user_params['role'], user=user_params['user'], serv=serv, servers=servers_waf,
	servers_all=servers, manage_rules=manage_rules, rules=rules, user_services=user_params['user_services'],
	waf_rule_file=waf_rule_file, waf_rule_id=waf_rule_id, config=config_read, cfg=cfg, token=user_params['token'],
	config_file_name=config_file_name, service=service, lang=user_params['lang']
)
print(rendered_template)
