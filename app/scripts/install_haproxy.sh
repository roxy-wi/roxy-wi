#!/bin/bash

for ARGUMENT in "$@"
do

    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            SOCK_PORT)    SOCK_PORT=${VALUE} ;;
            STAT_PORT)    STAT_PORT=${VALUE} ;;
            STAT_FILE)    STAT_FILE=${VALUE} ;;
            STATS_USER)    STATS_USER=${VALUE} ;;
            STATS_PASS)    STATS_PASS=${VALUE} ;;
            STAT_FILE)    STAT_FILE=${VALUE} ;;
            *)
    esac


done

if [[ $PROXY != "" ]]
then
	export http_proxy="$PROXY"
	export https_proxy="$PROXY"
fi

if [ -f /etc/haproxy/haproxy.cfg ];then
	echo -e 'error: Haproxy already installed. You can edit config<a href="/app/config.py" title="Edit HAProxy config">here</a> <br /><br />'
	exit 1
fi
set +x
if hash apt-get 2>/dev/null; then
	sudo apt-get install haproxy socat -y
else
	wget http://cbs.centos.org/kojifiles/packages/haproxy/1.8.1/5.el7/x86_64/haproxy18-1.8.1-5.el7.x86_64.rpm 
	sudo yum install haproxy18-1.8.1-5.el7.x86_64.rpm -y
fi

if [ $? -eq 1 ]
then
	sudo yum install wget socat -y > /dev/null
	wget http://cbs.centos.org/kojifiles/packages/haproxy/1.8.1/5.el7/x86_64/haproxy18-1.8.1-5.el7.x86_64.rpm 
	sudo yum install haproxy18-1.8.1-5.el7.x86_64.rpm -y
fi
if [ $? -eq 1 ]
then
	if hash apt-get 2>/dev/null; then
		sudo apt-get install socat  -y
	else
		sudo yum install haproxy socat -y > /dev/null
	fi
fi

bash -c 'echo "" > /tmp/haproxy.cfg'
bash -c cat << EOF > /tmp/haproxy.cfg
global
    log         127.0.0.1 local2
    chroot      /var/lib/haproxy
    pidfile     /var/run/haproxy.pid
    maxconn     4000
    user        haproxy
    group       haproxy
    daemon
    stats socket /var/lib/haproxy/stats
    stats socket *:$SOCK_PORT level admin
    stats socket /var/run/haproxy.sock mode 600 level admin
    server-state-file $STAT_FILE 

defaults
    mode                    http
    log                     global
    option                  httplog
    option                  dontlognull
    option http-server-close
    option forwardfor       except 127.0.0.0/8
    option                  redispatch
    retries                 3
    timeout http-request    10s
    timeout queue           1m
    timeout connect         10s
    timeout client          1m
    timeout server          1m
    timeout http-keep-alive 10s
    timeout check           10s
    maxconn                 3000

listen stats 
    bind *:$STAT_PORT 
    stats enable
    stats uri /stats
    stats realm HAProxy-04\ Statistics
    stats auth $STATS_USER:$STATS_PASS
    stats admin if TRUE 
EOF
sudo cp /tmp/haproxy.cfg /etc/haproxy/haproxy.cfg
sudo bash -c 'cat << EOF > /etc/rsyslog.d/haproxy.conf
local2.*                       /var/log/haproxy.log
EOF'

sudo sed -i 's/#$UDPServerRun 514/$UDPServerRun 514/g' /etc/rsyslog.conf
sudo sed -i 's/#$ModLoad imudp/$ModLoad imudp/g' /etc/rsyslog.conf 

sudo firewall-cmd --zone=public --add-port=8085/tcp --permanent
sudo firewall-cmd --reload
sudo setenforce 0
sudo sed -i 's/SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 
sudo systemctl enable haproxy
sudo systemctl restart haproxy

if [ $? -eq 1 ]
then
        echo "error: Can't start Haproxy service <br /><br />"
        exit 1
fi
echo "success"