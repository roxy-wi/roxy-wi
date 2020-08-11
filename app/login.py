#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import funct
import http.cookies
import sql
import create_db
import datetime
import uuid
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('login.html')
form = funct.form

cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
user_id = cookie.get('uuid')
ref = form.getvalue('ref')
login = form.getvalue('login')
password = form.getvalue('pass')
db_create = ""
error_log = ""
error = ""

def send_cookie(login):
	session_ttl = sql.get_setting('session_ttl')
	session_ttl = int(session_ttl)
	expires = datetime.datetime.utcnow() + datetime.timedelta(days=session_ttl)
	user_uuid = str(uuid.uuid4())
	user_token = str(uuid.uuid4())
	sql.write_user_uuid(login, user_uuid)
	sql.write_user_token(login, user_token)

	id = sql.get_user_id_by_uuid(user_uuid)
	try:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_group_id = cookie.get('group')
		user_group_id = user_group_id.value
		if sql.check_user_group(id,user_group_id):
			user_groups = user_group_id
		else:
			user_groups = sql.select_user_groups(id, limit=1)
	except:
		user_groups = sql.select_user_groups(id, limit=1)

	c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	c["uuid"] = user_uuid
	c["uuid"]["path"] = "/app"
	# c["uuid"]["samesite"] = "Strict"
	c["uuid"]["Secure"] = "True"
	c["uuid"]["expires"] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
	c["group"] = user_groups
	c["group"]["path"] = "/app"
	# c["group"]["samesite"] = "Strict"
	c["group"]["Secure"] = "True"
	c["group"]["expires"] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
	print(c.output())

	try:
		groups = sql.select_groups(id=user_groups)
		for g in groups:
			if g[0] == int(user_groups):
				user_group = g[1]
	except:
		user_group = ''

	try:
		funct.logging('locahost', ' user: '+sql.get_user_name_by_uuid(user_uuid)+', group: '+user_group+' log in', haproxywi=1)
	except:
		pass
	print("Content-type: text/html\n")
	print('ok')
	sys.exit()


def ban():
	c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=10)
	c["ban"] = 1
	c["ban"]["path"] = "/"
	# c["ban"]["samesite"] = "Strict"
	c["ban"]["Secure"] = "True"
	c["ban"]["expires"] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
	try:
		funct.logging('locahost', login+' failed log in', haproxywi=1, login=1)
	except:
		funct.logging('locahost', ' Failed log in. Wrong username', haproxywi=1)
	print(c.output())
	print("Content-type: text/html\n")
	print('ban')


def check_in_ldap(user, password):
	import ldap

	server = sql.get_setting('ldap_server')
	port = sql.get_setting('ldap_port')
	ldap_class_search = sql.get_setting('ldap_class_search')
	root_user = sql.get_setting('ldap_user')
	root_password = sql.get_setting('ldap_password')
	ldap_base = sql.get_setting('ldap_base')
	ldap_search_field = sql.get_setting('ldap_search_field')
	ldap_user_attribute = sql.get_setting('ldap_user_attribute')
	ldap_type = sql.get_setting('ldap_type')

	ldap_proto = 'ldap' if ldap_type == "0" else 'ldaps'

	l = ldap.initialize('{}://{}:{}/'.format(ldap_proto,server, port))
	try:
		l.protocol_version = ldap.VERSION3
		l.set_option(ldap.OPT_REFERRALS, 0)

		bind = l.simple_bind_s(root_user, root_password)

		criteria = "(&(objectClass="+ldap_class_search+")("+ldap_user_attribute+"="+user+"))"
		attributes = [ldap_search_field]
		result = l.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

		bind = l.simple_bind_s(result[0][0], password)
	except ldap.INVALID_CREDENTIALS:
		print("Content-type: text/html\n")
		print('<center><div class="alert alert-danger">Invalid credentials</div><br /><br />')
		sys.exit()
	except ldap.SERVER_DOWN:
		print("Content-type: text/html\n")
		print('<center><div class="alert alert-danger">Server down</div><br /><br />')
		sys.exit()
	except ldap.LDAPError as e:
		if type(e.message) == dict and e.message.has_key('desc'):
			print("Content-type: text/html\n")
			print('<center><div class="alert alert-danger">Other LDAP error: %s</div><br /><br />' % e.message['desc'])
			sys.exit()
		else:
			print("Content-type: text/html\n")
			print('<center><div class="alert alert-danger">Other LDAP error: %s</div><br /><br />' % e)
			sys.exit()

	send_cookie(user)


if ref is None:
	ref = "/index.html"

if form.getvalue('error'):
	error_log = '<div class="alert alert-danger">Somthing wrong :( I\'m sad about this, but try again!</div><br /><br />'

try:
	if sql.get_setting('session_ttl'):
		session_ttl = sql.get_setting('session_ttl')
except:
	error = '<center><div class="alert alert-danger">Can not find "session_ttl" parametr. Check into settings, "main" section</div>'
	pass

try:
	role = sql.get_user_role_by_uuid(user_id.value)
	user = sql.get_user_name_by_uuid(user_id.value)
except:
	role = ""
	user = ""
	pass


if form.getvalue('logout'):
	try:
		sql.delete_uuid(user_id.value)
	except:
		pass
	print("Set-cookie: uuid=; expires=Wed, May 18 03:33:20 2003; path=/app; httponly")
	print("Content-type: text/html\n")
	print('<meta http-equiv="refresh" content="0; url=/app/login.py">')
	sys.exit()

if login is not None and password is not None:
	USERS = sql.select_users(user=login)

	for users in USERS:
		if users[7] == 0:
			print("Content-type: text/html\n")
			print('Your login is disabled')
			sys.exit()
		if users[6] == 1:
			if login in users[1]:
				check_in_ldap(login, password)
		else:
			passwordHashed = funct.get_hash(password)
			if login in users[1] and passwordHashed == users[3]:
				send_cookie(login)
				break
			else:
				ban()
				sys.exit()
	else:
		ban()
		sys.exit()
	print("Content-type: text/html\n")

if login is None:
	print("Content-type: text/html\n")
	if create_db.check_db():
		if create_db.create_table():
			create_db.update_all()
			db_create = '<div class="alert alert-success">DB was created<br /><br />Now you can login, default: admin/admin</div>'

create_db.update_all_silent()

output_from_parsed_template = template.render(h2 = 0, title = "Login page",
													role = role,
													user = user,
													error_log = error_log,
													error = error,
													ref = ref,
													versions = funct.versions(),
													db_create = db_create)
print(output_from_parsed_template)
