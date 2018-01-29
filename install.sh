#!/bin/bash

echo "Enter dir for HAproxy-WI. Default: [/opt/haproxy-wi]"
read DIR
echo "Enter user for HAproxy-WI. Defailt: [haproxy-wi]"
read USER

if [[ $DIR = "" ]]; then
        DIR="/opt/haproxy-wi"
else
        sed -i "s!/opt/haproxy-wi!$DIR!" haproxy-webintarface.config 
        sed -i "s!/opt/haproxy-wi!$DIR!" server.py
        sed -i "s!/opt/haproxy-wi!$DIR!" haproxy-wi.service
fi

if [[ $USER = "" ]]; then
        USER="haproxy-wi"
fi

echo "Install req"
pip3 install -r requirements.txt

echo "Add user $USER"
useradd $USER -d $DIR -s /sbin/nologin

chmod +x server.py
chmod +x cgi-bin/*.py
chown $USER:$USER -R *

echo "Creating service"
sed -i "s/haproxy-wi/$USER/" haproxy-wi.service
mv haproxy-wi.service /etc/systemd/system
systemctl daemon-reload