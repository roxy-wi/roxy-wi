#!/usr/bin/env python3
import html
import cgi
import sys
import os
import funct
import sql

funct.head("Admin area: users manage")
funct.check_config()
funct.check_login()
funct.page_for_admin()

form = cgi.FieldStorage()

USERS = sql.select_users()
GROUPS = sql.select_groups()
SERVERS = sql.select_servers(full=1)
ROLES = sql.select_roles()

print('<script src="/inc/users.js"></script>'
	'<div id="tabs">'
			'<ul>'
				'<li><a href="#users">Users</a></li>'
				'<li><a href="#groups">Groups</a></li>'
				'<li><a href="#servers">Servers</a></li>'
				'<li><a href="#roles">Roles</a></li>'
			'</ul>'
			'<div id="users">'
				'<table class="overview" id="ajax-users">'
					'<tr class="overviewHead">'
						'<td class="padding10 first-collumn">Login name</td>'
						'<td>Password</td>'
						'<td>Email</td>'
						'<td>Role</td>'
						'<td>Group</td>'
						'<td></td>'
						'<td></td>'
					'</tr><tr>')

for users in USERS:
	print('<tr id="user-%s">' % users[0])
	print('<td class="padding10 first-collumn"><input type="text" id="login-%s" value="%s" class="form-control"></td>' % (users[0], users[1]))
	print('<td><input type="password" id="password-%s" value="%s" class="form-control"></td>' % (users[0], users[3]))
	print('<td><input type="text" id="email-%s" value="%s" class="form-control"></td>' % (users[0], users[2]))
	print('<td>')
	need_id_role = "role-%s" % users[0]
	sql.get_roles_select(need_id_role, selected=users[4])
	print('</td>')
	print('<td>')
	need_id_group = "usergroup-%s" % users[0]
	sql.get_groups_select(need_id_group, selected=users[5])
	print('</td>')
	#print('<td><a class="update-row" onclick="updateUser(%s)"  style="cursor: pointer;"></a></td>' % users[0])
	print('<td><a class="delete" onclick="removeUser(%s)"  style="cursor: pointer;"></a></td>' % users[0])
	print('</tr>')
print('</table>'
		'<br /><span class="add-button" title="Add user" id="add-user-button">+ Add</span>')

print('<br /><br /><table class="overview" id="user-add-table" style="display: none;">'
		'<tr class="overviewHead">'
			'<td class="padding10 first-collumn">New user</td>'
			'<td>Password</td>'
			'<td>Email</td>'
			'<td>Role</td>'
			'<td>Group</td>'
			'<td></td>'
		'</tr>'
		'<tr>'
			'<td class="padding10 first-collumn"><input type="text" name="new-username" id="new-username" class="form-control"></td>'
			'<td><input type="password" name="new-password" id="new-password" class="form-control"></td>'
			'<td><input type="text" name="new-email" id="new-email" class="form-control"></td><td>')
sql.get_roles_select("new-role")
print('</td><td>')
sql.get_groups_select("new-group")
print('</td>'
			'<td><a class="add-admin" id="add-user" style="cursor: pointer;"></a></td>'
		'</tr>')
print('</table>')
	
print('</div><div id="groups">'
				'<table class="overview" id="ajax-group">'
					'<tr class="overviewHead">'
						'<td class="padding10 first-collumn">Name</td>'
						'<td>Desciption</td>'
						'<td></td>'
						'<td></td>'
					'</tr>')
for group in GROUPS:
	print('<tr id="group-%s">' % group[0])
	print('<td class="padding10 first-collumn"><input type="text" id="name-%s" value="%s" class="form-control"></td>' % (group[0], group[1]))
	print('<td><input type="text" id="descript-%s" value="%s" class="form-control" size="100"></td>' % (group[0], group[2]))
	#print('<td><a class="update-row" onclick="updateGroup(%s)"  style="cursor: pointer;"></a></td>' % group[0])
	print('<td><a class="delete" onclick="removeGroup(%s)"  style="cursor: pointer;"></a></td>' % group[0])
	print('</tr>')
print('</table>'
		'<br /><span class="add-button" title="Add group" id="add-group-button">+ Add</span>')

print('<br /><br /><table class="overview" id="group-add-table" style="display: none;">'
		'<tr class="overviewHead">'
			'<td class="padding10 first-collumn">New group name</td>'
			'<td>Desciption</td>'
			'<td></td>'
		'</tr>'
		'<tr>'
			'<td class="padding10 first-collumn"><input type="text" name="new-group-add" id="new-group-add" class="form-control"></td>'
			'<td><input type="text" name="new-desc" id="new-desc" class="form-control" size="100"></td>'
			'<td><a class="add-admin" id="add-group" style="cursor: pointer;"></a></td>'
		'</tr>'
'</table>'
'</div>'
'<div id="servers">'
				'<table class="overview" id="ajax-servers">'
					'<tr class="overviewHead">'
						'<td class="padding10 first-collumn">Hostname</td>'
						'<td>IP</td>'
						'<td>Group</td>'
						'<td>Enable</td>'
						'<td>Virt</td>'
						'<td></td>'
						'<td></td>'
					'</tr>')
					
for server in SERVERS:
	print('<tr id="server-%s">' % server[0])
	print('<td class="padding10 first-collumn"><input type="text" id="hostname-%s" value="%s" class="form-control"></td>' % (server[0], server[1]))
	print('<td><input type="text" id="ip-%s" value="%s" class="form-control"></td>' % (server[0], server[2]))
	print('<td>')
	need_id_group = "servergroup-%s" % server[0]
	sql.get_groups_select(need_id_group, selected=server[3])
	print('</td>')
	print('<td>')
	sql.get_enable_checkbox(server[0])
	print('</td>')
	print('<td>')
	sql.get_type_ip_checkbox(server[0])
	print('</td>')
	#print('<td><a class="update-row" onclick="updateServer(%s)"  style="cursor: pointer;"></a></td>' % server[0])
	print('<td><a class="delete" onclick="removeServer(%s)"  style="cursor: pointer;"></a></td>' % server[0])
	print('</tr>')
print('</table>'
	'<br /><span class="add-button" title="Add server" id="add-server-button">+ Add</span>'
	'<br /><br /><table class="overview" id="server-add-table" style="display: none;">'
	'<tr class="overviewHead">'
		'<td class="padding10 first-collumn">New hostname</td>'
		'<td>IP</td>'
		'<td>Group</td>'
		'<td>Enable</td>'
		'<td>Virt</td>'
		'<td></td>'
	'</tr>'
	'<tr>'
		'<td class="padding10 first-collumn"><input type="text" name="new-server-add" id="new-server-add" class="form-control"></td>'
		'<td><input type="text" name="new-ip" id="new-ip" class="form-control"></td><td>')
sql.get_groups_select("new-server-group-add")
print('</td>'
		'<td><label for="enable"></label><input type="checkbox" id="enable" checked></td>'
		'<td><label for="typeip"></label><input type="checkbox" id="typeip"></td>'
		'<td><a class="add-admin"  id="add-server" style="cursor: pointer;"></a></td>'
		'</tr>')
print('</table>')
	
print('</div><div id="roles">'
				'<table class="overview" id="ajax-group">'
					'<tr class="overviewHead">'
						'<td class="padding10 first-collumn">Name</td>'
						'<td>Desciption</td>'
						'<td></td>'
						'<td></td>'
					'</tr><tr>')
for role in ROLES:
	print('<tr id="group-%s">' % role[0])
	print('<td class="padding10 first-collumn">%s</td>' % ( role[1]))
	print('<td>%s</td>' % (role[2]))
	print('</tr>')

print('</table>')