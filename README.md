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
10. Telegram notification

# Install
Can be used as a service, or via fastaci apache + fastCGI(recommend, because it works faster), how to use the service:

For install just dowload archive and untar somewhere:
```
$ cd /opt
$ unzip master.zip
$ mv haproxy-wi-master/ haproxy-wi
$ cd /opt/haproxy-wi
$ chmod +x install.sh
$ sudo ./install.sh
```
Edit listserv.py, add your HAproxy servers. 

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

# Start and auto start
```
systemctl enable haproxy-wi.service
systemctl start haproxy-wi.service
```

# Deb support

Sorry, but not use, because  adapt yourself
