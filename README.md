# Haproxy web interface
A simple web interface(user-frendly web GUI) for managing Haproxy servers. Leave your [feedback](https://github.com/Aidaho12/haproxy-wi/issues)

![alt text](image/haproxy-wi-config-show.jpeg "Show config page")

# Capabilities:
1. View statistics of all servers in one place
2. Server and service statsus in one place
3. View logs of all servers in one place
4. Map frontend, backends and servers
5. Runtime API with the ability to save changes (need install socat on all haproxy servers)
6. Browsing Configs
7. Add sections: listen, frontend, backend from web interface
8. Editing configs
9. Rollback to previous versions of the config
10. Master/slave servers
11. Configure firewalld on HAProxy servers based on config ports
12. Comparing versions of configs
13. Users roles: admin, editor, viewer
14. Server groups
15. Telegram notification
16. Creating HA HAProxy cluster

# Install
The installer will ask you a few questions
```
$ git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi
$ chmod +x install
$ cd /var/www/haproxy-wi
$ ./install
```
## Manual install
For install just clone:
```
$ cd /var/www/
$ git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi
$ chown -R apache:apache haproxy-wi/
$ pip install -r haproxy-wi/requirements.txt 
$ chmod +x haproxy-wi/cgi-bin/*.py 
```

For Apache do virtualhost with cgi-bin. Like this:
```
# vi /etc/httpd/conf.d/haproxy-wi.conf 
<VirtualHost *:8080>
        ServerName haproxy-wi
        ErrorLog /var/log/httpd/haproxy-wi.error.log
        CustomLog /var/log/httpd/haproxy-wi.access.log combined

        DocumentRoot /var/www/haproxy-wi
        ScriptAlias /cgi-bin/ "/var/www/haproxy-wi/cgi-bin/"

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
Edit $HOME_HAPROXY-WI/cgi-bin/haproxy-webintarface.config with your env
```
Login http://haproxy-wi-server/users.py, and add: users, groups and servers. Default: admin/admin

![alt text](image/haproxy-wi-admin-area.jpeg "Admin area")

Copy ssh key on all HAproxy servers

For Runtime API enable state file on HAproxt servers and need install socat on all haproxy servers:
```
    global
		stats socket *:1999 level admin 
		server-state-file /etc/haproxy/haproxy/haproxy.state
    defaults
		load-server-state-from-file global
   ```
![alt text](image/haproxy-wi-logs.jpeg "View logs page")

# Update DB
```
$ cd /var/www/haproxy-wi/cgi-bin
$ ./update_db.py
```

# Further development and support

Offer your ideas and wishes, ask questions. All this is [welcomed](https://github.com/Aidaho12/haproxy-wi/issues)


