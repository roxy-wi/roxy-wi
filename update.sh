#!/bin/bash

cp app/haproxy-wi.cfg  /tmp/

mv -f /tmp/haproxy-wi.cfg app/haproxy-wi.cfg 

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

chmod +x app/*py
chmod +x app/tools/*py

if hash apt-get 2>/dev/null; then
	sudo chown -R www-data:www-data app/
else
	sudo chown -R apache:apache app/
fi

cd app/
./create_db.py

LOG='/tmp/haproxy-wi_install.log'
pip3.5 install -r /var/www/haproxy-wi/requirements.txt &> $LOG

chmod +x ../update.sh

echo "################"
echo ""
echo "ATTENTION!!! New config file name is: haproxy-wi.cfg"
echo ""
echo ""
echo "Install log in $LOG"
echo ""
echo "################"