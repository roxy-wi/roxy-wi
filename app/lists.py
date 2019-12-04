#!/usr/bin/env python3
import os
import http, cgi
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('lists.html')

print('Content-type: text/html\n')
funct.check_login()
form = funct.form
funct.page_for_admin(level = 2)

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	user_group = sql.get_user_group_by_uuid(user_id.value)
	servers = sql.get_dick_permit(virt=1)
	token = sql.get_token(user_id.value)
	servbackend = form.getvalue('servbackend')
	serv = form.getvalue('serv')
	if servbackend is None:
		servbackend = ""
except:
	pass
	
	
dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')
white_dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+user_group+"/white"
black_dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+user_group+"/black"
if not os.path.exists(dir):
    os.makedirs(dir)
if not os.path.exists(dir+"/"+user_group):
    os.makedirs(dir+"/"+user_group)
if not os.path.exists(white_dir):
    os.makedirs(white_dir)
if not os.path.exists(black_dir):
    os.makedirs(black_dir)
	
white_lists = funct.get_files(dir=white_dir, format="lst")
black_lists = funct.get_files(dir=black_dir, format="lst")

template = template.render(h2 = 1,
							title = "Lists",
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							white_lists = white_lists,
							black_lists = black_lists,
							group = user_group,
							versions = funct.versions(),
							token = token)											
print(template)
