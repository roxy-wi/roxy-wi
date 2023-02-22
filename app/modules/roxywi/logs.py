import re

import modules.db.sql as sql
import modules.server.server as server_mod
from modules.common.common import checkAjaxInput
from modules.common.common import form
import modules.roxy_wi_tools as roxy_wi_tools
import modules.roxywi.common as roxywi_common

get_config_var = roxy_wi_tools.GetConfigVar()


def roxy_wi_log(**kwargs) -> list:
	log_path = get_config_var.get_config_var('main', 'log_path')

	if kwargs.get('log_id'):
		selects = roxywi_common.get_files(log_path, "log")
		for key, value in selects:
			log_file = f"{kwargs.get('file')}.log"
			if log_file == value:
				return key
	else:
		user_group_id = roxywi_common.get_user_group(id=1)
		if user_group_id != 1:
			user_group = roxywi_common.get_user_group()
			group_grep = f'|grep "group: {user_group}"'
		else:
			group_grep = ''
		cmd = f"find {log_path}/roxy-wi-* -type f -exec stat --format '%Y :%y %n' '{{}}' \; | sort -nr | cut -d: -f2- " \
				f"| head -1 |awk '{{print $4}}' |xargs tail {group_grep}|sort -r"
		try:
			output, stderr = server_mod.subprocess_execute(cmd)
			return output
		except Exception:
			return ['']


def show_log(stdout, **kwargs):
	i = 0
	out = ''
	grep = ''

	if kwargs.get('grep'):
		grep = kwargs.get('grep')
		grep = re.sub(r'[?|$|.|!|^|*|\]|\[|,| |]', r'', grep)
	for line in stdout:
		i = i + 1
		if kwargs.get('grep'):
			line = line.replace(grep, f'<span style="color: red; font-weight: bold;">{grep}</span>')
		line_class = "line3" if i % 2 == 0 else "line"
		out += f'<div class="{line_class}">{line}</div>'

	return out


def show_roxy_log(
		serv, rows='10', waf='0', grep=None, hour='00',
		minut='00', hour1='24', minut1='00', service='haproxy', **kwargs
) -> str:
	exgrep = form.getvalue('exgrep')
	log_file = form.getvalue('file')
	date = checkAjaxInput(hour) + ':' + checkAjaxInput(minut)
	date1 = checkAjaxInput(hour1) + ':' + checkAjaxInput(minut1)
	rows = checkAjaxInput(rows)
	waf = checkAjaxInput(waf)
	cmd = ''
	awk_column = 3

	if grep is not None:
		grep_act = '|egrep "%s"' % checkAjaxInput(grep)
	else:
		grep_act = ''

	if exgrep is not None:
		exgrep_act = '|egrep -v "%s"' % checkAjaxInput(exgrep)
	else:
		exgrep_act = ''

	log_file = checkAjaxInput(log_file) if log_file is not None else log_file

	if '..' in log_file: return 'error: nice try'

	if service in ('nginx', 'haproxy', 'apache', 'keepalived'):
		syslog_server_enable = sql.get_setting('syslog_server_enable')
		if syslog_server_enable is None or syslog_server_enable == 0:
			if service == 'nginx':
				local_path_logs = sql.get_setting('nginx_path_logs')
				commands = ["sudo cat %s/%s |tail -%s %s %s" % (local_path_logs, log_file, rows, grep_act, exgrep_act)]
			elif service == 'apache':
				local_path_logs = sql.get_setting('apache_path_logs')
				commands = [
					"sudo cat %s/%s| awk -F\"/|:\" '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)
				]
			elif service == 'keepalived':
				local_path_logs = sql.get_setting('keepalived_path_logs')
				commands = [
					"sudo cat %s/%s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (
						local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)
				]
			else:
				local_path_logs = sql.get_setting('haproxy_path_logs')
				commands = ["sudo cat %s/%s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, log_file, date, date1, rows, grep_act, exgrep_act)]
			syslog_server = serv
		else:
			commands = ["sudo cat /var/log/%s/syslog.log | sed '/ %s:00/,/ %s:00/! d' |tail -%s %s %s %s" % (serv, date, date1, rows, grep_act, grep, exgrep_act)]
			syslog_server = sql.get_setting('syslog_server')

		if waf == "1":
			local_path_logs = '/var/log/waf.log'
			commands = ["sudo cat %s |tail -%s %s %s" % (local_path_logs, rows, grep_act, exgrep_act)]
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
