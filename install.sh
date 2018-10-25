#!/bin/bash

PORT=8080
HOME_HAPROXY_WI=haproxy-wi

echo "Choose DB: (1)Sqlite or (2)Mysql? Default: Sqlite"
read DB

if [[ $DB == 2 ]];then
   echo "Mysql server is (1)remote  or (2)local?"
   read REMOTE
   if [[ $REMOTE == 1 ]];then
        echo "Enter IP remote Mysql server"
        read IP
   else
        MINSTALL=1
   fi
fi
echo "Choose Haproxy-WI port. Default: [$PORT]"
read CHPORT
echo "Enter Haproxy-wi home dir. Default: /var/www/[$HOME_HAPROXY_WI]"
read CHHOME_HAPROXY

if [[ -z $HAPROXY ]];then	
	HAPROXY="no"
fi

if [[ -n $CHPORT ]];then
        PORT=$CHPORT
fi
if [[ -n "$CHHOME_HAPROXY" ]];then
        HOME_HAPROXY_WI=$CHHOME_HAPROXY
fi
echo "################################"
echo ""
echo ""
echo -e "Installing Required Software"
echo ""
echo ""
echo "################################"

if hash apt-get 2>/dev/null; then
	apt-get install git  net-tools lshw dos2unix apache2 gcc netcat python3.5  python3-pip g++ freetype2-demos libatlas-base-dev -y
	HTTPD_CONFIG="/etc/apache2/apache2.conf"
	HAPROXY_WI_VHOST_CONF="/etc/apache2/sites-enabled/haproxy-wi.conf"
	HTTPD_NAME="apache2"
	HTTPD_PORTS="/etc/apache2/ports.conf"
	
	if [[ $MINSTALL == 1 ]];then
		apt-get install software-properties-common -y
		apt-key adv --recv-keys --keyserver hkp://keyserver.ubuntu.com:80 0xF1656F24C74CD1D8
		add-apt-repository 'deb [arch=amd64,i386,ppc64el] https://mirrors.evowise.com/mariadb/repo/10.1/ubuntu xenial main' -y
		apt-get install mariadb-server -y
	fi
else
	if [[ $(cat /etc/*-rele* |grep NAME |head -1) == 'NAME="CentOS Linux"' ]];then
        yum -y install epel-release
	fi
	yum -y install https://centos7.iuscommunity.org/ius-release.rpm 
	yum -y install git nmap-ncat net-tools python35u dos2unix python35u-pip httpd python35u-devel gcc-c++
	HTTPD_CONFIG="/etc/httpd/conf/httpd.conf"
	HAPROXY_WI_VHOST_CONF="/etc/httpd/conf.d/haproxy-wi.conf"
	HTTPD_NAME="httpd"
	HTTPD_PORTS=$HTTPD_CONFIG
		
	echo "Edit firewalld"
	firewall-cmd --zone=public --add-port=$PORT/tcp --permanent
	firewall-cmd --reload
	setenforce 0
	sed -i 's/SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 
	if [[ $MINSTALL == 1 ]];then
	   yum -y install mariadb mariadb-server mysql-devel
	fi
	
fi
 

if [ $? -eq 1 ]
then
	echo "################################"
	echo ""
	echo ""
	echo "Unable to install Required Packages Please check Yum config"
	echo ""
	echo ""
	echo "################################"
	exit 1
fi
echo "################################"
echo ""
echo ""
echo -e "Updating Apache config and Configuring Virtual Host"
echo ""
echo ""
echo "################################"

sudo sed -i "0,/^Listen .*/s//Listen $PORT/" $HTTPD_PORTS

echo "################################"
echo ""
echo ""
echo -e "Checking for Apache Vhost config"
echo ""
echo ""
echo "################################"

sudo touch $HAPROXY_WI_VHOST_CONF
/bin/cat $HAPROXY_WI_VHOST_CONF

if [ $? -eq 1 ]
then
	echo "################################"
	echo ""
	echo ""
	echo "Didnt Sense exisitng installation Proceeding ...."
	echo ""
	echo ""
	echo "################################"
	exit 1

else
	echo "################################"
	echo ""
	echo ""
	echo -e "Creating VirtualHost for Apache"
	echo ""
	echo ""
	echo "################################"
cat << EOF > $HAPROXY_WI_VHOST_CONF
<VirtualHost *:$PORT>
        ServerName haprox-wi.example.com
        ErrorLog /var/log/httpd/haproxy-wi.error.log
        CustomLog /var/log/httpd/haproxy-wi.access.log combined
		TimeOut 600

        DocumentRoot /var/www/$HOME_HAPROXY_WI
        ScriptAlias /cgi-bin/ "/var/www/$HOME_HAPROXY_WI/app/"


        <Directory /var/www/$HOME_HAPROXY_WI/app>
                Options +ExecCGI
                AddHandler cgi-script .py
                Order deny,allow
                Allow from all
        </Directory>
		
		<FilesMatch "\.config$">
                Order Deny,Allow
                Deny from all
        </FilesMatch>
</VirtualHost>
EOF
fi 

cat << EOF > /etc/systemd/system/multi-user.target.wants/checker_haproxy.service
[Unit]
Description=Haproxy backends state checker
After=syslog.target network.target

[Service]
Type=simple
WorkingDirectory=/var/www/$HOME_HAPROXY_WI/app/
ExecStart=/var/www/$HOME_HAPROXY_WI/app/tools/checker_master.py

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
if $programname startswith 'checker' then /var/www/$HOME_HAPROXY_WI/log/checker-error.log
& stop
EOF

cat << EOF > /etc/logrotate.d/checker
/var/www/$HOME_HAPROXY_WI/log/checker-error.log {
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
WorkingDirectory=/var/www/$HOME_HAPROXY_WI/app/
ExecStart=/var/www/$HOME_HAPROXY_WI/app/tools/metrics_master.py

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
systemctl restart metrics_haproxy.service
systemctl restart checker_haproxy.service
systemctl enable metrics_haproxy.service
systemctl enable checker_haproxy.service

if hash apt-get 2>/dev/null; then
	sed -i 's|/var/log/httpd/|/var/log/apache2/|g' $HAPROXY_WI_VHOST_CONF
	cd /etc/apache2/mods-enabled
	sudo ln -s ../mods-available/cgi.load
fi

echo "################################"
echo ""
echo ""
echo -e " Testing config"
echo ""
echo ""
echo "################################"
/usr/sbin/apachectl configtest 

if [ $? -eq 1 ]
then
	echo "apache Configuration Has failed, Please verify Apache Config"
   	echo ""
	echo ""
	echo "################################"
	exit 1
fi
echo "################################"
echo ""
echo ""
echo -e "Getting Latest software from The repository"
echo ""
echo ""
echo "################################"

/usr/bin/git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/$HOME_HAPROXY_WI

if [ $? -eq 1 ]
then
   echo "Unable to clone The repository Please check connetivity to Github"
   exit 1
fi
echo "################################"
echo ""
echo ""
echo -e "Installing required Python Packages"
echo ""
echo ""
echo "################################"
sudo -H pip3 install --upgrade pip
sudo pip3 install -r /var/www/$HOME_HAPROXY_WI/requirements.txt
sudo pip3.5 install -r /var/www/$HOME_HAPROXY_WI/requirements.txt

if [ $? -eq 1 ]
then
   echo "Unable to install Required Packages, Please check Pip error log and Fix the errors and Rerun the script"
   exit 1
else 
	echo "################################"
	echo ""
	echo ""
	echo -e "Installation Succesful"
	echo ""
	echo ""
	echo "################################"
fi

if [[ $MINSTALL = 1 ]];then
	echo "################################"
	echo ""
	echo ""
	echo -e "starting databse and applying config"
	echo ""
	echo ""
	echo "################################"
	systemctl enable mariadb
	systemctl start mariadb

	if [ $? -eq 1 ]
	then
		echo "################################"
		echo ""
		echo ""
		echo "Can't start Mariadb"
		echo ""
		echo ""
		echo "################################"
		exit 1
	fi

	if [ $? -eq 1 ]
	then
		echo "################################"
		echo ""
		echo ""
		echo "Unable to start Mariadb Service Please check logs"
		echo ""
		echo ""
		echo "################################"
		exit 1
	else 

		mysql -u root -e "create database haproxywi";
		mysql -u root -e "grant all on haproxywi.* to 'haproxy-wi'@'%' IDENTIFIED BY 'haproxy-wi';"
		mysql -u root -e "grant all on haproxywi.* to 'haproxy-wi'@'localhost' IDENTIFIED BY 'haproxy-wi';"
		mysql -u root -e "flush privileges;"
 
		echo "################################"
		echo ""
		echo ""
		echo -e "Databse has been created Succesfully and User permissions added"
		echo ""
		echo ""
		echo "################################"

  fi
fi


if [[ $DB == 2 ]];then
	echo "################################"
	echo ""
	echo ""
	echo -e "Setting Application to use Mysql As a backend"
	echo ""
	echo ""
	echo "################################"
	sed -i '0,/enable = 0/s//enable = 1/' /var/www/$HOME_HAPROXY_WI/app/haproxy-webintarface.config
fi

if [[ -n $IP ]];then
	sed -i "0,/mysql_host = 127.0.0.1/s//mysql_host = $IP/" /var/www/$HOME_HAPROXY_WI/app/haproxy-webintarface.config
fi
echo "################################"
echo ""
echo ""
echo -e " Starting Services"
echo ""
echo ""
echo "################################"

systemctl enable $HTTPD_NAME; systemctl restart $HTTPD_NAME

if [ $? -eq 1 ]
then
	echo "################################"
	echo ""
	echo ""
	echo "Services Has Not  been started, Please check error logs"
	echo ""
	echo ""
	echo "################################"

else 
	echo "################################"
	echo ""
	echo ""
    echo -e "Services have been started, Please Evaluate the tool by adding a host / DNS ectry for  /etc/hosts file. \n This can be done by adding an entry like this \n 192.168.1.100 haprox-wi.example.com"
	echo ""
	echo ""
	echo "################################"

fi 

sed -i "s|^fullpath = .*|fullpath = /var/www/$HOME_HAPROXY_WI|g" /var/www/$HOME_HAPROXY_WI/app/haproxy-wi.cfg
echo "################################"
echo ""
echo ""
echo -e " Thank You for Evaluating Haproxy-wi"
echo ""
echo ""
echo "################################"

sudo mkdir /var/www/$HOME_HAPROXY_WI/app/certs
sudo mkdir /var/www/$HOME_HAPROXY_WI/keys
sudo mkdir /var/www/$HOME_HAPROXY_WI/configs/
sudo mkdir /var/www/$HOME_HAPROXY_WI/configs/hap_config/
sudo mkdir /var/www/$HOME_HAPROXY_WI/configs/kp_config/
sudo mkdir /var/www/$HOME_HAPROXY_WI/log/
sudo sudo chmod +x /var/www/$HOME_HAPROXY_WI/app/*.py
sudo chmod +x /var/www/$HOME_HAPROXY_WI/app/tools/*.py
chmod +x /var/www/$HOME_HAPROXY_WI/update.sh
sudo ln -s /usr/bin/python3.5 /usr/bin/python3

cd /var/www/$HOME_HAPROXY_WI/app
./create_db.py
if hash apt-get 2>/dev/null; then
	sudo chown -R www-data:www-data /var/www/$HOME_HAPROXY_WI/
	sudo chown -R www-data:www-data /var/log/apache2/
else
	sudo chown -R apache:apache /var/www/$HOME_HAPROXY_WI/
	sudo chown -R apache:apache /var/log/httpd/
fi

exit 0
