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
echo "Your config saved in /tmp/haproxy-webintarface.config. Please compare with new and set your env back"
echo ""