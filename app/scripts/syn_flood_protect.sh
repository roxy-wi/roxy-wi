#!/bin/bash

if [[ $1 == "enable" ]]; then
	if grep -q "net.ipv4.tcp_syncookie = 1" /etc/sysctl.conf; then
		echo "SYN flood protectd allready enabled"
    else
		sudo bash -c cat <<EOF >> /etc/sysctl.conf
# Protection SYN flood
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.tcp_max_syn_backlog = 1024 
EOF
	
	sudo sysctl -w net.ipv4.tcp_syncookies=1
	sudo sysctl -w net.ipv4.conf.all.rp_filter=1
	sudo sysctl -w net.ipv4.tcp_max_syn_backlog=1024 
	sudo sysctl -w net.ipv4.tcp_synack_retries=3
	fi
fi

if [[ $1 == "disable" ]]; then
	sed -i 's/net.ipv4.tcp_max_syn_backlog = 1024/net.ipv4.tcp_max_syn_backlog = 256/' /etc/sysctl.conf
	sed -i 's/net.ipv4.tcp_synack_retries = 3/net.ipv4.tcp_synack_retries = 5/' /etc/sysctl.conf
	sudo sysctl -w net.ipv4.tcp_max_syn_backlog=256 
	sudo sysctl -w net.ipv4.tcp_synack_retries=5
fi