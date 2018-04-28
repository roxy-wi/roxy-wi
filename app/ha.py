#!/usr/bin/env python3
import html
import cgi
import funct
import sql
from configparser import ConfigParser, ExtendedInterpolation

funct.head("HA")
funct.check_login()
funct.page_for_admin()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)	
serv = ""

print('<script src="/inc/users.js"></script>'
		'<h2>Configure HA</h2>'
		'<table class="overview">'
		'<caption class="overviewHead"><h3 style="margin-left: 20px; margin-bottom: 10px;">Create new HA cluster</h3></caption>'
		'<tr class="overviewHead">'
			'<td class="padding10 first-collumn">Master</td>'
			'<td>Slave</td>'
			'<td>VRRP interface</td>'
			'<td>VRRP IP</td>'
			'<td><span title="Will be installed the latest version that you have in the repository">Install HAProxy(?)</span></td>'
			'<td></td>'
		'</tr>'
		'<tr>'
		'<td class="padding10 first-collumn">'
			'<select id="master">'
				'<option disable selected>Choose master</option>')
funct.choose_only_select(serv)
print('</select>'
		'</td>'
		'<td>'
		'<select id="slave">'
				'<option disable selected>Choose master</option>')
funct.choose_only_select(serv)
print('</select>'
		'</td>'
		'<td>'
			'<input type="text" id="interface" class="form-control">'
		'</td>'
		'<td>'
			'<input type="text" id="vrrp-ip" class="form-control">'
		'</td>'
		'<td>'
			'<label for="hap"></label><input type="checkbox" id="hap">'
		'</td>'
		'<td>'
			'<a class="ui-button ui-widget ui-corner-all" id="create" title="Create HA configuration">Create</a>'
		'</td>'
		'</table>'
		
		'<table>'
		'<caption class="overviewHead"><h3 style="margin-left: 20px; margin-bottom: 10px;">Or add VRRP to exist</h3></caption>'
		'<tr class="overviewHead">'
			'<td class="padding10 first-collumn">Master</td>'
			'<td>Slave</td>'
			'<td>VRRP interface</td>'
			'<td>VRRP IP</td>'
			'<td><span title="If checked Haproxy-WI will restart Keepalived">Restart Keepalived(?)</span></td>'
			'<td></td>'
		'</tr>'
		'<tr>'
		'<td class="padding10 first-collumn">'
			'<select id="master-add">'
				'<option disable selected>Choose master</option>')
funct.choose_only_select(serv)
print('</select>'
		'</td>'
		'<td>'
		'<select id="slave-add">'
				'<option disable selected>Choose master</option>')
funct.choose_only_select(serv)
print('</select>'
		'</td>'
		'<td>'
			'<input type="text" id="interface-add" class="form-control">'
		'</td>'
		'<td>'
			'<input type="text" id="vrrp-ip-add" class="form-control">'
		'</td>'
		'<td>'
			'<label for="kp"></label><input type="checkbox" id="kp">'
		'</td>'
		'<td>'
			'<a class="ui-button ui-widget ui-corner-all" id="add-vrrp" title="Add HA configuration">Add</a>'
		'</td>'
	'</table>'
	'<div id="ajax"></div>')

