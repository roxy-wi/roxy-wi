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
10. Comparing versions of configs
11. Users roles: admin, editor, viewer
12. Server groups
13. Telegram notification

# Install

For install just [dowload](https://github.com/Aidaho12/haproxy-wi/archive/master.zip) archive and untar somewhere:
```
$ cd /var/www/
$ unzip master.zip
$ mv haproxy-wi-master/ haproxy-wi
$ pip install -r haproxy-wi/requirements.txt 
$ cd haproxy-wi/cgi-bin
$ chmod +x *.py
```

For Apache do virtualhost with cgi-bin.

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
       server-state-file /etc/haproxy/haproxy/haproxy.state
    defaults
       load-server-state-from-file global
   ```
![alt text](image/haproxy-wi-logs.jpeg "View logs page")

# Further development and support

Offer your ideas and wishes, ask questions. All this is [welcomed](https://github.com/Aidaho12/haproxy-wi/issues)


