#!/usr/bin/env python3
import html
import cgi
import listserv as listhap
import subprocess
import os
import funct
import glob
import paramiko
import configparser
from paramiko import SSHClient
	
form = cgi.FieldStorage()
serv = form.getvalue('serv')
left = form.getvalue('left')
right = form.getvalue('right')

funct.head("Compare HAproxy configs")
funct.check_config()
funct.check_login()	

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

haproxy_configs_server = config.get('configs', 'haproxy_configs_server')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')

funct.chooseServer("diff.py#diff", "Compare HAproxy configs", "n")

if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	
	print('<form action="diff.py#diff" method="get">')
	print('<center><h3><span style="padding: 20px;">Choose left</span><span style="padding: 110px;">Choose right</span></h3>')
	
	print('<p><select autofocus required name="left" id="left">')
	print('<option disabled selected>Choose version</option>')
	
	os.chdir(hap_configs_dir)
	
	for files in sorted(glob.glob('*.cfg')):
		ip = files.split("-")
		if serv == ip[0]:
			if left == files:
				selected = 'selected'
			else:
				selected = ''
			print('<option value="%s" %s>%s</option>' % (files, selected, files))

	print('</select>')

	print('<select autofocus required name="right" id="right">')
	print('<option disabled selected>Choose version</option>')
	
	for files in sorted(glob.glob('*.cfg')):
		ip = files.split("-")
		if serv == ip[0]:
			if right == files:
				selected = 'selected'
			else:
				selected = ''
			print('<option value="%s" %s>%s</option>' % (files, selected, files))

	print('</select>')
	print('<input type="hidden" value="%s" name="serv">' % serv)
	print('<input type="hidden" value="open" name="open">')
	print('<button type="submit" value="Compare" name="Compare">Compare</button></p></form></center>')
	
if form.getvalue('serv') is not None and form.getvalue('right') is not None:
	commands = [ 'diff -ub %s%s %s%s' % (hap_configs_dir, left, hap_configs_dir, right) ]

	funct.ssh_command(haproxy_configs_server, commands, compare="1")
	
funct.footer()