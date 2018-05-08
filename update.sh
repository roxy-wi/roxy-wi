#!/bin/bash

cp app/haproxy-webintarface.config /tmp/

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

mkdir app/certs
chmod +x app/*py
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