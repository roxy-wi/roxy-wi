#!/bin/bash

# set -x 

cp app/haproxy-wi.cfg  /tmp/

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

git reset --hard
git pull  https://github.com/Aidaho12/haproxy-wi.git

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
