#!/bin/bash
cp app/haproxy-webintarface.config /tmp/

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

chmod +x app/*py
chown -R apache:apache *

cd app/
./update_db.py

echo ""
echo "#################"
echo "Change in config:"
diff --expand-tabs -W 100 -y /tmp/haproxy-webintarface.config haproxy-webintarface.config |grep "|"
echo ""
echo "Please set your config"
echo ""
echo "################"
echo "Your config saved in /tmp/haproxy-webintarface.config. Please comare with new and set your env back"
echo ""