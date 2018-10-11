#!/bin/bash

cp app/haproxy-wi.cfg  /tmp/

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

mkdir keys
mkdir app/certs
chmod +x app/*py
chmod +x app/tools/*py

if hash apt-get 2>/dev/null; then
	apt-get install git  net-tools lshw dos2unix apache2 gcc netcat python3-pip gcc-c++ -y
else
	yum -y install https://centos7.iuscommunity.org/ius-release.rpm
	yum -y install git nmap-ncat net-tools python35u dos2unix python35u-pip httpd python35u-devel gcc-c++
fi

cd app/
./create_db.py

pip3 install -r ../requirements.txt
pip3.5 install -r ../requirements.txt
chmod +x ../update.sh

mv /tmp/haproxy-wi.cfg app/haproxy-wi.cfg 
echo "################"
echo ""
echo ""
echo ""
echo "ATTENTION!!! New config file name is: haproxy-wi.cfg"
echo ""
echo ""
echo ""
echo "################"