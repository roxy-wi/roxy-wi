import json

import modules.db.sql as sql
import modules.common.common as common
import modules.config.config as config_mod
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools

form = common.form
serv = common.is_ip_or_dns(form.getvalue('serv'))
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()


def show_frontend_backend() -> None:
	haproxy_sock_port = int(sql.get_setting('haproxy_sock_port'))
	backend = common.checkAjaxInput(form.getvalue('ipbackend'))
	cmd = 'echo "show servers state"|nc %s %s |grep "%s" |awk \'{print $4}\'' % (serv, haproxy_sock_port, backend)
	output, stderr = server_mod.subprocess_execute(cmd)
	for i in output:
		if i == ' ':
			continue
		i = i.strip()
		print(i + '<br>')


def show_server() -> None:
	haproxy_sock_port = int(sql.get_setting('haproxy_sock_port'))
	backend = common.checkAjaxInput(form.getvalue('ipbackend'))
	backend_server = common.checkAjaxInput(form.getvalue('backend_server'))
	cmd = 'echo "show servers state"|nc %s %s |grep "%s" |grep "%s" |awk \'{print $5":"$19}\' |head -1' % (
		serv, haproxy_sock_port, backend, backend_server)
	output, stderr = server_mod.subprocess_execute(cmd)
	print(output[0])


def get_all_stick_table():
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show table"|nc %s %s |awk \'{print $3}\' | tr -d \'\n\' | tr -d \'[:space:]\'' % (serv, hap_sock_p)
	output, stderr = server_mod.subprocess_execute(cmd)
	return output[0]


def get_stick_table(table):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show table %s"|nc %s %s |awk -F"#" \'{print $2}\' |head -1 | tr -d \'\n\'' % (table, serv, hap_sock_p)
	output, stderr = server_mod.subprocess_execute(cmd)
	tables_head = []
	for i in output[0].split(','):
		i = i.split(':')[1]
		tables_head.append(i)

	cmd = 'echo "show table %s"|nc %s %s |grep -v "#"' % (table, serv, hap_sock_p)
	output, stderr = server_mod.subprocess_execute(cmd)

	return tables_head, output


def show_backends(server_ip, **kwargs):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show backend" |nc {server_ip} {hap_sock_p}'
	output, stderr = server_mod.subprocess_execute(cmd)
	if stderr:
		roxywi_common.logging('Roxy-WI server', ' ' + stderr, roxywi=1)
	if kwargs.get('ret'):
		ret = list()
	else:
		ret = ""
	for line in output:
		if any(s in line for s in ('#', 'stats', 'MASTER', '<')):
			continue
		if len(line) > 1:
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret.append(back[1])
			else:
				print(back[1], end="<br>")

	if kwargs.get('ret'):
		return ret


def get_backends_from_config(server_ip: str, backends='') -> None:
	config_date = get_date.return_date('config')
	configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
	format_cfg = 'cfg'

	try:
		cfg = configs_dir + roxywi_common.get_files(configs_dir, format_cfg)[0]
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		try:
			cfg = f'{configs_dir}{server_ip}-{config_date}.{format_cfg}'
		except Exception:
			roxywi_common.logging('Roxy-WI server', ' Cannot generate cfg path', roxywi=1)
			return
		try:
			config_mod.get_config(server_ip, cfg)
		except Exception:
			roxywi_common.logging('Roxy-WI server', ' Cannot download config', roxywi=1)
			print('error: Cannot get backends')
			return

	with open(cfg, 'r') as f:
		for line in f:
			if backends == 'frontend':
				if (line.startswith('listen') or line.startswith('frontend')) and 'stats' not in line:
					line = line.strip()
					print(line.split(' ')[1], end="<br>")


def change_ip_and_port() -> None:
	backend_backend = common.checkAjaxInput(form.getvalue('backend_backend'))
	backend_server = common.checkAjaxInput(form.getvalue('backend_server'))
	backend_ip = common.checkAjaxInput(form.getvalue('backend_ip'))
	backend_port = common.checkAjaxInput(form.getvalue('backend_port'))

	if form.getvalue('backend_ip') is None:
		print('error: Backend IP must be IP and not 0')
		return

	if form.getvalue('backend_port') is None:
		print('error: The backend port must be integer and not 0')
		return

	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	masters = sql.is_master(serv)
	for master in masters:
		if master[0] is not None:
			cmd = 'echo "set server %s/%s addr %s port %s check-port %s" |nc %s %s' % (
				backend_backend, backend_server, backend_ip, backend_port, backend_port, master[0], haproxy_sock_port)
			output, stderr = server_mod.subprocess_execute(cmd)
			print(output[0])
			roxywi_common.logging(
				master[0], 'IP address and port have been changed. On: {}/{} to {}:{}'.format(
					backend_backend, backend_server, backend_ip, backend_port
				),
				login=1, keep_history=1, service='haproxy'
			)

	cmd = 'echo "set server %s/%s addr %s port %s check-port %s" |nc %s %s' % (
		backend_backend, backend_server, backend_ip, backend_port, backend_port, serv, haproxy_sock_port)
	roxywi_common.logging(
		serv,
		f'IP address and port have been changed. On: {backend_backend}/{backend_server} to {backend_ip}:{backend_port}',
		login=1, keep_history=1, service='haproxy'
	)
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		print('error: ' + stderr[0])
	else:
		print(output[0])
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep %s %s -n -A25 |grep "server %s" |head -1|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/((1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])\.){3}(1?[0-9][0-9]?|2[0-4][0-9]|25[0-5]):[0-9]+/%s:%s/g" %s' % \
			  (backend_backend, cfg, backend_server, backend_ip, backend_port, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, just_save='save')


def change_maxconn_global() -> None:
	if form.getvalue('maxconn_global') is None:
		print('error: Maxconn must be integer and not 0')
		return

	maxconn = common.checkAjaxInput(form.getvalue('maxconn_global'))
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	masters = sql.is_master(serv)

	for master in masters:
		if master[0] is not None:
			cmd = f'echo "set maxconn global {maxconn}" |nc {master[0]} {haproxy_sock_port}'
			output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(master[0], f'Maxconn has been changed. Globally to {maxconn}', login=1, keep_history=1, service='haproxy')

	cmd = f'echo "set maxconn global {maxconn}" |nc {serv} {haproxy_sock_port}'
	print(cmd)
	roxywi_common.logging(serv, f'Maxconn has been changed. Globally to {maxconn}', login=1, keep_history=1, service='haproxy')
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		print(stderr[0])
	elif output[0] == '':
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep global %s -n -A5 |grep maxcon -n |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/[0-9]+/%s/g" %s' % (cfg, maxconn, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, just_save='save')
		print(f'success: Maxconn globally has been set to {maxconn} ')
	else:
		print(f'error: {output[0]}')


def change_maxconn_frontend() -> None:
	if form.getvalue('maxconn_int') is None:
		print('error: Maxconn must be integer and not 0')
		return

	frontend = common.checkAjaxInput(form.getvalue('maxconn_frontend'))
	maxconn = common.checkAjaxInput(form.getvalue('maxconn_int'))
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	masters = sql.is_master(serv)

	for master in masters:
		if master[0] is not None:
			cmd = f'echo "set maxconn frontend {frontend} {maxconn}" |nc {master[0]} {haproxy_sock_port}'
			output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(master[0], f'Maxconn has been changed. On: {frontend} to {maxconn}', login=1, keep_history=1, service='haproxy')

	cmd = f'echo "set maxconn frontend {frontend} {maxconn}" |nc {serv} {haproxy_sock_port}'
	roxywi_common.logging(serv, f'Maxconn has been changed. On: {frontend} to {maxconn}', login=1, keep_history=1, service='haproxy')
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		print(stderr[0])
	elif output[0] == '':
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep %s %s -n -A5 |grep maxcon -n |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/[0-9]+/%s/g" %s' % (frontend, cfg, maxconn, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, just_save='save')
		print(f'success: Maxconn for {frontend} has been set to {maxconn} ')
	else:
		print(f'error: {output[0]}')


def change_maxconn_backend() -> None:
	if form.getvalue('maxconn_int') is None:
		print('error: Maxconn must be integer and not 0')
		return

	backend = common.checkAjaxInput(form.getvalue('maxconn_backend'))
	backend_server = common.checkAjaxInput(form.getvalue('maxconn_backend_server'))
	maxconn = common.checkAjaxInput(form.getvalue('maxconn_int'))
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	masters = sql.is_master(serv)
	for master in masters:
		if master[0] is not None:
			cmd = f'echo "set maxconn server {backend}/{backend_server} {maxconn}" |nc {master[0]} {haproxy_sock_port}'
			output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(master[0], f'Maxconn has been changed. On: {backend}/{backend_server} to {maxconn}', login=1, keep_history=1, service='haproxy')

	cmd = f'echo "set maxconn server {backend}/{backend_server} {maxconn}" |nc {serv} {haproxy_sock_port}'
	print(cmd)
	roxywi_common.logging(serv, f'Maxconn has been changed. On: {backend} to {maxconn}', login=1, keep_history=1, service='haproxy')
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		print(stderr[0])
	elif output[0] == '':
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep %s %s -n -A10 |grep maxcon -n|grep %s |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/maxconn [0-9]+/maxconn %s/g" %s' % (backend, cfg, backend_server, maxconn, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, just_save='save')
		print(f'success: Maxconn for {backend}/{backend_server} has been set to {maxconn} ')
	else:
		print(f'error: {output[0]}')


def table_select():
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates'), autoescape=True,
					  extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'], trim_blocks=True, lstrip_blocks=True)
	table = form.getvalue('table_select')
	lang = roxywi_common.get_user_lang()

	if table == 'All':
		template = env.get_template('ajax/stick_tables.html')
		tables = get_all_stick_table()
		table = []
		for t in tables.split(','):
			if t != '':
				table_id = []
				tables_head1, table1 = get_stick_table(t)
				table_id.append(tables_head1)
				table_id.append(table1)
				table.append(table_id)

		template = template.render(table=table, lang=lang)
	else:
		template = env.get_template('ajax/stick_table.html')
		tables_head, table = get_stick_table(table)
		template = template.render(tables_head=tables_head, table=table, lang=lang)

	print(template)


def delete_ip_from_stick_table() -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	ip = common.checkAjaxInput(form.getvalue('ip_for_delete'))
	table = common.checkAjaxInput(form.getvalue('table_for_delete'))

	cmd = f'echo "clear table {table} key {ip}" |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	if stderr[0] != '':
		print(f'error: {stderr[0]}')


def clear_stick_table() -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	table = common.checkAjaxInput(form.getvalue('table_for_clear'))

	cmd = f'echo "clear table {table} " |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	if stderr[0] != '':
		print(f'error: {stderr[0]}')


def list_of_lists() -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show acl"|nc {serv} {haproxy_sock_port} |grep "loaded from" |awk \'{{print $1,$2}}\''
	output, stderr = server_mod.subprocess_execute(cmd)
	print(output)


def show_lists() -> None:
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/'), autoescape=True,
						extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'], trim_blocks=True, lstrip_blocks=True)
	template = env.get_template('ajax/list.html')
	list_id = common.checkAjaxInput(form.getvalue('list_select_id'))
	list_name = common.checkAjaxInput(form.getvalue('list_select_name'))

	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show acl #{list_id}"|nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)

	template = template.render(list=output, list_id=list_id, list_name=list_name)
	print(template)


def delete_ip_from_list() -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lib_path = get_config_var.get_config_var('main', 'lib_path')
	ip_id = common.checkAjaxInput(form.getvalue('list_ip_id_for_delete'))
	ip = common.is_ip_or_dns(form.getvalue('list_ip_for_delete'))
	list_id = common.checkAjaxInput(form.getvalue('list_id_for_delete'))
	list_name = common.checkAjaxInput(form.getvalue('list_name'))
	user_group = roxywi_common.get_user_group(id=1)
	cmd = f"sed -i 's!{ip}$!!' {lib_path}/lists/{user_group}/{list_name}"
	cmd1 = f"sed -i '/^$/d' {lib_path}/lists/{user_group}/{list_name}"
	output, stderr = server_mod.subprocess_execute(cmd)
	output1, stderr1 = server_mod.subprocess_execute(cmd1)
	if output:
		print(f'error: {output}')
	if stderr:
		print(f'error: {stderr}')
	if output1:
		print(f'error: {output1}')
	if stderr1:
		print(f'error: {stderr}')

	cmd = f'echo "del acl #{list_id} #{ip_id}" |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	if output[0] != '':
		print(f'error: {output[0]}')
	if stderr != '':
		print(f'error: {stderr[0]}')

	roxywi_common.logging(serv, f'{ip_id} has been delete from list {list_id}', login=1, keep_history=1, service='haproxy')


def add_ip_to_list() -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lib_path = get_config_var.get_config_var('main', 'lib_path')
	ip = form.getvalue('list_ip_for_add')
	ip = ip.strip()
	ip = common.is_ip_or_dns(ip)
	list_id = common.checkAjaxInput(form.getvalue('list_id_for_add'))
	list_name = common.checkAjaxInput(form.getvalue('list_name'))
	user_group = roxywi_common.get_user_group(id=1)
	cmd = f'echo "add acl #{list_id} {ip}" |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	if output[0]:
		print(f'error: {output[0]}')
	if stderr:
		print(f'error: {stderr[0]}')

	if 'is not a valid IPv4 or IPv6 address' not in output[0]:
		cmd = f'echo "{ip}" >> {lib_path}/lists/{user_group}/{list_name}'
		output, stderr = server_mod.subprocess_execute(cmd)
		if output:
			print(f'error: {output}')
		if stderr:
			print(f'error: {stderr}')

	roxywi_common.logging(serv, f'{ip} has been added to list {list_id}', login=1, keep_history=1, service='haproxy')


def select_session() -> None:
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates'), autoescape=True,
						extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'], trim_blocks=True, lstrip_blocks=True)
	session = common.checkAjaxInput(form.getvalue('sessions_select'))
	lang = roxywi_common.get_user_lang()
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	cmd = f'echo "show sess" |nc {session} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)

	template = env.get_template('ajax/sessions_table.html')
	template = template.render(sessions=output, lang=lang)

	print(template)


def show_session() -> None:
	session = common.checkAjaxInput(form.getvalue('sessions_select_show'))
	sess_id = common.checkAjaxInput(form.getvalue('sessions_select_id'))
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show sess {sess_id}" |nc {session} {haproxy_sock_port}'

	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr:
		print('error: ' + stderr[0])
	else:
		for o in output:
			print(f'{o}<br />')


def delete_session() -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	sess_id = common.checkAjaxInput(form.getvalue('session_delete_id'))
	cmd = 'echo "shutdown session %s" |nc %s %s' % (sess_id, serv, haproxy_sock_port)
	output, stderr = server_mod.subprocess_execute(cmd)
	if output[0] != '':
		print('error: ' + output[0])
	if stderr[0] != '':
		print('error: ' + stderr[0])
