#!/bin/bash
yum install haproxy -y > /dev/null

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

listen stats *:8085 
        stats enable
        stats uri /stats
        stats realm HAProxy-04\ Statistics
        stats auth admin:password
EOF
cat << EOF > /etc/rsyslog.d/haproxy.conf
local2.*                       /var/log/haproxy.log
EOF

sed -i "s/#$ModLoad imudp/$ModLoad imudp/g" /etc/rsyslog.conf 
sed -i "s/#$UDPServerRun/$UDPServerRun /g" /etc/rsyslog.conf 

firewall-cmd --zone=public --add-port=8085/tcp --permanent
firewall-cmd --reload
setenforce 0
sed -i 's/SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 
systemctl enable haproxy
systemctl restart haproxy

if [ $? -eq 1 ]
then
        echo "Can't start Haproxy service"
        exit 1
fi