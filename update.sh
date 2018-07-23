#!/bin/bash

cp app/haproxy-webintarface.config /tmp/

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

mkdir keys
mkdir app/certs
chmod +x app/*py
chmod +x app/tools/*py
chown -R apache:apache *


cat << EOF > /etc/systemd/system/multi-user.target.wants/checker_haproxy.service
[Unit]
Description=Haproxy backends state checker
After=syslog.target network.target

[Service]
Type=simple
WorkingDirectory=/var/www/haproxy-wi/app/
ExecStart=/var/www/haproxy-wi/app/tools/checker_master.py

RestartSec=2s
Restart=on-failure
TimeoutStopSec=1s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload      
systemctl start checker_haproxy.service
systemctl enable checker_haproxy.service

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