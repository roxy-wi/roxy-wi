#!/usr/bin/env python3
import html
import cgi
import json
import subprocess 
import funct
options = [ "acl", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "tcpka", "tcplog", "forwardfor", "option" ]

form = cgi.FieldStorage()
req = form.getvalue('req')
serv = form.getvalue('serv')
print('Content-type: text/html\n')
#print('Content-type: application/json\n')

if req is not None:
	if req is 1:
		for i in options:
			if req in i:
				print(i)
	else:
		for i in options:
				print(i)

backend = form.getvalue('backend')			
if backend is not None:
	
	cmd='echo "show backend" |nc %s 1999' % serv 
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	
	for line in output:
		if "#" in  line or "stats" in line:
			continue
		if backend != "1":
			if backend in line:
				print(json.dumps(line))
				continue
		if backend == "1":
			print(json.dumps(line))
			continue


if form.getvalue('ip') is not None and serv is not None:
	commands = [ "ip a |grep inet |egrep -v  '::1' |awk '{ print $2  }' |awk -F'/' '{ print $1  }'" ]
	funct.ssh_command(serv, commands, ip="ip")
	
if form.getvalue('name') is not None:
	name = form.getvalue('name')
	conf = open("/home/ploginov/haproxy/cgi-bin/hap_config/test.cfg", "r")
	s = form.getvalue('s')
	for line in conf:
		#print(line)
		if s in line and name in line:
#			print(line)
			print("yes")
			break
