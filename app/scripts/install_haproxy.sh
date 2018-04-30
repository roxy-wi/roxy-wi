#!/bin/bash

if [[ $1 != "" ]]
then
	export http_proxy="$1"
	export https_proxy="$1"
	echo "Exporting proxy"
fi

if [ -f /etc/haproxy/haproxy.cfg ];then
	echo -e 'error: Haproxy alredy installed. You can edit config<a href="/app/config.py" title="Edit HAProxy config">here</a>'
	exit 1
fi
wget http://cbs.centos.org/kojifiles/packages/haproxy/1.8.1/5.el7/x86_64/haproxy18-1.8.1-5.el7.x86_64.rpm 
yum install haproxy18-1.8.1-5.el7.x86_64.rpm -y

if [ $? -eq 1 ]
then
	yum install wget socat -y > /dev/null
	wget http://cbs.centos.org/kojifiles/packages/haproxy/1.8.1/5.el7/x86_64/haproxy18-1.8.1-5.el7.x86_64.rpm 
	yum install haproxy18-1.8.1-5.el7.x86_64.rpm -y
fi
if [ $? -eq 1 ]
then
	yum install haproxy socat -y > /dev/null
fi
echo "" > /etc/haproxy/haproxy.cfg
cat << EOF > /etc/haproxy/haproxy.cfg
global
    log         127.0.0.1 local2
    chroot      /var/lib/haproxy
    pidfile     /var/run/haproxy.pid
    maxconn     4000
    user        haproxy
    group       haproxy
    daemon
    stats socket /var/lib/haproxy/stats
    stats socket *:1999 level admin
	stats socket /var/run/haproxy.sock mode 600 level admin

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
		bind *:8085 
        stats enable
        stats uri /stats
        stats realm HAProxy-04\ Statistics
        stats auth admin:password
EOF
cat << EOF > /etc/rsyslog.d/haproxy.conf
local2.*                       /var/log/haproxy.log
EOF

sed -i 's/#$UDPServerRun 514/$UDPServerRun 514/g' /etc/rsyslog.conf
sed -i 's/#$ModLoad imudp/$ModLoad imudp/g' /etc/rsyslog.conf 

firewall-cmd --zone=public --add-port=8085/tcp --permanent
firewall-cmd --reload
setenforce 0
sed -i 's/SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 
systemctl enable haproxy
systemctl restart haproxy

if [ $? -eq 1 ]
then
        echo "error: Can't start Haproxy service"
        exit 1
fi
echo "success"