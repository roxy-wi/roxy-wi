#!/usr/bin/env python3
import subprocess
from subprocess import check_output, CalledProcessError
import time
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
	servers = sql.select_keep_alive()
	port = sql.get_setting('haproxy_sock_port')
	firstrun = True
	currentstat = []
	oldstat = []
	readstats = ""
	killer = GracefulKiller()
	old_stat_service = ""
	cur_stat_service = ""
	
	while True:
		for serv in servers:
			try:			
				readstats = subprocess.check_output(["echo show stat | nc "+serv[0]+" "+port], shell=True)
			except CalledProcessError as e:
				if firstrun == False:	
					cur_stat_service = "error"
					if old_stat_service != cur_stat_service:
						alert = "Try start HAProxy serivce at " + serv[0]
						#funct.telegram_send_mess(str(alert), ip=serv[2])
						funct.logging("localhost", " "+alert, keep_alive=1)
						start_command = []
						start_command.append(sql.get_setting('restart_command'))
						funct.ssh_command(serv[0], start_command)

				firstrun = False				
				old_stat_service = cur_stat_service
				continue
			except OSError as e:
				print(e)
				sys.exit()
			else:
				cur_stat_service = "Ok"
				"""
						
					if old_stat_service != cur_stat_service:
						alert = "Now UP HAProxy service at " + serv
						funct.telegram_send_mess(str(alert), ip=serv[2])
						funct.logging("localhost", " "+alert, alerting=1)
							
						time.sleep(5)	
				"""
				if firstrun == False:
					firstrun = True
				old_stat_service = cur_stat_service	
		
		
if __name__ == "__main__":
	funct.logging("localhost", " Keep alive service started", keep_alive=1)
	killer = GracefulKiller()
	
	while True:
		main()
		time.sleep(60)
		
		if killer.kill_now:
			break
			
	funct.logging("localhost", " Keep alive service shutdown", keep_alive=1)