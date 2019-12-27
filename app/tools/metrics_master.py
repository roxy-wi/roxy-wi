#!/usr/bin/env python3
import subprocess
import time
import argparse
import os, sys
sys.path.append(os.path.join(sys.path[0], os.path.dirname(os.getcwd())))
sys.path.append(os.path.join(sys.path[0], os.getcwd()))
import funct
import sql
import signal

class GracefulKiller:
	kill_now = False
	def __init__(self):
		signal.signal(signal.SIGINT, self.exit_gracefully)
		signal.signal(signal.SIGTERM, self.exit_gracefully)
	
	def exit_gracefully(self,signum, frame):
		self.kill_now = True

def main():
	sql.delete_mentrics()
	sql.delete_waf_mentrics()
	servers = sql.select_servers_metrics_for_master()
	started_workers = get_worker()
	servers_list = []
	
	for serv in servers:
		servers_list.append(serv[0])
			
	need_kill=list(set(started_workers) - set(servers_list))
	need_start=list(set(servers_list) - set(started_workers))
	
	if need_kill:
		for serv in need_kill:
			kill_worker(serv)
			
	if need_start:
		for serv in need_start:
			start_worker(serv)
	
	try:
		waf_servers = sql.select_all_waf_servers()
		waf_started_workers = get_waf_worker()
		waf_servers_list = []
				
		for serv in waf_servers:
			waf_servers_list.append(serv[0])
				
		waf_need_kill=list(set(waf_started_workers) - set(waf_servers_list))
		waf_need_start=list(set(waf_servers_list) - set(waf_started_workers))
		
		if waf_need_kill:
			for serv in waf_need_kill:
				kill_waf_worker(serv)
				
		if waf_need_start:
			for serv in waf_need_start:
				start_waf_worker(serv)
	except Exception as e:
		funct.logging("localhost", 'Problems with WAF worker metrics '+e, metrics=1)
		pass
	
def start_worker(serv):
	port = sql.get_setting('haproxy_sock_port')
	cmd = "tools/metrics_worker.py %s --port %s &" % (serv, port)
	os.system(cmd)
	funct.logging("localhost", " Master started new metrics worker for: "+serv, metrics=1)
	
def kill_worker(serv):
	cmd = "ps ax |grep 'tools/metrics_worker.py %s'|grep -v grep |awk '{print $1}' |xargs kill" % serv
	output, stderr = funct.subprocess_execute(cmd)
	funct.logging("localhost", " Master killed metrics worker for: "+serv, metrics=1)
	if stderr:
		funct.logging("localhost", stderr, metrics=1)
		
def start_waf_worker(serv):
	port = sql.get_setting('haproxy_sock_port')
	cmd = "tools/metrics_waf_worker.py %s --port %s &" % (serv, port)
	os.system(cmd)
	funct.logging("localhost", " Master started new WAF metrics worker for: "+serv, metrics=1)
	
def kill_waf_worker(serv):
	cmd = "ps ax |grep 'tools/metrics_waf_worker.py %s'|grep -v grep |awk '{print $1}' |xargs kill" % serv
	output, stderr = funct.subprocess_execute(cmd)
	funct.logging("localhost", " Master killed WAF metrics worker for: "+serv, metrics=1)
	if stderr:
		funct.logging("localhost", stderr, metrics=1)

def kill_all_workers():
	cmd = "ps ax |grep -e 'tools/metrics_worker.py\|tools/metrics_waf_worker.py' |grep -v grep |awk '{print $1}' |xargs kill"
	output, stderr = funct.subprocess_execute(cmd)
	funct.logging("localhost", " Master killing all metrics workers", metrics=1)
	if stderr:
		funct.logging("localhost", stderr, metrics=1)
		
def get_worker():
	cmd = "ps ax |grep 'tools/metrics_worker.py' |grep -v grep |awk '{print $7}'"
	output, stderr = funct.subprocess_execute(cmd)
	if stderr:
		funct.logging("localhost", stderr, metrics=1)
	return output
	
def get_waf_worker():
	cmd = "ps ax |grep 'tools/metrics_waf_worker.py' |grep -v grep |awk '{print $7}'"
	output, stderr = funct.subprocess_execute(cmd)
	if stderr:
		funct.logging("localhost", stderr, metrics=1)
	return output
	
if __name__ == "__main__":
	funct.logging("localhost", " Metrics master started", metrics=1)
	killer = GracefulKiller()
	
	while True:
		main()
		time.sleep(20)
		
		if killer.kill_now:
			break
			
	kill_all_workers()
	funct.logging("localhost", " Master shutdown", metrics=1)