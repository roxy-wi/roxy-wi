# Haproxy web interface
A simple web interface(user-frendly web GUI) for managing Haproxy servers

![alt text](image/5.jpeg "Edit config page")

# Capabilities:
1. View statistics of all servers in one place
2. View logs of all servers in one place
3. Disabling / enabling the backend servers without reboot (after reboot, will work as specified in the config), viewing server state data
4. Browsing Configs
5. Add sections: listen, frontend, backend from web interface
6. Editing configs
7. Rollback to previous versions of the config
8. Comparing versions of configs
9. Users roles: admin, viewer

# Install
For install just dowload archive and untar somewhere:
```
$ cd /opt
$ unzip master.zip
$ mv haproxy-web-interface-master/ haproxy
$ cd /opt/haproxy
$ pip3 install -r requirements.txt
$ chmod +x server.py
$ chmod +x -R cgi-bin/
$ chown user:user -R haproxy
```
Edit listserv.py, add your HAproxy servers. 

If foler not /opt/haproxy/, edit server.py:
```
path_config = "/opt/haproxy/haproxy-webintarface.config"
```

# Settings
edit haproxy-webintarface.config with your env

copy ssh key on all HAproxy servers

For online edit HAproxy settings enable socket on HAproxt servers:
```
global
    log         172.28.0.5 local2 debug err
    stats socket *:1999 level admin
   ```
![alt text](image/4.jpeg "View logs page")

# Start
Create systemd service to auto start:
```
[Unit]
Description=Haproxy web interface
After=syslog.target network.target 

[Service]
Type=simple
User=user_name

ExecStart=/opt/haproxy/server.py >> /opt/haproxy/log/haproxy-webface.log 

RestartSec=2s
Restart=on-failure
TimeoutStopSec=1s

[Install]
WantedBy=multi-user.target
```
![alt text](image/1.jpeg "Start page")
