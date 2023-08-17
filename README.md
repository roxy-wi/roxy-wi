# ![alt text](https://roxy-wi.org/static/images/logo_menu.png "Logo")
Web interface(user-friendly web GUI, alerting, monitoring and secure) for managing HAProxy, Nginx and Keepalived servers. Leave your [feedback](https://github.com/hap-wi/roxy-wi/issues)

# Get involved
* [Telegram Channel](https://t.me/roxy_wi_channel) about Roxy-WI, talks and questions are welcome

# Demo site
[Demo site](https://demo.roxy-wi.org) Login/password: admin/admin. Server resets every hour.

![alt text](https://roxy-wi.org/static/images/viewstat.png "HAProxy state page")

# Features:
1. Installing and updating HAProxy, Nginx, Apache and Keepalived with Roxy-WI as a system service
2. Installing and updating HAProxy and Nginx with Roxy-WI as a Docker service
3. Installing and updating Grafana, Prometheus servers with Roxy-WI
4. Installing and updating HAProxy, Nginx, Apache, Keepalived and Node exporters with Roxy-WI
5. Server provisioning on AWS, DigitalOcean and G-Core Labs
6. Downloading, updating and formatting GeoIP to the acceptable format for HAProxy with Roxy-WI
7. Dynamic change of Maxconn, Black/white lists and backend's IP address and port with saving changes to the config file
8. Configuring HAProxy, Nginx, Apache and Keepalived in a jiffy with Roxy-WI
9. Viewing and analysing the status of all Frontend/backend servers via Roxy-WI from a single control panel
10. Enabling/disabling servers through stats page without rebooting HAProxy
11. Viewing/Analysing HAProxy, Nginx, Apache and Keepalived logs right from the Roxy-WI web interface
12. Creating and visualizing the HAProxy workflow from Web Ui
13. Pushing Your changes to your HAProxy, Nginx, Apache and Keepalived servers with a single click via the web interface
14. Getting info on past changes, evaluating your config files and restoring the previous stable config at any time with a single click right from Web interface
15. Adding/Editing Frontend or backend servers via the web interface with a click
16. Editing the config of HAProxy, Nginx, Apache and Keepalived and push ingchanges to All Master/Slave servers by a single click
17. Adding Multiple server to ensure the Config Sync between servers
18. Managing the ports assigned to Frontend automatically
19. Evaluating the changes of recent configs pushed to HAProxy, Nginx, Apache and Keepalived instances right from the Web UI
20. Multiple User Roles support for privileged based Viewing and editing of Config
21. Creating Groups and adding/removing servers to ensure the proper identification for your HAProxy, Nginx and Apache Clusters
22. Sending notifications from Roxy-WI via Telegram, Slack, Email, PageDuty and via the web interface
23. Supporting high Availability to ensure uptime to all Master slave servers configured
24. Support of SSL (including Let's Encrypt)
25. Support of SSH Key for managing multiple HAProxy, Nginx, Apache and Keepalived Servers straight from Roxy-WI
26. SYN flood protect
27. Alerting about changes of the state of HAProxy backends
28. Alerting about the state of HAProxy, Nginx, Apache and Keepalived service
29. Gathering metrics for incoming connections
30. Web acceleration settings
31. Firewall for web application (WAF)
32. LDAP support
33. Keep active HAProxy, Nginx, Apache and Keepalived services
34. Possibility to hide parts of the config with tags for users with "guest" role: "HideBlockStart" and "HideBlockEnd"
35. Mobile-ready design
36. [SMON](https://roxy-wi.org/services/smon) (Check: Ping, TCP/UDP, HTTP(s), SSL expiry, HTTP body answer, DNS records)
37. Backup HAProxy, Nginx, Apache and Keepalived config files through Roxy-WI
38. Managing OpenVPN3 as a client via Roxy-WI



![alt text](https://Roxy-WI.org/static/images/roxy-wi-metrics.png "Merics")

# Install

## RPM

### Read instruction on the official [site](https://roxy-wi.org/installation#rpm)

## DEB

### Read instruction on the official [site](https://roxy-wi.org/installation#deb)

## Manual install

### Read instruction on the official [site](https://roxy-wi.org/installation#manual)

# OS support
Roxy-WI supports the following OSes:
1. EL7(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
2. EL8(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
3. EL9(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
4. Amazon Linux 2(RPM installation and manual installation). x86_64 only
5. Ubuntu(DEB installation and manual installation). x86_64 only
6. Other Linux distributions (manual installation only). x86_64 only

![alt text](https://roxy-wi.org/static/images/smon_dashboard.png "SMON area")

# Database support

Default Roxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

### For MySQL support:

### Read instruction on the official [site](https://roxy-wi.org/installation#database)

![alt text](https://roxy-wi.org/static/images/roxy-wi-overview.webp "Overview page")

# Settings


Login https://roxy-wi-server/users.py, and add: users, groups and servers. Default: admin/admin

### Read instruction on the official [site](https://roxy-wi.org/settings)

![alt text](https://roxy-wi.org/static/images/hapwi_overview.webp "HAProxy server overview page")


![alt text](https://roxy-wi.org/static/images/add.png "Add proxy page")



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
and check executable .py files

If you see plain text, check section "Directory" in httpd conf

[Read more](https://roxy-wi.org/troubleshooting)
