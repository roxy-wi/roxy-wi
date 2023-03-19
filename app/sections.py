#!/usr/bin/env python3
import os
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.config.section as section_mod
import modules.config.config as config_mod
import modules.roxy_wi_tools as roxy_wi_tools

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True, extensions=['jinja2.ext.loopcontrols'])
template = env.get_template('sections.html')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)
except Exception as e:
	print(f'error {e}')
	sys.exit()

form = common.form
serv = form.getvalue('serv')
section = form.getvalue('section')
is_serv_protected = sql.is_serv_protected(serv)
sections = ""
config_read = ""
cfg = ""
stderr = ""
error = ""
aftersave = ""
start_line = ""
end_line = ""
warning = ''
is_restart = ''

hap_configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')

if serv is not None and open is not None:
	cfg = f"{hap_configs_dir}{serv}-{get_date.return_date('config')}.cfg"
	error = config_mod.get_config(serv, cfg)
	sections = section_mod.get_sections(cfg)

if serv is not None and section is not None:

	try:
		roxywi_common.logging(serv, "sections.py open config")
	except Exception:
		pass

	start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section)
	server_id = sql.select_server_id_by_ip(serv)
	is_restart = sql.select_service_setting(server_id, 'haproxy', 'restart')

	os.system(f"/bin/mv {cfg} {cfg}.old")

if serv is not None and form.getvalue('config') is not None:
	try:
		roxywi_common.logging(serv, "sections.py edited config")
	except Exception:
		pass

	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')
	start_line = form.getvalue('start_line')
	end_line = form.getvalue('end_line')
	aftersave = 1

	if save == 'delete':
		config = ''
		save = 'reload'

	config = section_mod.rewrite_section(start_line, end_line, oldcfg, config)

	try:
		with open(cfg, "w") as conf:
			conf.write(config)
	except IOError:
		error = "Can't read import config file"

	stderr = config_mod.master_slave_upload_and_restart(serv, cfg, just_save=save, oldcfg=oldcfg)

	if "is valid" in stderr:
		warning = stderr
		stderr = ''

	config_mod.diff_config(oldcfg, cfg)

	os.system(f"/bin/rm -f {hap_configs_dir}*.old")

if user_params['lang'] == 'ru':
	title = 'Работа с секциями HAProxy'
elif user_params['lang'] == 'fr':
	title = 'Utilisation des sections de configuration HAProxy'
else:
	title = 'Working with HAProxy config sections'

rendered_template = template.render(
	h2=1, title=title, role=user_params['role'], action="sections.py", user=user_params['user'],
	select_id="serv", serv=serv, aftersave=aftersave, config=config_read, cfg=cfg, selects=user_params['servers'],
	stderr=stderr, error=error, start_line=start_line, end_line=end_line, section=section, sections=sections,
	is_serv_protected=is_serv_protected, user_services=user_params['user_services'], token=user_params['token'],
	warning=warning, is_restart=is_restart, lang=user_params['lang']
)
print(rendered_template)
