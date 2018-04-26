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
				'<li><a href="#cert">Ssh key</a></li>'
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
i = 0
for group in GROUPS:
	i = i + 1
	print('<tr id="group-%s">' % group[0])
	if i == 1:
		print('<td class="padding10 first-collumn">%s</td>' % (group[1]))
		print('<td>%s</td>' % (group[2]))
		print('<td></td>')
	else:
		print('<td class="padding10 first-collumn"><input type="text" id="name-%s" value="%s" class="form-control"></td>' % (group[0], group[1]))
		print('<td><input type="text" id="descript-%s" value="%s" class="form-control" size="100"></td>' % (group[0], group[2]))
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
						'<td><span title="Vitrual IP, something like VRRP">Virt(?)</span></td>'
						'<td><span title="Actions with master config will automatically apply on slave">Slave for (?)</span></td>'
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
	print('<td><select id="slavefor-%s"><option value="0" selected>Not slave</option>' % server[0])
	MASTERS = sql.select_servers(get_master_servers=1)
	for master in MASTERS:
		if master[0] == server[6]:
			selected = "selected"
		else:
			selected = ""
		print('<option value="%s" %s>%s</option>' % (master[0], selected, master[1]))
	print('</select></td>')
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
		'<td title="Actions with master config will automatically apply on slave">Slave for</td>'
		'<td></td>'
	'</tr>'
	'<tr>'
		'<td class="padding10 first-collumn"><input type="text" name="new-server-add" id="new-server-add" class="form-control"></td>'
		'<td><input type="text" name="new-ip" id="new-ip" class="form-control"></td><td>')
sql.get_groups_select("new-server-group-add")
print('</td>'
		'<td><label for="enable"></label><input type="checkbox" id="enable" checked></td>'
		'<td><label for="typeip"></label><input type="checkbox" id="typeip"></td>'
		'<td><select id="slavefor" value="0" selected><option>Not slave</option>')
MASTERS = sql.select_servers(get_master_servers=1)
for master in MASTERS:
	print('<option value="%s">%s</option>' % (master[0], master[1]))
print('</select></td>'
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

print('</table>'
		'</div>'
		'<div id="cert">'
			'<table id="ssh">'
			'<tr class="overviewHead" style="width: 50%;">'
				'<td class="padding10 first-collumn">Upload SSH Key</td>'
				'<td>'
					'<span title="Private key. Note: The public key must be pre-installed on all servers to which you plan to connect">Key(?)</span>'
				'</td>'
				'<td></td>'
			'</tr>'
			'<tr style="width: 50%;">'
				'<td class="first-collumn" valign="top" style="padding-top: 15px;">'
					'<b>Note:</b> Paste pem file content here'
				'</td>'
		'<td style="padding-top: 15px;">'
			'<textarea id="ssh_cert" cols="50" rows="5"></textarea><br /><br />'
			'<a class="ui-button ui-widget ui-corner-all" id="ssh_key_upload" title="Upload ssh key" onclick="uploadSsh()">Upload</a>'		
		'</td>'
		'<td></td>'
		'</table>'
		'<div id="ajax-ssh"></div>'
		'</div></div>')