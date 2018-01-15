# haproxy-webintarface
A simple web interface for managing Haproxy servers

![alt text](image/5.jpeg "Edit config page")

# Install
For install just dowload archive and untar somewhere:

$ cd /opt/haproxy-webintarface

$ tar xf haproxy-webintarface-master.zip

# Settings
edit haproxy-webintarface.config with your env

copy ssh key on all HAproxy servers

For online edit HAproxy settings enable socket on HAproxt servers:

global
    log         172.28.0.5 local2 debug err
    stats socket *:1999 level admin
    
![alt text](image/4.jpeg "View logs page")

# Start
Create systemd service to auto start:

[Unit]

Description=Haproxy web interface
After=syslog.target network.target 

[Service]

Type=simple
User=user

ExecStart=/opt/haproxy/server.py >> /opt/haproxy/log/haproxy-webface.log 

RestartSec=2s
Restart=on-failure
TimeoutStopSec=1s
#StandardOutput=null

[Install]

WantedBy=multi-user.target

![alt text](image/1.jpeg "Start page")
