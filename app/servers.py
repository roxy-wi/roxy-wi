#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('servers.html')
form = funct.form

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level=2)
try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
	ldap_enable = sql.get_setting('ldap_enable')
	user_group = funct.get_user_group(id=1)
	settings = sql.get_setting('', all=1)
	geoip_country_codes = sql.select_geoip_country_codes()
	services = sql.select_services()
except Exception as e:
	pass


output_from_parsed_template = template.render(title="Servers: ",
												role=role,
												user=user,
												users=sql.select_users(group=user_group),
												groups=sql.select_groups(),
												servers=sql.get_dick_permit(virt=1, disable=0, only_group=1),
												roles=sql.select_roles(),
												masters=sql.select_servers(get_master_servers=1, uuid=user_id.value),
												group=user_group,
												sshs=sql.select_ssh(group=user_group),
												token=token,
												settings=settings,
												backups=sql.select_backups(),
												page="servers.py",
												geoip_country_codes=geoip_country_codes,
												user_services=user_services,
												ldap_enable=ldap_enable,
											  	services=services)
print(output_from_parsed_template)
