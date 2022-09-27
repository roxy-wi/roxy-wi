#!/usr/bin/env python3
import os
import sys

from jinja2 import Environment, FileSystemLoader

import sql
import funct
import modules.roxy_wi_tools as roxy_wi_tools

get_config_var = roxy_wi_tools.GetConfigVar()
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True, extensions=['jinja2.ext.loopcontrols'])
template = env.get_template('sections.html')

print('Content-type: text/html\n')

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
except Exception:
	pass

try:
	funct.check_login(user_id, token, service=1)
except Exception as e:
	print(f'error {e}')
	sys.exit()

form = funct.form
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
	cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
	error = funct.get_config(serv, cfg)
	sections = funct.get_sections(cfg)

if serv is not None and section is not None:

	try:
		funct.logging(serv, "sections.py open config")
	except Exception:
		pass

	start_line, end_line, config_read = funct.get_section_from_config(cfg, section)
	server_id = sql.select_server_id_by_ip(serv)
	is_restart = sql.select_service_setting(server_id, 'haproxy', 'restart')

	os.system("/bin/mv %s %s.old" % (cfg, cfg))

if serv is not None and form.getvalue('config') is not None:
	try:
		funct.logging(serv, "sections.py edited config")
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

	config = funct.rewrite_section(start_line, end_line, oldcfg, config)

	try:
		with open(cfg, "w") as conf:
			conf.write(config)
	except IOError:
		error = "Can't read import config file"

	stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save, oldcfg=oldcfg)

	if "is valid" in stderr:
		warning = stderr
		stderr = ''

	funct.diff_config(oldcfg, cfg)

	os.system("/bin/rm -f " + hap_configs_dir + "*.old")


rendered_template = template.render(
	h2=1, title="Working with HAProxy config sections", role=role, action="sections.py", user=user, select_id="serv",
	serv=serv, aftersave=aftersave, config=config_read, cfg=cfg, selects=servers, stderr=stderr, error=error,
	start_line=start_line, end_line=end_line, section=section, sections=sections, is_serv_protected=is_serv_protected,
	user_services=user_services, token=token, warning=warning, is_restart=is_restart
)
print(rendered_template)
