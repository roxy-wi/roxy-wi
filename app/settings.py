#!/usr/bin/env python3
import html, http
import cgi
import sys
import os
import funct, sql
from configparser import ConfigParser, ExtendedInterpolation
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('viewsettings.html')

form = cgi.FieldStorage()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)
fullpath = config.get('main', 'fullpath')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin()
try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
except:
	pass
	
config_items_section_name = {}
for section_name in config.sections():
	config_items_section_name[section_name] = {}
	for name, value in config.items(section_name):
		config_items_section_name[section_name][name] =  value

output_from_parsed_template = template.render(h2 = 1, title = "Admin area: View settings",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												fullpath = fullpath,
												config_items_section_name = config_items_section_name)											
print(output_from_parsed_template)
