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
	servers = sql.select_alert()
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
	
def start_worker(serv):
	port = sql.get_setting('haproxy_sock_port')
	cmd = "tools/checker_worker.py %s --port %s &" % (serv, port)
	os.system(cmd)
	funct.logging("localhost", " Masrer started new worker for: "+serv, alerting=1)
	
def kill_worker(serv):
	cmd = "ps ax |grep 'tools/checker_worker.py %s'|grep -v grep |awk '{print $1}' |xargs kill" % serv
	output, stderr = funct.subprocess_execute(cmd)
	funct.logging("localhost", " Masrer killed worker for: "+serv, alerting=1)
	if stderr:
		funct.logging("localhost", stderr, alerting=1)

def kill_all_workers():
	cmd = "ps ax |grep 'tools/checker_worker.py' |grep -v grep |awk '{print $1}' |xargs kill"
	output, stderr = funct.subprocess_execute(cmd)
	funct.logging("localhost", " Masrer killing all workers", alerting=1)
	if stderr:
		funct.logging("localhost", stderr, alerting=1)
		
def get_worker():
	cmd = "ps ax |grep 'tools/checker_worker.py' |grep -v grep |awk '{print $7}'"
	output, stderr = funct.subprocess_execute(cmd)
	if stderr:
		funct.logging("localhost", stderr, alerting=1)
	return output
	
if __name__ == "__main__":
	funct.logging("localhost", " Checker master started", alerting=1)
	killer = GracefulKiller()
	
	while True:
		main()
		time.sleep(20)
		
		if killer.kill_now:
			break
			
	kill_all_workers()
	funct.logging("localhost", " Checker master shutdown", alerting=1)