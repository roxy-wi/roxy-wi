# Haproxy web interface
Web interface(user-friendly web GUI, alerting, monitoring and secure) for managing HAProxy servers. Leave your [feedback](https://github.com/Aidaho12/haproxy-wi/issues)

# Youtube
[Demo video](https://www.youtube.com/channel/UCo0lCg24j-H4f0S9kMjp-_w)

# Twitter
[Twitter](https://twitter.com/haproxy_wi), subscribe! I will write there about all the changes and news

# Telegram
[Channel](https://t.me/haproxy_wi) about HAProxy-WI, talks and questions are welcome
# Demo site
[Demo site](https://demo.haproxy-wi.org) Login/password: admin/admin. Server resets every hour.

![alt text](image/haproxy-wi-config-show.png "Show config page")

# Features:
1.  Installation and updating HAProxy, Nginx and Keepalived with HAProxy-WI
2.	Configure HAProxy, Nginx and Keepalived In a jiffy with HAProxy-WI
3.	View and analyse Status of all Frontend/backend server via HAProxy-WI from a single control panel.
4.	Enable/disable servers through stats page without rebooting HAProxy
5.	View/Analyse HAproxy, Nginx logs straight from the HAProxy-WI web interface
6.	Create and visualise the HAProxy workflow from Web Ui.
7.	Push Your changes to your HAProxy, Nginx and Keepalived servers with a single click through web interface
8.	Get info on past changes, evaluate your config files and restore a previous stable config anytime with a single click straight from Web interface
9.	Add/Edit Frontend or backend servers via web interface with a click of a button.
10.	Edit config of HAProxy, Nginx, Keepalived and push changes to All Master/Slave server with a single click
11.	Add Multiple server to ensure Config Sync between servers.
12.	Auto management of ports assigned to Fronted. 
13.	Evaluate the changes of recent configs pushed to HAProxy, Nginx and Keepalived instances straight from web ui
14.	Multiple User Roles support for privileged based Viewing and editing of Config
15.	Create Groups and add /remove servers to ensure proper identification for your HAProxy Clusters
16.	Send notifications to telegram directly from HAProxy-WI
17.	HAProxy-WI supports high Availability to ensure uptime to all Master slave servers configured
18.	SSL certificate support.
19.	SSH Key support for managing multiple HAProxy Servers straight from HAProxy-WI
20. SYN flood protect
21. Alerting about changes backends state
22. Alerting about HAProxy service state
23. Metrics incoming connections
24. Web acceleration settings
25. Web application firewall
26. LDAP support
27. Keep active HAProxy service
28. Ability to hide parts of the config with tags for users with "guest" role:  "HideBlockStart" and "HideBlockEnd"
29. Mobile-ready desing
30. REST API
31. Backup HAProxy's and Keepalived's config files through HAProxy-WI

![alt text](image/haproxy-wi-metrics.png "Merics")

# Install

## RPM
Install repository:
```
yum install https://repo.haproxy-wi.org/haproxy-wi-release-7-1-0.noarch.rpm 
```
After install HAProxy-WI:
```
yum install haproxy-wi
```

Supports EL7 and EL8

#### Before uses RPM repository you should donate to support project on [Patreon](https://www.patreon.com/haproxy_wi/overview) or on [PayPal](https://www.paypal.me/loginovpavel) and I will send you credentials for access. Actual prices you can see on [Patreon](https://www.patreon.com/haproxy_wi/overview)

### More information on the official [site](https://haproxy-wi.org/installation.py#rpm)

## Manual install
For install just clone:
```
CentOS:
$ sudo 	yum -y install git nmap-ncat net-tools python35u dos2unix python35u-pip mod_ssl httpd python35u-devel gcc-c++ openldap-devel python-devel python-jinja2 python35u-mod_wsgi ansible
$ cd /var/www/
$ git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi
$ chown -R apache:apache haproxy-wi/

Or if use Debian/Ubuntu:

$ sudo 	apt-get install git  net-tools lshw dos2unix apache2 gcc netcat python3.5 python3.5-mod_wsgi mod_ssl python3-pip g++ freetype2-demos libatlas-base-dev openldap-dev libpq-dev python-dev libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libffi-dev python3-dev libssl-dev ansible -y
$ git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi
$ chown -R www-data:www-data haproxy-wi/
```

Both

```
$ pip3 install -r haproxy-wi/requirements.txt 
$ chmod +x haproxy-wi/app/*.py 
$ sudo ln -s /usr/bin/python3.5 /usr/bin/python3
$ sudo cp haproxy-wi/config_other/logrotate/* /etc/logrotate.d/
$ sudo cp haproxy-wi/config_other/syslog/* /etc/rsyslog.d/
$ sudo cp haproxy-wi/config_other/systemd/* /etc/systemd/system/
$ sudo systemctl daemon-reload      
$ sudo systemctl restart httpd
$ sudo systemctl restart rsyslog
$ sudo systemctl restart metrics_haproxy.service
$ sudo systemctl restart checker_haproxy.service
$ sudo systemctl restart keep_alive.service
$ sudo systemctl enable metrics_haproxy.service
$ sudo systemctl enable checker_haproxy.service
$ sudo systemctl enable keep_alive.service
$ sudo mkdir /var/www/haproxy-wi/app/certs
$ sudo mkdir /var/www/haproxy-wi/keys
$ sudo mkdir /var/www/haproxy-wi/configs/
$ sudo mkdir /var/www/haproxy-wi/configs/hap_config/
$ sudo mkdir /var/www/haproxy-wi/configs/kp_config/
$ sudo mkdir /var/www/haproxy-wi/log/


```

For Apache do virtualhost with cgi-bin. Like this:
```
# vi /etc/httpd/conf.d/haproxy-wi.conf 
<VirtualHost *:8080>
		WSGIDaemonProcess api display-name=%{GROUP} user=apache group=apache processes=1 threads=5
        WSGIScriptAlias /api /var/www/haproxy-wi/api/app.wsgi

        <Directory /var/www/haproxy-wi/api>
            WSGIProcessGroup api
            WSGIApplicationGroup %{GLOBAL}
            Order deny,allow
            Allow from all
        </Directory>

        SSLEngine on
        SSLCertificateFile /var/www/haproxy-wi/app/certs/haproxy-wi.crt
        SSLCertificateKeyFile /var/www/haproxy-wi/app/certs/haproxy-wi.key

        ServerName haproxy-wi
        ErrorLog /var/log/httpd/haproxy-wi.error.log
        CustomLog /var/log/httpd/haproxy-wi.access.log combined
        TimeOut 600
        LimitRequestLine 16380
		
        DocumentRoot /var/www/haproxy-wi
        ScriptAlias /cgi-bin/ "/var/www/haproxy-wi/app/"

        <Directory /var/www/haproxy-wi/app>
		    DirectoryIndex overview.py
            Options +ExecCGI
            AddHandler cgi-script .py
            Order deny,allow
            Allow from all
        </Directory>
		
        <Directory /var/www/haproxy-wi/app/certs>
            Options +ExecCGI -Indexes +MultiViews
			Order Deny,Allow
			Deny from all
        </Directory>
	
        <Directory /var/www/haproxy-wi/keys>
		    Options +ExecCGI -Indexes +MultiViews
		    Order Deny,Allow
		    Deny from all
        </Directory>

        <FilesMatch "\.cfg$">
			Order Deny,Allow
			Deny from all
        </FilesMatch>
		
        <FilesMatch "\.db$">
		    Order Deny,Allow
		    Deny from all
        </FilesMatch>
		
        <IfModule mod_headers.c>
		    Header set X-XSS-Protection: 1;
		    Header set X-Frame-Options: deny
		    Header set X-Content-Type-Options: nosniff
		    Header set Strict-Transport-Security: max-age=3600;
		    Header set Cache-Control no-cache
		    Header set Expires: 0

		    <filesMatch ".(ico|css|js|gif|jpeg|jpg|png|svg|woff|ttf|eot)$">
				Header set Cache-Control "max-age=86400, public"
		    </filesMatch>
		</IfModule>
</VirtualHost>
```

### More information on the official [site](https://haproxy-wi.org/installation.py#manual)

# OS support
HAProxy-WI was tested on EL7, EL8 and all scripts too. Debian/Ubuntu OS support at 'beta' stage, may work not correct

# Database support

Default HAProxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

### For MySQL support:
```
MariaDB [(none)]> create user 'haproxy-wi'@'%';
MariaDB [(none)]> create database haproxywi;
MariaDB [(none)]> grant all on haproxywi.* to 'haproxy-wi'@'%' IDENTIFIED BY 'haproxy-wi';
MariaDB [(none)]> grant all on haproxywi.* to 'haproxy-wi'@'localhost' IDENTIFIED BY 'haproxy-wi';
```

### More information on the official [site](https://haproxy-wi.org/settings.py#db_settings)

![alt text](image/haproxy-wi-overview.png "Overview page")

# Settings
```
Edit $HOME_HAPROXY-WI/app/haproxy-wi.cfg with your env
```

Login https://haproxy-wi-server/users.py, and add: users, groups and servers. Default: admin/admin

![alt text](image/haproxy-wi-admin-area.png "Admin area")

For Runtime API, Metrics and Alerting enable state file and stat socket on HAproxt servers and need install socat on all haproxy servers, and configre HAProxy:
```
    global
        stats socket *:1999 level admin 
        stats socket /var/run/haproxy.sock mode 600 level admin
        server-state-file /etc/haproxy/haproxy.state
		
    defaults
        load-server-state-from-file global
		
    listen stats 
        bind *:8085
        stats enable
        stats uri /stats
        stats realm HAProxy-04\ Statistics
        stats auth admin:password
        stats admin if TRUE 
   ```
![alt text](image/haproxy-wi-logs.png "View logs page")


# Create and update DB
```
$ cd /var/www/haproxy-wi/app
$ ./create_db.py
```
# Troubleshooting
If you have error:
```
Forbidden
You don't have permission to access /app/overview.py on this server. 
```

Check owner(must be apache, or another user for apache)

If at first login you have:
```
Internal Server Error
```

Do this:
```
$ cd /var/www/haproxy-wi/app
$ ./create_db.py
```
and check executeble py files

If you see plain text, check section "Directory" in httpd conf
