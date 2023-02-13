import os

import modules.db.sql as sql
import modules.service.common as service_common
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
from modules.server.ssh import return_ssh_keys_path

form = common.form


def show_installation_output(error: str, output: str, service: str) -> bool:
	if error and "WARNING" not in error:
		roxywi_common.logging('Roxy-WI server', error, roxywi=1)
		print('error: ' + error)
		return False
	else:
		for line in output:
			if any(s in line for s in ("Traceback", "FAILED", "error", "ERROR", "UNREACHABLE")):
				try:
					correct_out = line.split('=>')
					print(f'error: {correct_out[1]}')
					break
				except Exception:
					print(output)
					break
		else:
			from jinja2 import Environment, FileSystemLoader
			env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
			template = env.get_template('include/show_success_installation.html')
			lang = roxywi_common.get_user_lang()
			rendered_template = template.render(service=service, lang=lang)
			print(rendered_template)
			roxywi_common.logging('Roxy-WI server', error, roxywi=1, keep_history=1, service=service)
			return True


def install_haproxy(server_ip: str, **kwargs):
	script = "install_haproxy.sh"
	hap_sock_p = str(sql.get_setting('haproxy_sock_port'))
	stats_port = str(sql.get_setting('stats_port'))
	server_state_file = sql.get_setting('server_state_file')
	stats_user = sql.get_setting('stats_user')
	stats_password = sql.get_setting('stats_password')
	proxy = sql.get_setting('proxy')
	haproxy_dir = sql.get_setting('haproxy_dir')
	container_name = sql.get_setting('haproxy_container_name')
	haproxy_ver = kwargs.get('hapver')
	server_for_installing = kwargs.get('server')
	docker = kwargs.get('docker')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(server_ip)

	os.system(f"cp scripts/{script} .")

	if haproxy_ver is None:
		haproxy_ver = '2.7.1-1'

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	syn_flood_protect = '1' if kwargs.get('syn_flood') == "1" else ''

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} SOCK_PORT={hap_sock_p} STAT_PORT={stats_port} "
		f"STAT_FILE={server_state_file} DOCKER={docker} SSH_PORT={ssh_settings['port']} STATS_USER={stats_user} "
		f"CONT_NAME={container_name} HAP_DIR={haproxy_dir} STATS_PASS='{stats_password}' HAPVER={haproxy_ver} "
		f"SYN_FLOOD={syn_flood_protect} HOST={server_ip} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' "
		f"KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])
	if server_for_installing:
		service = server_for_installing + ' HAProxy'
	else:
		service = ' HAProxy'

	if show_installation_output(error, output, service):
		sql.update_haproxy(server_ip)

	if docker == '1':
		server_id = sql.select_server_id_by_ip(server_ip)
		sql.insert_or_update_service_setting(server_id, 'haproxy', 'dockerized', '1')
		sql.insert_or_update_service_setting(server_id, 'haproxy', 'restart', '1')

	os.remove(script)


def waf_install(server_ip: str):
	script = "waf.sh"
	proxy = sql.get_setting('proxy')
	haproxy_dir = sql.get_setting('haproxy_dir')
	ver = service_common.check_haproxy_version(server_ip)
	service = ' WAF'
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(server_ip)

	os.system(f"cp scripts/{script} .")

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} HAPROXY_PATH={haproxy_dir} VERSION='{ver}' "
		f"SSH_PORT={ssh_settings['port']} HOST={server_ip} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' "
		f"KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	if show_installation_output(error, output, service):
		sql.insert_waf_metrics_enable(server_ip, "0")
		sql.insert_waf_rules(server_ip)

	os.remove(script)


def waf_nginx_install(server_ip: str):
	script = "waf_nginx.sh"
	proxy = sql.get_setting('proxy')
	nginx_dir = sql.get_setting('nginx_dir')
	service = ' WAF'
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(server_ip)

	os.system(f"cp scripts/{script} .")

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} NGINX_PATH={nginx_dir} SSH_PORT={ssh_settings['port']} "
		f"HOST={server_ip} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	if show_installation_output(error, output, service):
		sql.insert_nginx_waf_rules(server_ip)
		sql.insert_waf_nginx_server(server_ip)

	os.remove(script)


def install_service(server_ip: str, service: str, docker: str, **kwargs) -> None:
	script = f"install_{service}.sh"
	stats_user = sql.get_setting(f'{service}_stats_user')
	stats_password = sql.get_setting(f'{service}_stats_password')
	stats_port = str(sql.get_setting(f'{service}_stats_port'))
	stats_page = sql.get_setting(f'{service}_stats_page')
	config_path = sql.get_setting(f'{service}_config_path')
	service_dir = sql.get_setting(f'{service}_dir')
	server_for_installing = kwargs.get('server')
	proxy = sql.get_setting('proxy')
	container_name = sql.get_setting(f'{service}_container_name')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(server_ip)

	os.system(f"cp scripts/{script} .")

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	syn_flood_protect = '1' if form.getvalue('syn_flood') == "1" else ''

	if service == 'apache':
		correct_service_name = service_common.get_correct_apache_service_name(server_ip=server_ip, server_id=None)
		if service_dir == '/etc/httpd' and correct_service_name == 'apache2':
			service_dir = '/etc/apache2'
		elif service_dir == '/etc/apache2' and correct_service_name == 'httpd':
			service_dir = '/etc/httpd'

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} STATS_USER={stats_user} STATS_PASS='{stats_password}' "
		f"SSH_PORT={ssh_settings['port']} CONFIG_PATH={config_path} CONT_NAME={container_name} STAT_PORT={stats_port} "
		f"STAT_PAGE={stats_page} SYN_FLOOD={syn_flood_protect} DOCKER={docker} service_dir={service_dir} HOST={server_ip} "
		f"USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	if server_for_installing:
		service_name = f'{server_for_installing} {service.title()}'
	else:
		service_name = service.title

	if show_installation_output(error, output, service_name):
		if service == 'nginx':
			sql.update_nginx(server_ip)
		elif service == 'apache':
			sql.update_apache(server_ip)

	if docker == '1':
		server_id = sql.select_server_id_by_ip(server_ip)
		sql.insert_or_update_service_setting(server_id, service, 'dockerized', '1')
		sql.insert_or_update_service_setting(server_id, service, 'restart', '1')

	os.remove(script)


def geoip_installation():
	serv = common.is_ip_or_dns(form.getvalue('geoip_install'))
	geoip_update = common.checkAjaxInput(form.getvalue('geoip_update'))
	service = form.getvalue('geoip_service')
	proxy = sql.get_setting('proxy')
	maxmind_key = sql.get_setting('maxmind_key')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(serv)

	if service in ('haproxy', 'nginx'):
		service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
		script = f'install_{service}_geoip.sh'
	else:
		print('warning: select a server and service first')
		return

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	os.system(f"cp scripts/{script} .")

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} UPDATE={geoip_update} "
		f"maxmind_key={maxmind_key} service_dir={service_dir} HOST={serv} USER={ssh_settings['user']} "
		f"PASS={ssh_settings['password']} KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	show_installation_output(error, output, 'GeoLite2 Database')

	os.remove(script)


def grafana_install():
	script = "install_grafana.sh"
	proxy = sql.get_setting('proxy')
	proxy_serv = ''
	host = os.environ.get('HTTP_HOST', '')

	os.system(f"cp scripts/{script} .")

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	cmd = f"chmod +x {script} && ./{script} PROXY={proxy_serv}"
	output, error = server_mod.subprocess_execute(cmd)

	if error:
		roxywi_common.logging('Roxy-WI server', error, roxywi=1)
		print(
			f'success: Grafana and Prometheus servers were installed. You can find Grafana on http://{host}:3000<br>')
	else:
		for line in output:
			if any(s in line for s in ("Traceback", "FAILED")):
				try:
					print(line)
					break
				except Exception:
					print(output)
					break
		else:
			print(
				f'success: Grafana and Prometheus servers were installed. You can find Grafana on http://{host}:3000<br>')

	os.remove(script)


def keepalived_master_install():
	master = form.getvalue('master')
	eth = form.getvalue('interface')
	eth_slave = form.getvalue('slave_interface')
	vrrp_ip = form.getvalue('vrrpip')
	syn_flood = form.getvalue('syn_flood')
	virt_server = form.getvalue('virt_server')
	return_to_master = form.getvalue('return_to_master')
	haproxy = form.getvalue('hap')
	nginx = form.getvalue('nginx')
	router_id = form.getvalue('router_id')
	script = "install_keepalived.sh"
	proxy = sql.get_setting('proxy')
	keepalived_path_logs = sql.get_setting('keepalived_path_logs')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(master)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	os.system(f"cp scripts/{script} .")

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} router_id={router_id} "
		f"ETH={eth} IP={vrrp_ip} MASTER=MASTER ETH_SLAVE={eth_slave} keepalived_path_logs={keepalived_path_logs} "
		f"RETURN_TO_MASTER={return_to_master} SYN_FLOOD={syn_flood} HOST={master} HAPROXY={haproxy} NGINX={nginx} "
		f"USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	if show_installation_output(error, output, 'master Keepalived'):
		sql.update_keepalived(master)

		if virt_server != '0':
			group_id = sql.get_group_id_by_server_ip(master)
			cred_id = sql.get_cred_id_by_server_ip(master)
			hostname = sql.get_hostname_by_server_ip(master)
			firewall = 1 if server_mod.is_service_active(master, 'firewalld') else 0
			sql.add_server(
				hostname + '-VIP', vrrp_ip, group_id, '1', '1', '0', cred_id, ssh_settings['port'], f'VRRP IP for {master}',
				haproxy, nginx, '0', firewall
			)
	os.remove(script)


def keepalived_slave_install():
	master = form.getvalue('master_slave')
	slave = form.getvalue('slave')
	eth = form.getvalue('interface')
	eth_slave = form.getvalue('slave_interface')
	vrrp_ip = form.getvalue('vrrpip')
	syn_flood = form.getvalue('syn_flood')
	haproxy = form.getvalue('hap')
	nginx = form.getvalue('nginx')
	router_id = form.getvalue('router_id')
	script = "install_keepalived.sh"
	proxy = sql.get_setting('proxy')
	keepalived_path_logs = sql.get_setting('keepalived_path_logs')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(slave)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	os.system(f"cp scripts/{script} .")

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} router_id={router_id} ETH={eth} "
		f"IP={vrrp_ip} MASTER=BACKUP ETH_SLAVE={eth_slave} SYN_FLOOD={syn_flood} keepalived_path_logs={keepalived_path_logs} HAPROXY={haproxy} "
		f"NGINX={nginx} HOST={slave} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	show_installation_output(error, output, 'slave Keepalived')

	os.remove(script)
	sql.update_server_master(master, slave)
	sql.update_keepalived(slave)


def keepalived_masteradd():
	master = form.getvalue('masteradd')
	eth = form.getvalue('interfaceadd')
	slave_eth = form.getvalue('slave_interfaceadd')
	vrrp_ip = form.getvalue('vrrpipadd')
	router_id = form.getvalue('router_id')
	kp = form.getvalue('kp')
	return_to_master = form.getvalue('return_to_master')
	script = "install_keepalived.sh"
	proxy = sql.get_setting('proxy')
	keepalived_path_logs = sql.get_setting('keepalived_path_logs')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(master)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	os.system(f"cp scripts/{script} .")

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} ETH={eth} SLAVE_ETH={slave_eth} "
		f"keepalived_path_logs={keepalived_path_logs} RETURN_TO_MASTER={return_to_master} IP={vrrp_ip} MASTER=MASTER "
		f"RESTART={kp} ADD_VRRP=1 HOST={master} router_id={router_id} USER={ssh_settings['user']} "
		f"PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	show_installation_output(error, output, 'master VRRP address')
	os.remove(script)


def keepalived_slaveadd():
	slave = form.getvalue('slaveadd')
	eth = form.getvalue('interfaceadd')
	slave_eth = form.getvalue('slave_interfaceadd')
	vrrp_ip = form.getvalue('vrrpipadd')
	router_id = form.getvalue('router_id')
	kp = form.getvalue('kp')
	script = "install_keepalived.sh"
	proxy = sql.get_setting('proxy')
	keepalived_path_logs = sql.get_setting('keepalived_path_logs')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(slave)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	os.system(f"cp scripts/{script} .")

	commands = [
		f"chmod +x {script} && ./{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} ETH={eth} SLAVE_ETH={slave_eth} "
		f"keepalived_path_logs={keepalived_path_logs} IP={vrrp_ip} MASTER=BACKUP RESTART={kp} ADD_VRRP=1 HOST={slave} "
		f"router_id={router_id} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	output, error = server_mod.subprocess_execute(commands[0])

	show_installation_output(error, output, 'slave VRRP address')

	os.remove(script)
