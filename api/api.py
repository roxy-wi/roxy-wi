import os
import sys
os.chdir(os.path.dirname(__file__))
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app/'))
os.chdir(os.path.dirname(__file__))

from bottle import route, run, template, hook, response, request
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
	
	
@route('/', method=['GET', 'POST'])
@route('/help', method=['GET', 'POST'])
def index():
	if not check_login():
		return dict(error=_error_auth)
		
	data = {
		'servers':'show info about all servers',
		'server/<id,hostname,ip>':'show info about server by id or hostname or ip',
		'server/<id,hostname,ip>/status':'show HAProxy status by id or hostname or ip',
		'server/<id,hostname,ip>/runtime':'exec HAProxy runtime commands by id or hostname or ip',
		'server/<id,hostname,ip>/backends':'show backends by id or hostname or ip',
		'server/<id,hostname,ip>/action/start':'start HAProxy service by id or hostname or ip',
		'server/<id,hostname,ip>/action/stop':'stop HAProxy service by id or hostname or ip',
		'server/<id,hostname,ip>/action/restart':'restart HAProxy service by id or hostname or ip'
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
	