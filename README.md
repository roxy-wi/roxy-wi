# ![alt text](inc/images/logo_menu.png "Logo")
Web interface(user-friendly web GUI, alerting, monitoring and secure) for managing HAProxy, Nginx and Keepalived servers. Leave your [feedback](https://github.com/Aidaho12/haproxy-wi/issues)

# Get involved
* [Youtube Demo video](https://www.youtube.com/channel/UCo0lCg24j-H4f0S9kMjp-_w)
* [Twitter](https://twitter.com/haproxy_wi), subscribe!
* [Telegram Channel](https://t.me/haproxy_wi) about HAProxy-WI, talks and questions are welcome

# Demo site
[Demo site](https://demo.haproxy-wi.org) Login/password: admin/admin. Server resets every hour.

![alt text](image/haproxy-wi-config-show.png "Show config page")

# Features:
1.  Installation and updating HAProxy, Nginx and Keepalived with HAProxy-WI
1.  Installation and updating Grafana, Prometheus servers with HAProxy-WI
1.  Installation and updating HAProxy and Nginx exporters with HAProxy-WI
2.	Configure HAProxy, Nginx and Keepalived In a jiffy with HAProxy-WI
3.	Dynamic change of Maxconn, backend's IP address and port with saving changes to the config file
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
15.	Create Groups and add/remove servers to ensure proper identification for your HAProxy, Nginx Clusters
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
30. Simple port monitoring
31. Backup HAProxy's, Nginx's and Keepalived's config files through HAProxy-WI

![alt text](image/haproxy-wi-metrics.png "Merics")

# Install

## RPM

### Read instruction on the official [site](https://haproxy-wi.org/installation.py#rpm)

## Manual install

### Read instruction on the official [site](https://haproxy-wi.org/installation.py#manual)

# OS support
HAProxy-WI was tested on EL7, EL8 and all scripts too. Debian/Ubuntu OS support at 'beta' stage, may work not correct

![alt text](image/haproxy-wi-admin-area.png "Admin area")

# Database support

Default HAProxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

### For MySQL support:

### Read instruction on the official [site](https://haproxy-wi.org/settings.py#db_settings)

![alt text](image/haproxy-wi-overview.png "Overview page")

# Settings


Login https://haproxy-wi-server/users.py, and add: users, groups and servers. Default: admin/admin

### Read instruction on the official [site](https://haproxy-wi.org/settings.py)

![alt text](image/haproxy-wi-admin-area.png "Admin area")


![alt text](image/haproxy-wi-logs.png "View logs page")



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
