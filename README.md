# Haproxy web interface
A simple web interface(user-frendly web GUI) for managing Haproxy servers. Leave your [feedback](https://github.com/Aidaho12/haproxy-wi/issues)

![alt text](image/haproxy-wi-config-show.jpeg "Show config page")

# Features:
1.	Configure HAproxy In a jiffy with haproxy-wi
2.	View and analyse Status of all Frontend/backend server via haproxy-wi from a single control panel.
3.	View/Analyse HAproxy logs straight from the haproxy-wi web interface
4.	Create and visualise the HAproxy workflow from Web Ui.
5.	Push Your changes to your HAproxy servers with a single click through web interface.
6.	Get info on past changes, Evaluate your config files and restore a previous stable config anytime with a single click straight from Web interface.
7.	Add/Edit Frontend or backend servers via web interface with a click of a button.
8.	Edit config of HAproxy and push changes to All Master/Slave server with a single click.
9.	Add Multiple server to ensure Config Sync between servers.
10.	Auto management of ports assigned to Fronted. 
11.	Evaluate the changes of recent configs pushed to HAproxy instances straight from web ui
12.	Multiple User Roles support for privileged based Viewing and editing of Config.
13.	Create Groups and add /remove servers to ensure proper identification for your HAproxy Clusters
14.	Send notifications to telegram directly from haproxy-wi.
15.	haproxy-wi supports high Availability to ensure uptime to all Master slave servers configured.
16.	SSL certificate support.
17.	SSH Key support for managing multiple HAproxy Servers straight from haproxy-wi


# Install
The installer will ask you a few questions
```
$ git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi
$ cd /var/www/haproxy-wi
$ chmod +x install.sh
$ ./install
```
## Manual install
For install just clone:
```
$ cd /var/www/
$ git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi
$ chown -R apache:apache haproxy-wi/
$ pip install -r haproxy-wi/requirements.txt 
$ chmod +x haproxy-wi/app/*.py 
```

For Apache do virtualhost with cgi-bin. Like this:
```
# vi /etc/httpd/conf.d/haproxy-wi.conf 
<VirtualHost *:8080>
        ServerName haproxy-wi
        ErrorLog /var/log/httpd/haproxy-wi.error.log
        CustomLog /var/log/httpd/haproxy-wi.access.log combined

        DocumentRoot /var/www/haproxy-wi
        ScriptAlias /cgi-bin/ "/var/www/haproxy-wi/app/"

        <Directory /var/www/haproxy-wi>
                Options +ExecCGI
                AddHandler cgi-script .py
                Order deny,allow
                Allow from all
        </Directory>
</VirtualHost>
```
# Database support

Default Haproxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

## For MySQL support:
```
MariaDB [(none)]> create user 'haproxy-wi'@'%';
MariaDB [(none)]> create database haproxywi;
MariaDB [(none)]> grant all on haproxywi.* to 'haproxy-wi'@'%' IDENTIFIED BY 'haproxy-wi';
MariaDB [(none)]> grant all on haproxywi.* to 'haproxy-wi'@'localhost' IDENTIFIED BY 'haproxy-wi';
```
![alt text](image/haproxy-wi-overview.jpeg "Overview page")

# Settings
```
Edit $HOME_HAPROXY-WI/app/haproxy-webintarface.config with your env
```
Copy ssh key on all HAproxy servers

Login http://haproxy-wi-server/users.py, and add: users, groups and servers. Default: admin/admin

![alt text](image/haproxy-wi-admin-area.jpeg "Admin area")

For Runtime API enable state file on HAproxt servers and need install socat on all haproxy servers, and configre HAProxy:
```
    global
		stats socket *:1999 level admin 
		stats socket /var/run/haproxy.sock mode 600 level admin
		server-state-file /etc/haproxy/haproxy/haproxy.state
    defaults
		load-server-state-from-file global
   ```
![alt text](image/haproxy-wi-logs.jpeg "View logs page")

# Update DB
```
$ cd /var/www/haproxy-wi/app
$ ./update_db.py
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
$ ./update_db.py
```

# Further development and support

Offer your ideas and wishes, ask questions. All this is [welcomed](https://github.com/Aidaho12/haproxy-wi/issues)


