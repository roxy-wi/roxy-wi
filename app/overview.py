#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.roxywi.logs as roxy_logs
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('ovw.html')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception:
	print('error: your session is expired')
	sys.exit()

try:
	groups = sql.select_groups()
except Exception as e:
	groups = ''
	print(e)

rendered_template = template.render(
	h2=1, autorefresh=1, role=user_params['role'], user=user_params['user'], groups=groups,
	roles=sql.select_roles(), servers=user_params['servers'], user_services=user_params['user_services'],
	roxy_wi_log=roxy_logs.roxy_wi_log(), token=user_params['token'], guide_me=1, lang=user_params['lang']
)
print(rendered_template)
