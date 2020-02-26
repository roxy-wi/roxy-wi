#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(extensions=["jinja2.ext.do"],loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('servers.html')
form = funct.form

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)
try:
	user, user_id, role, token, servers = funct.get_users_params()
	ldap_enable = sql.get_setting('ldap_enable')
except:
	pass


output_from_parsed_template = template.render(title = "Servers manage",
												role = role,
												user = user,
												users = sql.select_users(),
												groups = sql.select_groups(),
												servers = sql.get_dick_permit(virt=1, disable=0),
												roles = sql.select_roles(),
												masters = sql.select_servers(get_master_servers=1, uuid=user_id.value),
												group = sql.get_user_group_by_uuid(user_id.value),
												sshs = sql.select_ssh(),
												telegrams = sql.get_user_telegram_by_uuid(user_id.value),
												token = token,
												versions = funct.versions(),
												backups = sql.select_backups(),
												ldap_enable = ldap_enable)
print(output_from_parsed_template)
