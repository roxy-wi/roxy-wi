#!/bin/bash

cp app/haproxy-webintarface.config /tmp/

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

mkdir keys
mkdir app/certs
chmod +x app/*py
chmod +x app/tools/*py

if hash apt-get 2>/dev/null; then
	apt-get install git  net-tools lshw dos2unix apache2 gcc netcat python3-pip gcc-c++ -y
else
	yum -y install git nmap-ncat net-tools python34 dos2unix python34-pip httpd python34-devel gcc-c++
fi

at << EOF > /etc/systemd/system/multi-user.target.wants/checker_haproxy.service
[Unit]
Description=Haproxy backends state checker
After=syslog.target network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)/app
ExecStart=$(pwd)/app/tools/checker_master.py

StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=checker

RestartSec=2s
Restart=on-failure
TimeoutStopSec=1s

[Install]
WantedBy=multi-user.target
EOF

cat << EOF > /etc/rsyslog.d/checker.conf 
if $programname startswith 'checker' then $(pwd)/log/checker-error.log
& stop
EOF

cat << EOF > /etc/logrotate.d/checker
$(pwd)/log/checker-error.log {
    daily
    rotate 10
    missingok
    notifempty
	create 0644 apache apache
	dateext
    sharedscripts
}
EOF

cat << EOF > /etc/systemd/system/multi-user.target.wants/metrics_haproxy.service
[Unit]
Description=Haproxy metrics
After=syslog.target network.target

[Service]
Type=simple
WorkingDirectory=/var/www/haproxy-wi/app/
ExecStart=/var/www/haproxy-wi/app/tools/metrics_master.py

StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=metrics

RestartSec=2s
Restart=on-failure
TimeoutStopSec=1s

[Install]
WantedBy=multi-user.target
EOF

cat << EOF > /etc/rsyslog.d/metrics.conf 
if $programname startswith 'metrics' then /var/www/$HOME_HAPROXY_WI/log/metrics-error.log
& stop
EOF

cat << EOF > /etc/logrotate.d/metrics
/var/www/$HOME_HAPROXY_WI/log/metrics-error.log {
    daily
    rotate 10
    missingok
    notifempty
	create 0644 apache apache
	dateext
    sharedscripts
}
EOF

sed -i 's/#$UDPServerRun 514/$UDPServerRun 514/g' /etc/rsyslog.conf
sed -i 's/#$ModLoad imudp/$ModLoad imudp/g' /etc/rsyslog.conf

systemctl daemon-reload      
systemctl restart logrotate
systemctl restart rsyslog
systemctl restart cmetrics_haproxy.service
systemctl restart checker_haproxy.service
systemctl enable metrics_haproxy.service
systemctl enable checker_haproxy.service

chown -R apache:apache *

cd app/
./update_db.py

pip3 install -r ../requirements.txt

echo ""
echo "#################"
echo "Change in config:"
diff --expand-tabs -W 100 -y /tmp/haproxy-webintarface.config haproxy-webintarface.config 
echo ""
echo "Please set your config"
echo ""
echo "################"
echo "Your config saved in /tmp/haproxy-webintarface.config. Please comare with new and set your env back"
echo ""