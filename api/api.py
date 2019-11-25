import os
import sys
os.chdir(os.path.dirname(__file__))
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app/'))
os.chdir(os.path.dirname(__file__))

from bottle import route, run, template, hook, response, request, error
import sql
import funct
import api_funct
import json


_error_auth = '403 Auth before'
_allow_origin = '*'
_allow_methods = 'PUT, GET, POST, DELETE, OPTIONS'
_allow_headers = 'Authorization, Origin, Accept, Content-Type, X-Requested-With'


@hook('before_request')
def check_login():
	try:	
		login = request.headers.get('login')
		password_from_user = request.headers.get('password')
		USERS = sql.select_users(user=login)
		password = funct.get_hash(password_from_user)
	except:
		return False
	
	for users in USERS:	
		if users[7] == 0:
			return False
		if login in users[1] and password == users[3]:
			return True
		else:
			return False


@hook('after_request')
def enable_cors():
    '''Add headers to enable CORS'''

    response.headers['Access-Control-Allow-Origin'] = _allow_origin
    response.headers['Access-Control-Allow-Methods'] = _allow_methods
    response.headers['Access-Control-Allow-Headers'] = _allow_headers
	
	
@error(500)
def error_handler_500(error):
	return json.dumps({"status": "error", "message": str(error.exception)})
	
	
@route('/', method=['GET', 'POST'])
@route('/help', method=['GET', 'POST'])
def index():
	if not check_login():
		return dict(error=_error_auth)
		
	data = {
		'help': 'show all available endpoints',
		'servers':'show info about all servers',
		'servers/status':'show status all servers',
		'server/<id,hostname,ip>':'show info about the server by id or hostname or ip',
		'server/<id,hostname,ip>/status':'show HAProxy status by id or hostname or ip',
		'server/<id,hostname,ip>/runtime':'exec HAProxy runtime commands by id or hostname or ip',
		'server/<id,hostname,ip>/backends':'show backends by id or hostname or ip',
		'server/<id,hostname,ip>/action/start':'start HAProxy service by id or hostname or ip',
		'server/<id,hostname,ip>/action/stop':'stop HAProxy service by id or hostname or ip',
		'server/<id,hostname,ip>/action/restart':'restart HAProxy service by id or hostname or ip',
		'server/<id,hostname,ip>/config/get':'get HAProxy config from the server by id or hostname or ip',
		'server/<id,hostname,ip>/config/send':'send HAProxy config to the server by id or hostname or ip. Has to have config header with config and action header for action after upload. Action header accepts next value: save, test, reload and restart. May be empty for just save',
		'server/<id,hostname,ip>/config/add':'add section to the HAProxy config by id or hostname or ip. Has to have config header with section and action header for action after upload. Action header accepts next value: save, test, reload and restart. May be empty for just save',
		'server/<id,hostname,ip>/log':'show HAProxy log by id or hostname or ip. May to have config next headers: rows(format INT) default: 10 grep, waf(if needs WAF log) deault: 0, start_hour(format: 24) default: 00, start_minut, end_hour(format: 24) default: 24, end_minut'
	}
	return dict(help=data)
	

@route('/servers', method=['GET', 'POST'])
def get_servers():
	if not check_login():
		return dict(error=_error_auth)
	try:
		login = request.headers.get('login')
		servers = sql.get_dick_permit(username=login)
		data = {}
		for s in servers:
			data[s[0]] = {  
				'id':s[0],
				'hostname':s[1],
				'ip':s[2],
				'group':s[3],
				'virt':s[4],
				'enable':s[5],
				'is_master':s[6],
				'creds':s[7],
				'alert':s[8],
				'metrics':s[9]
			}
	except:
		pass  
	return dict(servers=data)
	
	
@route('/servers/status', method=['GET', 'POST'])
def callback():
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.get_all_statuses()
	
@route('/server/<id>', method=['GET', 'POST'])
@route('/server/<id:int>', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.get_server(id)
	
	
@route('/server/<id>/status', method=['GET', 'POST'])
@route('/server/<id:int>/status', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.get_status(id)
	
	
@route('/server/<id>/action/<action:re:[a-z]+>', method=['GET', 'POST'])
@route('/server/<id:int>/action/<action:re:[a-z]+>', method=['GET', 'POST'])
def callback(id, action):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.actions(id, action)
	
	
@route('/server/<id>/runtime', method=['GET', 'POST'])
@route('/server/<id:int>/runtime', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.runtime(id)
	
	
@route('/server/<id>/backends', method=['GET', 'POST'])
@route('/server/<id:int>/backends', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.show_backends(id)
	
	
@route('/server/<id>/config/get', method=['GET', 'POST'])
@route('/server/<id:int>/config/get', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.get_config(id)
	
	
@route('/server/<id>/config/send', method=['GET', 'POST'])
@route('/server/<id:int>/config/send', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.upload_config(id)
	
	
@route('/server/<id>/config/add', method=['GET', 'POST'])
@route('/server/<id:int>/config/add', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.add_to_config(id)
	
	
@route('/server/<id>/log', method=['GET', 'POST'])
@route('/server/<id:int>/log', method=['GET', 'POST'])
def callback(id):
	if not check_login():
		return dict(error=_error_auth)
	return api_funct.show_log(id)
	