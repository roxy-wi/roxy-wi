#!/bin/bash

# set -x 

cp app/haproxy-wi.cfg  /tmp/

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

mv -f /tmp/haproxy-wi.cfg app/haproxy-wi.cfg 

mkdir keys
mkdir app/certs
chmod +x app/*py
chmod +x app/tools/*py

if hash apt-get 2>/dev/null; then
	apt-get install git  net-tools lshw dos2unix apache2 gcc netcat mod_ssl python3-pip gcc-c++ openldap-devel libpq-dev python-dev libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libffi-dev python3-dev -y
else
	yum -y install https://centos7.iuscommunity.org/ius-release.rpm
	yum -y install git nmap-ncat net-tools python35u dos2unix python35u-pip mod_ssl httpd python35u-devel gcc-c++ openldap-devel 
fi

cat << EOF > /etc/systemd/system/keep_alive.service
[Unit]
Description=Keep Alive Haproxy 
After=syslog.target network.target

[Service]
Type=simple
WorkingDirectory=/var/www/$HOME_HAPROXY_WI/app/
ExecStart=/var/www/$HOME_HAPROXY_WI/app/tools/keep_alive.py

StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=keep_alive

RestartSec=2s
Restart=on-failure
TimeoutStopSec=1s

[Install]
WantedBy=multi-user.target
EOF

cat << 'EOF' > /etc/rsyslog.d/keep_alive.conf 
if $programname startswith 'keep_alive' then /var/www/__HOME_HAPROXY_WI__/log/keep_alive.log
& stop
EOF
sed -i -e "s/__HOME_HAPROXY_WI__/$HOME_HAPROXY_WI/g" /etc/rsyslog.d/keep_alive.conf

cat << EOF > /etc/logrotate.d/metrics
/var/www/$HOME_HAPROXY_WI/log/keep_alive.log {
    daily
    rotate 10
    missingok
    notifempty
	create 0644 apache apache
	dateext
    sharedscripts
}
EOF

systemctl daemon-reload
systemctl restart keep_alive.service
systemctl enable keep_alive.service

cd app/
./create_db.py

pip3 install -r ../requirements.txt
pip3.5 install -r ../requirements.txt
chmod +x ../update.sh

echo "################"
echo ""
echo ""
echo ""
echo "ATTENTION!!! New config file name is: haproxy-wi.cfg"
echo ""
echo ""
echo ""
echo "################"
