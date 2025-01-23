import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
from app.modules.common.common import checkAjaxInput
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.roxywi.common as roxywi_common

get_config_var = roxy_wi_tools.GetConfigVar()


def roxy_wi_log() -> list:
	log_path = get_config_var.get_config_var('main', 'log_path')
	user_group_id = roxywi_common.get_user_group(id=1)

	if user_group_id != 1:
		user_group = roxywi_common.get_user_group()
		group_grep = f'|grep "group: {user_group}"'
	else:
		group_grep = ''
	cmd = f"find {log_path}/roxy-wi.log -type f -exec stat --format '%Y :%y %n' '{{}}' \; | sort -nr | cut -d: -f2- " \
			f"| head -1 |awk '{{print $4}}' |xargs tail {group_grep}|sort -r"
	try:
		output, stderr = server_mod.subprocess_execute(cmd)
		return output
	except Exception:
		return ['']


def show_log(stdout, **kwargs):
	i = 0
	out = ''
	grep = kwargs.get('grep')

	if grep:
		grep = common.sanitize_input_word(grep)
	for line in stdout:
		i = i + 1
		if grep:
			line = common.highlight_word(line, grep)
		line_class = "line3" if i % 2 == 0 else "line"
		out += common.wrap_line(line, line_class)

	return out


def show_roxy_log(
		serv, rows='10', waf=0, grep=None, exgrep=None, hour='00',
		minute='00', hour1='24', minute1='00', service='haproxy', log_file='123', **kwargs
) -> str:
	date = checkAjaxInput(hour) + ':' + checkAjaxInput(minute)
	date1 = checkAjaxInput(hour1) + ':' + checkAjaxInput(minute1)
	rows = checkAjaxInput(rows)
	cmd = ''
	awk_column = 3
	grep_act = ''
	exgrep_act = ''

	if grep:
		grep_act = '|egrep "%s"' % checkAjaxInput(grep)

	if exgrep:
		exgrep_act = '|egrep -v "%s"' % checkAjaxInput(exgrep)

	if log_file is not None:
		log_file = checkAjaxInput(log_file)
		if '..' in log_file: raise Exception('error: nice try')
	else:
		if '..' in serv: raise Exception('error: nice try')

	if service in ('nginx', 'haproxy', 'apache', 'keepalived', 'caddy'):
		syslog_server_enable = sql.get_setting('syslog_server_enable')
		if syslog_server_enable is None or syslog_server_enable == 0:
			local_path_logs = sql.get_setting(f'{service}_path_logs')
			if service == 'nginx':
				commands = "sudo cat %s/%s |tail -%s %s %s" % (local_path_logs, log_file, rows, grep_act, exgrep_act)
			elif service == 'apache':
				commands = "sudo cat %s/%s| awk -F\"/|:\" '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)
			elif service == 'keepalived':
				commands = "sudo cat %s/%s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)
			elif service == 'caddy':
				commands = "sudo cat %s/%s| awk -F\"/|:\" '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)
			else:
				commands = "sudo cat %s/%s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)

			syslog_server = serv
		else:
			if '..' in serv: raise Exception('error: nice try')

			commands = "sudo cat /var/log/%s/syslog.log | sed '/ %s:00/,/ %s:00/! d' |tail -%s %s %s %s" % (serv, date, date1, rows, grep_act, grep, exgrep_act)
			syslog_server = sql.get_setting('syslog_server')
			if syslog_server is None or syslog_server == '':
				raise Exception('error: Syslog server is enabled, but there is no IP for syslog server')

		if waf:
			local_path_logs = '/var/log/waf.log'
			commands = "sudo cat %s |tail -%s %s %s" % (local_path_logs, rows, grep_act, exgrep_act)

		if kwargs.get('html') == 0:
			a = server_mod.ssh_command(syslog_server, commands)
			return show_log(a, html=0, grep=grep)
		else:
			return server_mod.ssh_command(syslog_server, commands, show_log='1', grep=grep, timeout=10)
	elif service == 'apache_internal':
		apache_log_path = sql.get_setting('apache_log_path')

		if serv == 'roxy-wi.access.log':
			cmd = 'sudo cat {}| awk -F"/|:" \'$3>"{}:00" && $3<"{}:00"\' |tail -{} {} {}'.format(apache_log_path + "/" + serv, date, date1, rows, grep_act, exgrep_act)
		elif serv == 'roxy-wi.error.log':
			cmd = "sudo cat {}| awk '$4>\"{}:00\" && $4<\"{}:00\"' |tail -{} {} {}".format(apache_log_path + "/" + serv, date, date1, rows, grep_act, exgrep_act)
		elif serv == 'fail2ban.log':
			cmd = 'sudo cat {}| awk -F"/|:" \'$3>"{}:00" && $3<"{}:00\' |tail -{} {} {}'.format("/var/log/" + serv, date, date1, rows, grep_act, exgrep_act)

		output, stderr = server_mod.subprocess_execute(cmd)

		return show_log(output, grep=grep)
	elif service == 'internal':
		log_path = get_config_var.get_config_var('main', 'log_path')
		logs_files = roxywi_common.get_files(log_path, "log")
		user_group = roxywi_common.get_user_group()
		user_grep = ''

		if user_group != '' and user_group != 'Default':
			user_grep = f"|grep 'group: {user_group}'"

		for key, value in logs_files:
			if int(serv) == key:
				serv = value
				break
		else:
			return 'Haha'

		if serv == 'backup.log':
			awk_column = 2

		cmd = f"cat {log_path}/{serv}| awk '${awk_column}>\"{date}:00\" && ${awk_column}<\"{date1}:00\"' {user_grep} {grep_act} {exgrep_act} |tail -{rows}"

		output, stderr = server_mod.subprocess_execute(cmd)

		return show_log(output, grep=grep)
