# ![alt text](https://roxy-wi.org/static/images/logo_menu.png "Logo")
Web interface (user-friendly web GUI, alerting, monitoring, and secure) for managing HAProxy, Nginx, and Keepalived servers. Leave your [feedback](https://github.com/hap-wi/roxy-wi/issues)

# Get involved
* [Telegram Channel](https://t.me/roxy_wi_channel) about Roxy-WI, talks and questions are welcome

# Demo site
[Demo site](https://demo.roxy-wi.org) Login/password: admin/admin. Server resets every hour.

![alt text](https://roxy-wi.org/static/images/viewstat.png "HAProxy state page")

# Features:
1. Installing and updating HAProxy, Nginx, Apache and Keepalived with Roxy-WI as a system service
2. Installing and updating HAProxy and Nginx with Roxy-WI as a Docker service
3. Installing and updating HAProxy, Nginx, Apache, Keepalived, and Node exporters with Roxy-WI
4. Downloading, updating, and formatting GeoIP to the acceptable format for HAProxy, and NGINX with Roxy-WI
5. Dynamic change of Maxconn, Black/white lists, add, edit, or delete backend's IP address and port with saving changes to the config file
6. Configuring HAProxy, Nginx, Apache and Keepalived in a jiffy with Roxy-WI
7. Viewing and analyzing the status of all Frontend/backend servers via Roxy-WI from a single control panel
8. Enabling/disabling servers through stats page without rebooting HAProxy
9. Viewing/Analyzing HAProxy, Nginx, Apache and Keepalived logs right from the Roxy-WI web interface
10. Creating and visualizing the HAProxy workflow from Web Ui
11. Pushing Your changes to your HAProxy, Nginx, Apache, and Keepalived servers with a single click via the web interface
12. Getting info on past changes, evaluating your config files, and restoring the previous stable config at any time with a single click right from the Web interface
13. Adding/Editing Frontend or backend servers via the web interface with a click
14. Editing the config of HAProxy, Nginx, Apache, and Keepalived and push interchanges to All Master/Slave servers by a single click
15. Adding Multiple servers to ensure the Config Sync between servers
16. Managing the ports assigned to Frontend automatically
17. Evaluating the changes of recent configs pushed to HAProxy, Nginx, Apache, and Keepalived instances right from the Web UI
18. Multiple User Roles support for privileged-based Viewing and editing of Config
19. Creating Groups and adding/removing servers to ensure the proper identification for your HAProxy, Nginx, and Apache Clusters
20. Sending notifications from Roxy-WI via Telegram, Slack, Email, PageDuty, Mattermost, and via the web interface
21. Supporting high Availability to ensure uptime to all Master slave servers configured
22. Support of SSL (including Let's Encrypt)
23. Support of SSH Key for managing multiple HAProxy, Nginx, Apache, and Keepalived Servers straight from Roxy-WI
24. SYN flood protect
25. Alerting about changes of the state of HAProxy backends, about approaching the limit of Maxconn
26. Alerting about the state of HAProxy, Nginx, Apache, and Keepalived service
27. Gathering metrics for incoming connections
28. Web acceleration settings
29. Firewall for web application (WAF)
30. LDAP support
31. Keep active HAProxy, Nginx, Apache, and Keepalived services
32. Possibility to hide parts of the config with tags for users with the "guest" role: "HideBlockStart" and "HideBlockEnd"
33. Mobile-ready design
34. [SMON](https://roxy-wi.org/services/smon) (Check: Ping, TCP/UDP, HTTP(s), SSL expiry, HTTP body answer, DNS records, Status pages)
35. Backup HAProxy, Nginx, Apache, and Keepalived config files through Roxy-WI



![alt text](https://roxy-wi.org/static/images/roxy-wi-metrics.png "Merics")

# Install

## RPM

### Read instruction on the official [site](https://roxy-wi.org/installation#rpm)

## DEB

### Read instruction on the official [site](https://roxy-wi.org/installation#deb)

# OS support
Roxy-WI supports the following OSes:
1. EL7(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
2. EL8(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
3. EL9(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
4. Amazon Linux 2(RPM installation and manual installation). x86_64 only
5. Ubuntu (DEB installation and manual installation). x86_64 only
6. Other Linux distributions (manual installation only). x86_64 only

![alt text](https://roxy-wi.org/static/images/smon_dashboard.png "SMON area")

# Database support

Default Roxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

### For MySQL support:

### Read instruction on the official [site](https://roxy-wi.org/installation#database)

![alt text](https://roxy-wi.org/static/images/roxy-wi-overview.webp "Overview page")

# Settings


Login https://roxy-wi-server/admin, and add: users, groups, and servers. Default: admin/admin

### Read instruction on the official [site](https://roxy-wi.org/settings)

![alt text](https://roxy-wi.org/static/images/hapwi_overview.webp "HAProxy server overview page")


![alt text](https://roxy-wi.org/static/images/add.webp "Add proxy page")



# Troubleshooting
If you have error:
```
Internal Server Error
```

Do this:
```
$ cd /var/www/haproxy-wi/app
$ ./create_db.py
```

[Read more](https://roxy-wi.org/troubleshooting)
