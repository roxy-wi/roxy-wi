# ![alt text](https://roxy-wi.org/inc/images/logo_menu.png "Logo")
Web interface(user-friendly web GUI, alerting, monitoring and secure) for managing HAProxy, Nginx and Keepalived servers. Leave your [feedback](https://github.com/hap-wi/roxy-wi/issues)

# Get involved
* [Youtube Demo video](https://www.youtube.com/channel/UCo0lCg24j-H4f0S9kMjp-_w)
* [Twitter](https://twitter.com/roxy_wi), subscribe!
* [Telegram Channel](https://t.me/roxy_wi_channel) about Roxy-WI, talks and questions are welcome

# Demo site
[Demo site](https://demo.roxy-wi.org) Login/password: admin/admin. Server resets every hour.

![alt text](https://roxy-wi.org/inc/images/viewstat.png "HAProxy state page")

# Features:
1. Installing and updating HAProxy, Nginx and Keepalived with Roxy-WI as a system service
1. Installing and updating HAProxy and Nginx with Roxy-WI as a Docker service
2. Installing and updating Grafana, Prometheus servers with Roxy-WI
3. Installing and updating HAProxy and Nginx exporters with Roxy-WI
4. Server provisioning on AWS, DigitalOcean and G-Core Labs
5. Downloading, updating and formatting GeoIP to the acceptable format for HAProxy with Roxy-WI
6. Dynamic change of Maxconn, Black/white lists and backend's IP address and port with saving changes to the config file
7. Configuring HAProxy, Nginx, Apache and Keepalived in a jiffy with Roxy-WI
8. Viewing and analysing the status of all Frontend/backend servers via Roxy-WI from a single control panel
9. Enabling/disabling servers through stats page without rebooting HAProxy
1. Viewing/Analysing HAProxy, Nginx and Apache logs right from the Roxy-WI web interface
1. Creating and visualizing the HAProxy workflow from Web Ui
1. Pushing Your changes to your HAProxy, Nginx, Apache and Keepalived servers with a single click via the web interface
1. Getting info on past changes, evaluating your config files and restoring the previous stable config at any time with a single click right from Web interface
1. Adding/Editing Frontend or backend servers via the web interface with a click
1. Editing the config of HAProxy, Nginx, Apache and Keepalived and push ingchanges to All Master/Slave servers by a single click
1. Adding Multiple server to ensure the Config Sync between servers
1. Managing the ports assigned to Frontend automatically
1. Evaluating the changes of recent configs pushed to HAProxy, Nginx and Keepalived instances right from the Web UI
1. Multiple User Roles support for privileged based Viewing and editing of Config
1. Creating Groups and adding/removing servers to ensure the proper identification for your HAProxy and Nginx Clusters
1. Sending notifications from Roxy-WI via Telegram, Slack and via the web interface
1. Supporting high Availability to ensure uptime to all Master slave servers configured
1. Support of SSL (including Let's Encrypt)
1. Support of SSH Key for managing multiple HAProxy, Nginx, Apache and Keepalived Servers straight from Roxy-WI
1. SYN flood protect
1. Alerting about changes of the state of HAProxy backends
1. Alerting about the state of HAProxy, Nginx, Apache and Keepalived service
1. Gathering metrics for incoming connections
1. Web acceleration settings
1. Firewall for web application
1. LDAP support
1. Keep active HAProxy, Nginx and Keepalived services
1. Possibility to hide parts of the config with tags for users with "guest" role: "HideBlockStart" and "HideBlockEnd"
1. Mobile-ready design
1. Simple port monitoring (SMON)
1. Backup HAProxy, Nginx and Keepalived config files through Roxy-WI
1. Managing OpenVPN3 as a client via Roxy-WI



![alt text](https://Roxy-WI.org/inc/images/roxy-wi-metrics.png "Merics")

# Install

## RPM

### Read instruction on the official [site](https://roxy-wi.org/installation.py#rpm)

## DEB

### Read instruction on the official [site](https://roxy-wi.org/installation.py#deb)

## Manual install

### Read instruction on the official [site](https://roxy-wi.org/installation.py#manual)

# OS support
Roxy-WI supports the following OSes:
1. EL7(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
2. EL8(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
3. Amazon Linux 2(RPM installation and manual installation). x86_64 only
4. Ubuntu(DEB installation and manual installation). x86_64 only
5. Other Linux distributions (manual installation only). x86_64 only

![alt text](https://roxy-wi.org/inc/images/smon_dashboard.png "SMON area")

# Database support

Default Roxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

### For MySQL support:

### Read instruction on the official [site](https://roxy-wi.org/installation.py#database)

![alt text](https://roxy-wi.org/inc/images/roxy-wi-overview.webp "Overview page")

# Settings


Login https://roxy-wi-server/users.py, and add: users, groups and servers. Default: admin/admin

### Read instruction on the official [site](https://roxy-wi.org/settings.py)

![alt text](https://roxy-wi.org/inc/images/hapwi_overview.webp "HAProxy server overview page")


![alt text](https://roxy-wi.org/inc/images/add.png "Add proxy page")



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

[Read more](https://roxy-wi.org/troubleshooting.py)
